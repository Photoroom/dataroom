"""Helpers to keep OSImage.group_ids / memberships in sync with Postgres Memberships.

Each helper is a single update_by_query against the images index, scoped to the
affected image (or all images for the group-scrub case).

Encoding (see Group model docstring):
- ``group_ids`` entries: ``"<type>::<uuid>"``
- ``memberships`` entries: ``"<role>::<type>::<uuid>"``

The ``gid`` parameter passed in below is always the OS-encoded ``<type>::<uuid>``
form (use ``Group.os_encoded_id``); the painless scripts only see opaque strings.

Invariants maintained:
- group_ids contains a gid exactly once iff any membership in that group exists.
- memberships entries — at most one per (image, group, role). An image may hold
  several roles in the same group, so each (role, group) pair is its own entry.
"""

from backend.dataroom.datasets.os_sync import bulk_update_by_id
from backend.dataroom.groups.os_fields import text_to_keyword_field
from backend.dataroom.models.os_image import OSImage
from backend.dataroom.opensearch import OS

# We use update_by_query (rather than per-doc update) so the same helper handles
# bulk operations cleanly. ``conflicts: proceed`` lets concurrent writes race
# without aborting the whole batch.

# Purely additive + idempotent: an image can hold several roles in the same
# group, so adding one role must not disturb the others. Re-adding the same
# (role, group) is a no-op.
_ADD_SCRIPT = {
    "lang": "painless",
    "source": (
        # ensure group_ids array exists and contains the gid
        "if (ctx._source.group_ids == null) { ctx._source.group_ids = new ArrayList(); }"
        "if (!ctx._source.group_ids.contains(params.gid)) { ctx._source.group_ids.add(params.gid); }"
        # ensure memberships array exists; add the (role, gid) entry if absent.
        "if (ctx._source.memberships == null) { ctx._source.memberships = new ArrayList(); }"
        "String entry = params.role + '::' + params.gid;"
        "if (!ctx._source.memberships.contains(entry)) { ctx._source.memberships.add(entry); }"
    ),
}

# Apply an image's entire (role) delta for ONE group in a single pass: add the
# roles in params.add, drop the roles in params.remove, then recompute the
# group_ids entry from what's left. One update_by_query per image means two
# roles on the same image never race two sequential queries against each other
# (which `conflicts: proceed` would silently drop).
_APPLY_IMAGE_SCRIPT = {
    "lang": "painless",
    "source": (
        "if (ctx._source.group_ids == null) { ctx._source.group_ids = new ArrayList(); }"
        "if (ctx._source.memberships == null) { ctx._source.memberships = new ArrayList(); }"
        "for (r in params.add) {"
        "  String entry = r + '::' + params.gid;"
        "  if (!ctx._source.memberships.contains(entry)) { ctx._source.memberships.add(entry); }"
        "}"
        "for (r in params.remove) {"
        "  String entry = r + '::' + params.gid;"
        "  ctx._source.memberships.removeIf(e -> e == entry);"
        "}"
        "boolean stillMember = ctx._source.memberships.stream()"
        "  .anyMatch(e -> e.endsWith('::' + params.gid));"
        "if (stillMember) {"
        "  if (!ctx._source.group_ids.contains(params.gid)) { ctx._source.group_ids.add(params.gid); }"
        "} else {"
        "  ctx._source.group_ids.removeIf(g -> g == params.gid);"
        "}"
    ),
}

# Remove every role for a group from an image (group-scrub on full deletion).
_REMOVE_SCRIPT = {
    "lang": "painless",
    "source": (
        "if (ctx._source.group_ids != null) { ctx._source.group_ids.removeIf(g -> g == params.gid); }"
        "if (ctx._source.memberships != null) { ctx._source.memberships.removeIf(e -> e.endsWith('::' + params.gid)); }"
    ),
}


def refresh_images():
    """Make pending denorm writes visible to search. Called once per group by
    the sync task — never per membership. OpenSearch also auto-refreshes on its
    own interval, so this only tightens the visibility window."""
    OS.client.indices.refresh(index=OSImage.INDEX)


def add_membership_to_image(image_id: str, group_id: str, role: str) -> int:
    """Add (or replace) a membership entry on the image. Returns rows updated.

    Does not refresh — the caller (sync task) refreshes once after the batch.
    """
    body = {
        "query": {"term": {"id": image_id}},
        "script": {**_ADD_SCRIPT, "params": {"gid": group_id, "role": role}},
    }
    response = OS.client.update_by_query(
        index=OSImage.INDEX,
        body=body,
        params={"conflicts": "proceed"},
    )
    return response.get("updated", 0)


