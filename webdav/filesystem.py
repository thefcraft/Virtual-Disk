from wsgidav import util
from wsgidav.dav_error import HTTP_FORBIDDEN, DAVError
from wsgidav.dav_provider import DAVCollection, DAVNonCollection, DAVProvider

from src.inode import InodeMode
from src.path import Directory
from src.utils import abspath_to_paths

from .file_resource import CustomFileResource
from .folder_resource import CustomFolderResource


class CustomFilesystemProvider(DAVProvider):
    def __init__(self, root: Directory, *, readonly=False):
        super().__init__()
        self.root: Directory = root
        self.readonly: bool = readonly

    def is_readonly(self) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
        return self.readonly

    def __repr__(self):
        rw = "Read-Only" if self.readonly else "Read-Write"
        return f"{self.__class__.__name__} for disk {self.root.disk!r} ({rw})"

    def get_resource_inst(
        self, path: str, environ: dict
    ) -> DAVNonCollection | DAVCollection | None:
        self._count_get_resource_inst += 1

        root: Directory = self.root

        paths: list[bytes] = abspath_to_paths(path.encode("utf-8"))
        try:
            result = root.get_childs_inode(*paths)
        except NotADirectoryError as nad:
            util._logger.info(f"Error: {nad}; {paths=}")
            raise DAVError(HTTP_FORBIDDEN)
        if result is None:
            return None
        if result.inode.st_mode == InodeMode.DIRECTORY:
            return CustomFolderResource(
                root=root, abspath=paths, environ=environ, path=path
            )
        return CustomFileResource(root=root, abspath=paths, environ=environ, path=path)
