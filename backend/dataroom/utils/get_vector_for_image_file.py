import uuid

from PIL import Image

from backend.dataroom.utils.fetch_embedding import fetch_coca_embedding
from backend.dataroom.utils.vectors import normalize_vector

format_to_extension = {
    'JPEG': 'jpg',
    'PNG': 'png',
    'GIF': 'gif',
    'TIFF': 'tiff',
    'BMP': 'bmp',
    'WEBP': 'webp',
    'ICO': 'ico',
    'PCX': 'pcx',
}


def get_vector_for_image_file(image_file):
    pil_image = Image.open(image_file)
    ext = format_to_extension.get(pil_image.format, 'jpg')
    image_name = f'{uuid.uuid4().hex}.{ext}'

    vector = fetch_coca_embedding(pil_image, image_name)
    if not vector:
        return None

    return normalize_vector(vector)
