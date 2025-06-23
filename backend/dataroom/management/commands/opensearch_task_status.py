import datetime
import json
import time

from django.core.management.base import BaseCommand

from backend.dataroom.opensearch import OS


def check_opensearch_task_status(command, task_id, frequency=5):
    # check the status of the task
    while True:
        main_task = OS.client.transport.perform_request(
            'GET',
            f'/_tasks/{task_id}',
            timeout=10,
        )

        # check if the main task is completed
        if main_task.get('completed', False):
            error = main_task.get('error', None)
            if error:
                command.stdout.write(command.style.ERROR(f'{json.dumps(main_task, indent=4)}'))
                command.stdout.write(command.style.ERROR('Migration failed with error!'))
            else:
                command.stdout.write(command.style.SUCCESS(f'{json.dumps(main_task, indent=4)}'))
                command.stdout.write(command.style.SUCCESS('Migration completed!'))
            break

        # get main task status
        total = main_task.get('task', {}).get('status', {}).get('total', 0)
        progress = sum(
            [main_task.get('task', {}).get('status', {}).get(key, 0) for key in ['created', 'deleted', 'updated']]
        )

        elapsed_seconds = main_task.get('task', {}).get('running_time_in_nanos', 0) / 1000000000

        if len(main_task.get('task', {}).get('status', {}).get('slices', [])) > 0:
            # use the progress of the child tasks instead
            child_tasks_response = OS.client.transport.perform_request(
                'GET',
                '/_tasks',
                params={
                    'detailed': 'true',
                    'parent_task_id': task_id,
                },
                timeout=10,
            )

            total = 0
            progress = 0
            for node in child_tasks_response['nodes'].values():
                for child_task in node['tasks'].values():
                    total += child_task.get('status', {}).get('total', 0)
                    progress += sum(
                        [child_task.get('status', {}).get(key, 0) for key in ['created', 'deleted', 'updated']]
                    )

        percent = progress / total * 100 if total else 0
        remaining_seconds = (elapsed_seconds / progress * (total - progress)) if progress else 0
        time_left = datetime.timedelta(seconds=remaining_seconds)

        # print the task status
        command.stdout.write(
            command.style.SUCCESS(
                f'Migration {percent:.2f}% complete - {progress}/{total} migrated - {time_left} remaining'
            )
        )

        # sleep for a while
        time.sleep(frequency)


class Command(BaseCommand):
    help = 'Check the status of an OpenSearch task'

    def add_arguments(self, parser):
        parser.add_argument('task_id', type=str, help='The task ID to check')
        parser.add_argument('--frequency', type=int, required=False, default=5, help='The frequency of status checks')

    def handle(self, *args, **options):
        task_id = options['task_id']
        frequency = options['frequency']

        check_opensearch_task_status(self, task_id, frequency=frequency)
