import canopen
from abc import ABC
import canopen
from typing import Union, Any
from .datatypes import NodeInformation, NodeIndexes
import logging
from ..utils import get_valid_filename
import zipfile
from io import TextIOWrapper, BytesIO

XML_ZIP_INDEX = 0x2444
EDS_ZIP_INDEX = 0x1021

logger = logging.getLogger(__name__)

MPU_IDS = [i for i in range(0x50, 0x50 + 14)]
BMPU_IDS = [i for i in range(0x50 + 14, 0x50 + 14 + 16)]


class ControllerException(Exception):
    """A controller exception occred"""


class WattNodeController(ABC):
    """Adds a controller to the node for accessing specific information watt information
    These methods do not require an eds to be loaded and are node independent
    """

    def __init__(self, node: Union["canopen.RemoteNode", "canopen.LocalNode"], *args, **kwargs):
        self.node = node
        self.sw_info: NodeInformation = None

    def _write(self, value: Any, index: int, subindex: int = None):
        """Write sdo value to node via object dictionary"""
        if subindex is None:
            self.node.sdo[index].raw = value
        else:
            self.node.sdo[index][subindex].raw = value

    def _read(self, index: int, subindex: int = None):
        """Read sdo value from node via object dictionary"""
        # read value
        if subindex is None:
            return self.node.sdo[index].raw

        return self.node.sdo[index][subindex].raw

    def ping(self) -> None:
        """Ping a watt node by reading a common sdo value, if no response then raises an error ==> Node doesn't exist"""
        device_name = self.device_name

    def is_eds_contained(self) -> bool:
        """Check if EDS is contained inside node"""
        try:
            # Check format entry is present
            self.node.sdo.upload(0x1022, 0x0)
            return True
        except canopen.SdoAbortedError:
            return False

    @property
    def serial_nb(self):
        return int.from_bytes(
            self.node.sdo.upload(NodeIndexes.SN_INDEX, NodeIndexes.SN_SUBINDEX),
            byteorder="little",
        )

    @property
    def sw_version(self):
        return self.node.sdo.upload(NodeIndexes.SW_VERSION_INDEX, NodeIndexes.SW_VERSION_SUBINDEX).decode(
            "utf-8"
        )

    @property
    def sw_build(self):
        return int.from_bytes(
            self.node.sdo.upload(NodeIndexes.SW_BUILD_INDEX, NodeIndexes.SW_BUILD_SUBINDEX),
            byteorder="little",
        )

    @property
    def hardware_revision(self):
        hardware_revision = self.node.sdo.upload(
            NodeIndexes.HARDWARE_REVISION_INDEX, NodeIndexes.HARDWARE_REVISION_SUBINDEX
        ).decode("utf-8")
        # Remove trailing space and X character
        return get_valid_filename(hardware_revision.rstrip().rstrip("X"))

    @property
    def device_name(self):
        return self.node.sdo.upload(NodeIndexes.DEVICE_NAME_INDEX, NodeIndexes.DEVICE_NAME_SUBINDEX).decode(
            "utf-8"
        )

    @property
    def cobid_emcy(self):
        return int.from_bytes(
            self.node.sdo.upload(NodeIndexes.COBID_EMCY_INDEX, 0),
            byteorder="little",
        )

    def jump_into_bootloader(self) -> None:
        """Make the node jump into the bootloader,
        this is a broadcast message, the node will not respond when going to the bootloader
        """
        logger.info("Jumping to bootloader")
        BOOTLOADER_PASSWORD_INDEX = 0x2105
        UNLOCK_BOOTLOADER: int = 0x626F6F74
        try:
            self.node.sdo.download(
                BOOTLOADER_PASSWORD_INDEX,
                0,
                UNLOCK_BOOTLOADER.to_bytes(
                    length=4,
                    byteorder="little",
                ),
            )
        except canopen.sdo.exceptions.SdoCommunicationError:
            # No response will be received because node will not send response
            pass
            # TODO maybe raise an error if node actually responds (this means it didn't go to bootloader)

    def read_software_information(self, retries: int = 5, timeout: int = 0.4) -> NodeInformation:
        """Retreive node software information, no od needs to be loaded"""
        logger.debug(f"Reading software information of {self.node.id}")
        # TODO read_software_information shouldn't change internal node data
        self.node.sdo.MAX_RETRIES = retries
        self.node.sdo.RESPONSE_TIMEOUT = timeout
        try:
            device_name = self.device_name
            sw_build = self.sw_build
            sw_version = self.sw_version
            serial_nb = self.serial_nb
            hardware_revision = self.hardware_revision

            info = NodeInformation(
                id=self.node.id,
                nmt_state=self.node.nmt.state,
                sw_version=sw_version,
                sw_build=sw_build,
                hardware_revision=hardware_revision,
                device_name=device_name,
                serial_nb=serial_nb,
            )
        finally:
            self.node.sdo.MAX_RETRIES = 5
            self.node.sdo.RESPONSE_TIMEOUT = 0.3
        # Update internal software information
        self.sw_info = info
        return info

    def reboot(self):
        """Reboot node"""
        self.node.nmt.state = "RESET"

    def reset_comm(self):
        """Reset communication stack of node"""
        self.node.nmt.state = "RESET COMMUNICATION"

    def store_parameter(self):
        """Store parameter to use after storing a parameter"""
        self.node.sdo.download(
            NodeIndexes.STORE_PARAMETER_INDEX,
            NodeIndexes.STORE_PARAMETER_SUBINDEX,
            NodeIndexes.STORE_PARAMETER_COMMAND.to_bytes(length=4, byteorder="little"),
        )

    def erase_external_memory(self):
        """Erase external memory"""
        self.node.sdo.download(
            NodeIndexes.RESTORE_FACTORY_SETTINGS_INDEX,
            NodeIndexes.RESTORE_FACTORY_SETTINGS_SUBINDEX,
            NodeIndexes.ERASE_EXTERNAL_MEMORY_COMMAND.to_bytes(length=4, byteorder="little"),
        )

    def restore_factory_settings(self):
        """Restore factory settings"""
        self.node.sdo.download(
            NodeIndexes.RESTORE_FACTORY_SETTINGS_INDEX,
            NodeIndexes.RESTORE_FACTORY_SETTINGS_SUBINDEX,
            NodeIndexes.RESTORE_FACTORY_SETTINGS_COMMAND.to_bytes(length=4, byteorder="little"),
        )

    def _prepare_calibration_upload(self):
        """Prepare calibration upload"""
        pass

    def upload_dictionary(self, format: str) -> TextIOWrapper:
        """Retrieve dictionary and return a TextIOWrapper"""
        if format == "xml":
            # XML default location
            index = XML_ZIP_INDEX
        elif format == "eds":
            index = EDS_ZIP_INDEX
        else:
            raise ValueError("Unknown location for dictionary")

        logger.info(f"Downloading zipped {format} dictionary from node {self.node.id} at {index}")
        fp = self.node.sdo.open(index=index, mode="rb", block_transfer=True)
        zip = zipfile.ZipFile(BytesIO(fp.read()))
        return TextIOWrapper(zip.open(zip.namelist()[0], encoding="ascii"))


