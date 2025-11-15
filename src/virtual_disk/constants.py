from typing import TypeAlias, Literal

NULL_PTR: int = 0x00
NULL_BYTES: bytes = b'\x00'

NUM_DIRECT_PTR: int = 12
EPOCH_TIME_BYTES: int = 6

MAX_NAME_LEN: int = 255

TYPE_NULL_PTR: TypeAlias = Literal[0x00]