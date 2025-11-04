from .utils import current_time_epoch, ceil_division, floor_division
from .config import Config
from .protocol import Disk, BlockView, InodeView
from .constants import TYPE_NULL_PTR, NULL_PTR, NULL_BYTES, NUM_DIRECT_PTR, EPOCH_TIME_BYTES
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Self, Iterable, SupportsBytes, cast, overload
from itertools import islice

class InodeMode(Enum):
    REGULAR_FILE = auto()
    DIRECTORY = auto()
    # SYMBOLIC_LINK = auto()
    
@dataclass(frozen=False)
class Inode:
    st_mode: InodeMode
    st_size: int = 0 
    st_mtime: int = field(default_factory=current_time_epoch) # Modification time
    st_ctime: int = field(default_factory=current_time_epoch) # Metadata change
    directs: list[int | TYPE_NULL_PTR] = field(
        default_factory=lambda: list([NULL_PTR] * NUM_DIRECT_PTR)
    ) 
    indirect: int | TYPE_NULL_PTR = NULL_PTR # pointer to block of block pointers
    double_indirect: int | TYPE_NULL_PTR = NULL_PTR # pointer to block of indirect blocks
    triple_indirect: int | TYPE_NULL_PTR = NULL_PTR # pointer to block of double_indirect blocks
    
    @classmethod
    def from_bytes(cls, data: InodeView, config: Config) -> Self:
        if len(data) != config.inode_size:
            raise ValueError(f"{len(data)=} must be {config.inode_size}.")
        
        address_length: int = config.block_addr_length
        max_file_size_length: int = config.max_file_size_length
        
        offset: int = 0
        st_mode = int.from_bytes(
            data[offset:offset+1], byteorder="big", signed=False
        )
        offset += 1
        st_size = int.from_bytes(
            data[offset:offset+max_file_size_length], byteorder="big", signed=False
        )
        offset += max_file_size_length
        st_mtime = int.from_bytes(
            data[offset:offset+EPOCH_TIME_BYTES], byteorder="big", signed=False
        )
        offset += EPOCH_TIME_BYTES
        st_ctime = int.from_bytes(
            data[offset:offset+EPOCH_TIME_BYTES], byteorder="big", signed=False
        )
        offset += EPOCH_TIME_BYTES
        directs = [
            int.from_bytes(
                data[offset+i*address_length:offset+i*address_length+address_length],
                byteorder="big", signed=False
            ) for i in range(NUM_DIRECT_PTR)
        ]
        offset += NUM_DIRECT_PTR * address_length
        indirect = int.from_bytes(
            data[offset:offset+address_length],
            byteorder="big", signed=False
        )
        offset += address_length
        double_indirect = int.from_bytes(
            data[offset:offset+address_length],
            byteorder="big", signed=False
        )
        offset += address_length
        triple_indirect = int.from_bytes(
            data[offset:offset+address_length],
            byteorder="big", signed=False
        )
        # offset += NUM_DIRECT_PTR * address_length
        return cls(
            InodeMode(st_mode),
            st_size,
            st_mtime,
            st_ctime,
            directs,
            indirect,
            double_indirect,
            triple_indirect
        )
         
    def to_bytes(self, config: Config) -> bytes:
        address_length: int = config.block_addr_length
        max_file_size_length: int = config.max_file_size_length
        
        header = self.st_mode.value.to_bytes(
            length=1, byteorder="big", signed=False
        ) + self.st_size.to_bytes(
            length=max_file_size_length, byteorder="big", signed=False
        ) + self.st_mtime.to_bytes(
            length=EPOCH_TIME_BYTES, byteorder="big", signed=False
        ) + self.st_ctime.to_bytes(
            length=EPOCH_TIME_BYTES, byteorder="big", signed=False
        )
        data = header + (
            b''.join(
              direct.to_bytes(length=address_length, byteorder="big", signed=False)  
              for direct in self.directs
            ) + 
            self.indirect.to_bytes(length=address_length, byteorder="big", signed=False) + 
            self.double_indirect.to_bytes(length=address_length, byteorder="big", signed=False) +
            self.triple_indirect.to_bytes(length=address_length, byteorder="big", signed=False)
        )
        return data + NULL_BYTES * (
            config.inode_size - len(data) # -ve means b''
        )
     
