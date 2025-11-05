from .infile import  (
    InFileDisk,
    load_config_from_file,
    BitmapFile,
    ceil_division,
    InodesList,
    BlocksList,
    Inode,
    Directory,
    dump_bitmap,
    dump_config,
    InodeMode,
    NULL_BYTES,
    InFileDiskType
)
from .crypto import EncryptorProtocol, DecryptorProtocol, HkdfHmac
from .crypto import CipherChaCha20Encryptor, CipherChaCha20Decryptor

from types import TracebackType
from typing import Self, BinaryIO, ByteString
from src.config import Config

from io import BytesIO
import os
    
# NOTE: any other type of disk must have first bit not equal to zero as for raw infile disk first bit is NULL

class EncryptedBytesIOWrapper(BytesIO):
    def __init__(self, 
                 encryptor: EncryptorProtocol, 
                 decryptor: DecryptorProtocol, 
                 file: BinaryIO, 
                 auto_close: bool = False) -> None:
        self.file: BinaryIO = file
        self.encryptor: EncryptorProtocol = encryptor
        self.decryptor: DecryptorProtocol = decryptor
        self.auto_close: bool = auto_close
        self._closed: bool = False
        self._gap_size: int = 0
    
    @property
    def closed(self) -> bool: return self._closed or self.file.closed
    
    def writable(self) -> bool: return self.file.writable()
    def seekable(self) -> bool: return self.file.seekable()
    def readable(self) -> bool: return self.file.readable()
    def tell(self) -> int: return self.file.tell()

    def truncate(self, size: int | None = None) -> int: return self.file.truncate(size)
    
    def flush(self) -> None: self.file.flush()
    def close(self) -> None: 
        self._closed = True
        if self.auto_close: self.file.close()
    
    def _read_raw(self, size: int = -1) -> bytes: return self.file.read(size)
    def _write_raw(self, buffer: ByteString) -> int: return self.file.write(buffer)
    
    def read(self, size: int = -1) -> bytes: # type: ignore[override]
        pos: int = self.file.tell()
        data: bytes = self.file.read(size)
        self.decryptor.seek(pos)
        return self.decryptor.decrypt(data)
    
    def seek(self, pos: int, whence: int = 0) -> int: 
        self.file.seek(0, os.SEEK_END)
        end_pos: int = self.file.tell()
        
        result: int = self.file.seek(pos, whence)
        
        cur: int = self.file.tell()
        
        self._gap_size = max(0, cur - end_pos) # remember gap beyond EOF (if any)
        
        return result
    
    def write(self, buffer: ByteString) -> int: # type: ignore[override]
        pos: int = self.file.tell()
        if self._gap_size > 0:
            self.file.seek(-self._gap_size, os.SEEK_CUR)
            self.encryptor.seek(pos-self._gap_size)
            filler: bytes = self.encryptor.encrypt(NULL_BYTES * self._gap_size)
            result: int = self.file.write(filler)
            if result != self._gap_size:
                raise RuntimeError(f"{result=} should be equal to {self._gap_size=}")
            self._gap_size = 0
        else:
            self.encryptor.seek(pos)
        data: bytes = self.encryptor.encrypt(buffer)
        return self.file.write(data)
    
    def __enter__(self) -> Self: 
        if self.closed: 
            raise ValueError("I/O operation on closed file")
        return self
    def __exit__(self, 
                 exc_type: type[BaseException] | None, 
                 exc_val: BaseException | None, 
                 exc_tb: TracebackType | None) -> None: self.close()

