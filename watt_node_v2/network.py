from typing import Union, List, Dict, Optional, Any
import time
import csv
import platform
import pathlib
import logging
import concurrent.futures
from dataclasses import dataclass, field, asdict

import can
import canopen
from canopen import nmt
from canopen.nmt import NmtError
from canopen.objectdictionary import ObjectDictionary


from .node.base import WattRemoteNode
from .features.calibration import CALIBRATABLE_NODES
from .features.logging import DUMPABLE_NODES

from .node.base import WattNodeController
from .node.datatypes import (
    BOOTLOADER_IDS,
    BMPU_DCDC_IDS,
    NodeInformation,
    PM_IDS,
    SUP_IDS,
    MPU_IDS,
    BMPU_IDS,
    CS_IDS,
    PM_IDS,
    PM_ID_TO_NAME,
    NodeType,
    REAL_NODE_TYPES,
)
from .db import DBHandler
from . import ui
from .local_node import LocalNode

KVASER_CONFIG = {"bustype": "kvaser", "bitrate": 500000, "channel": 0}
KVASER_CONFIG_NO_VIRTUAL = {
    "bustype": "kvaser",
    "bitrate": 500000,
    "channel": 0,
    "accept_virtual": False,
}
SOCKET_CAN_CONFIG = {"bustype": "socketcan", "bitrate": 500000, "channel": "can0"}
KVASER_CONFIG_RECEIVE_OWN = {
    "bustype": "kvaser",
    "bitrate": 500000,
    "channel": 0,
    "receive_own_messages": True,
}
VIRTUAL_CONFIG = {"bustype": "kvaser", "bitrate": 500000, "channel": 0}

logger = logging.getLogger(__name__)


