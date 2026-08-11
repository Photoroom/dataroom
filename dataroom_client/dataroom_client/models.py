"""Shared client-facing types: errors, the file wrapper, and payload TypedDicts."""

import mimetypes
import uuid
from enum import Enum
from io import BytesIO
from typing import Optional, TypedDict

mimetypes.add_type("image/webp", ".webp")


class DataRoomError(Exception):
    """Base exception class for DataRoomClient errors"""

    def __init__(self, *args, **kwargs) -> None:
        self.response = kwargs.pop("response", None)
        super().__init__(*args, **kwargs)

    def __str__(self) -> str:
        if self.response:
            return f"{super().__str__()}\n{self.response.status_code}\n{self.response.text}"
        else:
            return super().__str__()


class DataRoomFile:
    """A wrapper for a file-like object that can be used with DataRoomClient"""

    def __init__(self, bytes_io, content_type, path=None, extension=None) -> None:
        """
        Initializes a DataRoomFile object.

        @param bytes_io: A file-like object (e.g., BytesIO) containing the file data.
        @param content_type: The MIME type of the file (e.g., 'image/jpeg').
        @param path: Optional. The original path of the file.
        @param extension: Optional. The file extension (e.g., '.jpg'). If not provided, it's inferred from content_type.
        """
        extension = (
            mimetypes.guess_extension(content_type) or "" if extension is None else extension
        )
        self.bytes_io = bytes_io
        self.content_type = content_type
        if extension[0] != ".":
            extension = f".{extension}"
        self.extension = extension
        self.name = f"{uuid.uuid4().hex}"
        self.filename = f"{self.name}{extension}"
        self.path = path

    @classmethod
    def from_path(cls, path: str) -> "DataRoomFile":
        """
        Creates a DataRoomFile from a local file path.

        @param path: The absolute or relative path to the local file.
        @return: A DataRoomFile instance.
        """
        content_type, encoding = mimetypes.guess_type(path)
        if not content_type:
            raise DataRoomError(f"Could not guess content type for file: {path}")
        with open(path, "rb") as f:
            return DataRoomFile(
                bytes_io=BytesIO(f.read()),
                content_type=content_type,
                path=path,
            )

    @classmethod
    def from_bytesio(cls, bytes_io, extension) -> "DataRoomFile":
        """
        Creates a DataRoomFile from a BytesIO object.

        @param bytes_io: A BytesIO object containing the file data.
        @param extension: The file extension (e.g., '.jpg').
        @return: A DataRoomFile instance.
        """
        assert extension is not None, "Please provide a file extension"
        return DataRoomFile(
            bytes_io=bytes_io,
            extension=extension,
            content_type=None,
            path=None,
        )


class ClientDuplicateState(Enum):
    UNPROCESSED = 'None'
    ORIGINAL = 1
    DUPLICATE = 2


class LatentType(TypedDict, total=False):
    latent_type: str
    file: DataRoomFile


class ImageUpdate(TypedDict, total=False):
    id: str  # noqa: A003
    source: Optional[str]
    attributes: Optional[dict]
    tags: Optional[list[str]]
    coca_embedding: Optional[str]
    related_images: Optional[dict[str, str]]


class ImageCreate(TypedDict, total=False):
    id: str  # noqa: A003
    source: str
    image_file: Optional[DataRoomFile]
    image_url: Optional[str]
    attributes: Optional[dict]
    tags: Optional[list[str]]
    related_images: Optional[dict[str, str]]


def arg_deprecation_msg(arg_name, msg='') -> str:
    return f'The "{arg_name}" argument is deprecated and will stop working in a future release. {msg}'.strip()
