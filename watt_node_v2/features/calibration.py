import json
from typing import Dict, List, Union
from dataclasses import dataclass, asdict
from ..node.base import WattLocalNode, WattNodeController, WattRemoteNode
from ..node.datatypes import NodeInformation, NodeNames, NodeType
from ..utils import generic_node_filename_timestamped
import logging
import canopen
import os
from ..node.datatypes import CS_IDS, MPU_IDS, BMPU_IDS

logger = logging.getLogger(__name__)

(
    CALIBRATION_SUCCESS,
    ERROR_INCOMPATIBLE_DEVICE,
    ERROR_READING_CALIBRATIONS,
    ERROR_UPLOADING_CALIBRATIONS,
    ERROR_OBJECT_DICTIONARY,
    ERROR_STORING_PARAMETERS,
) = range(6)

CALIBRATION_ERRORS = {
    CALIBRATION_SUCCESS: "Calibration was uploaded successfully",
    ERROR_INCOMPATIBLE_DEVICE: "This calibration file is incompatible with the device type",
    ERROR_READING_CALIBRATIONS: "Error trying to read calibrations from node",
    ERROR_UPLOADING_CALIBRATIONS: "Error trying to write calibrations to node",
    ERROR_OBJECT_DICTIONARY: "A calibration index does not correspond with the calibration indexes on the node ",
    ERROR_STORING_PARAMETERS: "Storing parameters inside non volatile memory failed",
}

CALIBRATABLE_NODES = CS_IDS + MPU_IDS + BMPU_IDS

CALIBRATABLE_TYPES = [
    NodeType.bmpu_pfc,
    NodeType.bmpu_dcdc,
    NodeType.mpu,
    NodeType.evis,
    NodeType.mpu_r2_pfc,
    NodeType.mpu_r2_dcdc,
]

CALIBRATION_INDEXES = {
    NodeType.bmpu_dcdc: ["calibration"],
    NodeType.bmpu_pfc: ["calibration"],
    NodeType.mpu: ["calibration"],
    NodeType.mpu_r2_pfc: ["calibration"],
    NodeType.mpu_r2_dcdc: ["calibration"],
    NodeType.evis: ["Calibration", "Calibration IMD"],
}


@dataclass
class CalibrationRegisterData:
    """Calibration Data Holder"""

    calibration_data: Dict[str, str]
    calibration_index_name: str

    @classmethod
    def from_node(
        cls,
        node: Union[WattRemoteNode, WattLocalNode],
        calibration_index_name: str,
    ):
        """Create calibration register object from a node, object dictionnary must be loaded"""
        calibration_data_dict = {}
        for subindex in node.sdo[calibration_index_name]:
            variable = node.sdo[calibration_index_name][subindex]
            logger.debug(f"{variable.name}")
            try:
                calibration_data_dict[variable.name] = variable.raw
                logger.debug(f"Read calibation : {variable.name} {variable.raw}")
            except canopen.sdo.SdoAbortedError:
                calibration_data_dict[variable.name] = None
                logger.debug(f"Read calibation : {variable.name} None")
        # Delete first entry, which is read only
        del calibration_data_dict[f"{calibration_index_name}.max sub-index"]
        logger.info(f"{calibration_index_name} created from {node}")
        return cls(
            calibration_data=calibration_data_dict,
            calibration_index_name=calibration_index_name,
        )

    def __str__(self):
        """Print out register data"""
        return_str = f"{self.calibration_index_name}"
        for key, value in self.calibration_data.items():
            return_str += f"\n\t{key} : {value}"
        return return_str


