import importlib.util
import json
import urllib.parse
from pathlib import Path

from django.core.management.base import BaseCommand
from opensearchpy import TransportError

from backend.dataroom.management.commands.opensearch_task_status import check_opensearch_task_status
from backend.dataroom.opensearch import OS


class Command(BaseCommand):
    help = 'Run a re-index migration from the opensearch_migrations directory'

    def add_arguments(self, parser):
        parser.add_argument('--migration', type=str, required=False, help='The migration name to run')
        parser.add_argument(
            '--date-updated-gt',
            type=str,
            required=False,
            help='Filter by date_updated in the migration source query, for example 2025-06-05T17:00:00Z',
        )

    def load_migration(self, migration_file):
        spec = importlib.util.spec_from_file_location(migration_file.stem, migration_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.migration

    def handle(self, *args, **options):
        migration_name = options['migration']
        date_updated_gt = options['date_updated_gt']

        migrations_folder = Path(__file__).parent.parent.parent / 'opensearch_migrations'
        available_migrations = sorted(
            [f.stem for f in migrations_folder.iterdir() if f.is_file() and f.suffix == '.py']
        )

        if not migration_name:
            self.stdout.write(self.style.ERROR(f'Available migrations: \n{'\n'.join(available_migrations)}'))
            return

        # shortcut by checking prefix matches
        if migration_name not in available_migrations:
            for available_migration in available_migrations:
                if available_migration.startswith(f'{migration_name}_'):
                    migration_name = available_migration
                    break

        # check if migration exists
        if migration_name not in available_migrations:
            self.stdout.write(self.style.ERROR(f'Migration {migration_name} does not exist!'))
            self.stdout.write(self.style.ERROR(f'Available migrations: \n{'\n'.join(available_migrations)}'))
            return

        migration_file = migrations_folder / f'{migration_name}.py'
        if not migration_file.exists():
            self.stdout.write(self.style.ERROR(f'Migration file {migration_name}.py not found!'))
            return

        migration_data = self.load_migration(migration_file)
        params = {
            'wait_for_completion': 'false',
            'slices': 'auto',
        }

        if date_updated_gt:
            migration_data['source']['query'] = {'range': {'date_updated': {'gt': date_updated_gt}}}

        self.stdout.write(self.style.SUCCESS(f'Selected migration: {migration_file.name}'))
        self.stdout.write(
            f'POST /_reindex?{urllib.parse.urlencode(params)}\n{json.dumps(migration_data, indent=4)}\n\n'
        )

        # confirm the migration
        if input(self.style.WARNING('Are you sure you want to run this re-index migration? (y/n): ')).lower() != 'y':
            self.stdout.write(self.style.ERROR('Aborted!'))
            return

        # run the migration
        self.stdout.write(
            self.style.WARNING(f'Running migration {migration_name}, please don\'t interrupt the process...')
        )
        try:
            response_json = OS.client.transport.perform_request(
                'POST',
                '/_reindex',
                body=migration_data,
                timeout=120,
                params=params,
            )
        except TransportError as e:
            self.stdout.write(self.style.ERROR(e.info))
            raise e
        else:
            task_id = response_json['task']
            self.stdout.write(self.style.SUCCESS(f'Migration started with task ID: {task_id}'))

        # confirm if we should check the status of the task
        if input(self.style.WARNING('Do you want to check the task status? (y/n): ')).lower() != 'y':
            self.stdout.write(self.style.SUCCESS('Done!'))
            return

        # check the status of the task
        check_opensearch_task_status(self, task_id)
