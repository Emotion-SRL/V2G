# Programmer for programming nodes
import itertools
import logging
import pathlib
import time
from typing import Callable, Dict, List, Tuple, Union
import copy

import canopen
from canopen.nmt import NmtError
from canopen.objectdictionary import import_od
from ..node.datatypes import (
    BOOTLOADER_IDS,
    NodeInformation,
    NodeType,
    TYPE_STR_TO_NODETYPE,
)
from .backup import Backup, create_backup
from ..ui import BaseUI, UITerminalAdapter
from ..network import Network, read_nodes_info, ScanResult
from ..node.base import WattRemoteNode, WattNodeController
from ..node.bootloader.bootloader import BootloaderController
from ..node.factory import create_remote_node

from watt_node_v2.features.calibration import CALIBRATION_SUCCESS, calibrate_controller
from ..node.factory_controller import ControllerFactory
from .exceptions import (
    ERROR_BOOTLOADER_ALREADY_ON_NETWORK,
    ERROR_BOOTLOADER_NOT_FOUND,
    ERROR_CREATING_BACKUP,
    ERROR_CURRENT_EDS_NOT_FOUND,
    ERROR_CURRENT_FIRMWARE_NOT_FOUND,
    ERROR_DOWNLOADING_CALIBRATIONS,
    ERROR_INCONSISTENT_NODE_TYPE,
    ERROR_NODE_ALREADY_ON_NETWORK,
    ERROR_NODE_NOT_RESPONDING_AFTER_REPROGRAM,
    ERROR_READING_NODE_INFORMATION,
    ERROR_RESTORING_FACTORY_SETTINGS,
    ERROR_UNABLE_TO_DETERMINE_NODE_ID,
    ERROR_UPDATE_EDS_NOT_FOUND,
    ERROR_UPDATE_FIRMWARE_NOT_FOUND,
    ProgrammerException,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 10
PFC_DCDC_OFFSET = 32


class ProgrammerConfigParser:
    """Programming configuration handler"""

    def __init__(self, scan: ScanResult) -> None:
        self.scan = scan
        self._individual_node_config_list: List[Tuple[int, NodeInformation]] = []
        self._type_node_config_list: List[Tuple[NodeType, NodeInformation]] = []

    def clear(self):
        """Clear the loaded configuration"""
        self._individual_node_config_list = []
        self._type_node_config_list = []

    def load(self, config: Dict) -> None:
        """Load the configuration, and parse it"""
        # Get single node configuration
        self.clear()
        try:
            for node in config["nodes_config"]:
                try:
                    type = TYPE_STR_TO_NODETYPE[node["node_type"]]
                except KeyError:
                    logger.error("Invalid type given")
                    raise
                id = int(node["node_id"])
                sw_version = node["sw_version"]
                sw_build = node["sw_build"]
                to_program = node.get("program", True)
                if to_program:
                    self._individual_node_config_list.append(
                        (
                            id,
                            NodeInformation(
                                sw_version=sw_version,
                                sw_build=sw_build,
                                device_name=None,
                                type=type,
                            ),
                        )
                    )
        except KeyError:
            # No individual node configuration given
            pass
        # Get all nodes configuration
        for node_type in ["evis", "mpu", "bmpu", "mpu-r2"]:
            try:
                sw_version = config["all_nodes_config"][node_type + "_sw_version"]
                sw_build = config["all_nodes_config"][node_type + "_sw_build"]
                self._type_node_config_list.append(
                    (
                        TYPE_STR_TO_NODETYPE[node_type],
                        NodeInformation(sw_version=sw_version, sw_build=sw_build, type=node_type),
                    )
                )
            except KeyError:
                logger.info(f"No configuration found for all {node_type}")
                pass

        if self._individual_node_config_list == [] and self._type_node_config_list == []:
            raise ValueError("Configuration is wrong or is empty")

    def calculate_desired_versions(self) -> List[Tuple[int, NodeInformation]]:
        """Calculate the desired nodes to update with the desired software versions and builds
        the individual "nodes_config" array takes precedence over the all_nodes_config
        """
        results: Dict[int, NodeInformation] = {}
        for node_type, sw_info in self._type_node_config_list:
            # Get all the nodes of the specified types, and add the same sw update information
            node_ids = self.scan.get_nodes_by_type([node_type])
            for id in node_ids:
                results[id] = sw_info
        # Individual configurations can overwrite global configs
        for id, sw_info in self._individual_node_config_list:
            results[id] = sw_info
        return list(results.items())


def parse_toml(toml_dict) -> List[Tuple[int, NodeInformation]]:
    """Parse toml takes a toml dict configuration and returns a list node ids and their software information"""
    sw_info_list: List[Tuple[int, NodeInformation]] = []
    for node in toml_dict["nodes_config"]:
        try:
            type = TYPE_STR_TO_NODETYPE[node["node_type"]]
        except KeyError:
            logger.error("Invalid type given")
            raise
        id = int(node["node_id"])
        sw_version = node["sw_version"]
        sw_build = node["sw_build"]
        to_program = node.get("program", True)
        if to_program:
            sw_info_list.append(
                (
                    id,
                    NodeInformation(
                        sw_version=sw_version,
                        sw_build=sw_build,
                        device_name=None,
                        type=type,
                    ),
                )
            )
    return sw_info_list


def parse_backup(backup: Backup) -> List[Tuple[int, NodeInformation]]:
    """Parse backup for a programming sequence"""
    future_nodes_info = []
    for node_info in backup.scan_result.node_info_list:
        future_nodes_info.append((node_info.id, node_info))
    return future_nodes_info


class WattDeviceProgrammer:
    """Class for reprogramming W&W devices."""

    MONITORING_NODE_ID = 0x5

    def __init__(
        self,
        network: Network,
        ui: BaseUI = BaseUI(UITerminalAdapter()),
        allow_same_version: bool = False,
        create_node: Callable[
            [int, canopen.objectdictionary.ObjectDictionary], WattRemoteNode
        ] = create_remote_node,
        disable_nodes: bool = False,
        max_programming_retries: int = 10,
        controller_factory: ControllerFactory = ControllerFactory(),
    ):
        self.network = network
        self.ui = ui
        self.allow_same_version = allow_same_version
        self.create_node = create_node
        self.disable_nodes = disable_nodes
        self.max_programming_retries = max_programming_retries
        self.controller_factory = controller_factory
        self._db = network.db_handler
        self.bootloader_controller: Dict[int, BootloaderController] = {}
        self.devices: Dict[int, List[WattNodeController]] = {}

        self.future_sw_dict: Dict[int, NodeInformation] = {}
        self.monitoring_controller: WattNodeController = self._create_controller(id=0x05, skip_read=True)
        self._add_bootloaders()

    def __enter__(self):
        """Context manager for programmer"""
        if self.disable_nodes:
            logger.info("Putting all nodes in pre-operational")
            self.network.nmt.state = "PRE-OPERATIONAL"
        logger.info("Disabling node monitoring")
        self.monitoring_controller.node.nmt.state = "STOPPED"
        return self

    def __exit__(self, type, value, traceback):
        logger.info("All nodes will be rebooted in 1 second")
        time.sleep(1)
        self.network.nmt.state = "RESET"

    def _add_bootloaders(
        self,
    ) -> None:
        """Add addressable bootloaders to programmer"""
        for id in BOOTLOADER_IDS:
            if not id in self.network:
                logger.info(f"Adding remote node {id} to bootloaders")
                self.network.add_node(self.create_node(id, None))
            self.bootloader_controller[id] = BootloaderController(self.network[id])

    def _create_controller(self, id: int, skip_read: bool = False) -> WattNodeController:
        """Create device controller for programmer"""
        if not id in self.network:
            logger.info(f"Adding remote node {id} to network")
            self.network.add_node(self.create_node(id, None))
        generic_controller = WattNodeController(self.network[id])
        if skip_read:
            return generic_controller
        try:
            logger.info(f"Reading {generic_controller.node.id}")
            generic_controller.read_software_information()
        except canopen.sdo.exceptions.SdoError:
            raise ProgrammerException(error=ERROR_READING_NODE_INFORMATION)
        controller = self.controller_factory.create_controller_for_type(
            type=generic_controller.sw_info.type, node=generic_controller.node
        )
        controller.sw_info = generic_controller.sw_info
        return controller

    def _prepare_controller_upgrade(
        self, controller: WattNodeController, future_sw_info: NodeInformation
    ) -> None:
        """Check that the associated node is on the bus"""
        current_sw_info = controller.sw_info
        future_sw_info.type = current_sw_info.type
        self._check_sw_info(current_sw_info, future_sw_info)
        # If no exceptions are raised then add od to remote node
        self._update_node_od(controller, current_sw_info)
        # Add the sw info the future_sw info dict
        self.future_sw_dict[controller.node.id] = copy.deepcopy(future_sw_info)

    def _update_node_od(self, controller: WattNodeController, new_sw_info: NodeInformation) -> None:
        """Update node object dictionnary
        This is used when node firmware is updated because id is the same
        but EDS changes
        """
        new_od = import_od(str(self._db.get_eds(new_sw_info)))
        controller.node.object_dictionary = new_od
        controller.node.sdo.od = new_od

    def _add_device(self, id: int, future_sw_info: NodeInformation) -> List[WattNodeController]:
        """Adds device to the device dict to program (can be a single or double controller) and returns it"""
        controllers: List[WattNodeController] = []
        controller = self._create_controller(id)
        self._prepare_controller_upgrade(controller, future_sw_info)
        controllers.append(controller)
        if controller.sw_info.type in [NodeType.bmpu_pfc, NodeType.mpu_r2_pfc]:
            # Also create a second controller
            other_controller = self._create_controller(id - PFC_DCDC_OFFSET)
            self._prepare_controller_upgrade(other_controller, future_sw_info)
            controllers.append(other_controller)
        for controller in controllers:
            self.ui.adapter.display(
                f"Will upgrade {controller.node.id} | {controller.sw_info} ==> {self.future_sw_dict[controller.node.id]} "
            )
        self.devices[id] = controllers

    def _start_reprogram(self, allow_bootloader: bool) -> None:
        """Before programming any node, make sure that no bootloader is on the network"""
        if self.network.scanner.is_bootloader_active() and not allow_bootloader:
            raise ProgrammerException(ERROR_BOOTLOADER_ALREADY_ON_NETWORK)

    def _finish_reprogram(self, controller: WattNodeController, store_param: bool = False) -> None:
        # First step is to check that node is responding
        self.ui.adapter.display(f"Checking that {controller.node.id} is responding")
        try:
            controller.ping()
            self.ui.adapter.display(f"{controller.node.id} is responding")
        except canopen.sdo.exceptions.SdoError:
            raise ProgrammerException(ERROR_NODE_NOT_RESPONDING_AFTER_REPROGRAM)

        # Then check that we can restore factory settings
        try:
            self.ui.adapter.display("Restoring factory settings")
            controller.restore_factory_settings()
        except canopen.sdo.exceptions.SdoError as e:
            logger.error(f"Error restoring factory settings : {e}")
            raise ProgrammerException(ERROR_RESTORING_FACTORY_SETTINGS)
        time.sleep(0.5)
        # Store parameters optionally (in case no calibration is done afterwards)
        if store_param:
            controller.store_parameter()
            time.sleep(0.5)
        # Once restored the second step is to reboot and try to communicate with the device
        self.ui.adapter.display("Rebooting")
        controller.reboot()
        # Add a little delay after finish reprogram to let the node boot
        time.sleep(1.0)

    def _get_active_bootloader_controller(
        self,
        bootloader_id: Union[int, None] = None,
    ) -> BootloaderController:
        """Get the first current active bootloader on the network or given bootloader id"""
        if bootloader_id is not None:
            # Ping the bootloader
            try:
                self.bootloader_controller[bootloader_id].ping()
            except canopen.sdo.exceptions.SdoError as e:
                raise ProgrammerException(excpt=e, error=ERROR_BOOTLOADER_NOT_FOUND)
            return self.bootloader_controller[bootloader_id]
        else:
            # Otherwise try 126 and 125
            for bootloader_id in BOOTLOADER_IDS:
                try:
                    self.bootloader_controller[bootloader_id].ping()
                except canopen.sdo.exceptions.SdoError:
                    logger.info(f"Bootloader id {bootloader_id} not responding")
                    pass
                else:
                    return self.bootloader_controller[bootloader_id]
        raise ProgrammerException(error=ERROR_BOOTLOADER_NOT_FOUND)

    def _check_sw_info(
        self,
        current_sw_info: NodeInformation,
        future_sw_info: NodeInformation,
    ) -> WattRemoteNode:
        """Check presence of necessary files"""
        if current_sw_info is not None:
            try:
                self._db.get_firmware(current_sw_info)
            except FileNotFoundError:
                raise ProgrammerException(error=ERROR_CURRENT_FIRMWARE_NOT_FOUND)
            try:
                self._db.get_eds(current_sw_info)
            except FileNotFoundError:
                raise ProgrammerException(error=ERROR_CURRENT_EDS_NOT_FOUND)
        try:
            self._db.get_firmware(future_sw_info)
        except FileNotFoundError:
            raise ProgrammerException(error=ERROR_UPDATE_FIRMWARE_NOT_FOUND)
        try:
            self._db.get_eds(future_sw_info)
        except FileNotFoundError:
            raise ProgrammerException(error=ERROR_UPDATE_EDS_NOT_FOUND)

    def _get_node_in_bootloader(self, backup: Backup) -> int:
        """Determine the node id of node that is supposed to be in bootloader and return the associated id"""
        self.ui.adapter.display("Starting network scan")
        # First thing to do is scan the network in slow mode in case some frames are missed :
        detected_node_ids = self.network.scan(fast=False, ui=self.ui)
        logger.error(detected_node_ids)
        detected_nodes = []
        # TODO refactor this node creation, this is not the proper place to do this
        # This adds nodes to the network
        for id in detected_node_ids:
            watt_node = self.create_node(id, None)
            detected_nodes.append(watt_node)
            self.network.add_node(watt_node)
        scan_result = read_nodes_info(detected_nodes)
        # # Get all info on nodes
        # Difference should be equal to unknown node id and bootloader id
        difference = backup.scan_result.get_nodes_difference(other_scan_result=scan_result)
        difference.sort()
        # There should be exactly one node difference and a bootloader on network
        if not (len(difference) == 1) or not any(
            id in scan_result.detected_node_ids for id in BOOTLOADER_IDS
        ):
            logger.error(f"Found difference {difference}")
            raise ProgrammerException(ERROR_UNABLE_TO_DETERMINE_NODE_ID)

        expected_id = difference[0]
        self.ui.adapter.display(f"Determined that node id {expected_id} is the node in bootloader")
        return expected_id

    def _calibrate_from_backup(self, controller: WattNodeController, backup: Backup) -> None:
        # Get the corresponding calibrations and calibrate the node
        try:
            calibration = backup.get_calibration(controller.node.id)
            # Calibrate the node
            calibration_result = None
            try:
                self.ui.adapter.display(f"Recalibrating {controller.node.id}")
                calibration_result = calibrate_controller(
                    controller, node_calibration=calibration, reboot=False
                )
                logger.info(f"Finished calibrating {controller.node.id}")
            except Exception as e:
                logger.error(f"Error {e}")
                raise ProgrammerException(excpt=e, error=ERROR_DOWNLOADING_CALIBRATIONS)
            if calibration_result != CALIBRATION_SUCCESS:
                raise ProgrammerException(
                    excpt=f"Calibration result {calibration_result}",
                    error=ERROR_DOWNLOADING_CALIBRATIONS,
                )
        except StopIteration:
            self.ui.adapter.display(f"No calibration was found for {controller.node.id}")

    def _create_backup(
        self,
        devices: Dict[int, List[WattNodeController]],
        backup_output_path: pathlib.Path,
    ) -> Backup:
        """This helper function creates a backup from a list of controllers and also exports it"""
        controllers = list(itertools.chain.from_iterable(list(devices.values())))
        try:
            backup = create_backup([controller.node for controller in controllers])
            backup.export_json("", backup_path=backup_output_path)
        except Exception as e:
            raise ProgrammerException(excpt=e, error=ERROR_CREATING_BACKUP)
        self.ui.adapter.display(f"Backup created successfully and stored in {backup_output_path}")
        return backup

    def _reprogram(self, controller: WattNodeController, backup: Backup, end: bool = False):
        """Reprogram a node and recalibrate, without bootloader checks"""
        future_sw_info = self.future_sw_dict[controller.node.id]
        self.ui.adapter.display(f"Reprogramming {controller.node.id} ==> {future_sw_info}")
        self.reprogram_node(
            controller,
            future_sw_info.sw_version,
            future_sw_info.sw_build,
            bypass_checks=True,
        )
        # Before calibrating reload eds then calibrate
        self._update_node_od(controller, future_sw_info)
        self._calibrate_from_backup(controller, backup)
        # Keep the node in pre-operational
        if self.disable_nodes and not end:
            logger.info("Re-Puting node in pre-operational")
            controller.node.nmt.state = "PRE-OPERATIONAL"
        else:
            logger.info("Not resetting because last node that is being programmed")

    def recover_node(
        self,
        controller: Union[int, WattNodeController, None],
        sw_version: str,
        sw_build: int,
        node_type: NodeType,
        bootloader_id: Union[int, None] = None,
    ) -> WattNodeController:
        """
        Recover a node, from a bootloader state.
        """
        if isinstance(controller, int):
            # Skip reading because node is not online by definition
            controller = self._create_controller(controller, skip_read=True)
            try:
                controller.ping()
            except canopen.sdo.exceptions.SdoError as e:
                pass
            else:
                raise ProgrammerException(error=ERROR_NODE_ALREADY_ON_NETWORK)
        future_sw_info = NodeInformation(sw_version=sw_version, sw_build=sw_build, type=node_type)
        self._check_sw_info(None, future_sw_info)
        self._start_reprogram(allow_bootloader=True)
        bootloader_controller = self._get_active_bootloader_controller(bootloader_id)
        # Program from the bootloader
        bootloader_controller.download_fw(
            firmware_path=self._db.get_firmware(future_sw_info),
            max_retries=self.max_programming_retries,
        )
        # Check that node responds after programming (if programming is done but the node id of the node after boot is not known then skip this part
        # This is unsafe)
        if controller is None:
            logger.warning("No node given to recover, skipping checks (this is unsafe)")
            self.ui.adapter.display("No node given to recover, skipping checks (this is unsafe)")
        else:
            try:
                controller.node.nmt.wait_for_heartbeat(timeout=10)
            except NmtError:
                raise ProgrammerException(ERROR_NODE_NOT_RESPONDING_AFTER_REPROGRAM)
            # Finish reprogram and store parameters even if no calibrations are supplied
            self._finish_reprogram(controller, store_param=True)
        return controller

    def reprogram_node(
        self,
        controller: Union[int, WattNodeController],
        sw_version: str,
        sw_build: int,
        bootloader_id: Union[int, None] = None,
        bypass_checks: bool = False,
    ) -> WattNodeController:
        """
        Reprogram a node given the software build and software version, return the associated controller
        This does not take care of saving calibrations
        """
        if isinstance(controller, int):
            controller = self._create_controller(controller)
            future_sw_info = NodeInformation(sw_version=sw_version, sw_build=sw_build, type=None)
            self._prepare_controller_upgrade(controller, future_sw_info)
        else:
            future_sw_info = NodeInformation(
                sw_version=sw_version, sw_build=sw_build, type=controller.sw_info.type
            )
        current_sw_info = controller.sw_info
        # Return if same version and same version not allowed
        if not self.allow_same_version and (future_sw_info == current_sw_info):
            logger.info("Reprogramming the same version is not allowed")
            return controller
        # Check that no node is in bootloader and prepare the network. (disable sync)
        if not bypass_checks:
            self._start_reprogram(allow_bootloader=False)
        else:
            logger.warning(
                "Bypassing network checks before programming (should only be done if reprogram node has already been called"
            )
        # Make it jump in bootloader
        controller.jump_into_bootloader()
        bootloader_controller = self._get_active_bootloader_controller(bootloader_id=bootloader_id)
        bootloader_controller.download_fw(
            self._db.get_firmware(future_sw_info),
            max_retries=self.max_programming_retries,
        )

        # Check that node responds after programming
        try:
            controller.node.nmt.wait_for_heartbeat(timeout=10)
        except NmtError:
            raise ProgrammerException(ERROR_NODE_NOT_RESPONDING_AFTER_REPROGRAM)
        self._finish_reprogram(controller)
        return controller

    def reprogram_nodes(
        self,
        node_info_list: List[Tuple[int, NodeInformation]],
        backup: Union[Backup, None] = None,
        backup_output_path: Union[pathlib.Path, None] = None,
    ) -> None:
        """Reprogram nodes with specific software versions and backup file"""
        # ---------------------------------------------------------------------------- #
        #                            Safety bootloader check                           #
        # ---------------------------------------------------------------------------- #
        self.ui.adapter.display("Checking if network is in a valid state (no nodes in bootloader)")
        if self.network.scanner.is_bootloader_active():
            if backup is None:
                raise ProgrammerException(error=ERROR_BOOTLOADER_ALREADY_ON_NETWORK)
            else:
                self.ui.adapter.display("Bootloader found, will try to recover the node from backup")
                expected_id = self._get_node_in_bootloader(backup)
                node_info = backup.scan_result[expected_id]
                recoverd_node_controller = self.recover_node(
                    expected_id,
                    sw_version=node_info.sw_version,
                    sw_build=node_info.sw_build,
                    node_type=node_info.type,
                )
                self.ui.adapter.display(f"Finished recovering {expected_id}")
                # Udate the node with new object dictionary
                self._update_node_od(
                    recoverd_node_controller,
                    NodeInformation.from_node_information(node_info),
                )
                self._calibrate_from_backup(recoverd_node_controller, backup)
                recoverd_node_controller.node.nmt.state = "PRE-OPERATIONAL"
                # Remove the programmed node from the list
                node_info_list = [(id, sw_info) for (id, sw_info) in node_info_list if id != expected_id]
        if self.network.scanner.is_bootloader_active():
            raise ProgrammerException(error=ERROR_BOOTLOADER_ALREADY_ON_NETWORK)

        # Program the first node, this is different because we won't check for bootloader afterwards
        self.ui.adapter.display("Starting reprogramming multiple nodes")
        # ---------------------------------------------------------------------------- #
        #                      Peform checks and add to devices                        #
        # ---------------------------------------------------------------------------- #
        self.devices = {}
        self.future_sw_dict = {}
        for id, future_sw_info in node_info_list:
            self._add_device(id, future_sw_info)
        # ---------------------------------------------------------------------------- #
        #                           Create a backup if needed                          #
        # ---------------------------------------------------------------------------- #
        if backup is None:
            self.ui.adapter.display("Creating a backup file before programming.")
            backup = self._create_backup(self.devices, backup_output_path=backup_output_path)
        else:
            self.ui.adapter.display(f"Will use the given backup to re-calibrate the nodes")
        # ---------------------------------------------------------------------------- #
        #                               reprogram devices                              #
        # ---------------------------------------------------------------------------- #
        # Get controller list from list of lists
        controllers = sum(self.devices.values(), [])
        last_controller = controllers.pop()
        for controller in controllers:
            self._reprogram(controller, backup)
        # Last device is programmed without re putting all nodes in pre-op
        self._reprogram(last_controller, backup, end=True)
        self.ui.adapter.display("All nodes have been reprogrammed with success !")
