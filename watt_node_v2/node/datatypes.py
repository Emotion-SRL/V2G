from dataclasses import dataclass
from enum import Enum, auto, IntEnum


class NodeType(IntEnum):
    evis = auto()
    mpu = auto()
    bmpu_pfc = auto()
    bmpu_dcdc = auto()
    pm = auto()
    sup = auto()
    bootloader = auto()
    generic_pu = auto()
    unknown = auto()
    empu = auto()
    ebmpu_pfc = auto()
    epm = auto()
    ebootloader = auto()
    pm_cha = auto()
    pm_ccs = auto()
    mpu_r2_pfc = auto()
    mpu_r2_dcdc = auto()


class NodeIndexes:
    NB_RETRY = 3

    RESPONSE_TIMEOUT = 0.5
    # CANOPEN VARIABLE
    COB_ID_SYNC_MESSAGE_INDEX = 0x1005

    DEVICE_NAME_INDEX = 0x1008
    DEVICE_NAME_SUBINDEX = 0x0

    HARDWARE_REVISION_INDEX = 0x1009
    HARDWARE_REVISION_SUBINDEX = 0x0

    SW_VERSION_INDEX = 0x100A
    SW_VERSION_SUBINDEX = 0x0

    SW_BUILD_INDEX = 0x2200
    SW_BUILD_SUBINDEX = 0x05

    SN_INDEX = 0x1018
    SN_SUBINDEX = 0x04

    FAULT_WORD_INDEX = 0x3000
    FAULT_WORD_SUBINDEX = 0x08

    CRITICAL_FAULT_WORD_INDEX = 0x3000
    CRITICAL_FAULT_WORD_SUBINDEX = 0x36

    COBID_EMCY_INDEX = 0x1014

    STORE_PARAMETER_INDEX = 0x1010
    STORE_PARAMETER_SUBINDEX = 0x1

    RESTORE_FACTORY_SETTINGS_INDEX = 0x1011
    RESTORE_FACTORY_SETTINGS_SUBINDEX = 0x1

    BUILD_NB_INDEX = 0x2200
    BUILD_NB_SUBINDEX = 0x5

    VIRTUAL_SCOPE_COMMAND_INDEX = 0x2320

    VIRTUAL_SCOPE_GET_DATA_INDEX = 0x2321

    VIRTUAL_SCOPE_SETTINGS_INDEX = 0x2322
    VIRTUAL_SCOPE_SAMPLING_TIME_SUBINDEX = 0x1
    VIRTUAL_SCOPE_LOG_CHANNEL_SUBINDEX = 0x3
    VIRTUAL_SCOPE_PRESCALER_SUBINDEX = 0x4
    VIRTUAL_SCOPE_SAMPLES_NB_SUBINDEX = 0x5
    VIRTUAL_SCOPE_PHASE_SAMPLES_NB_SUBINDEX = 0x6
    VIRTUAL_SCOPE_STATE_SUBINDEX = 0x7

    VIRTUAL_SCOPE_SIGNALS_INDEX = 0x2323

    VIRTUAL_SCOPE_NB_SAMPELS = 4096
    VIRTUAL_SCOPE_PRESCALER = 1
    VIRTUAL_SCOPE_CHANNEL_SELECTION = 25595

    # Specific CANopen commands

    ERASE_EXTERNAL_MEMORY_COMMAND = 0x64616564  # ='dead' in ascii
    RESTORE_FACTORY_SETTINGS_COMMAND = 0x64616F6C  # ='load' in ascii
    STORE_PARAMETER_COMMAND = 0x65766173  # ='save in ascii'


DEVICE_NAME_TO_TYPES = {
    "Watt & Well | EVIS ChipSet": NodeType.evis,
    "Watt-Consulting CO Bootloader ": NodeType.bootloader,
    "Watt&Well MPU-25": NodeType.mpu,
    "MPU-25 Emulated": NodeType.empu,
    "BMPU": NodeType.bmpu_pfc,
    "BMPU DC/DC": NodeType.bmpu_dcdc,
    "MPU-R2": NodeType.mpu_r2_pfc,
    "MPU-R2 DC/DC": NodeType.mpu_r2_dcdc,
}

TYPE_STR_TO_NODETYPE = {
    "mpu": NodeType.mpu,
    "bmpu": NodeType.bmpu_pfc,
    "mpu-r2": NodeType.mpu_r2_pfc,
    "evis": NodeType.evis,
    "pm": NodeType.pm,
}

NODETYPE_TO_TYPE_STR = {
    NodeType.mpu: "mpu",
    NodeType.bmpu_pfc: "bmpu",
    NodeType.mpu_r2_pfc: "mpu-r2",
    NodeType.evis: "evis",
}

