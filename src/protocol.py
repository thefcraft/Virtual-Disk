from types import TracebackType
from typing import ByteString, Iterator, Protocol, Self

from .bitmap import Bitmap
from .config import Config


class InodeView(Protocol):
    def __len__(self) -> int:
        raise NotImplementedError()

    def __setitem__(self, idx: "slice[None, None, None]", value: ByteString, /):
        raise NotImplementedError()

    def __getitem__(self, idx: "slice[int, int, None]", /) -> ByteString:
        raise NotImplementedError()


class BlockView(Protocol):
    def __iter__(self) -> Iterator[int]:
        raise NotImplementedError()

    def __setitem__(
        self, idx: "slice[int | None, int | None, None]", value: ByteString, /
    ):
        raise NotImplementedError()

    def __getitem__(self, idx: "slice[int | None, int | None, None]", /) -> ByteString:
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
    def reserved_space(self) -> int: ...

    @property
    def closed(self) -> bool: ...
    def close(self) -> None: ...

    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None: ...
