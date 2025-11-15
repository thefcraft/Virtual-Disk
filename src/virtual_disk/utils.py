import time


def ceil_division(a: int, b: int) -> int:
    """Return the ceiling of a divided by b, ceil(a/b)."""
    return (a + b - 1) // b


def floor_division(a: int, b: int) -> int:
    """Return the floor of a divided by b, floor(a/b)."""
    return a // b


def current_time_epoch() -> int:
    """The function `current_time_epoch` returns the current time in epoch format."""
    return int(time.time())


def abspath_to_paths(abspath: bytes) -> list[bytes]:
    abspath = abspath.strip(b"/")
    if abspath == b"":
        return []
    paths: list[bytes] = abspath.split(b"/")
    return paths
