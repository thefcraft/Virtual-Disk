from types import TracebackType
from .inode import Inode, InodeIO, InodeMode
from .protocol import Disk
from .config import Config
from .constants import MAX_NAME_LEN
from .utils import current_time_epoch, ceil_division
from io import SEEK_CUR, SEEK_SET, SEEK_END, BytesIO
from typing import Self, Iterable, NamedTuple, TypeAlias
from enum import Flag, auto


NAME_REPR_LEN: int = ceil_division(MAX_NAME_LEN.bit_length(), 8)
LIST_TREE_TYPE: TypeAlias = list[bytes | tuple[bytes, "LIST_TREE_TYPE"]]

class FileMode(Flag):
    """
    Flag	    Purpose
    READ	    open existing for reading
    WRITE	    open for writing (fails if not exist unless CREATE)
    APPEND	    open for appending
    CREATE	    create if not exist
    EXCLUSIVE	fail if exists and CREATE set
    TRUNCATE	truncate existing file to 0 bytes
    """
    READ     = auto()   # r
    WRITE    = auto()   # w
    APPEND   = auto()   # a
    CREATE    = auto()   # x -> create if not exists
    EXCLUSIVE = auto()   # fail if exists and CREATE set
    TRUNCATE  = auto()   # truncate if exists (like 'w')
    
    # Derived/aliases
    READWRITE = READ | WRITE

