from .utils import ceil_division

class Bitmap:
    __slots__ = ('_size', '_data')
    def __init__(self, size: int):
        self._size: int = size
        self._data: bytearray = bytearray(ceil_division(size, 8))
    def __repr__(self) -> str:
        data = (
            ('\n\t' if idx % 8 == 0 else '') + f' {byte:08b}'[::-1]
            for idx, byte in enumerate(self._data, start=0)
        )
        return f"{self.__class__.__name__}(size={self._size}, data=[{''.join(data)}\n])"
    
    def set(self, index: int): 
        if not (0 <= index < self._size): raise IndexError("Bitmap index out of range")
        self._data[index // 8] |= 1 << (index % 8)
    
    def clear(self, index: int):
        if not (0 <= index < self._size): raise IndexError("Bitmap index out of range")
        self._data[index // 8] &= ~(1 << (index % 8))
    
    def _get(self, index: int) -> bool: 
        return bool(self._data[index // 8] & (1 << (index % 8)))
    
    def get(self, index: int) -> bool:
        if not (0 <= index < self._size): raise IndexError("Bitmap index out of range")
        return self._get(index)
    
    def free_count(self) -> int:
        return sum(
            8 - value.bit_count()
            for value in self._data
        ) # NOTE: self._data is 0x00 so no need for handling last bits beyond _size...
        
    def find_free(self) -> int:
        """Find first 0 bit (free slot)"""
        for idx, value in enumerate(self._data):
            if value == 0xFF: continue
            base = idx * 8
            base_end = min(base+8, self._size)
            for index in range(base, base_end):
                if self._get(index): continue
                return index
        raise OSError(f"{self.__class__.__name__} is full, no more free slot")
    
    def find_and_flip_free(self) -> int:
        """Find first 0 bit (free slot) and flip it."""
        index = self.find_free()
        self.set(index)
        return index
        

