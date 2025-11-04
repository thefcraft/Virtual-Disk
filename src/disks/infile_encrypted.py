from .infile import InFileDisk

from typing import Self, BinaryIO
from src.config import Config

from io import BytesIO
class EncryptedBytesIO(BytesIO):
    ...

class InFileEncryptedDisk(InFileDisk):
    def __init__(self, filepath: str | BinaryIO) -> None:
        # super().__init__(filepath)
        raise NotImplementedError()
    @classmethod
    def new_disk(cls, filepath: str | BinaryIO, config: Config) -> Self:
        # return super().new_disk(filepath, config)
        raise NotImplementedError()