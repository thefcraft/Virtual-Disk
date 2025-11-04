
    free_block_before = disk.blocks_bitmap.free_count()
    free_inode_before = disk.inodes_bitmap.free_count()
    try:
        ...
    finally:
        ...
    assert disk.blocks_bitmap.free_count() == free_block_before
    assert disk.inodes_bitmap.free_count() == free_inode_before