class InodeIO:
    def __init__(self, inode: Inode, disk: Disk) -> None: 
        self.inode: Inode = inode
        self.disk: Disk = disk
    
    # --- Random-access primitives ---
    def read_at(self, pos: int, n: int = -1) -> bytes:
        """Read up to n bytes starting at pos. If n==-1, read to EOF."""
        inode: Inode = self.inode
        disk: Disk = self.disk
        config: Config = disk.config
        
        if pos < 0: raise ValueError("negative read position")
        if pos >= inode.st_size: return b""
        
        if n < 0: n = inode.st_size - pos
        else: n = min(n, inode.st_size - pos)
        
        start_block_idx, start_block_off = divmod(pos, config.block_size)
        end_block_idx, end_block_off = divmod(pos+n, config.block_size)
        out = bytearray()
        blocks = islice(
            self.iteritem(), 
            start_block_idx, 
            end_block_idx + bool(end_block_off)
        )
        try: 
            start_block = disk.blocks[next(blocks)]
        except StopIteration: 
            raise RuntimeError(f"Something went wrong...")
        out.extend(start_block[start_block_off:])
        
        for block_ptr in blocks:
            out.extend(disk.blocks[block_ptr])
        if len(out) < n: 
            raise RuntimeError(f"Something went wrong, {len(out)=}.")
        return bytes(out[:n])
        
    def write_at(self, pos: int, data: bytes) -> int:
        """Write data starting at pos. Returns number of bytes written."""
        inode: Inode = self.inode
        disk: Disk = self.disk
        config: Config = disk.config
        
        if pos < 0: raise ValueError("negative read position")
        if pos > inode.st_size: 
            # NOTE: as block may not be empty, may have garbage data so please fill with NULL_BYTES
            self.write_at(inode.st_size, NULL_BYTES * (pos-inode.st_size))
        if not data: return 0
    
        start_block_idx, start_block_off = divmod(pos, config.block_size)
        
        remaining: int = len(data)
        src_off: int = 0
        
        try: 
            blocks = islice(
                self.iteritem(), 
                start_block_idx, 
                None
            )
            to_write = min(config.block_size - start_block_off, remaining)
            start_block = disk.blocks[next(blocks)]
            start_block[start_block_off:start_block_off+to_write] = data[:to_write]
            src_off += to_write
            remaining -= to_write
            while remaining > 0:
                to_write = min(config.block_size, remaining)
                block = disk.blocks[next(blocks)]
                block[:to_write] = data[src_off:src_off + to_write]
                src_off += to_write
                remaining -= to_write
            pos += src_off
            if pos > inode.st_size:
                inode.st_size = pos
            return src_off
        except StopIteration: 
            pos += src_off
            inode.st_size = pos # NOTE: no need to check `if pos > inode.st_size:` as it always true as if we need more block => need to store larger file
        while remaining > 0:
            to_write = min(config.block_size, remaining)
            block_ptr = self._allocate_block(st_size=pos + src_off)
            block = disk.blocks[block_ptr]
            block[:to_write] = data[src_off:src_off + to_write]
            src_off += to_write
            remaining -= to_write
        inode.st_size = pos + src_off
        return src_off
        
    def iteritem(self) -> Iterable[int]:
        inode: Inode = self.inode
        disk: Disk = self.disk
        config: Config = disk.config
        
        # |--------------------------- DIRECT ---------------------------|
        for direct in inode.directs:
            if direct == NULL_PTR: return None
            yield direct
            
        # |--------------------------- INDIRECT ---------------------------|
        if inode.indirect == NULL_PTR: return None
        
        def iter_ptr_from_indirect_recursive(
            indirect: int | TYPE_NULL_PTR, 
            recursive_depth: int = 1
        ) -> Iterable[int]:
            if indirect == NULL_PTR: return None
            if recursive_depth <= 0: raise ValueError(f"{recursive_depth=} must be positive.")
            data: BlockView
            off: int
            if recursive_depth == 1: 
                data = disk.blocks[indirect]
                for idx in range(config.num_inode_addr_per_block):
                    off = idx * config.block_addr_length
                    ptr = int.from_bytes(
                        data[off: off + config.block_addr_length], 
                        byteorder='big', 
                        signed=False
                    )
                    if ptr == NULL_PTR: return None
                    yield ptr
                return None
            data = disk.blocks[indirect]
            for idx in range(config.num_inode_addr_per_block):
                off = idx * config.block_addr_length
                child_ptr: int | TYPE_NULL_PTR = int.from_bytes(
                    data[off: off + config.block_addr_length], 
                    byteorder='big', 
                    signed=False
                )
                yield from iter_ptr_from_indirect_recursive(
                    indirect=child_ptr, 
                    recursive_depth=recursive_depth-1
                )
        
        yield from iter_ptr_from_indirect_recursive(
            inode.indirect, recursive_depth=1
        )
        
        # |--------------------------- DOUBLE INDIRECT ---------------------------|
        if inode.double_indirect == NULL_PTR: return None
        yield from iter_ptr_from_indirect_recursive(
            inode.double_indirect, recursive_depth=2
        )
        
        # |--------------------------- TRIPLE INDIRECT ---------------------------|
        if inode.triple_indirect == NULL_PTR: return None
        yield from iter_ptr_from_indirect_recursive(
            inode.triple_indirect, recursive_depth=3
        )
    
    def getitem(self, idx: int) -> int | TYPE_NULL_PTR: 
        inode: Inode = self.inode
        disk: Disk = self.disk
        config: Config = disk.config
        
        if idx < 0:
            raise IndexError(f"{idx=} is negative, use new_idx = (self.getlen()-{idx}).")
        
        # |--------------------------- DIRECT ---------------------------|        
        if idx < NUM_DIRECT_PTR:
            return inode.directs[idx]
        
        # |--------------------------- INDIRECT ---------------------------|
        idx -= NUM_DIRECT_PTR
        
        def get_ptr_from_indirect_recursive(idx: int, indirect: int | TYPE_NULL_PTR, recursive_depth: int = 1) -> int | TYPE_NULL_PTR:
            if indirect == NULL_PTR: return NULL_PTR
            if recursive_depth <= 0: raise ValueError(f"{recursive_depth=} must be positive.")
            if recursive_depth == 1: 
                off: int = idx * config.block_addr_length
                return int.from_bytes(
                    disk.blocks[indirect][off: off + config.block_addr_length], 
                    byteorder='big', 
                    signed=False
                )
            elif recursive_depth == 2: num_inode_addr_per_block = config.num_inode_addr_per_block
            elif recursive_depth == 3: num_inode_addr_per_block = config.num_inode_addr_double_range
            else: raise ValueError(f"{recursive_depth=} not supported.")
            
            idx_lvl1 = idx // num_inode_addr_per_block
            idx_lvl2 = idx % num_inode_addr_per_block
            
            off_lvl1 = idx_lvl1 * config.block_addr_length
            
            ptr_lvl1 = int.from_bytes(
                disk.blocks[indirect][off_lvl1: off_lvl1 + config.block_addr_length], 
                byteorder='big', 
                signed=False
            )
            return get_ptr_from_indirect_recursive(idx=idx_lvl2, indirect=ptr_lvl1, recursive_depth=recursive_depth-1)
            
        if idx < config.num_inode_addr_per_block:
            return get_ptr_from_indirect_recursive(idx=idx, indirect=inode.indirect, recursive_depth=1)
            
        # |--------------------------- DOUBLE INDIRECT ---------------------------|
        idx -= config.num_inode_addr_per_block
        if idx < config.num_inode_addr_double_range:
            return get_ptr_from_indirect_recursive(idx=idx, indirect=inode.double_indirect, recursive_depth=2)
        
        # |--------------------------- TRIPLE INDIRECT ---------------------------|
        idx -= config.num_inode_addr_double_range
        if idx < config.num_inode_addr_triple_range:
            return get_ptr_from_indirect_recursive(idx=idx, indirect=inode.triple_indirect, recursive_depth=3)
        
        idx += (
            NUM_DIRECT_PTR + config.num_inode_addr_per_block + 
            config.num_inode_addr_double_range
        )
        range = (
            NUM_DIRECT_PTR + config.num_inode_addr_per_block + 
            config.num_inode_addr_double_range + 
            config.num_inode_addr_triple_range
        )
        raise IndexError(f"{idx=} is out of {range=}.")
    
    def truncate_to(self, st_size: int = 0):
        block_required = ceil_division(st_size, self.disk.config.block_size)
        self._truncate_block_to(
            block_required
        )
        self.inode.st_size = st_size
    
    
    def get_size(self) -> int: return self.inode.st_size
    
    # --- Private primitives ---
    def _setitem(self, idx: int, value: int) -> None:
        inode: Inode = self.inode
        disk: Disk = self.disk
        config: Config = disk.config
        
        if value == NULL_PTR:
            raise ValueError(f"{value=} can't be NULL_PTR please use self.truncate(block_required={idx}).")
        
        if idx < 0:
            raise IndexError(f"{idx=} is negative, use new_idx = (self.getlen()-{idx}).")
        
        # |--------------------------- DIRECT ---------------------------|        
        if idx < NUM_DIRECT_PTR:
            inode.directs[idx] = value
            return None
        
        # |--------------------------- INDIRECT ---------------------------|
        idx -= NUM_DIRECT_PTR
        
        def set_ptr_from_indirect_recursive(idx: int, indirect: int | TYPE_NULL_PTR, recursive_depth: int = 1) -> None:
            if recursive_depth <= 0: raise ValueError(f"{recursive_depth=} must be positive.")
            
            if indirect == NULL_PTR: 
                indirect = disk.blocks_bitmap.find_and_flip_free()
                disk.blocks[indirect][:] = NULL_BYTES * config.block_size
                if recursive_depth == 1: inode.indirect = indirect
                elif recursive_depth == 2: inode.double_indirect = indirect
                elif recursive_depth == 3: inode.triple_indirect = indirect
                else: raise ValueError(f"{recursive_depth=} not supported.")
                
            if recursive_depth == 1: 
                off: int = idx * config.block_addr_length
                disk.blocks[indirect][off: off + config.block_addr_length] = value.to_bytes(
                    length=config.block_addr_length,
                    byteorder='big', 
                    signed=False
                )
                return None
            elif recursive_depth == 2: num_inode_addr_per_block = config.num_inode_addr_per_block
            elif recursive_depth == 3: num_inode_addr_per_block = config.num_inode_addr_double_range
            else: raise ValueError(f"{recursive_depth=} not supported.")
            
            idx_lvl1 = idx // num_inode_addr_per_block
            idx_lvl2 = idx % num_inode_addr_per_block
            
            off_lvl1 = idx_lvl1 * config.block_addr_length
            
            ptr_lvl1 = int.from_bytes(
                disk.blocks[indirect][off_lvl1: off_lvl1 + config.block_addr_length], 
                byteorder='big', 
                signed=False
            )
            if ptr_lvl1 == NULL_PTR:
                child_ptr = self.disk.blocks_bitmap.find_and_flip_free()
                disk.blocks[child_ptr][:] = NULL_BYTES * config.block_size
                # store the child's pointer into the parent index block slot
                disk.blocks[indirect][off_lvl1: off_lvl1 + config.block_addr_length] = child_ptr.to_bytes(
                    length=config.block_addr_length,
                    byteorder='big',
                    signed=False
                )
                ptr_lvl1 = child_ptr
            return set_ptr_from_indirect_recursive(idx=idx_lvl2, 
                                                   indirect=ptr_lvl1, 
                                                   recursive_depth=recursive_depth-1)
            
        if idx < config.num_inode_addr_per_block:
            return set_ptr_from_indirect_recursive(idx=idx, 
                                                   indirect=inode.indirect, 
                                                   recursive_depth=1)
            
        # |--------------------------- DOUBLE INDIRECT ---------------------------|
        idx -= config.num_inode_addr_per_block
        
        if idx < config.num_inode_addr_double_range:
            return set_ptr_from_indirect_recursive(idx=idx, 
                                                   indirect=inode.double_indirect, 
                                                   recursive_depth=2)
        
        # |--------------------------- TRIPLE INDIRECT ---------------------------|
        idx -= config.num_inode_addr_double_range

        if idx < config.num_inode_addr_triple_range:
            return set_ptr_from_indirect_recursive(idx=idx, 
                                                   indirect=inode.triple_indirect, 
                                                   recursive_depth=3)
        
        idx += (
            NUM_DIRECT_PTR + config.num_inode_addr_per_block + 
            config.num_inode_addr_double_range
        )
        range = (
            NUM_DIRECT_PTR + config.num_inode_addr_per_block + 
            config.num_inode_addr_double_range + 
            config.num_inode_addr_triple_range
        )
        raise IndexError(f"{idx=} is out of {range=}.")
    
    def _allocate_block(self, st_size: int | None = None) -> int:
        """
        Allocate a new DATA block and return its block address (index).
        This will create pointer/indirection blocks as needed (single/double/triple).
        """
        disk: Disk = self.disk
        if st_size is None:
            st_size = self.inode.st_size
        
        block_ptr = disk.blocks_bitmap.find_and_flip_free()
        self._setitem(
            idx=ceil_division(st_size, self.disk.config.block_size), 
            value=block_ptr
        )
        return block_ptr
        
    def _truncate_block_to(self, block_required: int = 0) -> int: # TODO: handle inode.st_size later
        """
        dealloc blocks and return num blocks which are deallocated and 
        return -ve value if block_required is greater then current blocks.
        """
        inode: Inode = self.inode
        disk: Disk = self.disk
        config: Config = disk.config
        
        for idx in range(NUM_DIRECT_PTR):
            ptr = inode.directs[idx]
            if ptr == NULL_PTR: return -block_required
            if block_required <= 0: 
                disk.blocks_bitmap.clear(ptr)
                inode.directs[idx] = NULL_PTR
            block_required -= 1
        
        # |--------------------------- INDIRECT ---------------------------|
        if inode.indirect == NULL_PTR: return -block_required
        
        def truncate_indirect_recursive(
            indirect: int, 
            recursive_depth: int = 1,
        ) -> bool:
            nonlocal block_required
            if indirect == NULL_PTR: raise ValueError(f"{indirect=} must not be NULL_PTR.")
            if recursive_depth <= 0: raise ValueError(f"{recursive_depth=} must be positive.")
            data: BlockView
            off: int
            is_empty: bool
            if recursive_depth == 1: 
                data = disk.blocks[indirect]
                is_empty = True
                for idx in range(config.num_inode_addr_per_block):
                    off = idx * config.block_addr_length
                    ptr = int.from_bytes(
                        data[off: off + config.block_addr_length], 
                        byteorder='big', 
                        signed=False
                    )
                    if ptr == NULL_PTR: return is_empty
                    if block_required <= 0: 
                        disk.blocks_bitmap.clear(ptr)
                        data[off: off + config.block_addr_length] = NULL_BYTES * config.block_addr_length                        
                    else: is_empty = False
                    block_required -= 1
                return is_empty
            
            data = disk.blocks[indirect]
            is_empty = True
            for idx in range(config.num_inode_addr_per_block):
                off = idx * config.block_addr_length
                child_ptr: int | TYPE_NULL_PTR = int.from_bytes(
                    data[off: off + config.block_addr_length], 
                    byteorder='big', 
                    signed=False
                )
                if child_ptr == NULL_PTR: return is_empty
                child_is_empty = truncate_indirect_recursive(
                    indirect=child_ptr, 
                    recursive_depth=recursive_depth-1
                )
                if child_is_empty:
                    disk.blocks_bitmap.clear(child_ptr)
                    data[off: off + config.block_addr_length] = NULL_BYTES * config.block_addr_length                        
                else: is_empty = False
            return is_empty
        
        if truncate_indirect_recursive(
            inode.indirect, recursive_depth=1
        ):
            disk.blocks_bitmap.clear(inode.indirect)
            inode.indirect = NULL_PTR
            
         # |--------------------------- DOUBLE INDIRECT ---------------------------|
        if inode.double_indirect == NULL_PTR: return -block_required
        if truncate_indirect_recursive(
            inode.double_indirect, recursive_depth=2
        ):
            disk.blocks_bitmap.clear(inode.double_indirect)
            inode.double_indirect = NULL_PTR
        
        # |--------------------------- TRIPLE INDIRECT ---------------------------|
        if inode.triple_indirect == NULL_PTR: return -block_required
        if truncate_indirect_recursive(
            inode.triple_indirect, recursive_depth=3
        ):
            disk.blocks_bitmap.clear(inode.triple_indirect)
            inode.triple_indirect = NULL_PTR
        return -block_required

