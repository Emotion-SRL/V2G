import logging
from ..node.datatypes import NodeType
from .base import WattLocalNode, WattRemoteNode, WattNodeController
from ..network import Network
from ..node.evis.evis import EvisNode
from ..db import DBHandler
import canopen
import zipfile
from io import TextIOWrapper, BytesIO

logger = logging.getLogger(__name__)


def create_remote_node(id, od):
    return WattRemoteNode(id, od)


# 1) Read device anyhow,
# 2) Check if EDS is present on disks or paths
# 3) if device id permits it & download is enabled then 4) else fail
# then download it & save it to disk (cache folder & save inside network cache if same version loaded again)
# If still not present then fail
# 4) Else return a textiowrapper


class EDSNotFoundError(FileNotFoundError):
    """Couldn't find EDS of node"""


def retrieve_eds(
    controller: WattNodeController,
    db: DBHandler = None,
    allow_download: bool = True,
    retries: int = 10,
) -> TextIOWrapper:
    """Retrieve EDS of a specific node ID
    This function first tries the DB store &
    then tries to download it from the node if possible
    """
    info = controller.read_software_information()
    try:
        eds_path = db.get_eds(info)
        return eds_path
    except FileNotFoundError:
        pass
    if not allow_download:
        raise EDSNotFoundError("Couldn't find EDS in folders")
    # Try to download EDS from the node.
    if not controller.is_eds_contained():
        raise EDSNotFoundError("EDS couldn't be found neither in database & is not stored on node")
    logger.info("EDS was not found inside DB, attempting to get it from node")
    for _ in range(retries):
        try:
            dictionary_io_wrapper = controller.upload_dictionary(format="eds")
            logger.info("EDS was uploaded successfully !")
            return dictionary_io_wrapper
        except canopen.sdo.SdoAbortedError as e:
            if e.code == 0x06020000:
                raise EDSNotFoundError(
                    "EDS couldn't be found neither in database & entry 0x1021 is not present on node"
                )


class WattNodeFactory:
    """Factory for creating watt nodes"""

    @staticmethod
    def create_watt_remote_node(
        network: Network, node_id: int, db_handler: DBHandler = None, **kwargs
    ) -> WattRemoteNode:
        # Retreive all the necessary information about the node
        # Before creating the node, verify it's type and that we can actually create it
        temp_node = network.add_node(node_id)
        controller = WattNodeController(temp_node)
        sw_info = controller.read_software_information()
        logger.info(sw_info)
        try:
            eds_path = db_handler.get_eds(sw_info)
            watt_node: WattRemoteNode = WattNodeFactory.remote_node_choices[sw_info.type](node_id, eds_path)
            # Update software information because node got re-created
            watt_node.sw_info = sw_info
            watt_node.controller.sw_info = sw_info
            del network[temp_node.id]
            network.add_node(watt_node)
            return watt_node

        except KeyError:
            raise ValueError(f"Unknown device name {sw_info.device_name}")

    local_node_choices = {
        NodeType.ebmpu_pfc: WattLocalNode,
        NodeType.empu: WattLocalNode,
    }

    remote_node_choices = {
        NodeType.bootloader: WattRemoteNode,
        NodeType.evis: EvisNode,
        NodeType.mpu: WattRemoteNode,
        NodeType.bmpu_pfc: WattRemoteNode,
        NodeType.bmpu_dcdc: WattRemoteNode,
        NodeType.mpu_r2_pfc: WattRemoteNode,
        NodeType.mpu_r2_dcdc: WattRemoteNode,
    }
