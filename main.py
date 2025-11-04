from src.disk import InMemoryDisk
from src.inode import Inode, InodeIO, InodeMode
from src.path import FileIO, Directory, FileMode
from src.config import Config

from pprint import pprint


def main() -> None:
    config = Config(
        block_size=1024,
        inode_size=48,
        num_blocks=1024,
        num_inodes=1024
    )
    disk = InMemoryDisk(
        config=config
    )
    root = disk.root
    
    print(disk.inodes_bitmap.free_count(), disk.blocks_bitmap.free_count())
    try:
        
        with root.open(b'hello.txt', mode=FileMode.WRITE | FileMode.CREATE) as f:
            f.write(b'hello')
        with root.open(b'hello.txt', mode=FileMode.READ) as f:
            print(f.read())
            
        home = root.mkdir(b'home')
        with home.open(b'home.txt', mode=FileMode.WRITE | FileMode.CREATE) as f:
            f.write(b'hii i am laksh')
    
        pprint(root.listtree())
        
        root.copy_tree([b'home'], [b'src'])
        
        
        print(root.listdir())
        print(root.chdir(b'src').listdir())
        
        root.rm_tree(b'home')
        root.rm_tree(b'src')
        
        # root.rename([b'home'], [b'src'])
        # root.copy_file([b'src', b'home.txt'], [b'src.txt'])
        # print(root.listdir())
        
        # with root.open(b'src.txt', mode=FileMode.READ) as f:
        #     print(f.read())
        
        # root.chdir(b'src').remove(b'home.txt')
        
        # root.remove(b'src.txt')
        # root.rmdir(b'src')
        root.remove(b'hello.txt')
        
    finally:
        print(disk.inodes_bitmap.free_count(), disk.blocks_bitmap.free_count())
    

if __name__ == "__main__":
    main()