@dataclass
class NodeCalibrationData:
    """Data holder for multiple calibration objects"""

    node_software_information: NodeInformation
    calibrations: List[CalibrationRegisterData]

    def __str__(self):
        return_str = f""
        for calibration in self.calibrations:
            return_str += f"\n{calibration}"
        return return_str

    def subindex_dict(self) -> Dict[str, float]:
        """Return all the calibrations of the registers in the
        form of a dictionnary of subindex and values"""
        rtn_dict = {}
        for calibration in self.calibrations:
            for k, v in calibration.calibration_data.items():
                _, subindex = k.split(".")
                rtn_dict[subindex] = v
        return rtn_dict

    @classmethod
    def _from_old_json(cls, calibrations: Dict[str, List[int]], filename: str) -> "NodeCalibrationData":
        """Import from an old JSON format file"""
        calibration_registers: List[CalibrationRegisterData] = []
        if "BMPUDCDC" in filename:
            calibration_index_name = "calibration"
            calibration_data = {}
            for key, value in calibrations.items():
                calibration_data[calibration_index_name + "." + key] = value[1]
            calibration_registers.append(CalibrationRegisterData(calibration_data, calibration_index_name))
            sw_info = NodeInformation(sw_version="", sw_build=0, device_name=NodeNames.BMPU_DCDC.value)
        elif "BMPU" in filename:
            calibration_index_name = "calibration"
            calibration_data = {}
            for key, value in calibrations.items():
                calibration_data[calibration_index_name + "." + key] = value[1]
            calibration_registers.append(CalibrationRegisterData(calibration_data, calibration_index_name))
            sw_info = NodeInformation(sw_version="", sw_build=0, device_name=NodeNames.BMPU.value)

        elif "MPU25" in filename:
            calibration_index_name = "calibration"
            calibration_data = {}
            for key, value in calibrations.items():
                calibration_data[calibration_index_name + "." + key] = value[1]
            calibration_registers.append(CalibrationRegisterData(calibration_data, calibration_index_name))
            sw_info = NodeInformation(sw_version="", sw_build=0, device_name=NodeNames.MPU25.value)

        elif "EVIS" in filename:
            calibration_index_name_imd = "Calibration IMD"
            calibration_index_name = "Calibration"
            calibration_data_imd = {}
            calibration_data = {}
            for key, value in calibrations.items():
                if "ins_dc" in key:
                    calibration_data_imd[calibration_index_name_imd + "." + key] = value[1]
                else:
                    calibration_data[calibration_index_name + "." + key] = value[1]
            calibration_registers.append(CalibrationRegisterData(calibration_data, calibration_index_name))
            calibration_registers.append(
                CalibrationRegisterData(calibration_data_imd, calibration_index_name_imd),
            )
            sw_info = NodeInformation(sw_version="", sw_build=0, device_name=NodeNames.EVIS.value)
        return cls(sw_info, calibration_registers)

    @classmethod
    def from_node(cls, node: Union[WattRemoteNode, WattLocalNode]):
        controller = WattNodeController(node)
        node_software_information = controller.read_software_information()
        calibrations = []
        # Determine the calibration index names, some old versions can have missing index names
        calibration_index_names = CALIBRATION_INDEXES[node_software_information.type]
        for index_name in calibration_index_names:
            if index_name in node.sdo:
                calibration_reg = CalibrationRegisterData.from_node(node, index_name)
                calibrations.append(calibration_reg)
        return cls(
            calibrations=calibrations,
            node_software_information=node_software_information,
        )

    @classmethod
    def from_json(cls, calibration_path: str):
        """Create calibration object from backup JSON file"""
        with open(calibration_path, "r") as infile:
            calibration_file = json.load(infile)
            try:
                calibration_data: Dict = calibration_file["calibration_data"]
            except KeyError:
                # Problem with loading calibration, try the old format
                logger.warning("Attempting to import via old format")
                _, filename = os.path.split(calibration_path)
                return NodeCalibrationData._from_old_json(calibration_file, filename)
            node_software_information = NodeInformation(**calibration_file["node_software_information"])
        # Recreate calibrations list
        calibrations = []
        for k in calibration_data.keys():
            calibrations.append(
                CalibrationRegisterData(calibration_index_name=k, calibration_data=calibration_data[k])
            )
        logger.info(f"Created calibration object from backup JSON : {calibration_path}")
        return cls(
            calibrations=calibrations,
            node_software_information=node_software_information,
        )

    def to_dict(self):
        return asdict(self)


