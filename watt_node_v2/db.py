from typing import List, Tuple, Dict
import os
from abc import ABC, abstractclassmethod
import pathlib
from .node.datatypes import NodeInformation, NodeType
from .node.lu import LookupTable
import logging
from .utils import extract_firmware_info

logger = logging.getLogger(__name__)


class DBHandler(ABC):
    """Abstract base class for db handler
    This class fetches relevant Node files given the node information
    """

    @abstractclassmethod
    def get_eds(self, info: NodeInformation) -> str:
        """Returns EDS file descriptor corresponding to node information"""

    @abstractclassmethod
    def get_firmware(self, info: NodeInformation) -> str:
        """Returns device firmware file descriptor (.wtcfw) corresponding to node information"""

    @abstractclassmethod
    def get_versions(self) -> Dict[NodeType, List[Tuple]]:
        """Returns a dictonnary containing device type, version and build"""


class FolderDBHandler(DBHandler):
    def __init__(self, paths):
        """Initialize folder db handler with the paths to check"""
        self.paths: List[pathlib.Path] = paths
        # Initialize the lookup table
        self.lut = LookupTable()

    def _get_file(self, info: NodeInformation, extension: str) -> str:
        """Helper function for retreiving any data file for a specific node according to the extension
        This function returns the first valid data file found
        """
        folder = info.folder
        folders: List[pathlib.Path] = []
        for path in self.paths:
            abs_folder = path.joinpath(folder)
            if abs_folder.is_dir():
                folders.append(abs_folder)
        if len(folders) == 0:
            raise FileNotFoundError(f"Couldn't find directory for node with {info}")

        # At least one valid folder has been found, try to get the file
        for folder in folders:
            file = folder.joinpath(info.construct_filename(extension=extension))
            if file.is_file():
                return str(file)
        # The data file was not found
        raise FileNotFoundError(f"Couldn't file the file with extension {extension}, for {info}")

    def get_eds(self, info: NodeInformation):
        return self._get_file(info, extension=".eds")

    def get_firmware(self, info: NodeInformation):
        return self._get_file(info, extension=".wtcfw")

    def get_versions(self) -> Dict[NodeType, List[Tuple]]:
        """Return list of (version,build) per node type"""
        versions = {NodeType.mpu: [], NodeType.bmpu_pfc: [], NodeType.evis: [], NodeType.mpu_r2_pfc: []}
        for path in self.paths:
            files = os.listdir(path)
            for file in files:
                try:
                    node_type, version, build = extract_firmware_info(file)
                    # add it to list if not already present
                    if not (version, build) in versions[node_type]:
                        versions[node_type].append((version, build))
                except ValueError:
                    logger.debug(f"skipped {file} because invalid format")
        return versions