REAL_NODE_TYPES = [
    NodeType.evis,
    NodeType.mpu,
    NodeType.bmpu_dcdc,
    NodeType.bmpu_pfc,
    NodeType.mpu_r2_pfc,
    NodeType.mpu_r2_dcdc,
    NodeType.bootloader,
]


class NodeNames(Enum):
    EVIS = "Watt & Well | EVIS ChipSet"
    MPU25 = "Watt&Well MPU-25"
    BMPU_DCDC = "BMPU DC/DC"
    BMPU = "BMPU"
    BOOTLOADER = "Watt-Consulting CO Bootloader "


# These are standard W&W base folder names for devices
NODE_TYPE_TO_FOLDER_PREFIX = {
    NodeType.evis: "WL1-EVIS-BIN-v",
    NodeType.mpu: "WL1-MPU-DSP-BIN-v",
    NodeType.empu: "WL1-MPU-DSP-BIN-v",
    NodeType.bmpu_pfc: "WL1-BMPU-DSP-BIN-v",
    NodeType.bmpu_dcdc: "WL1-BMPU-DSP-BIN-v",
    NodeType.mpu_r2_pfc: "WL1-MPU-R2-DSP-BIN-v",
    NodeType.mpu_r2_dcdc: "WL1-MPU-R2-DSP-BIN-v",
    NodeType.bootloader: "WL1-BOOT-28335-BIN-v",
    NodeType.ebmpu_pfc: "WL1-BMPU-DSP-BIN-v",
}


@dataclass
class NodeInformation:
    """Data holder for general node information, generally speaking this is NodeSoftwareInformation + some more info"""

    id: int = None
    nmt_state: str = None
    sw_version: str = None
    sw_build: int = None
    device_name: str = None
    type: NodeType = None
    serial_nb: int = None
    hardware_revision: str = None

    def __post_init__(self):
        # Define the type according to the relation device name <==> type
        # If the node name doesn't match anything put unknown type'
        if self.type is not None:
            return
        try:
            self.type = DEVICE_NAME_TO_TYPES[self.device_name]
        except KeyError:
            self.type = NodeType.unknown

    def __eq__(self, other: "NodeInformation"):
        if other == None:
            return False
        return (
            (self.sw_version == other.sw_version)
            and self.sw_build == (other.sw_build)
            and (self.type == other.type)
        )

    @property
    def folder(self):
        """Return folder name containing node data files"""
        # Same as file but without an extension
        return self.construct_filename(extension="")

    def construct_filename(self, extension: str) -> str:
        """Constructs a node specific data file"""
        file_prefix = NODE_TYPE_TO_FOLDER_PREFIX[self.type]
        # This is specific to Bootloader versions
        self.sw_version = self.sw_version.replace("000", "0.")
        # Special rule for BMPU/MPU-R2 DCDC that has a -Dcdc between build nb and prefix, only if postfix is not empty and not firmware prefix
        # This is ugly but there isn't a really good way to handle this edge case
        if (
            self.type in [NodeType.bmpu_dcdc, NodeType.mpu_r2_dcdc]
            and extension != ""
            and extension != ".wtcfw"
        ):
            extension = "-Dcdc" + extension
        return f"{file_prefix}{self.sw_version}-Build{self.sw_build}{extension}"


class DeviceType(Enum):
    UNKNOWN = auto()
    EVIS = auto()
    MPU = auto()
    BMPU = auto()


NODE_ID_TO_NODE_TYPE = {
    0x10: NodeType.evis,
    0x18: NodeType.evis,
    0x20: NodeType.evis,
    0x30: NodeType.bmpu_dcdc,
    0x50: NodeType.mpu,
    0x51: NodeType.mpu,
    0x52: NodeType.mpu,
    0x5E: NodeType.bmpu_pfc,
}


PM_ID_TO_NAME = {
    0x11: "PM CCS EVIS A",
    0x13: "PM CHA EVIS A",
    0x21: "PM CCS EVIS B",
    0x23: "PM CHA EVIS B",
    0x19: "PM CCS EVIS C",
    0x1B: "PM CHA EVIS C",
    0x29: "PM CCS EVIS D",
    0x2B: "PM CHA EVIS D",
}


CS_IDS = [16, 24, 32, 40]
MPU_IDS = [i for i in range(0x50, 0x50 + 14)]
BMPU_DCDC_IDS = [
    i for i in range(47, 48 + 16)
]  # Start at 47 because 47 is also a possible id when dcdc does not recognize pfc
BMPU_IDS = [i for i in range(0x5E, 0x5E + 16)]
PM_CCS_IDS = [0x11, 0x21, 0x19, 0x29]
PM_CHA_IDS = [0x13, 0x23, 0x1B, 0x2B]
PM_IDS = PM_CCS_IDS + PM_CHA_IDS
SUP_IDS = [0x02, 0x03]
BOOTLOADER_IDS = [125, 126]
