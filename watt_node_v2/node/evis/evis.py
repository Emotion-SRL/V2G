import verboselogs
import canopen
import logging
from typing import Dict, Union
from packaging import version
from ..base import WattRemoteNode, WattNodeController
from .datatypes import EvisReleases, EvisIndexes
from ...node.datatypes import NodeIndexes


verboselogs.install()
logger = logging.getLogger(__name__)


def v2g_compatible(f):
    def wrapper(*args):
        if args[0].is_v2g():
            return f(*args)
        else:
            raise NotImplementedError("Evis needs to be v2g compatible to access this property")

    return wrapper


class EvisController(WattNodeController):
    """Evis controller"""

    @property
    def max_cpu_load(self):
        """Maximum current cpu load of EVIS, this is reset upon reboot"""
        return self.node.sdo["RT diagnostic"]["Slow Task Max Cpu Load"].raw

    def unlock_imd(self):
        """Unlock evis IMD for writing values"""
        logger.info("Unlocking IMD calibrations")
        try:
            self.node.sdo.download(
                EvisIndexes.IMD_PASSWORD_INDEX,
                0,
                EvisIndexes.IMD_PASSWORD_VALUE.to_bytes(length=4, byteorder="little"),
            )
        except canopen.SdoAbortedError as e:
            if e.code == 0x06020000:
                # Object does not exist
                logger.info("Failed to unlock IMD, probably because old EVIS")
                return
            raise

    def disable_securities(self, imd: bool = True, emergency: bool = True, control_pilot: bool = True):
        """Update evis securities : True to disable, False to enable"""
        # Unlock IMD
        self.unlock_imd()
        # Put IMD in force OK mode
        self._write(int(imd), "Debug IMD", "imd_force_ok")
        # Disable Emergency input check
        self._write(int(emergency), "Debug", "Disable_check_emergency_input")
        # Disable ControlPilot check
        self._write(int(control_pilot), "Debug", "Disable_check_control_pilot")

    def disable_sync(self):
        """Disable sync"""
        temp = int.from_bytes(
            self.node.sdo.upload(NodeIndexes.COB_ID_SYNC_MESSAGE_INDEX, 0),
            byteorder="little",
        )
        # compute new cob id
        temp = temp & (~(1 << 30))  # Set bit 30 to 0
        # deactivate sending of sync object
        self.node.sdo.download(
            NodeIndexes.COB_ID_SYNC_MESSAGE_INDEX,
            0,
            temp.to_bytes(length=4, byteorder="little"),
        )

    def force_error(self):
        """Force both chargepoints in error state with a SUP2_Cancellation command"""
        self._write(
            EvisIndexes.SUP_ERROR_CODE,
            EvisIndexes.CS_CHARGEPOINT_0_INDEX,
            EvisIndexes.SUP_REQUEST_CODE_SUBINDEX,
        )
        self._write(
            EvisIndexes.SUP_ERROR_CODE,
            EvisIndexes.CS_CHARGEPOINT_1_INDEX,
            EvisIndexes.SUP_REQUEST_CODE_SUBINDEX,
        )

    @property
    def release(self) -> EvisReleases:
        """Determine the release type of evis"""
        # Get release type directly
        if self.sw_info is None:
            self.read_software_information()
        sw_info = self.sw_info
        sw_version = version.parse(sw_info.sw_version)
        if sw_version >= version.parse(EvisIndexes.V2G_SW_VERSION):
            release = EvisReleases.V2G
        elif sw_version >= version.parse(EvisIndexes.EFAST_SW_VERSION):
            release = EvisReleases.EFAST
        else:
            release = EvisReleases.LEGACY
        return release

    @property
    def rpdo_sup_base(self) -> int:
        """Returns location of first SUP rpdo"""
        release = self.release
        if release == EvisReleases.LEGACY:
            return 41
        elif release == EvisReleases.EFAST:
            return 135
        elif release == EvisReleases.V2G:
            return 143

    @property
    def tpdo_sup_base(self) -> int:
        """Returns location of first SUP tpdo"""
        # Define rpdo_sup_base and tpdo_sup_base
        release = self.release
        if release == EvisReleases.V2G:
            return 78
        elif release == EvisReleases.EFAST:
            return 72
        else:
            # TODO check this, probably wrong but was missing
            return 72

    def _prepare_calibration_upload(self):
        self.unlock_imd()


class EvisNode(WattRemoteNode):
    FOLDER_PREFIX = "WL1-EVIS-BIN-v"
    FILE_PREFIX = "WL1-EVIS-BIN-v"
    CALIBRATION_INDEX_NAMES = ["Calibration", "Calibration IMD"]

    def __init__(
        self,
        node_id: int,
        object_dictionary: Union[canopen.objectdictionary.ObjectDictionary, str, None],
        *args,
        **kwargs,
    ):
        super().__init__(node_id=node_id, object_dictionary=object_dictionary, *args, **kwargs)
        self.controller: EvisController = EvisController(self)
        self.release: EvisReleases = None
        self.lookup_maps: Dict = {}
        self.pdos_read: bool = False

    def read_pdos(self) -> None:
        """Read pdo configuration of Evis !! This is long so must be done only once"""
        if not self.pdos_read:
            self.rpdo.read()
            self.tpdo.read()
            self.pdos_read = True

    def update(self):
        """Update all information, once node has been created and added to the network"""
        if self.network is None:
            raise ValueError("Node is not connected to the network")
        # Get release type directly
        self.release = self.controller.release

        # Define rpdo_sup_base and tpdo_sup_base
        if self.release == EvisReleases.V2G:
            self.rpdo_sup_base = 143
            self.tpdo_sup_base = 78
        elif self.release == EvisReleases.EFAST:
            self.rpdo_sup_base = 135
            self.tpdo_sup_base = 72
        else:
            self.rpdo_sup_base = 41

    def _prepare_calibration_upload(self):
        self.controller.unlock_imd()

    def is_v2g(self):
        return self.release == EvisReleases.V2G
