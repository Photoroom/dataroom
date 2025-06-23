import asyncio
import os

from .client import DataRoomFile, DataRoomClient, DataRoomError
from .counter import Counter
from .print_utils import print_error, print_status


class DataRoomLoader:

    def __init__(
        self,
        client: DataRoomClient,
        folder_path: str,
        concurrency: int = 2,
        verbose=True,
        image_source: str = 'loader',
        image_id_prefix: str = None,
    ):
        self.client = client
        self.concurrency = concurrency
        self.folder_path = folder_path
        self.counter = Counter(0)
        self.verbose = verbose
        self.image_source = image_source
        self.image_id_prefix = image_id_prefix

    async def run(self):
        images = os.listdir(self.folder_path)

        self.counter = Counter(len(images))
        self.counter.start()

        semaphore = asyncio.Semaphore(self.concurrency)
        tasks = []
        for image_path in images:
            tasks.append(self._process_image(image_path=image_path, semaphore=semaphore))

        await asyncio.gather(*tasks)

        self.counter.end()

    async def _process_image(self, image_path: str, semaphore: asyncio.Semaphore):
        async with semaphore:
            image_id = image_path.split('.')[0]
            if self.image_id_prefix:
                image_id = f"{self.image_id_prefix}{image_id}"
            full_path = os.path.join(self.folder_path, image_path)
            if self.verbose:
                print_status(f"Processing image: {full_path}")
            try:
                image_file = DataRoomFile.from_path(full_path)
            except DataRoomError as e:
                print_error(f"Failed to read image: {image_path} - Error: {e}")
            else:
                try:
                    await self.client.create_image(image_id=image_id, image_file=image_file, source=self.image_source)
                except DataRoomError as e:
                    print_error(f"Failed to create image: {image_path} - Error: {e}")
            finally:
                self.counter.increment()
