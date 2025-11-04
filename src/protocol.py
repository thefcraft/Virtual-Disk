from .config import Config
from .bitmap import Bitmap
from typing import Protocol, Iterator

class InodeView(Protocol):
    def __len__(self) -> int:
        raise NotImplementedError()
    def __setitem__(
        self, 
        idx: "slice[None, None, None]", 
        value: bytes,
        /
    ):
        raise NotImplementedError()
    def __getitem__(
        self,
        idx: "slice[int, int, None]",
        /
    ) -> bytes:
        raise NotImplementedError()    

class BlockView(Protocol):
    def __iter__(self) -> Iterator[int]: 
        raise NotImplementedError()
    
    def __setitem__(
        self, 
        idx: "slice[int | None, int | None, None]", 
        value: bytes,
        /
    ):
        raise NotImplementedError()
    def __getitem__(
        self,
        idx: "slice[int | None, int | None, None]",
        /
    ) -> bytes:
        raise NotImplementedError()
    
class InodesList(Protocol): 
    def __getitem__(self, idx: int, /) -> InodeView: 
        raise NotImplementedError()
    
class BlocksList(Protocol): 
    def __getitem__(self, idx: int, /) -> BlockView: 
        raise NotImplementedError()
    
class Disk(Protocol):
    config: Config
    inodes_bitmap: Bitmap
    blocks_bitmap: Bitmap
    
    inodes: InodesList
    blocks: BlocksList
    
    def total_space(self) -> int: ...
    def free_space(self) -> int: ...
    def used_space(self) -> int: ...