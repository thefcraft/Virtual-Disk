from cheroot import wsgi

from wsgidav import util
from wsgidav.wsgidav_app import WsgiDAVApp

from webdav.config import get_config

from src.disk import InMemoryDisk, InFileDisk, InFileChaCha20EncryptedDisk
from src.config import Config
from src.path import Directory

import os

def format_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"

def main(root: Directory, readonly: bool = False, host: str = "0.0.0.0", port: int=8081) -> None:
    config = get_config(
        root=root, readonly=readonly
    )
    
    config["host"] = host
    config["port"] = port
    config["verbose"] = 2
    
    app = WsgiDAVApp(config)
    version = (
        f"{util.public_wsgidav_info} {wsgi.Server.version} {util.public_python_info}"
    )
    server = wsgi.Server(
        bind_addr=(config["host"], config["port"]),
        wsgi_app=app,
        server_name=version,
        numthreads=1
        # numthreads = 50, # NOTE/TODO: MY LIB IS NOT COMPATABLE YET
    )
    app.logger.info(f"Running {version}")
    app.logger.info(f"Serving on http://{config['host']}:{config['port']}/ ...")
    try:
        server.start()
    except KeyboardInterrupt:
        app.logger.info("Received Ctrl-C: stopping...")
    finally:
        server.stop()
        
if __name__ == "__main__":
    basedir = os.path.dirname(os.path.abspath(__file__))
    instance = os.path.join(basedir, 'instance')
    if not os.path.exists(instance): os.mkdir(instance)
    filepath = os.path.join(instance, 'disk.bin.enc')
    if not os.path.exists(filepath):
        config = Config(
            block_size=6144,
            inode_size=64,
            num_blocks=1024*16,
            num_inodes=1024*16
        )
        disk = InFileChaCha20EncryptedDisk.new_disk(
            filepath=filepath,
            config=config,
            password=b'very secure password :->'
        )
        # disk = InFileDisk.new_disk(
        #     filepath=filepath,
        #     config=config
        # )
    else:
        # disk = InFileDisk(
        #     filepath=filepath
        # )
        disk = InFileChaCha20EncryptedDisk(
            filepath=filepath,
            password=b'very secure password :->'
        )
    with disk:
        print("TOTAL SPACE: ", format_size(disk.total_space()))
        print("USED SPACE: ", format_size(disk.used_space()))
        print("FREE SPACE: ", format_size(disk.free_space()))
        print("RESERVED SPACE: ", format_size(disk.reserved_space()))
        main(root=disk.root)