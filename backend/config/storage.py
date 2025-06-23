import os
import pathlib

from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import FileSystemStorage
from django.core.files.utils import validate_file_name


class OverwriteStorage(FileSystemStorage):
    """
    File system storage that overwrites the file if it already exists.
    """

    def get_alternative_name(self, file_root, file_ext):
        """
        Return the filename as is.
        """
        return f"{file_root}{file_ext}"

    def get_available_name(self, name, max_length=None):
        """
        Return a filename that's free on the target storage system and
        available for new content to be written to.
        Deletes the existing file if the name is already taken.
        """
        name = str(name).replace("\\", "/")
        dir_name, file_name = os.path.split(name)
        if ".." in pathlib.PurePath(dir_name).parts:
            raise SuspiciousFileOperation(
                f"Detected path traversal attempt in '{dir_name}'",
            )
        validate_file_name(file_name)
        file_root, file_ext = os.path.splitext(file_name)
        # If the filename already exists, delete it.
        # Truncate original name if required, so the new filename does not
        # exceed the max_length.
        while self.exists(name) or (max_length and len(name) > max_length):
            # file_ext includes the dot.
            if self.exists(name):
                self.delete(name)
            if max_length is None:
                continue
            # Truncate file_root if max_length exceeded.
            truncation = len(name) - max_length
            if truncation > 0:
                file_root = file_root[:-truncation]
                # Entire file_root was truncated in attempt to find an
                # available filename.
                if not file_root:
                    raise SuspiciousFileOperation(
                        f'Storage can not find an available filename for "{name}". '
                        'Please make sure that the corresponding file field '
                        'allows sufficient "max_length".',
                    )
                if self.exists(name):
                    self.delete(name)
        return name
