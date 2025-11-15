from wsgidav import util
from wsgidav.dav_error import HTTP_FORBIDDEN, DAVError
from wsgidav.dav_provider import DAVCollection, DAVNonCollection, DAVProvider

from src.config import Config
from src.inode import InodeMode
from src.path import Directory
from src.protocol import Disk
from src.utils import abspath_to_paths

from .file_resource import CustomFileResource


class CustomFolderResource(DAVCollection):
    """Represents a single existing file system folder DAV resource.

    See also _DAVResource, DAVCollection, and FilesystemProvider.
    """

    def __init__(
        self, root: Directory, abspath: list[bytes], *, path: str, environ: dict
    ):
        super().__init__(path, environ)
        self.abspath: list[bytes] = abspath
        self.root: Directory = root
        self.fs_opts: DAVProvider = self.provider
        self._move_deleted: bool = False

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
    def get_creation_date(self) -> int:
        result = self.assert_get_childs_inode(*self.abspath)
        return result.inode.st_ctime

    def get_display_name(self) -> str:
        return self.name

    def get_directory_info(self) -> None:
        return None

    def get_etag(self) -> None:
        return None

    def get_used_bytes(self) -> int:
        return (
            self.disk.config.num_blocks - self.disk.blocks_bitmap.free_count()
        ) * self.disk.config.block_size

    def get_available_bytes(self) -> int:
        return self.disk.blocks_bitmap.free_count() * self.disk.config.block_size

    def get_last_modified(self) -> int:  # pyright: ignore[reportIncompatibleMethodOverride]
        result = self.assert_get_childs_inode(*self.abspath)
        return result.inode.st_mtime

    def is_link(self) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
        return False

    def support_recursive_move(self, dest_path: str) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
        return True

    def get_member_names(self) -> list[str]:
        directory = self.root.chdir(*self.abspath)
        return [name.decode("utf-8") for name in directory.listdir()]

    def get_member(self, name: str) -> DAVNonCollection | DAVCollection | None:
        new_abs_path: list[bytes] = [*self.abspath, name.encode("utf-8")]
        result = self.root.get_childs_inode(*new_abs_path)
        if result is None:
            return None
        if result.inode.st_mode == InodeMode.DIRECTORY:
            return CustomFolderResource(
                self.root,
                abspath=new_abs_path,
                path=util.join_uri(self.path, name),
                environ=self.environ,
            )
        return CustomFileResource(
            self.root,
            new_abs_path,
            path=util.join_uri(self.path, name),
            environ=self.environ,
        )

    # --- Read / write -------------------------------------------------------
    def create_collection(self, name: str) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        assert "/" not in name
        if self.provider.is_readonly():
            raise DAVError(HTTP_FORBIDDEN)
        self.root.makedirs(*self.abspath, name.encode("utf-8"), exist_ok=False)

    def create_empty_resource(self, name: str) -> DAVNonCollection:
        """Create an empty (length-0) resource.

        See DAVResource.create_empty_resource()
        """
        assert "/" not in name
        if self.provider.is_readonly():
            raise DAVError(HTTP_FORBIDDEN)
        encode_name = name.encode("utf-8")
        directory = self.root.chdir(*self.abspath)
        directory.create_empty_file(encode_name)

        return CustomFileResource(
            self.root,
            abspath=[*self.abspath, encode_name],
            path=util.join_uri(self.path, name),
            environ=self.environ,
        )

    def delete(self) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Remove this resource or collection (recursive).

        See DAVResource.delete()
        """
        if self.provider.is_readonly():
            raise DAVError(HTTP_FORBIDDEN)
        if not self._move_deleted:
            *parent_path, name = self.abspath  # auto prevent root delete
            parent = self.root.chdir(*parent_path)
            parent.rm_tree(name)
        else:
            util._logger.debug(
                f"delete(): {self.path} already gone, skipping; {self._move_deleted=}"
            )
        self.remove_all_properties(recursive=True)
        self.remove_all_locks(recursive=True)

    def move_recursive(self, dest_path: str) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        if self.provider.is_readonly():
            raise DAVError(HTTP_FORBIDDEN)

        paths: list[bytes] = abspath_to_paths(dest_path.encode("utf-8"))
        self.root.rename(src=self.abspath, dest=paths)
        self._move_deleted = True

    def copy_move_single(self, dest_path: str, *, is_move: bool) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """See DAVResource.copy_move_single()"""
        if self.provider.is_readonly():
            raise DAVError(HTTP_FORBIDDEN)

        paths: list[bytes] = abspath_to_paths(dest_path.encode("utf-8"))

        self.root.makedirs(*paths, exist_ok=False)

    def set_last_modified(
        self, dest_path: str, time_stamp: str, *, dry_run: bool
    ) -> bool:
        """Set last modified time for destPath to timeStamp on epoch-format"""
        secs: int | None = util.parse_time_string(time_stamp)
        if secs is None:
            raise ValueError(f"Unable to Parse {time_stamp=}")

        if not dry_run:
            result = self.assert_get_childs_inode(*self.abspath)
            result.inode.st_mtime = secs
            self.disk.inodes[result.inode_ptr][:] = result.inode.to_bytes(self.config)
        return True
