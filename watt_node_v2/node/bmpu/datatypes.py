from enum import Enum
from dataclasses import dataclass
from typing import List

from canopen.emcy import EmcyError


class BMPUStates(Enum):
    INIT = 0
    STANDBY = 1
    POWER_ON = 2
    CHARGE = 3
    SAFE_D = 4
    SAFE_C = 5
    STOPPING = 6
    LOCK_DSP = 7
    FAULT_ACK = 8


class BMPUFault(Enum):
    """BMPU faults present (bits inside critical fault word)"""

    OVER_CURRENT_L1 = 0
    OVER_CURRENT_L2 = 1
    OVER_CURRENT_L3 = 2
    OVER_CURRENT_L4 = 3
    OVER_VOLTAGE_L1 = 4
    OVER_VOLTAGE_L2 = 5
    OVER_VOLTAGE_L3 = 6
    OVER_VOLTAGE_L4 = 7
    OVER_FREQUENCY = 8
    UNDER_FREQUENCY = 9
    ANTI_ISLANDING = 10
    OV_V_BUS = 11
    OV_V_BATT = 12
    UV_V_BATT = 13
    OC_I_BATT = 14
    OVER_TEMP_DCDC_PRIM = 15
    OVER_TEMP_DCDC_SEC = 16
    OVER_TEMP_PFC = 17
    OVER_TEMP_TRANSFORMER = 18
    OVER_TEMP_AMBIENT = 19
    OVRT_DISCONNECTION = 20
    UVRT_DISCONNECTION = 21
    OVP_AUX_LV = 22
    UVP_AUX_LV = 23
    EMERGENCY_SHUTDOWN = 24
    DEVICE_TIMEOUT = 25
    DCDC_PFC_COM_LOSS = 26
    DCDC_PFC_COM_ERRORS = 27
    CHARGE_P = 28
    ADDRESS_SELECTION = 29
    PRECHARGE_FAILURE = 30
    OV_REGUL_V_BATT = 31


@dataclass
class BMPUStateWord:
    """Container for BMPUStateWord"""

    state: BMPUStates  # bits 0:3
    conf: int  # bits 13:15
    mode: int  # bits 11:12
    substate: int = None  # bits  4:7
    dcdc_state: int = None  # bits 8:10

    @property
    def raw(self):
        """Constructs the state word to a raw value in object dictionnary"""
        status = (self.conf << 13) | (self.mode << 11) | self.state.value
        status |= 1 << 31
        return status

    @raw.setter
    def raw(self, raw_value: int):
        self.state = BMPUStates(raw_value & 0b1111)
        self.mode = (raw_value >> 11) & 0b11
        self.conf = (raw_value >> 13) & 0b111

    @classmethod
    def from_raw(cls, raw_value: int) -> "BMPUStateWord":
        inst = cls(0, 0, 0)
        inst.raw = raw_value
        return inst


@dataclass
class BMPUIndexes:
    FIRST_RPDO_INDEX = 0x200
    SECOND_RPDO_INDEX = 0x300
    THIRD_RPDO_INDEX = 0x400
    BASE_ADDRESS = 0x60


KEEP_ALL_MASK = 2**32 - 1


@dataclass
class BMPUFaultWord:
    raw_fault: int
    mask: int = KEEP_ALL_MASK  # By default all faults are considered

    def __str__(self):
        """Representation"""
        return_str = "Fault word : \n"
        return_str += f"\nraw : {self.raw_fault} ({bin(self.raw_fault)})\n"
        return_str += f"masked raw : {self.raw_fault & self.mask} ({bin(self.raw_fault & self.mask)})\n"
        faults = self.faults
        for fault in faults:
            return_str += str(fault) + "\n"
        return return_str

    @property
    def faults(self) -> List[BMPUFault]:
        """Return a list of all the faults
        This does not take into account a mask
        """
        faults = []
        for fault in BMPUFault:
            if self.raw_fault & (1 << fault.value):
                faults.append(fault)
        return faults

    @property
    def faults_masked(self) -> List[str]:
        """Return a list of all the faults applying the mask"""
        masked_raw = self.raw_fault & self.mask
        faults = []
        for fault in BMPUFault:
            if masked_raw & (1 << fault.value):
                faults.append(fault)
        return faults

    @classmethod
    def from_emcy(cls, emcy: EmcyError, mask: int = KEEP_ALL_MASK) -> "BMPUFaultWord":
        """Create from emergency frame by extracting the information"""
        # Skip the first vendor data byte, which is not part of the fault word
        raw_fault = int.from_bytes(emcy.data[1:], byteorder="little")
        return cls(raw_fault, mask)

    @classmethod
    def from_faults(cls, faults: List[BMPUFault], mask: int = KEEP_ALL_MASK) -> "BMPUFaultWord":
        """Create a fault word from a list of faults"""
        raw_fault = 0
        for fault in faults:
            raw_fault += 1 << fault.value
        return cls(raw_fault, mask)

    def as_row(self):
        return [f"raw_fault : {self.raw_fault}", f"mask : {self.mask}"]


FIRST_BMPU_PFC_NODE_ID = 0x5E
MAX_NUM_BMPU = 16
BMPU_PFC_NODE_IDS = [i for i in range(0x5E, FIRST_BMPU_PFC_NODE_ID)]