class WattLocalNode(canopen.LocalNode):
    def __init__(
        self,
        node_id: int,
        object_dictionary: Union[canopen.objectdictionary.ObjectDictionary, str],
        controller: WattNodeController = None,
    ):
        super().__init__(node_id, object_dictionary)
        # Add a node controller
        self.controller: WattNodeController = WattNodeController(self) if controller is None else controller

        self._sw_info: NodeInformation = None

    def _prepare_calibration_upload(self):
        """Prepare the node for calibrations upload"""
        pass

    @property
    def sw_info(self):
        return self._sw_info

    @sw_info.setter
    def sw_info(self, sw_info: NodeInformation):
        """Software information of node"""
        self._sw_info = sw_info

    def __str__(self):
        return f"WattLocalNode id : {self.id}"


class WattRemoteNode(canopen.RemoteNode):
    def __init__(
        self,
        node_id: int,
        object_dictionary: Union[canopen.objectdictionary.ObjectDictionary, str, None],
        load_od=False,
        controller: WattNodeController = None,
    ):
        super().__init__(node_id, object_dictionary, load_od)
        # Add a node controller
        self.od_path: str = object_dictionary if isinstance(object_dictionary, str) else None
        self.controller: WattNodeController = WattNodeController(self) if controller is None else controller
        # 5 default retries
        self.sdo.MAX_RETRIES = 5

        self._sw_info = None

    @property
    def sw_info(self):
        return self._sw_info

    @sw_info.setter
    def sw_info(self, sw_info: NodeInformation):
        """Software information of node"""
        self._sw_info = sw_info

    def _prepare_calibration_upload(self):
        """Prepare the node for calibrations upload"""

    def __str__(self):
        return f"WattRemoteNode id : {self.id}"
