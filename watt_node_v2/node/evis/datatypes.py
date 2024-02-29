from dataclasses import dataclass
from enum import Enum
import struct
from typing import List
from canopen.emcy import EmcyError

from ..lu import LookupTable


class ExtendedErrorCategory(Enum):
    NO_ERROR = 0
    SUP = 1
    PM = 2
    CS = 3
    MPU = 4
    BMPU = 5
    MULTIPLE_PU = 6
    MONITORING_NODE = 7
    UNKNOWN = 8


@dataclass
class ExtendedErrorWord:
    raw: int

    @property
    def category(self) -> ExtendedErrorCategory:
        """Return error category"""
        try:
            return ExtendedErrorCategory(self.raw & 0b1111)
        except ValueError:
            return ExtendedErrorCategory.UNKNOWN

    @property
    def index(self) -> int:
        """Return error index"""
        return (self.raw >> 4) & 0b11111

    @property
    def error(self) -> int:
        """Return error error value"""
        return (self.raw >> 9) & 0b1111111

    @classmethod
    def from_raw(cls, raw: int):
        """Construct extended error from raw value"""
        return cls(raw=raw)

    @classmethod
    def from_values(cls, category: ExtendedErrorCategory, index: int, error: int):
        """Construct extended error word from category, index and error"""
        return cls(category.value | (index << 4) | (error << 9))


@dataclass
class EvisIndexes:

    # Real implementation should be changed
    NUM_MPUS = 14
    NUM_BMPUS = 16

    CS_CHARGEPOINT_0_INDEX = 0x7000
    CS_CHARGEPOINT_1_INDEX = 0x7500
    CS_CHARGEPOINT_INDEXS = (CS_CHARGEPOINT_0_INDEX, CS_CHARGEPOINT_1_INDEX)
    CCS_INTERFACE = 0
    CHA_INTERFACE = 1
    EFAST_PDO_DEFINITION_BUILD = 17270
    V2G_PDO_DEFINITION_BUILD = 17519
    V2G_SW_VERSION = "5.0.0"
    EFAST_SW_VERSION = "4.0.0"
    OLD_SW_VERSION = "1.0.0"

    SUP_REQUEST_CODE_SUBINDEX = 0x9
    SUP_ERROR_CODE = 2

    IMD_PASSWORD_INDEX = 0x3100
    IMD_PASSWORD_VALUE = 0x21646D69  # imd! in ASCII

    EFAST_INTERFACE_BIT = 64

    REQUEST_CODE_MASK = 0b1111

    CURRENT_GAIN = 100
    VOLTAGE_GAIN = 10
    POWER_GAIN = 100
    TEMPERATURE_GAIN = 1

    # FOLDER_PREFIX = 'WL1-EVIS-BIN-v'
    # FILE_PREFIX = 'WL1-EVIS-BIN-v'


class EvisReleases(Enum):
    LEGACY = 0
    EFAST = 1
    V2G = 2
    OLD = 5


class ChargePointInterface(Enum):
    CCS = 0
    CHA = 1


class ChargePointState(Enum):
    CP0_Init = 0
    CP1_WaitForSupApprob = 1
    CP2_WaitForEV = 2
    CP4_WaitForPUs = 4
    CP6_LockCableToEV = 6
    CP7_CableCheck = 7
    CP8_ChargeLoop = 8
    CP10_StopPUsAndPMs = 10
    CP11_SafetyChecks = 11
    CP12_StopCommWithEV = 12
    CP14_ReleasePUs = 14
    CP15_UnlockEvConnector = 15
    CP16_WaitForPMidle = 16
    CP17_EmergencyStop = 17
    CP18_Reset = 18


class ChargePointSubState(Enum):
    CP2_S1_WaitForPUsAllocation = 21
    CP2_S2_SetupPUs = 22


class SupervisorInterface(Enum):
    LEGACY = 0
    EFAST = 1
    V2G = 2


class SupervisorRequestCode(Enum):
    SUP0_Idle = 0
    SUP1_Approbation = 1
    SUP2_Cancellation = 2
    SUP3_AllocationDone = 3
    SUP4_EVSEStopChargeReq = 4
    SUP5_Terminate = 5
    SUP6_Reset = 6
    SUP7_RearmChargeWithoutUnplug = 7
    SUP15_DefaultValue = 15


class EvisType(Enum):
    A = 0x10
    B = 0x20
    C = 0x18
    D = 0x28


@dataclass
class EVISFaultWord:
    """Container for an EVIS fault word : sent with an emergency message"""

    raw_fault: bytes
    extended_error: int = None
    extended_error_str: str = "lut not loaded"
    error: int = None
    error_str: str = "lut not loaded"
    additional_info: int = None
    lut: LookupTable = None

    @property
    def interface(self):
        """Return the corresponding charge point interface of the emergency"""
        return ChargePointInterface(self.additional_info & 0b1)

    def __str__(self):
        """Representation"""
        return_str = "Evis fault word : "
        # return_str += f"\nraw : {self.raw_fault} ({bin(self.raw_fault)})\n"
        return_str += f"Extended error : {self.extended_error}\n"
        return_str += f"Error : {self.error}\n"
        return_str += f"Additional info : {self.additional_info}\n"
        return return_str

    def __post_init__(self):
        """Initialize extended_error, error and additional info"""
        self.error = struct.unpack("<B", self.raw_fault[0:1])[0]
        self.extended_error = struct.unpack("<H", self.raw_fault[1:3])[0]
        self.additional_info = struct.unpack("<B", self.raw_fault[3:4])[0]
        if self.lut is not None:
            # If lookup table given update string values with correct ones
            self.extended_error_str = self.lut.get_extended_error(self.extended_error)
            self.error_str = self.lut.get_error(self.error)

    @classmethod
    def from_emcy(cls, emcy: EmcyError, lut: LookupTable = None) -> "EVISFaultWord":
        """Create from emergency frame by extracting the information"""
        # Skip the first vendor data byte, which is not part of the critical fault word
        return cls(emcy.data[1:], lut=lut)

    @classmethod
    def from_values(
        cls,
        extended_error: int,
        error: int,
        additional_info: int,
        lut: LookupTable = None,
    ) -> "EVISFaultWord":
        """Create from values"""
        raw = struct.pack("<BHB", error, extended_error, additional_info)
        return cls(raw, lut=lut)

    def as_row(self) -> List[str]:
        return [
            f"raw_fault : {self.raw_fault}",
            f"extended error raw : {self.extended_error}",
            f"extended error : {self.extended_error_str}",
            f"error raw : {self.error}",
            f"error : {self.error_str}",
            f"additionnal_info : {self.additional_info}",
        ]
