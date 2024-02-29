from enum import Enum
from dataclasses import dataclass
from typing import List
from canopen.emcy import EmcyError


class MPUState(Enum):
    """All possible MPU states"""

    STARTUP = 0
    IDLE = 1
    PASSIVE_PRECHARGE = 2
    ACTIVE_PRECHARGE = 3
    SAFE_C = 4
    CHARGING = 5
    STOP = 6
    FAULT = 7


class MPUFault(Enum):
    """All possible MPU faults"""

    OC_PHASE_A_CURRENT = 0
    OC_PHASE_B_CURRENT = 1
    OC_PHASE_C_CURRENT = 2
    OC_PHASE_A_VOLTAGE = 3
    OC_PHASE_B_VOLTAGE = 4
    OC_PHASE_C_VOLTAGE = 5
    UV_PHASE_A_VOLTAGE_RMS = 6
    UV_PHASE_B_VOLTAGE_RMS = 7
    UV_PHASE_C_VOLTAGE_RMS = 8
    OV_PFC_P400V_VOLTAGE = 9
    OV_PFC_M400V_VOLTAGE = 10
    OV_DCDC_P400V_VOLTAGE = 11
    OV_DCDC_M400V_VOLTAGE = 12
    OV_VOUT_VOLTAGE = 13
    OV_REGUL_VOUT_VOLTAGE = 14
    OC_IOUT_CURRENT = 15
    UV_PFC_PRECHARGE_FAILURE = 16
    UV_PFC_PASSIVE_COND = 17
    SHUT_T_TEMP_DCDC1_IMS = 18
    SHUT_T_TEMP_DCDC2_IMS = 19
    SHUT_T_TEMP_DCDC1_XFO = 20
    SHUT_T_TEMP_DCDC2_XFL = 21
    SHUT_T_TEMP_DCDC2_L = 22
    SHUT_T_TEMP_AMB = 23
    OV_LV_VOLTAGE = 24
    UV_LV_VOLTAGE = 25
    OC_LV_CURRENT = 26
    EMERGENCY_SHUTDOWN = 27
    DEVICE_TIMEOUT = 28
    DISCHARGE_FAIL_DIODE_BREAK = 29
    CHARGE_P = 30
    ADDRESS_SELECTION = 31


def faults_as_str(faults: List[MPUFault]) -> str:
    return "".join(["_" + fault.name for fault in faults])[1:]


KEEP_ALL_MASK = 2**32 - 1


@dataclass
class MPUFaultWord:
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
    def faults(self) -> List[MPUFault]:
        """Return a list of all the faults
        This does not take into account a mask
        """
        faults = []
        for fault in MPUFault:
            if self.raw_fault & (1 << fault.value):
                faults.append(fault)
        return faults

    @property
    def faults_masked(self) -> List[str]:
        """Return a list of all the faults applying the mask"""
        masked_raw = self.raw_fault & self.mask
        faults = []
        for fault in MPUFault:
            if masked_raw & (1 << fault.value):
                faults.append(fault)
        return faults

    @classmethod
    def from_emcy(cls, emcy: EmcyError, mask: int = KEEP_ALL_MASK) -> "MPUFaultWord":
        """Create from emergency frame by extracting the information"""
        # Skip the first vendor data byte, which is not part of the fault word
        raw_fault = int.from_bytes(emcy.data[1:], byteorder="little")
        return cls(raw_fault, mask)

    @classmethod
    def from_faults(cls, faults: List[MPUFault], mask: int = KEEP_ALL_MASK) -> "MPUFaultWord":
        """Create a fault word from a list of faults"""
        raw_fault = 0
        for fault in faults:
            raw_fault += 1 << fault.value
        return cls(raw_fault, mask)

    def as_row(self):
        return [f"raw_fault : {self.raw_fault}", f"mask : {self.mask}"]