class CalibrationModule:
    """Management of node calibrations , need eds for accessing"""

    def __init__(self):
        self.node_info: NodeInformation = None
        self.node_calibration: NodeCalibrationData = None

    def _validate_calibration(self, node: WattRemoteNode) -> bool:
        """Validate that calibration between node and calibration data is valid"""
        # Validation is done with the device name
        node_name_from_calibration = self.node_calibration.node_software_information.device_name
        return node.sw_info.device_name == node_name_from_calibration

    def import_from_controller(self, controller: WattNodeController) -> NodeCalibrationData:
        """Import calibrations from a Node"""
        if controller.sw_info is None:
            self.node_info = controller.read_software_information()
        else:
            self.node_info = controller.sw_info
        self.node_calibration = NodeCalibrationData.from_node(controller.node)

        return self.node_calibration

    def import_from_json(self, calibration_path: str) -> NodeCalibrationData:
        """Import calibrations from a JSON file"""
        node_calibration = NodeCalibrationData.from_json(calibration_path)
        self.node_calibration = node_calibration
        self.node_info = node_calibration.node_software_information
        return self.node_calibration

    def export_json(self, calibration_path: str):
        """Export calibration data to a JSON file"""
        info = self.node_info
        filename = f"CALIBRATION-{generic_node_filename_timestamped(info)}.json"
        output_file = os.path.join(calibration_path, filename)
        with open(output_file, "w") as outfile:
            # Create dictionnary with calibrations and index names
            calibrations_data_dict = {}
            for calibration in self.node_calibration.calibrations:
                calibrations_data_dict[calibration.calibration_index_name] = calibration.calibration_data
            output_json = {
                "node_software_information": asdict(self.node_calibration.node_software_information),
                "calibration_data": calibrations_data_dict,
            }
            json.dump(output_json, outfile, indent=4)
            logger.debug(f"JSON output : {output_json}")
            logger.info(f"Wrote calibation file to {output_file}")


def calibrate_controller(
    controller: WattNodeController,
    node_calibration: NodeCalibrationData,
    check_validity: bool = False,
    reboot: bool = True,
) -> int:
    """Function for calibrating a remote node with calibration data"""
    if check_validity:
        logger.debug(f"Validating calibration")
        if not (controller.sw_info.device_name == node_calibration.node_software_information.device_name):
            logger.error(f"Incompatible calibrations !")
            return ERROR_INCOMPATIBLE_DEVICE
    # Prepare for calibration upload (this is node dependent)
    controller._prepare_calibration_upload()
    # Get the calibration the potential calibration registers of the node :
    calibration_index_names = CALIBRATION_INDEXES[node_calibration.node_software_information.type]
    # Get all the subindexes and values
    subindex_dict = node_calibration.subindex_dict()
    # Iterate over the possible names
    for index_name in calibration_index_names:
        for subindex_name, value in subindex_dict.items():
            try:
                logger.debug(
                    f"Uploading calibrations to node {controller.node} {index_name} {subindex_name} =  {value}"
                )
                controller.node.sdo[index_name][subindex_name].raw = value
            except ValueError:
                # When value is not in correct datatype, put 0
                controller.node.sdo[index_name][subindex_name].raw = 0
                logger.debug(
                    f"Error in calibration value uploading to {controller.node} {index_name} {subindex_name} 0"
                )
            except canopen.sdo.SdoAbortedError as e:
                if e.code == 0x06090011:
                    # If subindex does not exist, just ignore
                    logger.debug(
                        f"SDO subindex does not exist for {controller.node} {index_name} {subindex_name}"
                    )
            except KeyError as e:
                logger.debug(f"Key error {controller.node} {index_name} {subindex_name} with error {e}")

            except canopen.sdo.exceptions.SdoError as e:
                logger.error(f"Error uploading calibrations {e}")
                return ERROR_UPLOADING_CALIBRATIONS

    try:
        controller.store_parameter()
    except canopen.sdo.exceptions.SdoError as e:
        logger.error("Failed store parameter")
        return ERROR_STORING_PARAMETERS

    # Reboot the node to get out of pre operational
    if reboot:
        controller.reboot()
    return CALIBRATION_SUCCESS
