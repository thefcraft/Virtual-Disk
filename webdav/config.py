from wsgidav.dc.base_dc import BaseDomainController

from src.virtual_disk.path import Directory

from .filesystem import CustomFilesystemProvider


class CustomDomainController(BaseDomainController):
    def __init__(self, wsgidav_app, config):
        self.realm = f"{self.__class__.__name__}Realm"

    def get_domain_realm(self, path_info, environ) -> str:
        return self.realm

    def require_authentication(self, realm, environ) -> bool:
        return False  # Require authentication always

    def is_realm_user(self, realmname, username, environ) -> bool:
        return username == "admin"  # Allow only "admin"

    def basic_auth_user(self, realm, user_name, password, environ) -> bool:
        return True  # NO PASSWORD ALWAYS
        if user_name != "admin":
            return False
        environ["wsgidav.customauth.password"] = password
        return True  # Accept any password for admin

    def supports_http_digest_auth(self) -> bool:
        return False  # Use basic auth only


def get_config(root: Directory, *, readonly: bool = False) -> dict:
    if not root.inode_ptr == 0:
        raise ValueError(f"{root.inode_ptr=} must be zero or NULL_PTR.")
    config: dict = {
        "http_authenticator": {
            "domain_controller": f"{CustomDomainController.__module__}.{CustomDomainController.__name__}",
            "accept_basic": True,
            "accept_digest": False,
            "default_to_digest": False,
            "trusted_auth_header": None,
        },
        "provider_mapping": {
            "/": CustomFilesystemProvider(root, readonly=readonly)  # for now readonly
        },
        "logging": {"enable": True},
        "verbose": 4,
    }
    return config
