"""Keep ``OSImage.datasets`` in sync with Dataset membership in Postgres.

Postgres is the source of truth. An image's ``datasets`` array (a list of
Dataset ``slug_version`` strings, indexed for filtering/search) is a pure
denormalization of a two-hop relation::

    Dataset --(active DatasetMembership)--> Group --(active Membership)--> image

Datasets *own* the field: we recompute the whole array from PG truth and
SET it, rather than incrementally adding/removing single entries. That makes the
write idempotent and self-healing — the same primitive serves both the inline
API path and the periodic reconciler.

Two distinct changes can desync an image's ``datasets``:

1. a group's membership in a dataset changes (add/remove groups) — backed by
   ``DatasetMembership.os_synced`` and ``reconcile_datasets``;
2. an image's membership in a group changes — backed by the existing
   ``group.Membership.os_synced`` path, which calls in here too.

Both ultimately call :func:`recompute_datasets_for_images` for the affected
images, so the derivation lives in exactly one place.
"""

import logging
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings

from backend.dataroom.models.dataset import DatasetMembership
from backend.dataroom.models.group import Membership
from backend.dataroom.models.os_image import OSImage
from backend.dataroom.opensearch import OS

logger = logging.getLogger(__name__)

# Datasets own the field, so we overwrite it wholesale from PG truth.
#
# ``ctx.op = 'noop'`` when the value is already what we would write. OpenSearch
# otherwise re-indexes the whole document - all of it, not just this field - and bumps
# its _version, even when nothing changed. Most writes here change nothing: the
# reconciler's confirming write always re-sets the value the inline write already
# wrote, re-adding a group is idempotent, and adding one group to a dataset recomputes
# every image of every group it touches. Both sides are sorted lists, so `equals` is
# exact. Measured on 500 8KB docs: 91ms to rewrite an unchanged value, 44ms to noop it.
_SET_DATASETS_SCRIPT = {
    "lang": "painless",
    "source": (
        "if (ctx._source.datasets != null && ctx._source.datasets.equals(params.datasets)) {"
        "  ctx.op = 'noop';"
        "} else {"
        "  ctx._source.datasets = params.datasets;"
        "}"
    ),
}


# Single write for the single_image add path: set BOTH the group denorm
# (group_ids/memberships) and the datasets denorm in one pass. Addressed by _id, so the
# gid and the dataset list are this doc's own - no per-image maps to ship in the body.
# noop when neither field would change; see _SET_DATASETS_SCRIPT.
_SET_SINGLE_IMAGE_DENORM_SCRIPT = {
    "lang": "painless",
    "source": (
        "boolean changed = false;"
        "if (ctx._source.group_ids == null) { ctx._source.group_ids = new ArrayList(); }"
        "if (!ctx._source.group_ids.contains(params.gid)) { ctx._source.group_ids.add(params.gid); changed = true; }"
        "if (ctx._source.memberships == null) { ctx._source.memberships = new ArrayList(); }"
        "String entry = params.role + '::' + params.gid;"
        "if (!ctx._source.memberships.contains(entry)) { ctx._source.memberships.add(entry); changed = true; }"
        "if (ctx._source.datasets == null || !ctx._source.datasets.equals(params.datasets)) {"
        "  ctx._source.datasets = params.datasets;"
        "  changed = true;"
        "}"
        "if (!changed) { ctx.op = 'noop'; }"
    ),
}


def sync_single_image_denorm(gid_by_image: dict[str, str], role: str) -> int:
    """Write the single_image denorm for these images and WAIT for it.

    This used to be a fire-and-forget ``update_by_query`` (``wait_for_completion=false``),
    because rewriting a few hundred large docs that way took ~10s+. That is a property of
    update_by_query - a search, then a reindex of every hit - not of the write itself.
    Addressed by _id, a bulk update costs ~0.09ms per doc: 1000 images, the endpoint's
    cap, is under 100ms. There is no reason not to wait.

    Waiting is what earns the right to mark the rows os_synced: it is the only way to see
    that the write landed. So the caller may, and the reconciler goes back to being the
    rare repair it was meant to be rather than re-writing every doc a second time.

    Sets group_ids/memberships and datasets in one script, and noops when neither would
    change. Returns the number of docs written.
    """
    image_ids = list(gid_by_image)
    if not image_ids:
        return 0
    mapping = _datasets_by_image(image_ids)
    ops = [
        (
            image_id,
            {
                **_SET_SINGLE_IMAGE_DENORM_SCRIPT,
                "params": {
                    "role": role,
                    "gid": gid_by_image[image_id],
                    "datasets": sorted(mapping.get(image_id, ())),
                },
            },
        )
        for image_id in image_ids
    ]
    return bulk_update_by_id(ops)


