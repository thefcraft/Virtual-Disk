import os
from contextlib import asynccontextmanager
from io import BytesIO
from typing import Generator

from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from src.virtual_disk.config import Config
from src.virtual_disk.disk import InFileDisk
from src.virtual_disk.protocol import Disk

basedir = os.path.dirname(os.path.abspath(__file__))
instance = os.path.join(basedir, "instance")
if not os.path.exists(instance):
    os.mkdir(instance)
filepath = os.path.join(instance, "disk.bin")


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
        disk = InFileDisk(f)
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
    html = """
<!DOCTYPE html>
<html>
<head>
  <title>Disk Visualizer</title>
  <meta charset="UTF-8">
  <style>
    body {
      font-family: monospace;
      background: #111;
      color: #eee;
      text-align: center;
      margin: 0;
      padding: 0;
    }
    .tabs {
      display: flex;
      justify-content: center;
      border-bottom: 2px solid #333;
      background: #1b1b1b;
    }
    .tab {
      padding: 12px 24px;
      cursor: pointer;
      font-weight: bold;
      color: #aaa;
      transition: 0.2s;
    }
    .tab.active {
      color: #fff;
      border-bottom: 3px solid #33cc33;
    }
    .tab:hover {
      color: #fff;
    }
    .content {
      display: none;
      padding: 20px;
    }
    .content.active {
      display: block;
    }
    canvas {
      background: #222;
      display: block;
      margin: 20px auto;
      border-radius: 8px;
      box-shadow: 0 0 10px #000a;
    }
    .stats { margin: 10px; }
  </style>
</head>
<body>
  <h1>🧩 Disk Visualization</h1>

  <div class="tabs">
    <div class="tab active" data-tab="blocks">Blocks</div>
    <div class="tab" data-tab="inodes">Inodes</div>
  </div>

  <div id="blocks" class="content active">
    <div class="stats" id="block-stats"></div>
    <canvas id="block-canvas" width="800" height="400"></canvas>
  </div>

  <div id="inodes" class="content">
    <div class="stats" id="inode-stats"></div>
    <canvas id="inode-canvas" width="800" height="400"></canvas>
  </div>

<script>
const blockCanvas = document.getElementById('block-canvas');
const inodeCanvas = document.getElementById('inode-canvas');
const blockCtx = blockCanvas.getContext('2d');
const inodeCtx = inodeCanvas.getContext('2d');
const blockStatsDiv = document.getElementById('block-stats');
const inodeStatsDiv = document.getElementById('inode-stats');

// --- Tab switching ---
const tabs = document.querySelectorAll('.tab');
const contents = document.querySelectorAll('.content');
tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    tabs.forEach(t => t.classList.remove('active'));
    contents.forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(tab.dataset.tab).classList.add('active');
  });
});

async function fetchDisk() {
  const res = await fetch('/api/disk');
  return res.json();
}

function renderGrid(ctx, canvas, arr, labelDiv, name) {
  const count = arr.length;
  const cols = Math.ceil(Math.sqrt(count));
  const rows = Math.ceil(count / cols);
  const cellW = canvas.width / cols;
  const cellH = canvas.height / rows;

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  arr.forEach((used, i) => {
    const x = (i % cols) * cellW;
    const y = Math.floor(i / cols) * cellH;
    ctx.fillStyle = used ? '#33cc33' : '#222';
    ctx.fillRect(x, y, cellW - 0.5, cellH - 0.5);
  });

  const usedCount = arr.reduce((a, b) => a + b, 0);
  const percent = ((usedCount / count) * 100).toFixed(1);
  labelDiv.innerHTML = `<b>${name}:</b> ${usedCount}/${count} used (${percent}%)`;
}

async function refresh() {
  const data = await fetchDisk();
  renderGrid(blockCtx, blockCanvas, data.blocks, blockStatsDiv, "Blocks");
  renderGrid(inodeCtx, inodeCanvas, data.inodes, inodeStatsDiv, "Inodes");
  // setTimeout(refresh, 2000); // refresh every 2s
}

refresh();
</script>
</body>
</html>
"""
    return HTMLResponse(html)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
