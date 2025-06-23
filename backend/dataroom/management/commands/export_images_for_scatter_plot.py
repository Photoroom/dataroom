import csv

from django.core.management.base import BaseCommand

from backend.dataroom.models.os_image import OSImage
from backend.dataroom.utils.umap import images_to_2d_coordinates


class Command(BaseCommand):
    help = 'Create a CSV to be used for deepscatter (for development purposes only)'

    def handle(self, *args, **options):
        images = OSImage.objects.all(number=1000)

        with open('images_for_scatter_plot.csv', 'w', newline='') as file:
            csv_writer = csv.writer(file)
            csv_writer.writerow(['id', 'source', 'x', 'y'])

            for image, x, y in images_to_2d_coordinates(images):
                csv_writer.writerow([image.id, image.source, x, y])

        self.stdout.write(self.style.SUCCESS('Done!'))
