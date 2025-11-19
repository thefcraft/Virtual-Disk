from io import BytesIO

from wsgidav import util
from wsgidav.dav_error import HTTP_FORBIDDEN, DAVError
from wsgidav.dav_provider import DAVNonCollection, DAVProvider

from src.virtual_disk.config import Config
from src.virtual_disk.path import Directory, FileIO, FileMode
from src.virtual_disk.protocol import Disk
from src.virtual_disk.utils import abspath_to_paths

import threading

FILE_LOCKS: dict[int, threading.Lock] = {}  # map inode_ptr -> Lock
FILE_LOCKS_LOCK = threading.Lock()

def get_file_lock(inode_ptr: int) -> threading.Lock:
    with FILE_LOCKS_LOCK:
        if inode_ptr not in FILE_LOCKS:
            FILE_LOCKS[inode_ptr] = threading.Lock()
        return FILE_LOCKS[inode_ptr]

class CustomFileResource(DAVNonCollection):
    """Represents a single existing DAV resource instance.

    See also _DAVResource, DAVNonCollection, and FilesystemProvider.
    """

    def __init__(
        self, root: Directory, abspath: list[bytes], *, path: str, environ: dict
    ):
        super().__init__(path, environ)
        self.abspath: list[bytes] = abspath
        self.root: Directory = root
        self.fs_opts: DAVProvider = self.provider
        self._move_deleted: bool = False
        self._write_lock: threading.Lock | None = None

    @property
    def disk(self) -> Disk:
        return self.root.disk

    @property
    def config(self) -> Config:
        return self.disk.config

    def assert_get_childs_inode(self, *names: bytes) -> Directory._InodeResult:
        result = self.root.get_childs_inode(*names)
        if result is None:
            raise RuntimeError(
                f"{self.abspath=} is not found, TREE: {self.root.listtree()=}"
            )
        return result

    # Getter methods for standard live properties
    def get_content_length(self) -> int:
        result = self.assert_get_childs_inode(*self.abspath)
        return result.inode.st_size

    def get_content_type(self) -> str:
        return util.guess_mime_type(self.path)

    def get_creation_date(self) -> int:
        result = self.assert_get_childs_inode(*self.abspath)
        return result.inode.st_ctime

    def get_display_name(self) -> str:
        return self.name

    def get_etag(self) -> str:  # pyright: ignore[reportIncompatibleMethodOverride]
        result = self.assert_get_childs_inode(*self.abspath)
        return f"{result.inode_ptr}-{result.inode.st_mtime}-{result.inode.st_size}"

    def get_last_modified(self) -> int:  # pyright: ignore[reportIncompatibleMethodOverride]
        result = self.assert_get_childs_inode(*self.abspath)
        return result.inode.st_mtime

    def is_link(self) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
        return False

    def support_etag(self) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
        return True

    def support_ranges(self) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
        return True

    def support_recursive_move(self, dest_path: str) -> bool:
        return False

    def get_content(self) -> BytesIO:
        """Open content as a stream for reading.

        See DAVResource.get_content()
        """
        result = self.assert_get_childs_inode(*self.abspath)
        return FileIO(
            disk=self.disk,
            inode_ptr=result.inode_ptr,
            inode=result.inode,
            mode=FileMode.READ,
        )

    def begin_write(self, *, content_type: str | None = None) -> BytesIO:  # pyright: ignore[reportIncompatibleMethodOverride]
        if self.provider.is_readonly():  # ...
            raise DAVError(HTTP_FORBIDDEN)
        result = self.assert_get_childs_inode(*self.abspath)
        
        lock = get_file_lock(result.inode_ptr)
        lock.acquire()  # Exclusive write
        self._write_lock = lock

        return FileIO(
            disk=self.disk,
            inode_ptr=result.inode_ptr,
            inode=result.inode,
            mode=FileMode.WRITE,
        )
    
    def end_write(self, *, with_errors):
        
        # Always release lock
        if self._write_lock is not None:
            self._write_lock.release()

        return super().end_write(with_errors=with_errors)

    def delete(self) -> None:
        """Remove this resource or collection (recursive).

        See DAVResource.delete()
        """
        if self.provider.is_readonly():
            raise DAVError(HTTP_FORBIDDEN)

        if not self._move_deleted:
            *parent_path, name = self.abspath  # auto prevent root delete
            parent = self.root.chdir(*parent_path)
            parent.remove(name)
        else:
            util._logger.debug(
                f"delete(): {self.path} already gone, skipping; {self._move_deleted=}"
            )

        self.remove_all_properties(recursive=True)
        self.remove_all_locks(recursive=True)

    def copy_move_single(self, dest_path: str, *, is_move: bool) -> None:
        """See DAVResource.copy_move_single()"""

        if self.provider.is_readonly():
            raise DAVError(HTTP_FORBIDDEN)

        paths: list[bytes] = abspath_to_paths(dest_path.encode("utf-8"))

        if is_move:
            self.root.rename(src=self.abspath, dest=paths)
            self._move_deleted = True
            return None

        chunk_size = 1024 * 1024 * 32  # 32 MB at a time

        self.root.copy_file(
            src=self.abspath, dest=paths, overwrite=True, chunk_size=chunk_size
        )

    def set_last_modified(
        self, dest_path: str, time_stamp: str, *, dry_run: bool
    ) -> bool:
        """Set last modified time for destPath to timeStamp on epoch-format"""
        # Translate time from RFC 1123 to seconds since epoch format
        secs: int | None = util.parse_time_string(time_stamp)
        if secs is None:
            raise ValueError(f"Unable to Parse {time_stamp=}")
        if not dry_run:
            result = self.assert_get_childs_inode(*self.abspath)
            result.inode.st_mtime = secs
            self.disk.inodes[result.inode_ptr][:] = result.inode.to_bytes(self.config)
        return True
