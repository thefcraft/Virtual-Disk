from wsgidav import util
from wsgidav.dav_provider import DAVProvider, DAVCollection, DAVNonCollection

from src.path import Directory
from src.path import Directory
from src.inode import Inode, InodeMode
from src.utils import abspath_to_paths
import os
from .folder_resource import CustomFolderResource
from .file_resource import CustomFileResource

class CustomFilesystemProvider(DAVProvider):
    def __init__(self, root: Directory, *, readonly=False):
        super().__init__()
        self.root: Directory = root
        self.readonly: bool = readonly
        
    def is_readonly(self) -> bool: return self.readonly # pyright: ignore[reportIncompatibleMethodOverride]
    
    def __repr__(self):
        rw = "Read-Only" if self.readonly else "Read-Write"
        return f"{self.__class__.__name__} for disk {self.root.disk!r} ({rw})"
    
    def get_resource_inst(self, path: str, environ: dict) -> DAVNonCollection | DAVCollection | None:
        self._count_get_resource_inst += 1
        
        root: Directory = self.root
        
        paths: list[bytes] = abspath_to_paths(
            path.encode('utf-8')
        )
        result = root.get_childs_inode(*paths)
        if result is None: return None
        if result.inode.st_mode == InodeMode.DIRECTORY:
            return CustomFolderResource(
                root=root,
                abspath=paths,
                environ=environ,
                path=path
            )
        return CustomFileResource(
            root=root,
            abspath=paths,
            environ=environ,
            path=path
        )