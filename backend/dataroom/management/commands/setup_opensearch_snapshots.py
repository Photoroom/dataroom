from django.conf import settings
from django.core.management.base import BaseCommand

from backend.dataroom.opensearch import OS


def setup_snapshot_repository():
    body = {
        "type": "s3",
        "settings": {
            "bucket": settings.OPENSEARCH_SNAPSHOT_BUCKET,
            "region": "us-west-2",
            "role_arn": settings.OPENSEARCH_SNAPSHOT_ROLE_ARN,
        },
    }
    OS.client.transport.perform_request(
        method='POST',
        url=f'/_snapshot/{settings.OPENSEARCH_SNAPSHOT_REPOSITORY_NAME}',
        body=body,
    )


def setup_automatic_snapshots():
    body = {
        "description": "DataRoom snapshots",
        "creation": {
            "schedule": {
                "cron": {
                    "expression": "0 0 * * *",
                    "timezone": "UTC",
                },
            },
            "time_limit": "3h",
        },
        "deletion": {
            "schedule": {
                "cron": {
                    "expression": "0 1 * * *",
                    "timezone": "UTC",
                },
            },
            "condition": {
                "max_age": "30d",
                "max_count": 21,
                "min_count": 7,
            },
            "time_limit": "3h",
        },
        "snapshot_config": {
            "date_format": "yyyy-MM-dd-HH:mm",
            "timezone": "UTC",
            "indices": "*",
            "repository": settings.OPENSEARCH_SNAPSHOT_REPOSITORY_NAME,
            "ignore_unavailable": True,
            "include_global_state": False,
            "partial": True,
            "metadata": {
                "managed_by": "automated_policy",
            },
        },
    }
    OS.client.transport.perform_request(
        method='POST',
        url=f'/_plugins/_sm/policies/{settings.OPENSEARCH_SNAPSHOT_NAME}',
        body=body,
    )


class Command(BaseCommand):
    help = 'Setup OpenSearch snapshots'

    def handle(self, *args, **options):
        setup_snapshot_repository()
        setup_automatic_snapshots()

        self.stdout.write(self.style.SUCCESS('Done!'))
