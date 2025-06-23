import json
import urllib.parse

from django.core.management.base import BaseCommand
from opensearchpy import TransportError

from backend.dataroom.management.commands.opensearch_task_status import check_opensearch_task_status
from backend.dataroom.opensearch import OS


class Command(BaseCommand):
    help = 'Run a re-index command'

    def add_arguments(self, parser):
        parser.add_argument('--source', type=str, required=True, help='The index to re-index from')
        parser.add_argument('--destination', type=str, required=True, help='The index to re-index to')
        parser.add_argument(
            '--date-updated-gt',
            type=str,
            required=False,
            help='Filter by date_updated in re-index request, for example 2025-06-05T17:00:00Z',
        )

    def handle(self, *args, **options):
        source_index = options['source']
        destination_index = options['destination']
        date_updated_gt = options['date_updated_gt']

        source_exists = OS.client.indices.exists(index=source_index)
        destination_exists = OS.client.indices.exists(index=destination_index)
        if not source_exists or not destination_exists:
            if not source_exists:
                self.stdout.write(self.style.ERROR(f'Source index {source_index} does not exist!'))
            if not destination_exists:
                self.stdout.write(self.style.ERROR(f'Destination index {destination_index} does not exist!'))
            return

        body = {
            "source": {"index": source_index},
            "dest": {"index": destination_index},
        }
        params = {
            'wait_for_completion': 'false',
            'slices': 'auto',
        }

        if date_updated_gt:
            body['source']['query'] = {'range': {'date_updated': {'gt': date_updated_gt}}}

        self.stdout.write(self.style.SUCCESS(f'Re-indexing from {source_index} to {destination_index}'))
        self.stdout.write(f'POST /_reindex?{urllib.parse.urlencode(params)}\n{json.dumps(body, indent=4)}\n\n')

        # confirm the command
        if input(self.style.WARNING('Are you sure you want to run this re-index? (y/n): ')).lower() != 'y':
            self.stdout.write(self.style.ERROR('Aborted!'))
            return

        # run the command
        self.stdout.write(self.style.WARNING('Running re-index, please don\'t interrupt the process...'))
        try:
            response_json = OS.client.transport.perform_request(
                'POST',
                '/_reindex',
                body=body,
                timeout=120,
                params=params,
            )
        except TransportError as e:
            self.stdout.write(self.style.ERROR(e.info))
            raise e
        else:
            task_id = response_json['task']
            self.stdout.write(self.style.SUCCESS(f'Re-index started with task ID: {task_id}'))

        # confirm if we should check the status of the task
        if input(self.style.WARNING('Do you want to check the task status? (y/n): ')).lower() != 'y':
            self.stdout.write(self.style.SUCCESS('Done!'))
            return

        # check the status of the task
        check_opensearch_task_status(self, task_id)
