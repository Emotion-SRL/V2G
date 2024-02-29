# Create an image of all the nodes on the bus
import json
import pathlib
from typing import List, Dict, Tuple
import logging

from watt_node_v2.node.base import WattRemoteNode, WattNodeController
from watt_node_v2.node.datatypes import (
    NodeInformation,
    NodeType,
    NodeInformation,
)
from ..network import ScanResult, read_nodes_info
from dataclasses import asdict, dataclass
from ..features.calibration import (
    CALIBRATABLE_TYPES,
    CalibrationRegisterData,
    NodeCalibrationData,
    CalibrationModule,
)

logger = logging.getLogger(__name__)


@dataclass
class Backup:
    scan_result: ScanResult
    calibrations: List[Tuple[int, NodeCalibrationData]]

    def export_json(self, filename: str, backup_path: pathlib.Path) -> None:
        """Export backup to JSON file"""
        backup_dict = {}
        for node_info in self.scan_result.node_info_list:
            backup_dict[node_info.id] = {"node_information": asdict(node_info)}
        for calibration in self.calibrations:
            backup_dict[calibration[0]]["calibrations"] = asdict(calibration[1])["calibrations"]
        with open(backup_path.joinpath(filename), "w") as outfile:
            json.dump(backup_dict, outfile, indent=4)

    def get_calibration(self, node_id: int) -> NodeCalibrationData:
        """Get node calibration of specific node id"""
        node_id, calibration = next(
            calibration for calibration in self.calibrations if calibration[0] == node_id
        )
        return calibration


def create_backup(nodes: List[WattRemoteNode]) -> Backup:
    """Create a backup from a list of controllers to backup :
    Generate a file containing nodes information (node ids, node versions, node calibrations)
    """
    calibrations = []

    # Read all the software information
    scan_result = read_nodes_info(nodes)
    calibratable_nodes: List[WattRemoteNode] = []
    for node in nodes:
        # Get the type of each node & check if calibratable
        node_type = scan_result[node.id].type
        if node_type in CALIBRATABLE_TYPES:
            calibratable_nodes.append(node)
    # Then get all the calibrations (of calibratable nodes)
    calibration_module = CalibrationModule()
    for node in calibratable_nodes:
        calibration_module.import_from_controller(WattNodeController(node))
        calibrations.append((node.id, calibration_module.node_calibration))

    # Then finally construct the backup
    return Backup(scan_result=scan_result, calibrations=calibrations)


def import_backup(backup_to_import: pathlib.Path):
    """Import a backup file"""
    node_information_list: List[NodeInformation] = []
    calibrations = []
    with open(backup_to_import, "r") as f:
        backup_dict: Dict = json.load(f)
        for node_id, value in backup_dict.items():
            node_information: Dict = value["node_information"]
            if "state" in node_information:
                nmt_state = node_information.pop("state", "")
            elif "nmt_state" in node_information:
                nmt_state = node_information.pop("nmt_state", "")
            else:
                nmt_state = ""
            node_type = NodeType(node_information.pop("type"))
            # Retreive other values
            id = int(node_information.pop("id", int(node_id)))
            node_info = NodeInformation(**node_information, type=node_type, nmt_state=nmt_state, id=id)
            node_information_list.append(node_info)
            # Create a correctly formated dictionary for calibrations
            node_calibration_data = NodeCalibrationData(
                node_software_information=node_info,
                calibrations=[
                    CalibrationRegisterData(el["calibration_data"], el["calibration_index_name"])
                    for el in value["calibrations"]
                ],
            )
            calibrations.append((id, node_calibration_data))
        return Backup(
            scan_result=ScanResult(node_info_list=node_information_list),
            calibrations=calibrations,
        )