# One bulk request per this many documents, and this many of those requests in flight
# at once.
#
# The chunk used to be 1000 on the reasoning that it "only bounds the request body" -
# true when a document rewrite cost 0.1ms and a thousand of them took 100ms. On an index
# whose vectors live on s3vector a rewrite costs ~100ms (an S3 round trip per doc), so
# 1000 docs is ~100s in a single request: past the client's 60s timeout, and past the
# 120s gunicorn worker timeout that would SIGKILL the whole gevent worker - taking every
# other request on it down too. Smaller chunks keep one request well inside both.
#
# Chunks then go out concurrently, because the cost is latency, not CPU: while one bulk
# waits on S3 the connection is idle. Under gevent (the web workers) these threads are
# greenlets and the waits interleave cooperatively; in the task runner they are real
# threads, and socket waits release the GIL either way. The client's connection pool is
# maxsize=120, so it is not the constraint.
#
# Concurrency is deliberately modest: the ceiling is how much simultaneous S3 traffic the
# CLUSTER tolerates, not what we can issue. It also multiplies - several concurrent adds
# each fan out by this much. Both are settings so they can be tuned against the numbers
# without a code change; compare the per-chunk ms/doc with the TOTAL line to see whether
# the cluster is actually parallelizing the S3 fetches or just queueing them.
_BULK_CHUNK = getattr(settings, 'OPENSEARCH_DENORM_BULK_CHUNK', 50)
_BULK_CONCURRENCY = getattr(settings, 'OPENSEARCH_DENORM_BULK_CONCURRENCY', 20)


def _send_chunk(chunk: list[tuple[str, dict]]) -> tuple[int, int, int]:
    """One bulk request: build the body, send it, account for every item.

    Returns (rewritten, noop, missing). A doc that no longer exists is not an error - the
    image was deleted - but any other per-item error raises, which propagates out of the
    pool and fails the whole write, leaving the rows os_synced=False for the reconciler.
    """
    body: list[dict] = []
    for image_id, script in chunk:
        body.append({"update": {"_id": image_id, "retry_on_conflict": 3}})
        body.append({"script": script})

    started = time.perf_counter()
    response = OS.client.bulk(index=OSImage.INDEX, body=body)
    elapsed_ms = (time.perf_counter() - started) * 1000

    rewritten = noop = missing = 0
    for item in response["items"]:
        result = item["update"]
        error = result.get("error")
        if error is None:
            if result.get("result") == "noop":
                noop += 1
            else:
                rewritten += 1
        elif error.get("type") == "document_missing_exception":
            missing += 1
        else:
            raise RuntimeError(f'OpenSearch bulk update failed for {result["_id"]}: {error}')

    logger.info(
        'os denorm bulk update: %d docs in %.0f ms (%.2f ms/doc) | opensearch took=%s ms '
        '(network %.0f ms) | rewritten=%d noop=%d missing=%d',
        len(chunk),
        elapsed_ms,
        elapsed_ms / len(chunk),
        response.get("took"),
        elapsed_ms - (response.get("took") or 0),
        rewritten,
        noop,
        missing,
    )
    return rewritten, noop, missing


