class MissingEmbeddingError(Exception):
    """Raised when the OSImage instance does not have a corresponding embedding instance"""

    def __init__(self, message=None, image_id=None):
        if not message:
            message = f'Image "{image_id}" does not have an embedding'
        self.message = message
        self.image_id = image_id
        super().__init__(self.message)


class SaveConflictError(Exception):
    """Raised when saving to OS fails because of a version_conflict_engine_exception"""

    description = 'Conflict during save! Another process updated the same document in the meantime.'


class LatentTypeValidationError(Exception):
    """Raise when a LatentType is not defined in the database"""

    def __init__(self, message=None, latent_type=None):
        if not message:
            message = f"Invalid latent type '{latent_type}'"
        self.message = message
        self.latent_type = latent_type
