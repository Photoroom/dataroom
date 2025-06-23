import logging

logger = logging.getLogger(__name__)


def cleanup_instance_files(instance, field_names):
    """
    Deletes the given field names of an instance. Useful for cleaning up files from S3 before deleting the instance.
    """
    for field_name in field_names:
        field_instance = getattr(instance, field_name)
        if field_instance:
            try:
                field_instance.delete()
            except Exception as e:
                logger.exception(e)