def bulk_update_by_id(ops: list[tuple[str, dict]]) -> int:
    """Apply a painless script to each named document, addressed by ``_id``.

    ``update_by_query`` is the wrong tool when the ids are already known: it takes a
    search snapshot, and any doc modified since the last refresh fails the seq_no check.
    With ``conflicts: proceed`` that write is dropped SILENTLY - so the callers had to
    refresh the whole index after every write just to keep the *next* write from being
    lost. A bulk ``update`` addresses the doc directly: no snapshot, no conflict,
    ``retry_on_conflict`` for genuine concurrent writers, and no refresh needed.

    ``ops`` is [(image_id, script), ...]. Returns the number of docs updated. A doc
    that no longer exists in the index is not an error (the image was deleted); any
    other per-item error raises.

    Every denorm write in the system funnels through here, so this is where the cost of
    one is measured. Each chunk logs wall-clock, OpenSearch's own ``took``, and the
    updated/noop split, all per doc. What to read into them:

    * A scripted update is NOT a partial write. Lucene documents are immutable, so
      OpenSearch loads the whole ``_source``, runs the script, tombstones the old doc and
      indexes a new one. The price is the size of the DOCUMENT, not of the field we
      touched. ~0.1ms/doc on a small doc; ~0.2ms with a 768-dim faiss vector.
    * If the index keeps its vectors on the **s3vector** engine, that ``_source`` load is
      an S3 read PER DOC, and the re-index an S3 write - so ms/doc goes to tens or
      hundreds and a 1000-image request stops being interactive. ``noop`` does not save
      you: the script still has to be evaluated, so the read happens either way. A high
      noop count with a high ms/doc is the signature.
    * ``took`` is the cluster's own time. Wall-clock minus ``took`` is network/serialization.

    Chunks are sent concurrently (see _BULK_CONCURRENCY). A chunk that raises propagates
    here and fails the whole write; the caller's rows stay os_synced=False, so the
    reconciler picks them up. Sibling chunks already in flight still land, which is fine -
    every write here is idempotent.
    """
    chunks = [ops[start : start + _BULK_CHUNK] for start in range(0, len(ops), _BULK_CHUNK)]
    if not chunks:
        return 0

    if len(chunks) == 1:
        rewritten, noop, missing = _send_chunk(chunks[0])
        return rewritten + noop

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=_BULK_CONCURRENCY) as pool:
        results = list(pool.map(_send_chunk, chunks))
    elapsed_ms = (time.perf_counter() - started) * 1000

    rewritten = sum(r for r, _, _ in results)
    noop = sum(n for _, n, _ in results)
    missing = sum(m for _, _, m in results)
    logger.info(
        'os denorm bulk update TOTAL: %d docs in %d chunk(s) x%d concurrent, %.0f ms '
        '(%.2f ms/doc) | rewritten=%d noop=%d missing=%d',
        len(ops),
        len(chunks),
        _BULK_CONCURRENCY,
        elapsed_ms,
        elapsed_ms / len(ops),
        rewritten,
        noop,
        missing,
    )
    return rewritten + noop


def bulk_set_datasets(datasets_by_image: dict[str, list[str]]) -> int:
    """SET ``datasets`` on each image, one script per doc. See bulk_update_by_id."""
    ops = [
        (image_id, {**_SET_DATASETS_SCRIPT, "params": {"datasets": list(datasets)}})
        for image_id, datasets in datasets_by_image.items()
    ]
    return bulk_update_by_id(ops)


# Append ONE slug_version to an image's datasets, if absent. For copy: every image in
# the copied groups gains exactly the new dataset, and nothing is removed, so a targeted
# append is correct and skips re-deriving each image's full list from PG. noops if the
# slug is already there.
_APPEND_DATASET_SCRIPT = {
    "lang": "painless",
    "source": (
        "if (ctx._source.datasets == null) { ctx._source.datasets = new ArrayList(); }"
        "if (ctx._source.datasets.contains(params.sv)) { ctx.op = 'noop'; }"
        "else { ctx._source.datasets.add(params.sv); }"
    ),
}


def append_dataset_to_images(image_ids, slug_version: str) -> int:
    """Add ``slug_version`` to each image's datasets denorm, addressed by _id.

    The copy path: the recompute primitive would re-derive every image's whole dataset
    list (two membership queries) only to add the one slug we already know. This skips
    that - one write, no derivation. Returns docs written.
    """
    ops = [(image_id, {**_APPEND_DATASET_SCRIPT, "params": {"sv": slug_version}}) for image_id in image_ids]
    return bulk_update_by_id(ops)


