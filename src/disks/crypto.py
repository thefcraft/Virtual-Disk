try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers import Cipher, CipherContext, algorithms
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
except ImportError as e:
    raise RuntimeError(
        f"crypto dependencies are missing, please run `uv sync --extra crypto`"
        f"\nImportError: {e}"
    )
import hmac
from hashlib import sha256
from typing import ByteString, Protocol

CHA_CHA_20_BLOCK_SIZE: int = 64

NULL_BYTES: bytes = b"\x00"


class HkdfHmac:
    HMAC_SIZE: int = 32

    @classmethod
    def make(cls, password: bytes, nonce: bytes, info: bytes) -> bytes:
        auth_key: bytes = HKDF(
            algorithm=hashes.SHA256(),
            length=cls.HMAC_SIZE,
            salt=cls.__name__.encode() + b":nonce:" + nonce,
            info=info,
        ).derive(password)
        auth_tag: bytes = hmac.new(auth_key, nonce, sha256).digest()
        return auth_tag

    @classmethod
    def verify(
        cls, password: bytes, nonce: bytes, info: bytes, stored_tag: bytes
    ) -> bool:
        if len(stored_tag) != cls.HMAC_SIZE:
            raise ValueError(f"{len(stored_tag)=} must be of size: {cls.HMAC_SIZE}")
        auth_key: bytes = HKDF(
            algorithm=hashes.SHA256(),
            length=cls.HMAC_SIZE,
            salt=cls.__name__.encode() + b":nonce:" + nonce,
            info=info,
        ).derive(password)
        auth_tag: bytes = hmac.new(auth_key, nonce, sha256).digest()
        return hmac.compare_digest(auth_tag, stored_tag)


class EncryptorProtocol(Protocol):
    def encrypt(self, data: ByteString) -> ByteString: ...
    def seek(self, offset: int = 0, /) -> None: ...


class DecryptorProtocol(Protocol):
    def decrypt(self, data: ByteString) -> ByteString: ...
    def seek(self, offset: int = 0, /) -> None: ...


class CipherChaCha20:
    context: CipherContext
    _nonce: bytes

    def seek(self, offset: int = 0, /):
        block_counter, block_offset = divmod(offset, CHA_CHA_20_BLOCK_SIZE)

        self.context.reset_nonce(
            nonce=(block_counter.to_bytes(4, "little") + self._nonce)
        )

        if block_offset:  # Burn the keystream until we reach byte offset
            self.context.update(NULL_BYTES * block_offset)

    def update(self, data: ByteString) -> ByteString:
        return self.context.update(data)


class CipherChaCha20Encryptor(CipherChaCha20):
    def __init__(self, password: bytes, nonce: bytes) -> None:
        key: bytes = sha256(password).digest()
        cipher = Cipher(
            algorithms.ChaCha20(key, NULL_BYTES * 4 + nonce),
            mode=None,
            backend=default_backend(),
        )
        self.context: CipherContext = cipher.encryptor()
        self._nonce: bytes = nonce

    def encrypt(self, data: ByteString) -> ByteString:
        return self.context.update(data)


class CipherChaCha20Decryptor(CipherChaCha20):
    def __init__(self, password: bytes, nonce: bytes) -> None:
        key: bytes = sha256(password).digest()
        cipher = Cipher(
            algorithms.ChaCha20(key, NULL_BYTES * 4 + nonce),
            mode=None,
            backend=default_backend(),
        )
        self.context: CipherContext = cipher.decryptor()
        self._nonce: bytes = nonce

    def decrypt(self, data: ByteString) -> ByteString:
        return self.context.update(data)
