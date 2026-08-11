"""
Import images from a local folder into DataRoom via API.
"""

import hashlib
import logging
import os
from argparse import ArgumentParser
from typing import Any, TypedDict

from django.core.management.base import BaseCommand, CommandError

from backend.users.models import Token, User
from dataroom_client import DataRoomClientSync, DataRoomError, DataRoomFile

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS: set[str] = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff'}


def get_image_id(image_path: str) -> str:
    """Calculate SHA256 hash of image file for Dataroom ID

    This is the convention we use internally in the ML team for image IDs.
    """
    with open(image_path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


class ImageFile(TypedDict):
    path: str
    file: DataRoomFile


class Command(BaseCommand):
    help = 'Import images from a local folder into DataRoom using dataroom_client.'

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            'folder',
            type=str,
            nargs='?',
            default='/app/sample_images',
            help='Path to folder containing images (default: /app/sample_images)',
        )
        parser.add_argument(
            '--source',
            type=str,
            default='local-import',
            help='Source name for imported images (default: local-import)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='List files without importing',
        )
        parser.add_argument(
            '--api-url',
            type=str,
            default='http://localhost:8000/api/',
            help='DataRoom API URL (default: http://localhost:8000/api/)',
        )
        parser.add_argument(
            '--api-key',
            type=str,
            default=None,
            help='DataRoom API key (default: auto-detect from database - first superuser)',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=10,
            help='Number of images per bulk request (default: 10)',
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Use DataRoomClientSync to upload files from `folder` using specified `api_key`."""
        folder: str = options['folder']
        api_key: str = options.get('api_key') or self._get_api_key()

        if not os.path.isdir(folder):
            raise CommandError(f"Folder not found: {folder}")

        self.stdout.write(f"Scanning folder: {options['folder']}")
        self.stdout.write(f"API URL: {options['api_url']}")
        self.stdout.write(f"Batch size: {options['batch_size']}\n")

        image_paths: list[str] = self._list_images(folder)
        self.stdout.write(f"Found {len(image_paths)} image files\n")

        if options['dry_run']:
            self.stdout.write("DRY RUN - would import (first 10):")
            for f in image_paths[:10]:
                self.stdout.write(f"  - {f}")
            return

        client = DataRoomClientSync(api_url=options['api_url'], api_key=api_key)
        image_files: list[ImageFile] = self._load_image_files(image_paths)
        imported, errors = self._import_batches(client, image_files, options['source'], options['batch_size'])

        self.stdout.write(self.style.SUCCESS(f"\nImported: {imported}"))
        if errors:
            self.stdout.write(self.style.ERROR(f"\nErrors: {errors}"))

    def _load_image_files(self, image_paths: list[str]) -> list[ImageFile]:
        image_files: list[ImageFile] = []
        for path in image_paths:
            try:
                image_files.append({'path': path, 'file': DataRoomFile.from_path(path)})
            except DataRoomError as e:
                self.stdout.write(self.style.ERROR(f"ERROR loading: {path} - {e}"))
        return image_files

    def _import_batches(
        self,
        client: DataRoomClientSync,
        image_files: list[ImageFile],
        source: str,
        batch_size: int,
    ) -> tuple[int, int]:
        imported = 0
        errors = 0

        for i in range(0, len(image_files), batch_size):
            batch = image_files[i : i + batch_size]
            success, error_count = self._import_batch(client, batch, source)
            imported += success
            errors += error_count

        return imported, errors

    def _import_batch(
        self,
        client: DataRoomClientSync,
        batch: list[ImageFile],
        source: str,
    ) -> tuple[int, int]:
        try:
            client.create_images(
                {"id": get_image_id(img['path']), "source": source, "image_file": img['file']} for img in batch
            )
            for img in batch:
                self.stdout.write(self.style.SUCCESS(f"- OK: {img['path']}"))
            return len(batch), 0
        except Exception as e:
            error_msg = str(e)
            if "already exist" in error_msg.lower():
                self.stdout.write(f"SKIP (batch has existing images): {error_msg}")
            else:
                self.stdout.write(self.style.ERROR(f"ERROR batch: {e}"))
                logger.exception("Failed to import batch")
            return 0, len(batch)

    def _get_api_key(self) -> str:
        """Get or create API key from database - expects superuser to be created."""
        user = User.objects.filter(is_superuser=True).first()
        if not user:
            raise CommandError("No superuser found. Create one first with: python manage.py createsuperuser")

        token, created = Token.objects.get_or_create(user=user)
        if created:
            self.stdout.write(f"Created API token for user: {user.email}")

        return token.key

    def _list_images(self, folder: str) -> list[str]:
        """List all image files in folder recursively."""
        images: list[str] = []
        for root, _, files in os.walk(folder):
            for filename in files:
                if self._is_image(filename):
                    images.append(os.path.join(root, filename))
        return images

    def _is_image(self, filepath: str) -> bool:
        """Check if file is an image based on extension."""
        return any(filepath.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)