def active_image_ids_for_groups(group_ids) -> list[str]:
    """Distinct image ids with an active membership in any of these groups."""
    if not group_ids:
        return []
    return list(
        Membership.objects.filter(group_id__in=group_ids, deleted_at__isnull=True)
        .values_list('image_id', flat=True)
        .distinct()
    )


def _datasets_by_image(image_ids, image_to_groups=None) -> dict[str, set[str]]:
    """Map each image id to the set of Dataset slug_versions it belongs to.

    Derived from PG in two unambiguous steps joined in Python: the image's active
    group memberships, then those groups' active dataset memberships.

    (Done as two queries on purpose: referencing the same multi-valued relation
    in both ``filter()`` and ``values_list()`` makes Django emit a second,
    unfiltered join and return NULL slug_versions.) Images with no dataset are
    simply absent from the result (the caller treats them as an empty set).
    """
    if image_to_groups is None:
        image_to_groups = defaultdict(set)
        for image_id, group_id in (
            Membership.objects.filter(image_id__in=image_ids, deleted_at__isnull=True)
            .values_list('image_id', 'group_id')
            .distinct()
        ):
            image_to_groups[image_id].add(group_id)
    group_ids = {group_id for groups in image_to_groups.values() for group_id in groups}

    group_to_datasets: dict[object, set[str]] = defaultdict(set)
    if group_ids:
        for group_id, slug_version in (
            DatasetMembership.objects.filter(group_id__in=group_ids, deleted_at__isnull=True)
            .values_list('group_id', 'dataset__slug_version')
            .distinct()
        ):
            group_to_datasets[group_id].add(slug_version)

    mapping: dict[str, set[str]] = defaultdict(set)
    for image_id, groups in image_to_groups.items():
        for group_id in groups:
            mapping[image_id] |= group_to_datasets.get(group_id, set())
    return mapping


def recompute_datasets_for_images(image_ids, *, _image_to_groups=None) -> int:
    """Recompute and SET ``datasets`` from PG truth for each given image.

    One bulk update per 1000 images, each doc addressed by its ``_id`` and given its own
    dataset list. Images that end up in no dataset get an empty array written (so removals
    take effect). Returns docs written; unchanged docs are noop'd, not rewritten.

    Never refreshes the index: the docs are addressed by ``_id`` (no search snapshot,
    no version conflict with an unrefreshed write), so the write is durable immediately
    and OpenSearch's own refresh interval makes it searchable. See bulk_update_by_id.
    """
    image_ids = list(dict.fromkeys(image_ids))  # de-dupe, preserve order
    if not image_ids:
        return 0

    mapping = _datasets_by_image(image_ids, image_to_groups=_image_to_groups)
    return bulk_set_datasets({image_id: sorted(mapping.get(image_id, ())) for image_id in image_ids})


def recompute_datasets_for_groups(group_ids) -> int:
    """Recompute ``datasets`` for every image in the given groups.

    Used by the dataset<->group trigger: after groups are added to / removed
    from a dataset, every image in those groups may have gained or lost the
    dataset's slug_version.

    Fetches ``image -> all-its-groups`` in a single query (subquery: images that
    are in ``group_ids``) and hands it straight to the recompute — we still need
    each image's *full* group set (the ``datasets`` array is SET wholesale), but
    this avoids the extra ``group_ids -> image_ids -> group_ids`` round trip.

    """
    if not group_ids:
        return 0
    images_in_groups = Membership.objects.filter(group_id__in=group_ids, deleted_at__isnull=True).values('image_id')
    image_to_groups: dict[str, set] = defaultdict(set)
    for image_id, group_id in (
        Membership.objects.filter(image_id__in=images_in_groups, deleted_at__isnull=True)
        .values_list('image_id', 'group_id')
        .distinct()
    ):
        image_to_groups[image_id].add(group_id)
    return recompute_datasets_for_images(list(image_to_groups), _image_to_groups=image_to_groups)