class Directory(): # NOTE: may have errors on '..' or '.' so please use abs path...
    """Helper class for directory operations on an Inode"""
    
    class _RawDirEntry(NamedTuple):
        """Represents a directory entry"""
        name: bytes
        inode_ptr: int
    
    class _InodeResult(NamedTuple):
        inode: Inode
        inode_ptr: int
    
    def __init__(self, disk: Disk, inode_ptr: int, inode: Inode):
        if inode.st_mode != InodeMode.DIRECTORY: # NOTE: this will rase error in chdir etc if inode is not a dir
            raise NotADirectoryError(f"{inode.st_mode=} is not a DIRECTORY")
        self.disk: Disk = disk
        self.config: Config = disk.config
        self.inode_ptr: int = inode_ptr
        self.inode_io: InodeIO = InodeIO(
            inode, disk
        )
    
    @classmethod
    def new(cls, disk: Disk, inode_ptr: int, inode: Inode, parent_inode_ptr: int) -> Self:
        new_dir = cls(
            disk, inode_ptr, inode
        )
        new_dir._add_entry(
            name=b'.', inode_ptr=inode_ptr
        )
        new_dir._add_entry(
            name=b'..', inode_ptr=parent_inode_ptr
        )
        new_dir._write_self_inode_back()
        return new_dir
    
    def _write_self_inode_back(self) -> None:
        """Persist the in-memory inode to disk for this directory's inode."""
        self.disk.inodes[self.inode_ptr][:] = self.inode_io.inode.to_bytes(self.config)

    def _iter_entries(self) -> Iterable["Directory._RawDirEntry"]:
        """Iter all entries in the directory"""
        inode_io: InodeIO = self.inode_io
        config: Config = self.disk.config
        
        # read full is more efficient as directory generally have small content
        data: bytes = inode_io.read_at(
            pos=0, n=-1
        )
        offset = 0
        while offset < len(data):
            name_len_bytes = data[offset: offset+1]
            name_len = int.from_bytes(
                name_len_bytes,
                byteorder='big', 
                signed=False
            )
            name = data[offset+1: offset+1+name_len]
            if len(name) != name_len:
                raise ValueError("Insufficient data for name.")
            inode_ptr_bytes = data[
                offset+1+name_len
                : 
                offset+1+name_len+config.inode_addr_length
            ]
            if len(inode_ptr_bytes) != config.inode_addr_length:
                raise ValueError("Insufficient data for inode_ptr.")
            inode_ptr = int.from_bytes(
                inode_ptr_bytes,
                byteorder='big', 
                signed=False
            ) 
            offset += 1+name_len+config.inode_addr_length
            yield self.__class__._RawDirEntry(name, inode_ptr)
    
    def _find_entry(self, name: bytes) -> int | None:
        """Find an entry by name, return inode number or None"""
        entries = self._iter_entries()
        for entry in entries:
            if entry.name == name:
                return entry.inode_ptr
        return None
    
    def _add_entry(self, name: bytes, inode_ptr: int) -> None:
        """Add a new entry to the directory""" 
        if len(name) > MAX_NAME_LEN:
            raise ValueError(f"{len(name)=} can be at max 255.")
            
        inode_io: InodeIO = self.inode_io
        config: Config = self.disk.config
            
        # Serialize the new entry
        entry_data = len(name).to_bytes(
            length=NAME_REPR_LEN,
            byteorder='big', 
            signed=False
        ) + name + inode_ptr.to_bytes(
            length=config.inode_addr_length,
            byteorder='big', 
            signed=False
        )
        
        # Append to the end of directory data
        pos = inode_io.get_size()
        inode_io.write_at(
            pos,
            entry_data
        )
        
    def _remove_entry(self, name: bytes) -> int:
        """Remove an entry from the directory and compact (no fragmentation).
        Returns the inode_ptr of the removed entry.
        """
        inode_io: InodeIO = self.inode_io
        config: Config = self.disk.config
        
        # Parse entries and find the one to remove
        found_entry: "Directory._RawDirEntry | None" = None
        entries: list["Directory._RawDirEntry"] = []
        for entry in self._iter_entries():
            if entry.name != name:
                entries.append(entry)
            else:
                if found_entry is not None:
                    raise RuntimeError(f"Multiple entries with same {name=}")
                found_entry = entry
        if found_entry is None:
            raise FileNotFoundError(f"Entry '{name!r}' not found")
        
        # Build new directory data without the removed entry
        new_data = bytearray()
        
        for entry in entries:
            # Re-serialize each entry (to ensure contiguous data)
            entry_bytes = len(entry.name).to_bytes(
                length=NAME_REPR_LEN,
                byteorder='big', 
                signed=False
            ) + entry.name + entry.inode_ptr.to_bytes(
                length=config.inode_addr_length,
                byteorder='big', 
                signed=False
            )
            new_data.extend(entry_bytes)
        
        # Write the compacted directory data
        inode_io.write_at(
            0,
            bytes(new_data)
        )
        # truncate
        inode_io.truncate_to(len(new_data))
        
        return found_entry.inode_ptr
    

    def get_childs_inode(self, *names: bytes) -> "Directory._InodeResult | None":
        if len(names) == 0: return self.__class__._InodeResult(
            inode_ptr=self.inode_ptr,
            inode=self.inode_io.inode
        )
        *dir_names, last_name = names
        
        current = self
        for name in dir_names:
            if name == b'.': continue
            inode_ptr = current._find_entry(name)
            if inode_ptr is None: return None
            current = Directory(
                disk=self.disk,
                inode_ptr=inode_ptr,
                inode=Inode.from_bytes(
                    self.disk.inodes[inode_ptr], 
                    config=self.config
                )
            )
            
        inode_ptr = current._find_entry(last_name)
        if inode_ptr is None: return None
        return self.__class__._InodeResult(
            inode_ptr=inode_ptr,
            inode=Inode.from_bytes(
                self.disk.inodes[inode_ptr], 
                config=self.config
            )
        )
     
    def listdir(self, ignore_default: bool = True) -> list[bytes]:
        it = self._iter_entries()
        if ignore_default:
            it = filter(
                lambda entry: not (entry.name == b'.' or entry.name == b'..'),
                it
            )
        return list(map(
            lambda entry: entry.name, 
            it
        ))
    
    def listtree(self, ignore_default: bool = True) -> LIST_TREE_TYPE:
        result: LIST_TREE_TYPE = []
        for entry in self._iter_entries():
            if entry.name == b'.' or entry.name == b'..': 
                if not ignore_default: result.append(entry.name)
                continue
            inode = Inode.from_bytes(
                self.disk.inodes[entry.inode_ptr],
                self.config
            )
            if inode.st_mode == InodeMode.DIRECTORY:
                directory = Directory(
                    self.disk, entry.inode_ptr, inode
                )
                result.append((
                    entry.name,
                    directory.listtree(ignore_default=ignore_default)
                ))
            else:
                result.append(entry.name)
        return result
    
    def mkdir(self, name: bytes, exist_ok: bool = False) -> "Directory":
        # Check if name already exists
        inode_ptr = self._find_entry(name)
        if inode_ptr is not None:
            if exist_ok:
                return Directory(
                    disk=self.disk, 
                    inode_ptr=inode_ptr,
                    inode=Inode.from_bytes(
                        self.disk.inodes[inode_ptr], config=self.config
                    )
                )
            raise FileExistsError(f"Entry '{name!r}' already exists") 
        inode_ptr = self.disk.inodes_bitmap.find_and_flip_free()
        inode = Inode(
            InodeMode.DIRECTORY
        )
        self._add_entry(
            name=name, inode_ptr=inode_ptr
        )
        self._write_self_inode_back()
        return Directory.new(
            disk=self.disk, 
            inode=inode, 
            inode_ptr=inode_ptr,
            parent_inode_ptr=self.inode_ptr
        )
        
    def makedirs(self, *names: bytes, exist_ok: bool = False) -> "Directory":
        name, *rest = names
        if not rest: return self.mkdir(name, exist_ok=exist_ok)
        child = self.mkdir(name, exist_ok=True)
        return child.makedirs(*rest, exist_ok=exist_ok)

    def chdir(self, *names: bytes) -> "Directory":
        current = self
        for name in names:
            if name == b'.': continue
            inode_ptr = current._find_entry(name)
            if inode_ptr is None:
                raise FileNotFoundError(f"Directory '{name!r}' not exists")
            current = Directory(
                disk=self.disk,
                inode_ptr=inode_ptr,
                inode=Inode.from_bytes(
                    self.disk.inodes[inode_ptr], 
                    config=self.config
                )
            )
        return current

    def remove(self, name: bytes, removed_ok: bool = False, *, inode_ptr: int | None = None) -> None:
        if inode_ptr is None:
            inode_ptr = self._find_entry(name)
            if inode_ptr is None:
                if removed_ok: return None
                raise FileNotFoundError(f"File '{name!r}' not exists") 
        inode = Inode.from_bytes(
            self.disk.inodes[inode_ptr], config=self.config
        )
        if inode.st_mode == InodeMode.DIRECTORY:
            raise IsADirectoryError(f"{name=} is a DIRECTORY")
        inode_io = InodeIO(inode, self.disk)
        inode_io.truncate_to(0)
        self.disk.inodes_bitmap.clear(inode_ptr)
        inode_ptr_removed = self._remove_entry(name)
        if inode_ptr != inode_ptr_removed:
            raise RuntimeError(f"mismatched removed inode pointer, {inode_ptr=} but removed {inode_ptr_removed=}.")
        self._write_self_inode_back()
    
    def rmdir(self, dir_name: bytes) -> None:
        if dir_name == b'.' or dir_name == b'..':
            raise ValueError(f"{dir_name=} can't be self or parent")
        child = self.chdir(dir_name)
        if len(child.listdir(ignore_default=False)) > 2: # [b'.', b'..']
            raise OSError(f"Directory {dir_name=} not empty.")
        child._remove_entry(b'.')
        child._remove_entry(b'..')
        if child.inode_io.get_size() != 0:
            raise RuntimeError(f"Something went wrong, {child.inode_io.get_size()=} is not zero.")
        # child.inode_io.truncate_to(0)
        self.disk.inodes_bitmap.clear(child.inode_ptr)
        
        inode_ptr_removed = self._remove_entry(dir_name)
        if child.inode_ptr != inode_ptr_removed:
            raise RuntimeError(f"mismatched removed inode pointer, {child.inode_ptr=} but removed {inode_ptr_removed=}.")
        self._write_self_inode_back()
    
    def removedirs(self, *names: bytes) -> None:
        name, *rest = names
        if not rest: return self.rmdir(name)
        child = self.chdir(name)
        child.removedirs(*rest)
        return self.rmdir(name)
    
    def rename(self, src: list[bytes], dest: list[bytes], *, overwrite: bool = False) -> None:
        *src_dir_names, src_name = src
        *dest_dir_names, dest_name = dest
        
        src_dir = self.chdir(*src_dir_names)
        dest_dir = self.chdir(*dest_dir_names)
        
        inode_ptr = src_dir._find_entry(src_name)
        if inode_ptr is None: 
            raise FileNotFoundError(f"{src=} path not exists.")
        inode = Inode.from_bytes(
            self.disk.inodes[inode_ptr], 
            config=self.config
        )
        
        if overwrite:
            dest_dir.remove(dest_name, removed_ok=True) # NOTE: can raise IsADirectoryError
        elif dest_dir._find_entry(dest_name) is not None:
            raise FileExistsError(f'{dest=} path already exists.')
        
        if inode.st_mode == InodeMode.DIRECTORY: 
            directory = src_dir.chdir(src_name)
            directory._remove_entry(b'..')
            directory._add_entry(b'..', dest_dir.inode_ptr)
        
        inode_ptr_removed = src_dir._remove_entry(src_name)
        if inode_ptr != inode_ptr_removed:
            raise RuntimeError(f"mismatched removed inode pointer, {inode_ptr=} but removed {inode_ptr_removed=}.")
        dest_dir._add_entry(dest_name, inode_ptr)
        
        dest_dir._write_self_inode_back()
        src_dir._write_self_inode_back()

    def copy_file(self, src: list[bytes], dest: list[bytes], overwrite: bool = False, chunk_size: int | None = None) -> None:
        *src_dir_names, src_name = src
        *dest_dir_names, dest_name = dest
        
        src_dir = self.chdir(*src_dir_names)
        dest_dir = self.chdir(*dest_dir_names)
        
        if overwrite:
            dest_dir.remove(dest_name, removed_ok=True) # NOTE: can raise IsADirectoryError
            
        with (
            dest_dir.open(dest_name, mode=FileMode.CREATE | FileMode.WRITE | FileMode.EXCLUSIVE) as dest_file, 
            src_dir.open(src_name, mode=FileMode.READ) as src_file
        ):
            while data := src_file.read(size=chunk_size):
                dest_file.write(data)
                dest_file.flush()
    
    def rm_tree(self, dir_name: bytes):
        if dir_name == b'.' or dir_name == b'..':
            raise ValueError(f"{dir_name=} can't be self or parent")
        child = self.chdir(dir_name)
        for entry in child._iter_entries():
            if entry.name == b'.' or entry.name == b'..': continue
            inode = Inode.from_bytes(
                self.disk.inodes[entry.inode_ptr], config=self.config
            )
            if inode.st_mode == InodeMode.DIRECTORY:
                child.rm_tree(dir_name=entry.name)
            else:
                child.remove(name=entry.name, inode_ptr=entry.inode_ptr)
        child.inode_io.truncate_to(0)
        if child.inode_io.get_size() != 0:
            raise RuntimeError(f"Something went wrong, {child.inode_io.get_size()=} is not zero.")
        self.disk.inodes_bitmap.clear(child.inode_ptr)
        
        inode_ptr_removed = self._remove_entry(dir_name)
        if child.inode_ptr != inode_ptr_removed:
            raise RuntimeError(f"mismatched removed inode pointer, {child.inode_ptr=} but removed {inode_ptr_removed=}.")
        self._write_self_inode_back()
    
    def copy_tree(self, src: list[bytes], dest: list[bytes], overwrite: bool = False, chunk_size: int | None = None) -> None:
        *dest_dir_names, dest_dir_name = dest
       
        src_dir = self.chdir(*src)
        dest_parent_dir = self.chdir(*dest_dir_names)
        dest_dir = dest_parent_dir.mkdir(dest_dir_name, exist_ok=True)
        
        def copy_tree_recursive(src_dir: "Directory", dest_dir: "Directory"):
            for entry in src_dir._iter_entries():
                if entry.name == b'.' or entry.name == b'..': continue
                inode = Inode.from_bytes(
                    self.disk.inodes[entry.inode_ptr], config=self.config
                )
                if inode.st_mode == InodeMode.DIRECTORY:
                    new_src_dir = Directory(
                        disk=self.disk,
                        inode_ptr=entry.inode_ptr,
                        inode=inode
                    )
                    new_dest_dir = dest_dir.mkdir(entry.name, exist_ok=True)
                    copy_tree_recursive(
                        src_dir=new_src_dir,
                        dest_dir=new_dest_dir
                    )
                else:
                    if overwrite:
                        dest_dir.remove(entry.name, removed_ok=True) # NOTE: can raise IsADirectoryError
                    with (
                        dest_dir.open(entry.name, mode=FileMode.CREATE | FileMode.WRITE | FileMode.EXCLUSIVE) as dest_file, 
                        src_dir.open(entry.name, mode=FileMode.READ) as src_file
                    ):
                        while data := src_file.read(size=chunk_size):
                            dest_file.write(data)
        copy_tree_recursive(
            src_dir=src_dir,
            dest_dir=dest_dir
        )
        
    def exists(self, *names: bytes) -> bool:
        *dir_names, last_name = names
        try: 
            current = self.chdir(*dir_names)
        except FileNotFoundError: return False
        return current._find_entry(last_name) is not None
    
    def isdir(self, *names: bytes) -> bool | None:
        result = self.get_childs_inode(*names)
        if result is None: return None
        return result.inode.st_mode == InodeMode.DIRECTORY
    def isfile(self, *names: bytes) -> bool | None:
        result = self.get_childs_inode(*names)
        if result is None: return None
        return result.inode.st_mode == InodeMode.REGULAR_FILE
    
    def create_empty_file(self, name: bytes) -> "Directory._InodeResult":
        inode_ptr = self.disk.inodes_bitmap.find_and_flip_free()
        inode = Inode(
            InodeMode.REGULAR_FILE
        )
        self.disk.inodes[inode_ptr][:] = inode.to_bytes(self.config)
        self._add_entry(name, inode_ptr)
        self._write_self_inode_back()
        return self.__class__._InodeResult(
            inode=inode,
            inode_ptr=inode_ptr
        )
    def open(self, name: bytes, mode: FileMode = FileMode.READ) -> "FileIO":
        # TODO: prevend from opening same file multiple times maybe raise error, may need global state?
        inode_ptr = self._find_entry(name)
        if inode_ptr is None:
            if not mode & FileMode.CREATE: 
                raise FileNotFoundError(f"File '{name.decode()}' not found (no CREATE flag).")
            if mode & (FileMode.WRITE | FileMode.APPEND):
                result = self.create_empty_file(name)
                inode_ptr = result.inode_ptr
                inode = result.inode
            else: raise FileNotFoundError(f"File '{name.decode()}' not found.")
        elif (mode & FileMode.CREATE) and (mode & FileMode.EXCLUSIVE):
            raise FileExistsError(f"File '{name.decode()}' already exists")
        else:
            inode = Inode.from_bytes(
                self.disk.inodes[inode_ptr], 
                config=self.config
            )
            if inode.st_mode != InodeMode.REGULAR_FILE:
                raise IsADirectoryError(f"'{name=}' is not a file.")
        return FileIO(self.disk, inode_ptr=inode_ptr, inode=inode, mode=mode)

