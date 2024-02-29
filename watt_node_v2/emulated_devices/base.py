from abc import ABC, abstractclassmethod
from enum import Enum
from typing import Union

from watt_node_v2.node.datatypes import NodeInformation

from ..network import Network
from ..local_node import LocalNode


class EmulatedDevice(ABC):
    """Emulated device abstract class"""

    STATE_MACHINE_DELAY_MS: int = 0.5

    def __init__(self, node: LocalNode, *args, **kwargs):
        """Initialize emulated device with nodes"""
        self.node = node
        self.requested_state: Enum = None
        self._running: bool = False
        self._internal_sync_count: int = 0

    @abstractclassmethod
    def run_state_machine(self):
        """Run state machine, this call is blocking"""
