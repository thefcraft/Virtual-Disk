from src.virtual_disk.config import Config
from src.virtual_disk.disk import InMemoryDisk
from src.virtual_disk.inode import InodeIO
from src.virtual_disk.path import FileIO, FileMode

from . import assert_disk_not_changed, disk


@assert_disk_not_changed
def test_rename_folder_at_level1():
    root = disk.root
    
    root.mkdir(b'level-1-depth')
    root.rename([b'level-1-depth'], [b'level-1-depth-renamed'])
    
    root.removedirs(b'level-1-depth-renamed')

@assert_disk_not_changed
def test_rename_file_at_level1():
    root = disk.root
    
    root.create_empty_file(b'level-1-depth.txt')
    root.rename([b'level-1-depth.txt'], [b'level-1-depth-renamed.txt'])
    
    root.remove(b'level-1-depth-renamed.txt')


@assert_disk_not_changed
def test_rename_file_at_level2_manual():
    root = disk.root
    
    root.mkdir(b'level-1-depth')
    root.chdir(b'level-1-depth').create_empty_file(b'level-2-depth.txt')

    root.chdir(b'level-1-depth').rename([b'level-2-depth.txt'], [b'level-2-depth-renamed.txt'])
    
    root.chdir(b'level-1-depth').remove(b'level-2-depth-renamed.txt')
    root.rmdir(b'level-1-depth')


@assert_disk_not_changed
def test_rename_file_at_level2():
    root = disk.root
    
    root.mkdir(b'level-1-depth')
    root.chdir(b'level-1-depth').create_empty_file(b'level-2-depth.txt')
    
    root.rename([b'level-1-depth', b'level-2-depth.txt'], [b'level-1-depth', b'level-2-depth-renamed.txt'])
    
    root.chdir(b'level-1-depth').remove(b'level-2-depth-renamed.txt')
    root.rmdir(b'level-1-depth')


@assert_disk_not_changed
def test_rename_at_level2():
    root = disk.root
    
    root.mkdir(b'level-1-depth')
    
    root.makedirs(b'level-1-depth', b'level-2-depth')
    root.rename([b'level-1-depth', b'level-2-depth'], [b'level-1-depth', b'level-2-depth-renamed'])
    
    root.removedirs(b'level-1-depth', b'level-2-depth-renamed')  # remove both
