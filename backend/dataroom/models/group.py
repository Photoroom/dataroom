from django.core.validators import RegexValidator
from django.db import models

from backend.common.base_model import BaseModel

NAME_VALIDATOR = RegexValidator(
    regex=r'^[a-z0-9_]+$',
    message='name must be lowercase alphanumeric with underscores',
)

# Caps the number of groups accepted in one bulk create/delete request.
BULK_GROUPS_LIMIT = 1000


class Role(models.Model):
    """An allowed Membership.role value. Shared across GroupTypes via M2M."""

    name = models.CharField(
        primary_key=True,
        max_length=64,
        validators=[NAME_VALIDATOR],
    )
    description = models.TextField(blank=True, default='')

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class GroupType(models.Model):
    """A configurable group type. Owns the per-type validation rules.

    Defined by admins through the Django admin. The ``name`` is what gets
    prepended to the group's UUID in the OS denorm encoding (``<name>::<uuid>``),
    so it must be lowercase alphanumeric/underscore. Postgres ids stay plain
    UUIDs — type lives in its own column.
    """

    name = models.CharField(
        primary_key=True,
        max_length=64,
        validators=[NAME_VALIDATOR],
    )
    description = models.TextField(blank=True, default='')
    metadata_schema = models.JSONField(blank=True, default=dict)
    roles = models.ManyToManyField(Role, through='GroupTypeRole', related_name='group_types')
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class GroupTypeRole(BaseModel):
    """Through table: which roles a GroupType allows, and whether each is required."""

    group_type = models.ForeignKey(GroupType, on_delete=models.CASCADE, related_name='type_roles')
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name='type_roles')
    is_required = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('group_type', 'role'), name='grouptyperole_uniq'),
        ]
        ordering = ('group_type', 'role')

    def __str__(self):
        return f'{self.group_type_id}:{self.role_id}{"!" if self.is_required else ""}'


class Group(BaseModel):
    """A typed container of images.

    Two encodings of a group's identity coexist:
    - Postgres: plain UUID in ``id``; ``type`` is its own column (FK to GroupType).
    - OpenSearch denorm: ``"<type>::<uuid>"`` in ``OSImage.group_ids`` and
      ``"<role>::<type>::<uuid>"`` in each ``OSImage.memberships`` entry.

    Single ``::`` separator everywhere lets prefix queries slice at any level:
    - prefix(group_ids, "<type>::")               -> all groups of a type
    - prefix(memberships, "<role>::")             -> a role in any group
    - prefix(memberships, "<role>::<type>::")     -> a role in any group of a type
    - term(memberships,   "<role>::<type>::<id>") -> exact (role, group)

    Type-level filters are pure OS; exact-group filters resolve UUID -> type
    once on the server before issuing the OS query.
    """

    name = models.CharField(max_length=255)
    type = models.ForeignKey(GroupType, on_delete=models.PROTECT, related_name='groups')
    description = models.TextField(blank=True, default='')
    cover_image_id = models.CharField(max_length=255, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    author = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='image_groups',
    )
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['type']),
            # Backs cursor pagination on the list endpoint (ordering=-date_created).
            models.Index(fields=['-date_created']),
        ]
        constraints = [
            # Names are only unique among active (non-deleted) groups so a
            # soft-deleted group doesn't permanently squat its name.
            models.UniqueConstraint(
                fields=['name'],
                condition=models.Q(deleted_at__isnull=True),
                name='dataroom_group_name_unique_when_active',
            ),
        ]
        ordering = ('-date_created',)

    def __str__(self):
        return f'{self.type_id}::{self.id}'

    @property
    def os_encoded_id(self) -> str:
        """``<type>::<uuid>`` — derived; not stored in Postgres, only in OS denorm."""
        return f'{self.type_id}::{self.id}'


class Membership(BaseModel):
    """A typed link between an image (in OS) and a Group (in Postgres).

    Postgres is the source of truth; OSImage carries denormalized arrays
    (group_ids, memberships) for cheap filtering — see commit 3. Removals
    soft-delete (``deleted_at`` set) so the reconciler can see what changed
    since its last pass; a re-add of the same (image, role) revives the row.

    ``os_synced`` is False whenever Postgres has changed and the OS denorm
    may not yet reflect it. The API path flips it back to True once the
    inline OS write returns successfully; the periodic reconciler picks up
    any rows still False after a failure or crash.
    """

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    image_id = models.CharField(max_length=255)
    role = models.CharField(max_length=64)
    metadata = models.JSONField(default=dict, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    os_synced = models.BooleanField(default=False)

    class Meta:
        constraints = [
            # One row per (group, image, role): an image may hold several roles
            # in the same group (e.g. on_model + full_outfit), but not the same
            # role twice. A re-add of a soft-deleted membership revives the
            # same row (see GroupViewSet._bulk_replace_pg), so this stays
            # unconditional.
            models.UniqueConstraint(
                fields=('group', 'image_id', 'role'),
                name='memberships_group_image_role_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['image_id']),
            models.Index(fields=['group', 'role']),
            # "Active memberships of this group" — backs the image_count
            # annotation JOIN and the `existing` load in _bulk_replace_pg.
            # Without it those scan every soft-deleted row too.
            models.Index(fields=['group', 'deleted_at']),
            # Reconciler feed query: distinct groups with at least one
            # unsynced row. Partial so the index stays tiny — in steady
            # state almost every row is os_synced=True.
            models.Index(
                fields=['group'],
                condition=models.Q(os_synced=False),
                name='memberships_unsynced_idx',
            ),
        ]
        ordering = ('date_created',)

    def __str__(self):
        return f'{self.image_id}@{self.group_id}:{self.role}'
