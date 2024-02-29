from typing import Optional
from enum import Enum


class AllocationMode(Enum):
    PARALLEL = 0
    SERIES = 1


class AllocationWord:
    """Allocation word used in EVSE for selecting PUs"""

    NB_MPUS = 14
    NB_BMPUS = 16

    def __init__(self, raw: int = 0, mode: Optional[AllocationMode] = None) -> None:
        """Initialize allocation word, mode will overwrite raw value if not the same."""
        self._raw = raw
        if mode is not None:
            self.mode = mode

    def __str__(self) -> str:
        """Representation of allocation word"""
        mpu_list = self.mpu_list
        bmpu_list = self.bmpu_list
        mode = self.mode
        return_str = f"------------------Allocation word-----------------\n"
        return_str += f"mode : {mode}\t\t| total PUs : {len(mpu_list) + len(bmpu_list)}\n"
        return_str += f"MPUs : {mpu_list}\t\t| total : {len(mpu_list)}\n"
        return_str += f"BMPUs: {bmpu_list}\t\t| total : {len(bmpu_list)}\n"
        return_str += f"binary repr : {bin(self.raw)}\n"
        return_str += f"--------------------------------------------------\n"
        return return_str

    def __eq__(self, other: "AllocationWord"):
        return other.raw == self.raw

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({repr(self.raw)})"

    def _set_bit(self, bit):
        self.raw = self.raw | (1 << bit)

    def _clear_bit(self, bit):
        self.raw = self.raw & ~(1 << bit)

    @property
    def mode(self) -> AllocationMode:
        if self.raw & (1 << 31):
            return AllocationMode.SERIES

        else:
            return AllocationMode.PARALLEL

    @mode.setter
    def mode(self, mode: AllocationMode):
        """Set allocation mode to parallel or series"""
        if mode == AllocationMode.SERIES:
            self._set_bit(31)
        elif mode == AllocationMode.PARALLEL:
            self._clear_bit(31)
        else:
            raise ValueError("invalid allocation mode")

    @property
    def raw(self):
        return self._raw

    @raw.setter
    def raw(self, raw_value: int):
        if 0 <= raw_value <= 2**32 - 1:
            self._raw = raw_value
        else:
            raise ValueError("Value is not correct")

    @property
    def mpu_list(self):
        # Construct the mpu list of current allocation word
        mpu_list = []
        for i in range(14):
            if self.raw & (1 << i):
                mpu_list.append(i + 1)
        return mpu_list

    @mpu_list.setter
    def mpu_list(self, mpu_list):
        # Clear set mpus of allocation word
        self.raw = self.raw & (~0 << 14)
        for mpu in mpu_list:
            self._set_bit(mpu - 1)

    @property
    def bmpu_list(self):
        # Construct the bmpu list of current allocation word
        bmpu_list = []
        for i in range(14, 30):
            if self.raw & (1 << i):
                bmpu_list.append(i + 1 - self.NB_MPUS)
        return bmpu_list

    @bmpu_list.setter
    def bmpu_list(self, bmpu_list):
        # Clear set bmpus of allocation word
        mask = (~(~0 << 14)) | (1 << 31)
        self.raw = self.raw & mask
        for bmpu in bmpu_list:
            self._set_bit(bmpu - 1 + self.NB_MPUS)
