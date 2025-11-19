import os
from contextlib import asynccontextmanager
from io import BytesIO
from typing import Generator

from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from src.virtual_disk.config import Config
from src.virtual_disk.disk import InFileChaCha20EncryptedDisk, InFileDisk
from src.virtual_disk.protocol import Disk

basedir = os.path.dirname(os.path.abspath(__file__))
instance = os.path.join(basedir, "instance")
template = os.path.join(basedir, "templates")
if not os.path.exists(instance):
    os.mkdir(instance)
filepath = os.path.join(instance, "large_disk.bin.enc")
dashboard_path = os.path.join(template, "dashboard.html")
with open(dashboard_path, "r") as f:
    html: str = f.read()


def get_disk() -> Generator[Disk]:
    # disk = InFileDisk.new_disk(
    #     filepath=BytesIO(),
    #     config=Config(
    #         block_size=2248,
    #         inode_size=64,
    #         num_blocks=2,
    #         num_inodes=32
    #     )
    # )
    with open(filepath, "rb") as f:
        # disk = InFileDisk(f)
        disk = InFileChaCha20EncryptedDisk(f, password=b"very secure password :->")
        with disk:
            yield disk


app = FastAPI(title="Disk Visualizer")


@app.get("/api/disk")
def disk_state(disk: Disk = Depends(get_disk)):
    state = {
        "block_size": disk.config.block_size,
        "block_count": disk.blocks_bitmap._size,
        "inode_count": disk.inodes_bitmap._size,
        "blocks_free": disk.blocks_bitmap.free_count(),
        "inodes_free": disk.inodes_bitmap.free_count(),
        "blocks": [
            1 if disk.blocks_bitmap._get(i) else 0
            for i in range(disk.blocks_bitmap._size)
        ],
        "inodes": [
            1 if disk.inodes_bitmap._get(i) else 0
            for i in range(disk.inodes_bitmap._size)
        ],
    }
    return JSONResponse(state)


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(html)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