class FileIO(BytesIO):
    """Helper class for directory operations on an Inode"""
    
    class _PseudoMemview:
        """For wsgidav compatibility - only needs .nbytes."""
        def __init__(self, size: int): self._size = size
        @property
        def nbytes(self) -> int: return self._size     
    
    def __init__(self, disk: Disk, inode_ptr: int, inode: Inode, mode: FileMode = FileMode.READWRITE):
        if inode.st_mode != InodeMode.REGULAR_FILE:
            raise IsADirectoryError(f"{inode.st_mode=} is not a REGULAR_FILE")
        self.inode_ptr: int = inode_ptr
        self.disk = disk
        self.config = disk.config
        self.inode_io: InodeIO = InodeIO(
            inode, disk
        )
        self._closed: bool = False
        
        self._readable = bool(mode & FileMode.READ)
        self._writable = bool(mode & (FileMode.WRITE | FileMode.APPEND))
        self._append = bool(mode & FileMode.APPEND)
        self._truncate_on_open = bool(mode & FileMode.TRUNCATE)
        
        if self._truncate_on_open: # truncate underlying inode to 0
            self.inode_io.truncate_to(0)
            self.inode_io.inode.st_mtime = current_time_epoch()
            self._pos = 0
        elif self._append: # start at EOF
            self._pos = self.inode_io.get_size()
        else:
            self._pos = 0
    
    @property
    def closed(self) -> bool: return self._closed
    def close(self): 
        if self._closed: return
        self.disk.inodes[self.inode_ptr][:] = self.inode_io.inode.to_bytes(self.config)
        self._closed = True
        
    def seekable(self) -> bool: return True
    def readable(self) -> bool: return self._readable
    def writable(self) -> bool: return self._writable
    def tell(self) -> int: return self._pos
    
    def seek(self, offset: int, whence: int = 0) -> int:
        """Seek to a position in the file"""
        if self._closed: raise ValueError("I/O operation on closed file")
        
        inode: Inode = self.inode_io.inode
        
        if whence == SEEK_SET: new_pos = offset
        elif whence == SEEK_CUR: new_pos = self._pos + offset
        elif whence == SEEK_END: new_pos = inode.st_size + offset
        else: raise ValueError(f"Invalid whence value: {whence}")
        
        # Allow seeking beyond EOF (standard file behavior)
        if new_pos < 0: raise ValueError("Negative seek position")
    
        self._pos = new_pos
        return self._pos
    
    def truncate(self, size: int | None = None) -> int: 
        """Truncate file to given size"""
        if self._closed: raise ValueError("I/O operation on closed file")
        if not self.writable(): raise IOError("File not open for writing")

        inode: Inode = self.inode_io.inode
        
        if size is None: size = self._pos
        if size < 0: raise ValueError("Negative truncate size")
        
        self.inode_io.truncate_to(size)
        inode.st_mtime = current_time_epoch()
        
        if self._pos > inode.st_size:
            self._pos = inode.st_size
            
        return inode.st_size
    
    def read(self, size: int | None = -1) -> bytes:
        """Read up to size bytes from the file at current position"""
        if self._closed: raise ValueError("I/O operation on closed file")
        if not self.readable(): raise IOError("File not open for reading")
        if size is None: size = -1
        
        data = self.inode_io.read_at(self._pos, size)
        self._pos += len(data)
        return data
    
    def write(self, buffer: bytes) -> int: # type: ignore[override]
        if self._closed: raise ValueError("I/O operation on closed file")
        if not self.writable(): raise IOError("File not open for writing")
        
        if self._append: # append mode: always write at EOF
            self._pos = self.inode_io.get_size()

        written = self.inode_io.write_at(self._pos, buffer)
        self._pos += written
        self.inode_io.inode.st_mtime = current_time_epoch()
        return written
    
    def getbuffer(self) -> "FileIO._PseudoMemview": # type: ignore[override]
        return self.__class__._PseudoMemview(
            size = self.inode_io.get_size()
        ) # just have .nbytes property
    
    def writelines(self, lines: Iterable[bytes]): # type: ignore[override]
        for line in lines:
            self.write(line)
    
    def flush(self):
        """Force all pending data to be written to disk."""
        if self._closed:
            raise ValueError("I/O operation on closed file")
        # ensure inode is persisted
        self.disk.inodes[self.inode_ptr][:] = self.inode_io.inode.to_bytes(self.config)

       
    def __repr__(self) -> str:
        inode: Inode = self.inode_io.inode
        return (f"<FileIO inode={inode} pos={self._pos} "
                f"size={inode.st_size} closed={self._closed}>")

    def __enter__(self) -> Self: 
        if self.closed:
            raise ValueError("I/O operation on closed file")
        return self
    def __exit__(self, 
                 exc_type: type[BaseException] | None, 
                 exc_val: BaseException | None, 
                 exc_tb: TracebackType | None) -> None:
        # persist and close; let exceptions propagate
        self.close()
        return None

