from cheroot import wsgi

from wsgidav import util
from wsgidav.wsgidav_app import WsgiDAVApp

from webdav.config import get_config

from src.disk import InMemoryDisk
from src.config import Config

def main(readonly: bool = False, host: str = "0.0.0.0", port: int=8080) -> None:
    config = Config(
        block_size=1024,
        inode_size=48,
        num_blocks=1024,
        num_inodes=1024
    )
    disk = InMemoryDisk(
        config=config
    )
    
    config = get_config(
        root=disk.root, readonly=readonly
    )
    
    config["host"] = host
    config["port"] = port
    # config["verbose"] = 1
    
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
    main()