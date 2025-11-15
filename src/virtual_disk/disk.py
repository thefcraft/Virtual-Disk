from .disks import BaseDisk
from .disks.infile import InFileDisk
from .disks.inmemory import InMemoryDisk

try:
    from .disks.infile_encrypted import InFileChaCha20EncryptedDisk # pyright: ignore[reportAssignmentType]
except ImportError:
    class InFileChaCha20EncryptedDisk:
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Encrypted disk support requires the 'crypto' extra.\n"
                "Install with: uv add 'virtual-disk[crypto]'"
            )


__all__ = ["BaseDisk", "InMemoryDisk", "InFileDisk", "InFileChaCha20EncryptedDisk"]
