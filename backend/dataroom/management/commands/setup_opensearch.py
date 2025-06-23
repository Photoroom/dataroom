from django.core.management.base import BaseCommand
from opensearchpy import TransportError

from backend.dataroom.models.os_image import OSImage
from backend.dataroom.opensearch import OS


class Command(BaseCommand):
    help = 'Create or update the OpenSearch index'

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true', help='Skip the confirmation prompt')
        parser.add_argument('--index', type=str, required=False, help='The name of the index to create or update')

    def handle(self, *args, **options):
        confirm = options['confirm']
        index_name = options['index'] or OSImage.INDEX

        exists = OS.client.indices.exists(index=index_name)
        if exists:
            self.stdout.write(f'Index "{index_name}" already exists. Mappings will be updated.')
        else:
            self.stdout.write(f'Creating new index "{index_name}".')

        if not confirm and input('Continue? (y/n): ') != 'y':
            self.stdout.write(self.style.ERROR('Aborted!'))
            return

        if exists:
            try:
                OS.client.indices.put_mapping(
                    index=index_name,
                    body=OSImage.INDEX_SETTINGS['mappings'],
                )
            except TransportError as e:
                self.stdout.write(self.style.ERROR(e.info))
                raise e
        else:
            try:
                OS.client.indices.create(
                    index=index_name,
                    body=OSImage.INDEX_SETTINGS,
                )
            except TransportError as e:
                self.stdout.write(self.style.ERROR(e.info))
                raise e

        self.stdout.write(self.style.SUCCESS('Done!'))