_ADD_ENTRIES_SCRIPT = {
    "lang": "painless",
    "source": (
        "boolean changed = false;"
        "if (ctx._source.group_ids == null) { ctx._source.group_ids = new ArrayList(); }"
        "if (ctx._source.memberships == null) { ctx._source.memberships = new ArrayList(); }"
        "for (g in params.groupIds) {"
        "  if (!ctx._source.group_ids.contains(g)) { ctx._source.group_ids.add(g); changed = true; }"
        "}"
        "for (m in params.memberships) {"
        "  if (!ctx._source.memberships.contains(m)) { ctx._source.memberships.add(m); changed = true; }"
        "}"
        "if (!changed) { ctx.op = 'noop'; }"
    ),
}


def add_group_entries_to_images(entries_by_image: dict[str, dict]) -> int:
    """Append group/membership denorm entries to many images in one bulk request.

    ``entries_by_image``: ``{image_id: {"group_ids": [gid, ...], "memberships": [entry, ...]}}``
    where ``gid`` is ``"<type>::<uuid>"`` and ``entry`` is ``"<role>::<type>::<uuid>"``.
    Addressed by _id (no search snapshot), idempotent, noops an image whose entries are
    all already present. Returns docs written.
    """
    from backend.dataroom.datasets.os_sync import bulk_update_by_id

    ops = [
        (
            image_id,
            {
                **_ADD_ENTRIES_SCRIPT,
                "params": {"groupIds": e.get("group_ids", []), "memberships": e.get("memberships", [])},
            },
        )
        for image_id, e in entries_by_image.items()
    ]
    return bulk_update_by_id(ops)


def apply_delta_to_images(image_ids, group_id: str, add_roles, remove_roles) -> int:
    """Apply the same (add, remove) delta to many images in one OS call.

    A bulk ``update`` addressed by ``_id``, not an ``update_by_query``: the ids are
    already known, so there is no reason to take a search snapshot that a not-yet-
    refreshed write would invalidate. That snapshot is what used to force an index-wide
    refresh after every write - without it the *next* update_by_query silently dropped
    its write under ``conflicts: proceed``. See bulk_update_by_id.
    """
    if not image_ids:
        return 0
    script = {
        **_APPLY_IMAGE_SCRIPT,
        "params": {"gid": group_id, "add": list(add_roles), "remove": list(remove_roles)},
    }
    return bulk_update_by_id([(image_id, script) for image_id in image_ids])


# Remove every role for ANY of several groups from an image (bulk group deletion).
# The membership entries are "<role>::<type>::<uuid>", so a group matches on the "::<gid>"
# suffix - same test as _REMOVE_SCRIPT, just over a set.
_REMOVE_MANY_SCRIPT = {
    "lang": "painless",
    "source": (
        "if (ctx._source.group_ids != null) {"
        "  ctx._source.group_ids.removeIf(g -> params.gids.contains(g));"
        "}"
        "if (ctx._source.memberships != null) {"
        "  ctx._source.memberships.removeIf(e -> {"
        "    for (def g : params.gids) { if (e.endsWith('::' + g)) { return true; } }"
        "    return false;"
        "  });"
        "}"
    ),
}


def remove_groups_from_images(image_ids, group_ids) -> int:
    """Strip several groups from several images in one bulk write, addressed by ``_id``.

    The bulk-delete counterpart of :func:`scrub_group_from_all_images`, which is one
    ``update_by_query`` PER GROUP - fine for a single delete, N searches for a thousand.
    Here the caller already knows which images carry the groups (it read the memberships
    out of Postgres before soft-deleting them), so there is nothing to search for: the
    docs are addressed by _id and one bulk request covers every (image, group) pair.

    The trade-off against ``scrub_group_from_all_images`` is that a search finds images
    OpenSearch still references even when Postgres has no membership row for them, and
    this does not. That is a pre-existing PG<->OS desync, which is the reconciler's job
    (``Membership.os_synced``), not something a delete should be papering over.
    """
    image_ids = list(dict.fromkeys(image_ids))
    group_ids = list(group_ids)
    if not image_ids or not group_ids:
        return 0
    script = {**_REMOVE_MANY_SCRIPT, "params": {"gids": group_ids}}
    return bulk_update_by_id([(image_id, script) for image_id in image_ids])


def scrub_group_from_all_images(group_id: str) -> dict:
    """Remove all references to a group from every image in the index, and WAIT.

    This is the one write that legitimately searches rather than addressing docs by
    _id: the point is to find every image still carrying the group. Every caller
    (the delete view, the cleanup command) needs to know the scrub finished before
    it proceeds, so there is no fire-and-forget branch - a write nobody observes is
    a write nobody may claim happened.
    """
    body = {
        # TODO: fix after reindexing on prod — drop text_to_keyword_field() once group_ids is keyword everywhere.
        "query": {"term": {text_to_keyword_field("group_ids"): group_id}},
        "script": {**_REMOVE_SCRIPT, "params": {"gid": group_id}},
    }
    return OS.client.update_by_query(
        index=OSImage.INDEX,
        body=body,
        params={"conflicts": "proceed", "refresh": "true"},
    )