class InFileChaCha20EncryptedDisk(InFileDisk):
    def __init__(self, filepath: str | BinaryIO, password: bytes) -> None:
        if isinstance(filepath, str):
            if not os.path.exists(filepath):
                raise FileNotFoundError(f"{filepath=} not exists.")    
            self.file = open(filepath, "rb+")
        else:
            self.file = filepath
        self._closed: bool = False
        
        try:
            disk_type = InFileDiskType(int.from_bytes(
                self.file.read(1), byteorder='big', signed=False
            ))
        except ValueError:
            raise TypeError(
                f"{filepath=} is not of {self.__class__.__name__} type."
                f" maybe disk is corrupted."
            )
        if disk_type != InFileDiskType.CHA_CHA_20_ENCRYPTED:
            raise TypeError(
                f"{filepath=} is not of {self.__class__.__name__} type."
                f" Please use approprate disk class to load it."
                f" {disk_type=};"
            )
        
        nonce: bytes = self.file.read(12)
        encryptor: EncryptorProtocol = CipherChaCha20Encryptor(
            password=password,
            nonce=nonce
        )
        decryptor: DecryptorProtocol = CipherChaCha20Decryptor(
            password=password,
            nonce=nonce
        )
        auth_tag: bytes = self.file.read(HkdfHmac.HMAC_SIZE)
        if not HkdfHmac.verify(
            password=password, 
            nonce=nonce, 
            info=self.__class__.__name__.encode('utf-8'),
            stored_tag=auth_tag
        ):
            raise ValueError(
                "Incorrect password."
                "\nor maybe disk is corrupted."
            )
        
        self.file = EncryptedBytesIOWrapper(
            encryptor, decryptor,
            self.file, auto_close=True
        )
        self.config = load_config_from_file(self.file)
        
        len_config_bytes: int = self.file.tell()
        
        self.inodes_bitmap = BitmapFile(self.config.num_inodes, self.file, 
                                        pos=len_config_bytes)
        self.blocks_bitmap = BitmapFile(self.config.num_blocks, self.file, 
                                        pos=len_config_bytes + self.inodes_bitmap.size_bytes)
        
        header_prefix_size_required: int = (
            len_config_bytes + 
            self.inodes_bitmap.size_bytes +
            self.blocks_bitmap.size_bytes
        )
        header_size_required: int = (
            header_prefix_size_required + 
            self.config.inode_size * self.config.num_inodes
        )
        self._reserved_space = header_size_required
        
        disk_size = self.config.disk_size
        if disk_size < (header_size_required + self.config.block_size):
            raise ValueError(
                f"{disk_size=} is too small try {header_size_required + self.config.block_size}, matbe disk is corrupted."
            )
        num_super_blocks: int = ceil_division(header_size_required, self.config.block_size)
        if num_super_blocks == 0:
            raise RuntimeError(f"Something went wrong, {num_super_blocks=} should not be zero, matbe disk is corrupted.")
        for i in range(num_super_blocks):
            if not self.blocks_bitmap.get(i):
                raise RuntimeError(f"Something went wrong, {self.blocks_bitmap.get(i)=}[{i=}] should be set, matbe disk is corrupted.")        
        
        if not self.inodes_bitmap.get(0):
            raise RuntimeError(f"Something went wrong, {self.inodes_bitmap.get(0)=} should be set, matbe disk is corrupted.")        
        
        self.inodes = InodesList(
            self.file, 
            pos=header_prefix_size_required,
            inode_size=self.config.inode_size, 
            num_inodes=self.config.num_inodes
        )
        self.blocks = BlocksList(
            self.file, 
            block_size=self.config.block_size, 
            num_blocks=self.config.num_blocks
        )
        
        root_inode = Inode.from_bytes(
            data=self.inodes[0],
            config=self.config
        )
        self.root = Directory(
            disk=self,
            inode=root_inode, 
            inode_ptr=0
        )
        
    @classmethod
    def new_disk(cls, filepath: str | BinaryIO, config: Config, password: bytes) -> Self: # type: ignore[override]
        disk_size = config.disk_size
        
        self = cls.__new__(cls)
        
        nonce: bytes = os.urandom(12)
        encryptor: EncryptorProtocol = CipherChaCha20Encryptor(
            password=password,
            nonce=nonce
        )
        decryptor: DecryptorProtocol = CipherChaCha20Decryptor(
            password=password,
            nonce=nonce
        )
        auth_tag: bytes = HkdfHmac.make(
            password=password, 
            nonce=nonce, 
            info=self.__class__.__name__.encode('utf-8')
        )
        
        root_inode = Inode(InodeMode.DIRECTORY)
        if len(root_inode.to_bytes(config)) != config.inode_size:
            raise ValueError(f"{config.inode_size=} is too small try={len(root_inode.to_bytes(config))}.")
        
        self.config = config
        config_bytes: bytes = dump_config(config)
        
        if isinstance(filepath, str):
            if os.path.exists(filepath):
                raise FileExistsError(f"{filepath=} already exists.")
            self.file = EncryptedBytesIOWrapper(
                encryptor, decryptor,
                file=open(filepath, "wb+"),
                auto_close=True
            )
        else:
            self.file = EncryptedBytesIOWrapper(
                encryptor, decryptor,
                file=filepath,
                auto_close=True
            )
        self._closed = False
        self.file._write_raw(InFileDiskType.CHA_CHA_20_ENCRYPTED.value.to_bytes(
            length=1, byteorder='big', signed=False
        ))
        self.file._write_raw(nonce) # first 12 bit is nonce
        self.file._write_raw(auth_tag) # next HMAC_SIZE is auth_tag
        self.file.write(config_bytes)
        len_config_bytes: int = self.file.tell()
        
        self.file.seek(disk_size - 1, os.SEEK_SET)
        self.file.write(NULL_BYTES) # NOTE: created file with config...
        
        self.inodes_bitmap = BitmapFile(config.num_inodes, self.file, 
                                        pos=len_config_bytes)
        self.blocks_bitmap = BitmapFile(config.num_blocks, self.file, 
                                        pos=len_config_bytes + self.inodes_bitmap.size_bytes)
        
        
        header_prefix_size_required: int = (
            len_config_bytes + 
            self.inodes_bitmap.size_bytes +
            self.blocks_bitmap.size_bytes
        )
        header_size_required: int = (
            header_prefix_size_required + 
            config.inode_size * config.num_inodes
        )
        self._reserved_space = header_size_required
        
        if disk_size < (header_size_required + self.config.block_size):
            raise ValueError(
                f"{disk_size=} is too small try {header_size_required + self.config.block_size}."
            )
            
        num_super_blocks: int = ceil_division(header_size_required, config.block_size)
        if num_super_blocks == 0:
            raise RuntimeError(f"Something went wrong, {num_super_blocks=} should not be zero.")
        for i in range(num_super_blocks):
            self.blocks_bitmap.set(i) # for super blocks
        
        self.inodes = InodesList(
            self.file, 
            pos=header_prefix_size_required,
            inode_size=self.config.inode_size, 
            num_inodes=self.config.num_inodes
        )
        self.blocks = BlocksList(
            self.file, 
            block_size=self.config.block_size, 
            num_blocks=self.config.num_blocks
        )
        
        self.root = Directory.new(
            disk=self,
            inode=root_inode, 
            inode_ptr=0,
            parent_inode_ptr=0
        )
        
        self.inodes[0][:] = root_inode.to_bytes(config)
        self.inodes_bitmap.set(0) # for root
        
        return self
    