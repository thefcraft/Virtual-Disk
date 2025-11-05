# Virtual Disk Filesystem

This project is a user-level virtual filesystem implemented from scratch in Python. It simulates a standard UNIX-like filesystem structure, including inodes, data blocks, and bitmaps for allocation management. The filesystem can be backed by different storage mechanisms (in-memory, a single file, or an encrypted file) and can be mounted and accessed over the network via a built-in WebDAV server.

## ⚠️ Caution

The Readme was AI-generated. (cause i hate writing by my own...)

## Features

*   **UNIX-like Filesystem Model**: Core concepts like inodes, data blocks, and allocation bitmaps are implemented to manage file and directory structures.
*   **Large File Support**: Utilizes a combination of direct, single, double, and triple indirect block pointers within inodes, allowing for very large files.
*   **Multiple Storage Backends**:
    *   **`InMemoryDisk`**: A volatile, in-memory implementation perfect for rapid testing and development.
    *   **`InFileDisk`**: Persists the entire filesystem state to a single binary file.
    *   **`InFileChaCha20EncryptedDisk`**: A persistent backend that encrypts the entire disk file with ChaCha20 and authenticates it with an HMAC, requiring a password for access.
*   **WebDAV Server Integration**: Exposes the virtual disk as a WebDAV share using `wsgidav` and `cheroot`, allowing it to be mounted as a network drive on major operating systems.
*   **Disk Visualizer**: A simple web-based dashboard built with FastAPI to visualize the real-time allocation status of inodes and data blocks.

## Installation

This project requires Python 3.13 or newer.

1.  Clone the repository:
    ```bash
    git clone https://github.com/thefcraft/Virtual-Disk.git
    cd Virtual-Disk
    ```

2.  Install dependencies using `uv` or `pip`. Using `uv` is recommended as it leverages the `uv.lock` file.

    ```bash
    # Install all dependencies using uv
    uv sync
    ```

    Alternatively, you can install with `pip`:

    ```bash
    # Install base dependencies
    pip install .

    # To include encryption support
    pip install .[crypto]

    # To install all development dependencies (for tests and visualizer)
    pip install .[dev]
    ```

## Usage

### 1. Running the WebDAV Server

The primary way to interact with the virtual disk is by running the WebDAV server. The `run_webdav.py` script starts a server that serves an encrypted, persistent virtual disk.

```bash
python run_webdav.py
```

This command will:
*   Create an encrypted disk file at `instance/disk.bin.enc` if it doesn't exist, using a default password.
*   Start the WebDAV server, accessible by default at **`http://0.0.0.0:8081`**.
*   Print disk space statistics to the console.

You can now connect to this URL using any WebDAV client or by mounting it as a network drive in your operating system (e.g., Windows' "Map network drive" or macOS' "Connect to Server").

### 2. Visualizing the Disk

The repository includes a simple tool to visualize how inodes and data blocks are being used in real-time.

```bash
python disk_visualizer.py
```
*   The dashboard will be available at **`http://localhost:8000`**.
*   It displays separate grids for inode and block allocation, with statistics on total, used, and free resources. Used resources are colored green, while free ones are dark gray.

### 3. Programmatic API

You can also create and interact with the virtual disk directly in your Python code.

```python
from src.config import Config
from src.disk import InFileDisk
from src.path import FileMode

# Define the disk configuration
config = Config(
    block_size=4096,
    inode_size=64,
    num_blocks=1024,
    num_inodes=1024
)

# Create a new persistent, non-encrypted disk
disk = InFileDisk.new_disk(filepath="my_disk.bin", config=config)

# The disk must be used as a context manager to ensure it's properly closed
with disk:
    root = disk.root

    # Create a new directory
    my_dir = root.mkdir(b"documents")
    print("Created directory 'documents'")

    # Create a file and write to it
    with my_dir.open(b"report.txt", mode=FileMode.CREATE | FileMode.WRITE) as f:
        f.write(b"This is a virtual file system report.")
    
    # Read the file back
    with my_dir.open(b"report.txt", mode=FileMode.READ) as f:
        content = f.read()
        print(f"Read from report.txt: {content.decode()}")

    # List the contents of the root directory
    print(f"Root contents: {root.listdir()}")

# >> Created directory 'documents'
# >> Read from report.txt: This is a virtual file system report.
# >> Root contents: [b'documents']
```

## Architecture

The filesystem is designed with several core components:

*   **Configuration (`src/config.py`)**: A `Config` dataclass holds all fundamental parameters of the disk, such as block size, inode size, and total resource counts. This configuration is stored in the superblock of persistent disks.
*   **Bitmaps (`src/bitmap.py`)**: Two bitmaps efficiently track the allocation status of inodes and data blocks.
*   **Inodes (`src/inode.py`)**: The `Inode` class represents a file or directory, storing metadata like mode (file/directory), size, and timestamps. It contains an array of block pointers to locate data. `InodeIO` provides a low-level, block-aware I/O interface for the data associated with an inode.
*   **Path API (`src/path.py`)**: The `Directory` and `FileIO` classes provide a high-level, user-friendly API for filesystem operations.
    *   `Directory`: Manages directory entries (name -> inode mappings) and supports operations like `mkdir`, `rmdir`, `listdir`, `rename`, and `open`.
    *   `FileIO`: A file-like object that implements a standard `io.BytesIO` interface (`read`, `write`, `seek`, `truncate`) for interacting with files.
*   **Disk Backends (`src/disks/`)**:
    *   **In-Memory (`inmemory.py`)**: Uses Python lists and `bytearray` objects to represent the disk. Fast but volatile.
    *   **In-File (`infile.py`)**: Manages the filesystem within a single binary file. The file starts with a superblock (the disk's `Config`), followed by the inode/block bitmaps, the inode table, and finally the data blocks.
    *   **Encrypted In-File (`infile_encrypted.py`)**: Extends `InFileDisk` by wrapping all I/O in a ChaCha20 encryption layer. The disk file header contains a nonce and an HMAC tag to verify the password and integrity before use.
*   **WebDAV Provider (`webdav/`)**: A custom `DAVProvider` implementation bridges the `wsgidav` server and the virtual disk's API, translating WebDAV requests (`GET`, `PUT`, `MKCOL`) into calls on the `Directory` and `FileIO` objects.