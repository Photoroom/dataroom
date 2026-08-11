"""Optional expansion of a page of groups into their roles + per-image data.

Mirrors the images API's ``include_fields`` idea: everything is opt-in via query
params and everything is batched (1 PG query for the page's memberships + at most
1 OpenSearch query for all their images), so expanding a page never N+1s.
"""

from collections import defaultdict

from rest_framework import serializers

from backend.dataroom.models.dataset import DatasetMembership
from backend.dataroom.models.group import Membership
from backend.dataroom.models.os_image import OSImage

# selectable via ?include_fields= . `roles` adds the roles[] array; presigned_url,
# thumbnail_url and os_metadata add per-image data (and imply roles); `datasets` is
# group-level: the slug_versions of the datasets this group belongs to.
ROLES = 'roles'
PRESIGNED_URL = 'presigned_url'
THUMBNAIL_URL = 'thumbnail_url'
OS_METADATA = 'os_metadata'
DATASETS = 'datasets'
VALID_INCLUDE_FIELDS = {ROLES, PRESIGNED_URL, THUMBNAIL_URL, OS_METADATA, DATASETS}


def _csv(value):
    if not value:
        return None
    return [v.strip() for v in value.split(',') if v.strip()]


class GroupExpandParamsSerializer(serializers.Serializer):
    """Query params controlling how much per-group data to return. All optional;
    default is the plain group (no roles, no metadata, no image data)."""

    return_roles = serializers.CharField(required=False)  # CSV; default = all roles
    include_metadata = serializers.BooleanField(required=False, default=False)
    include_fields = serializers.CharField(required=False)  # CSV of presigned_url, os_metadata

    def opts(self):
        """Parsed/validated options dict."""
        data = self.validated_data
        include_fields = set(_csv(data.get('include_fields')) or [])
        unknown = include_fields - VALID_INCLUDE_FIELDS
        if unknown:
            raise serializers.ValidationError({'include_fields': f'unknown field(s): {", ".join(sorted(unknown))}'})
        presigned = PRESIGNED_URL in include_fields
        thumbnail = THUMBNAIL_URL in include_fields
        os_metadata = OS_METADATA in include_fields
        return {
            'roles': ROLES in include_fields or presigned or thumbnail or os_metadata,
            'return_roles': _csv(data.get('return_roles')),  # None = all
            'include_metadata': data.get('include_metadata', False),
            'presigned_url': presigned,
            'thumbnail_url': thumbnail,
            'os_metadata': os_metadata,
            'datasets': DATASETS in include_fields,
        }


def expand_groups(groups, opts):
    """{group_id: {roles?: [...], metadata?, datasets?}} for a page of Group objects.

    1 PG query for all memberships on the page, 1 OS query for their images when
    per-image fields are requested, and 1 PG query for dataset memberships when
    `datasets` is requested. All page-scoped: expanding a page never N+1s.
    """
    result = {g.id: {} for g in groups}
    group_ids = [g.id for g in groups]

    if opts['include_metadata']:
        for g in groups:
            result[g.id]['metadata'] = g.metadata

    if opts['datasets']:
        # One join over the membership table for the whole page: which datasets
        # each group belongs to, as sorted slug_versions.
        by_group = defaultdict(set)
        for group_id, slug_version in DatasetMembership.objects.filter(
            group_id__in=group_ids, deleted_at__isnull=True
        ).values_list('group_id', 'dataset__slug_version'):
            by_group[group_id].add(slug_version)
        for g in groups:
            result[g.id]['datasets'] = sorted(by_group.get(g.id, ()))

    if not opts['roles']:
        return result

    memberships = Membership.objects.filter(group_id__in=group_ids, deleted_at__isnull=True)
    if opts['return_roles']:
        memberships = memberships.filter(role__in=opts['return_roles'])
    rows = list(memberships.values('group_id', 'image_id', 'role', 'metadata').order_by('date_created'))

    want_images = opts['presigned_url'] or opts['thumbnail_url'] or opts['os_metadata']
    image_by_id = {}
    if want_images:
        image_ids = list({r['image_id'] for r in rows})
        fields = []
        if opts['presigned_url']:
            fields.append('image')
        if opts['thumbnail_url']:
            # 'image' rides along for the fallback below, same as the cover path.
            fields.extend(('thumbnail', 'image'))
        if opts['os_metadata']:
            fields.append('attributes')
        if image_ids:
            image_by_id = {
                img.id: img for img in OSImage.objects.get_multiple(image_ids, fields=fields, number=len(image_ids))
            }

    rows_by_group = {}
    for r in rows:
        rows_by_group.setdefault(r['group_id'], []).append(r)

    for g in groups:
        roles = []
        for r in rows_by_group.get(g.id, []):
            # Membership metadata always rides with the expanded roles: the query
            # already fetched it, so gating it behind include_metadata only threw
            # it away. include_metadata still gates GROUP metadata (above).
            role = {'image_id': r['image_id'], 'role': r['role'], 'metadata': r['metadata']}
            if want_images:
                img = image_by_id.get(r['image_id'])
                if opts['presigned_url']:
                    # The original's url or null - never a thumbnail pretending to
                    # be one. Ask for thumbnail_url if that is what you want.
                    role['presigned_url'] = img.image_url if img else None
                if opts['thumbnail_url']:
                    # Thumbnails are generated asynchronously, so an image can sit
                    # without one for a while. Fall back to the original rather than
                    # hand back null and leave the UI with a blank tile - the same
                    # rule the cover thumbnails follow (batch_cover_thumbnails).
                    role['thumbnail_url'] = (img.thumbnail_url or img.image_url) if img else None
                if opts['os_metadata']:
                    role['os_metadata'] = img.attributes.to_json() if (img and img.attributes) else None
            roles.append(role)
        result[g.id]['roles'] = roles
    return result