class Network(canopen.Network):
    """Network for using watt nodes, acts similarly as the basic canopen.Network,
    with the possibility of creating nodes directly from a dictionnary"""

    def __init__(
        self,
        db_handler: DBHandler,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.db_handler = db_handler
        self.scanner = AdvancedNodeScanner(self)

    def __setitem__(self, node_id: int, node: Union[canopen.RemoteNode, canopen.LocalNode]):
        assert node_id == node.id
        if node_id in self.nodes:
            # Remove old callbacks # PR 342 on github
            self.nodes[node_id].remove_network()
        self.nodes[node_id] = node
        node.associate_network(self)

    def connect(self, *args, **kwargs) -> "Network":
        """Connect to CAN bus using python-can.

        Arguments are passed directly to :class:`can.BusABC`. Typically these
        may include:

        :param channel:
            Backend specific channel for the CAN interface.
        :param str bustype:
            Name of the interface. See
            `python-can manual <https://python-can.readthedocs.io/en/stable/configuration.html#interface-names>`__
            for full list of supported interfaces.
        :param int bitrate:
            Bitrate in bit/s.

        :raises can.CanError:
            When connection fails.
        """
        # If bitrate has not been specified, try to find one node where bitrate
        # has been specified
        if "bitrate" not in kwargs:
            for node in self.nodes.values():
                if node.object_dictionary.bitrate:
                    kwargs["bitrate"] = node.object_dictionary.bitrate
                    break
        self.bus = can.thread_safe_bus.ThreadSafeBus(*args, **kwargs)
        logger.info("Connected to '%s'", self.bus.channel_info)
        self.notifier = can.Notifier(self.bus, self.listeners, 1)
        return self

    def create_node(
        self, node: int, object_dictionary: Union[str, ObjectDictionary, None] = None
    ) -> LocalNode:
        """Create and add a node to the network"""
        local_node = LocalNode(node, object_dictionary)
        self[node] = local_node
        return local_node

    def scan(self, ui: ui.BaseUI, fast=True) -> List[int]:
        """Scan the network and return all the node ids that have been detected.
        Detected IDs can be real or fake nodes (for example PM uses multiple nodes to increase PDOs)
        """
        total = 0
        ui.display_progress(0, 127, prefix="Scanning", suffix="Complete")
        for iteration in range(127):
            sdo_req = b"\x40\x00\x10\x00\x00\x00\x00\x00"
            self.send_message(0x600 + iteration, sdo_req)
            if fast:
                time.sleep(0.01)
            else:
                time.sleep(0.1)
            total += 1
            ui.display_progress(iteration, 127, prefix="Scanning", suffix="Complete")
        print("")
        return self.scanner.nodes


class AdvancedNodeScanner(object):
    """Observes which nodes are present on the bus.
    Listens for the following messages:
     - Heartbeat (0x700)
     - SDO response (0x580)
     - TxPDO (0x180, 0x280, 0x380, 0x480)
     - EMCY (0x80)
    :param canopen.Network network:
        The network to use when doing active searching.
    """

    #: Activate or deactivate scanning
    active = True

    SERVICES = (0x700, 0x580, 0x180, 0x280, 0x380, 0x480, 0x80)

    def __init__(self, network: Optional[Network] = None):
        self.network = network
        #: A :class:`list` of nodes discovered
        self.nodes: List[int] = []

    def on_message_received(self, can_id: int):
        service = can_id & 0x780
        node_id = can_id & 0x7F
        if node_id not in self.nodes and node_id != 0 and service in self.SERVICES:
            self.nodes.append(node_id)

    def reset(self):
        """Clear list of found nodes."""
        self.nodes = []

    def search(self, limit: int = 127) -> None:
        """Search for nodes by sending SDO requests to all node IDs."""
        if self.network is None:
            raise RuntimeError("A Network is required to do active scanning")
        sdo_req = b"\x40\x00\x10\x00\x00\x00\x00\x00"
        for node_id in range(1, limit + 1):
            self.network.send_message(0x600 + node_id, sdo_req)

    def _is_alive(self, id: int):
        """Checks wether a node is alive by pinging it and waiting for a hearbeat"""
        if not id in self.network:
            node = WattRemoteNode(id, None)
            self.network.add_node(node)
        node: WattRemoteNode = self.network[id]
        controller = WattNodeController(node)
        try:
            controller.ping()
        except canopen.sdo.exceptions.SdoError:
            pass
        else:
            return True
        try:
            node.nmt.wait_for_heartbeat(1.5)
        except nmt.NmtError:
            return False
        else:
            return True

    def is_bootloader_active(self) -> bool:
        """Check if bootloader is active on the network"""
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [executor.submit(self._is_alive, id) for id in BOOTLOADER_IDS]
            results = [future.result() for future in futures]
            return any(results)

    def get_calibratable_nodes(self) -> List[int]:
        """Get nodes that are calibratable"""
        return list(set(self.nodes).intersection(CALIBRATABLE_NODES))

    def get_dumpable_nodes(self) -> List[int]:
        """Get nodes that are dumpable"""
        return list(set(self.nodes).intersection(DUMPABLE_NODES))


@dataclass
class ScanResult:
    host_platform: str = None
    node_info_list: List[NodeInformation] = field(default_factory=list)

    def __post_init__(self):
        # Sort the results
        self.node_info_list.sort(key=lambda node_info: node_info.id)

    def export_csv(self, output_file: pathlib.Path) -> None:
        """Export the results to a CSV file"""
        with open(output_file, "w", newline="") as outfile:
            writer = csv.writer(outfile)
            writer.writerow(
                [
                    "Node ID",
                    "Node ID (hex)",
                    "Device name",
                    "Serial number",
                    "Software version",
                    "Software Build Nb",
                    "Hardware revision",
                    "NMT state",
                ]
            )
            for node_info in self.node_info_list:
                writer.writerow(
                    [
                        node_info.id,
                        hex(node_info.id),
                        node_info.device_name,
                        node_info.serial_nb,
                        node_info.serial_nb,
                        node_info.sw_version,
                        node_info.sw_build,
                        node_info.hardware_revision,
                        node_info.nmt_state,
                    ]
                )

    @property
    def detected_node_ids(self) -> List[int]:
        """Return only the ids"""
        return [node_info.id for node_info in self.node_info_list]

    def __getitem__(self, node_id: int):
        """Returns the node information based on the node id"""
        for node_info in self.node_info_list:
            if node_info.id == node_id:
                return node_info
        raise KeyError(f"id {node_id} not present in scan result")

    def __len__(self):
        """Returns length of the node_info_list"""
        return len(self.node_info_list)

    def get_nb_valid_nodes(self):
        """Get nb of valid nodes in scan"""
        # TODO remove this is deprecated
        return len(self)

    def get_nodes_by_type(self, node_types: List[NodeType] = REAL_NODE_TYPES) -> List[int]:
        """Returns all the nodes that are nodes of the given node types, by default this returns W&W nodes"""
        return [node_info.id for node_info in self.node_info_list if node_info.type in node_types]

    def get_nodes_difference(self, other_scan_result: "ScanResult") -> List[int]:
        """Get node id that are in this scan result but not the other scan result
        This only applies on "real" W&W nodes
        """
        other_real_ids = other_scan_result.get_nodes_by_type(REAL_NODE_TYPES)
        this_real_ids = self.get_nodes_by_type(REAL_NODE_TYPES)

        return [id for id in this_real_ids if id not in other_real_ids]

    def to_dict(self) -> Dict[int, Dict[str, Any]]:
        """Convert to a dictionary with ids as the keys"""
        result_dict = {}
        for node_info in self.node_info_list:
            result_dict[node_info.id] = asdict(node_info)
        return result_dict


def read_controller_info(controller: WattNodeController):
    """This read controller information, will be changed in the future to use only controller read_software_information"""
    # Create empty NodeInformation, we will fill gradually
    info: NodeInformation = NodeInformation()
    sw_info: NodeInformation = None
    node = controller.node
    info.id = node.id
    # Some nodes aren't real nodes so we need to get this information on the compute module
    # Create a local controller for reading

    if node.id in SUP_IDS:
        try:
            sw_info = controller.read_software_information(timeout=0.01)
        except (canopen.sdo.SdoCommunicationError, canopen.sdo.SdoAbortedError):
            # If error reading node info supply "supposed" basic information
            # TODO fetch the info somehow
            info.id = node.id
            info.device_name = "SUPERVISOR"
            info.sw_version = ""
            info.sw_build = 0

    elif node.id in PM_IDS:
        try:
            sw_info = controller.read_software_information(timeout=0.01)
        except (canopen.sdo.SdoCommunicationError, canopen.sdo.SdoAbortedError):
            # If error reading node info supply "supposed" basic information
            # TODO fetch the info somehow
            info.id = node.id
            info.device_name = PM_ID_TO_NAME[node.id]
            info.sw_version = ""
            info.sw_build = 0

    elif node.id in (CS_IDS + MPU_IDS + BMPU_IDS + BMPU_DCDC_IDS + BOOTLOADER_IDS):
        # This should be a real node, so expect to read the correct software information
        try:
            sw_info = controller.read_software_information()
        except canopen.sdo.exceptions.SdoError:
            logger.info(f"Attempting to reset comm stack of {node.id}")
            controller.reset_comm()
            time.sleep(0.5)
            # CANOpen stack should be up by now
            try:
                sw_info = controller.read_software_information()
                logger.info(f"Was able to read {node.id} after a communication reset")
            except canopen.sdo.exceptions.SdoError as e:
                logger.info(
                    f"Couldn't read software information of node {node.id} even after communication reset ({e})"
                )
    else:
        # This should't be a real node device, so try to read but if fails then this is ok
        logger.info(f"{node.id} should'nt be a real node, still trying to read")
        try:
            sw_info = controller.read_software_information(timeout=0.01)
        except (canopen.sdo.SdoCommunicationError, canopen.sdo.SdoAbortedError):
            # If no sdo response is received continue
            pass

    if sw_info != None:
        # We managed to read sw_info so update it
        info.serial_nb = sw_info.serial_nb
        info.device_name = sw_info.device_name
        info.hardware_revision = sw_info.hardware_revision
        info.sw_build = sw_info.sw_build
        info.sw_version = sw_info.sw_version
        info.type = sw_info.type

    # Wait for at least one heartbeat to get node state, some nodes like bmpu dcdc do not have a heartbeat
    try:
        node.nmt.wait_for_heartbeat(1.3)
        info.nmt_state = node.nmt.state
        return info
    except NmtError:
        if sw_info is None:
            # We didn't manage to read software info and we didn't receive any heartbeat so probably not a real node
            return None
        else:
            info.nmt_state = "NO HEARTBEAT RECEIVED"
        return info


def read_node_info(node: WattRemoteNode) -> Union[NodeInformation, None]:
    """[DEPRECTATED]This reads node information and returns a NodeInformation if we get a hearbeat or manage to read software information"""
    # Create empty NodeInformation, we will fill gradually
    info: NodeInformation = NodeInformation()
    sw_info: NodeInformation = None
    info.id = node.id
    # Some nodes aren't real nodes so we need to get this information on the compute module
    # Create a local controller for reading
    controller = WattNodeController(node)

    if node.id in SUP_IDS:
        try:
            sw_info = controller.read_software_information(timeout=0.01)
        except (canopen.sdo.SdoCommunicationError, canopen.sdo.SdoAbortedError):
            # If error reading node info supply "supposed" basic information
            # TODO fetch the info somehow
            info.id = node.id
            info.device_name = "SUPERVISOR"
            info.sw_version = ""
            info.sw_build = 0

    elif node.id in PM_IDS:
        try:
            sw_info = controller.read_software_information(timeout=0.01)
        except (canopen.sdo.SdoCommunicationError, canopen.sdo.SdoAbortedError):
            # If error reading node info supply "supposed" basic information
            # TODO fetch the info somehow
            info.id = node.id
            info.device_name = PM_ID_TO_NAME[node.id]
            info.sw_version = ""
            info.sw_build = 0

    elif node.id in (CS_IDS + MPU_IDS + BMPU_IDS + BMPU_DCDC_IDS + BOOTLOADER_IDS):
        # This should be a real node, so expect to read the correct software information
        try:
            sw_info = controller.read_software_information()
        except canopen.sdo.exceptions.SdoError:
            logger.info(f"Attempting to reset comm stack of {node.id}")
            controller.reset_comm()
            time.sleep(0.5)
            # CANOpen stack should be up by now
            try:
                sw_info = controller.read_software_information()
                logger.info(f"Was able to read {node.id} after a communication reset")
            except canopen.sdo.exceptions.SdoError as e:
                logger.info(
                    f"Couldn't read software information of node {node.id} even after communication reset ({e})"
                )
    else:
        # This should't be a real node device, so try to read but if fails then this is ok
        logger.info(f"{node.id} should'nt be a real node, still trying to read")
        try:
            sw_info = controller.read_software_information(timeout=0.01)
        except (canopen.sdo.SdoCommunicationError, canopen.sdo.SdoAbortedError):
            # If no sdo response is received continue
            pass

    if sw_info != None:
        # We managed to read sw_info so update it
        info.serial_nb = sw_info.serial_nb
        info.device_name = sw_info.device_name
        info.hardware_revision = sw_info.hardware_revision
        info.sw_build = sw_info.sw_build
        info.sw_version = sw_info.sw_version
        info.type = sw_info.type

    # Wait for at least one heartbeat to get node state, some nodes like bmpu dcdc do not have a heartbeat
    try:
        node.nmt.wait_for_heartbeat(1.3)
        info.nmt_state = node.nmt.state
        return info
    except NmtError:
        if sw_info is None:
            # We didn't manage to read software info and we didn't receive any heartbeat so probably not a real node
            return None
        else:
            info.nmt_state = "NO HEARTBEAT RECEIVED"
        return info


def read_nodes_info(nodes: List[WattRemoteNode]) -> "ScanResult":
    """[DEPRECATED]Read detected nodes software information and state"""
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(read_node_info, node) for node in nodes]
        results = [future.result() for future in futures if future.result() is not None]
        return ScanResult(host_platform=platform.system(), node_info_list=results)


def read_controllers_info(controllers: List[WattNodeController]) -> "ScanResult":
    """Read controllers information"""
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(read_controller_info, controller) for controller in controllers]
        results = [future.result() for future in futures if future.result() is not None]
        return ScanResult(host_platform=platform.system(), node_info_list=results)
