import io

import aioboto3
from ddtrace import tracer
from django.conf import settings
from PIL import Image


@tracer.wrap()
async def async_open_image(image_path, as_pil=True):
    """
    Asynchronously open an image from S3 using aioboto3 and PIL.
    @param image_path: Path to the image in S3
    @return: PIL Image object
    """

    async with aioboto3.Session(
        aws_access_key_id=settings.AWS_S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_S3_SECRET_ACCESS_KEY,
    ).client('s3') as s3_client:
        response = await s3_client.get_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=image_path)
        file_content = await response['Body'].read()
        if as_pil:
            pil_image = Image.open(io.BytesIO(file_content))
            pil_image.filename = image_path.split('/')[-1]
            return pil_image
        return io.BytesIO(file_content)
