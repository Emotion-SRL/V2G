# Print iterations progress
from .node.datatypes import NodeInformation, NodeType
import datetime
import re
from typing import Tuple


def generate_progress_bar(
    iteration,
    total,
    prefix="",
    suffix="",
    decimals=1,
    length=100,
    fill="#",
    printEnd="\r",
) -> str:
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filledLength = int(length * iteration // total)
    bar = fill * filledLength + "-" * (length - filledLength)
    return f"{prefix} |{bar}| {percent}% {suffix}"


def get_valid_filename(name):
    """
    Return the given string converted to a string that can be used for a clean
    filename. Remove leading and trailing spaces; convert other spaces to
    underscores; and remove anything that is not an alphanumeric, dash,
    underscore, or dot.
    """
    s = str(name).strip().replace(" ", "_")
    s = re.sub(r"(?u)[^-\w.]", "", s)
    return s


def extract_firmware_info(filename: str) -> Tuple:
    pattern = r'(?i)v(\d+\.\d+\.\d+.*)-Build(\d+)'
    match = re.search(pattern, filename)
    if not match:
        raise ValueError(f'{filename} does not have a correct firmware version format')
    node_type = None
    if "WL1-EVI" in filename:
        node_type = NodeType.evis
    elif "WL1-MPU-R2" in filename:
        node_type = NodeType.mpu_r2_pfc
    elif "WL1-MPU" in filename:
        node_type = NodeType.mpu
    elif "WL1-BMPU" in filename:
        node_type = NodeType.bmpu_pfc
    else:
        raise ValueError("unrecognized firmware type")
    firmware_version = match.group(1)
    build = match.group(2)
    return node_type, firmware_version, build


def generic_node_filename(info: NodeInformation) -> str:
    """Create a generic filename, useful for creating specific file names for node"""
    return get_valid_filename(
        f"TYPE-{info.type.name}-HW-{info.hardware_revision}-SN-{info.serial_nb}-VERSION-{info.sw_version}-BUILD-{info.sw_build}"
    )


def generic_node_filename_timestamped(info: NodeInformation) -> str:
    """Create a generic filename, useful for creating specific file names for node"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%Hh-%Mm-%Ss")
    return get_valid_filename(
        f"TYPE-{info.type.name}-HW-{info.hardware_revision}-SN-{info.serial_nb}-VERSION-{info.sw_version}-BUILD-{info.sw_build}-TIMESTAMP-{timestamp}".replace(
            "\x00", "", -1
        )
    )
