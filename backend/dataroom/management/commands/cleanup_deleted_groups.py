from django.core.management.base import BaseCommand

from backend.dataroom.groups.os_sync import scrub_group_from_all_images
from backend.dataroom.models.group import Group
from backend.dataroom.models.os_image import OSImage
from backend.dataroom.opensearch import OS


class Command(BaseCommand):
    help = (
        "Remove OpenSearch image-doc references to every soft-deleted Group. "
        "Use when single-delete scrubs may have failed or after a backfill mishap."
    )

    def handle(self, *args, **options):
        deleted = Group.objects.filter(deleted_at__isnull=False)
        total = deleted.count()
        self.stdout.write(f"Soft-deleted groups: {total}")
        for g in deleted.iterator():
            res = scrub_group_from_all_images(g.os_encoded_id)
            updated = res.get('updated', 0)
            self.stdout.write(f"  {g.id} ({g.name}) -> updated {updated} docs")
        OS.client.indices.refresh(index=OSImage.INDEX)
        self.stdout.write(self.style.SUCCESS("Done"))
