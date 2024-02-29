from .base import WattLocalNode, WattNodeController, WattRemoteNode
from .datatypes import NodeType
from .evis.evis import EvisController
from .bootloader import BootloaderController
from typing import Dict, Union

DEFAULT_CONTROLLER_TYPE_CHOICES = {
    NodeType.bootloader: BootloaderController,
    NodeType.evis: EvisController,
    NodeType.mpu: WattNodeController,
    NodeType.bmpu_pfc: WattNodeController,
    NodeType.bmpu_dcdc: WattNodeController,
    NodeType.mpu_r2_pfc: WattNodeController,
    NodeType.mpu_r2_dcdc: WattNodeController,
}

DEFAULT_CONTROLLER_ID_CHOICES = dict([(id, WattNodeController) for id in range(126)])
DEFAULT_CONTROLLER_ID_CHOICES[125] = BootloaderController
DEFAULT_CONTROLLER_ID_CHOICES[126] = BootloaderController


class ControllerFactory:
    """Factory for creating node controllers, it is possible to add external controllers for specific ids"""

    def __init__(
        self,
        controller_type_choices: Dict[NodeType, WattNodeController] = DEFAULT_CONTROLLER_TYPE_CHOICES,
        controller_id_choices: Dict[int, WattNodeController] = DEFAULT_CONTROLLER_ID_CHOICES,
    ) -> None:
        """Intialize"""
        self.controller_type_choices = controller_type_choices
        self.controller_id_choices = controller_id_choices

    def add_controller_for_type(self, type: NodeType, controller: WattNodeController):
        """Add a node controller for a specific node type, can be useful for devices that are not standard CANOpen nodes"""
        self.controller_type_choices[type] = controller

    def add_controller_for_id(self, id: int, controller: WattNodeController):
        """Adds a node controller for a specific node ID"""
        self.controller_id_choices[id] = controller

    def create_controller_for_type(
        self, type: NodeType, node: Union[WattRemoteNode, WattLocalNode], *args, **kwargs
    ) -> "WattNodeController":
        """Factory constructor for controller by node type"""
        return self.controller_type_choices[type](node, *args, **kwargs)

    def create_controller_for_id(
        self, id: int, node: Union[WattRemoteNode, WattLocalNode], *args, **kwargs
    ) -> "WattNodeController":
        """Facotry constructor for controller by node id"""
        return self.controller_id_choices[id](node, *args, **kwargs)
