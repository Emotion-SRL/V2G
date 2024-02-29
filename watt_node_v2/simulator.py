from typing import Dict, List
import toml
from dataclasses import dataclass
import argparse
import pathlib
from threading import Thread

from .network import Network
from .emulated_devices import EmulatedBMPU, EmulatedMPU, EmulatedPM
from .emulated_devices import LocalNode
from .emulated_devices.base import EmulatedDevice
from .node.datatypes import NodeInformation, NodeType, TYPE_STR_TO_NODETYPE
import time
import logging

logger = logging.getLogger(__name__)

# Default EDS location for emulated devices
EDS_DATA_PATH = pathlib.Path(__file__).parent.joinpath("eds")
DEFAULT_BMPU_EDS_PATH = EDS_DATA_PATH.joinpath("ebmpu.eds")
DEFAULT_MPU_EDS_PATH = EDS_DATA_PATH.joinpath("empu.eds")
DEFAULT_PM_EDS_PATH = EDS_DATA_PATH.joinpath("epm.eds")

NODE_TYPE_FACTORY_MAP = {"mpu": EmulatedMPU, "pm": EmulatedPM, "bmpu": EmulatedBMPU}


@dataclass
class SimulatorConfiguration:
    """Simulator configuration
    holds information on the devices to be simulated
    """

    node_infos: List[NodeInformation]
    node_configurations: Dict[int, Dict[str, int]]

    @classmethod
    def from_toml(cls, configuration: Dict) -> "SimulatorConfiguration":
        """Create a simulator configuration from a toml dict"""
        node_infos = []
        node_configurations = {}
        for config in configuration["nodes_config"]:
            node_type = TYPE_STR_TO_NODETYPE[config["node_type"]]
            info = NodeInformation(id=config["node_id"], type=node_type)
            node_infos.append(info)
            # Specific device configurations (everything except node_type and node_id)
            node_configuration: Dict = config
            node_configuration.pop("node_id")
            node_configuration.pop("node_type")
            node_configurations[info.id] = node_configuration
            logger.debug(f"got configurations for {info.id} : {node_configuration}")
        return cls(node_infos, node_configurations)


class Simulator:
    sync_period_ms: int = 0.1

    """Simulator class for device emulation management"""

    def __init__(self, network: Network, configuration: Dict, generate_sync: bool) -> None:
        """Initialize simulator"""
        self.network = network
        self.configuration = configuration
        self.generate_sync = generate_sync
        self.devices: Dict[int, EmulatedDevice] = {}
        self.devices_configurations: Dict[int, Dict] = {}
        self.tasks: List[Thread] = []

    def _check_already_present(self, id: int):
        """Check that a node is not already present on the BUS before adding it
        Scanner stores a history of the seen IDs on the bus
        """
        if id in self.network.scanner.nodes:
            raise SimulatorException(
                f"node id {id} is already present on the bus, this will cause unexpected behaviour. remove conflicting node"
            )

    def add_mpu(
        self,
        id: int,
        configurations: Dict = None,
        eds: pathlib.Path = DEFAULT_MPU_EDS_PATH,
    ) -> EmulatedDevice:
        """Add an emulated MPU
        the emulated MPU has an internal MPU state machine and mimicks communication
        however it does not emulate real hardware
        """
        self._check_already_present(id)
        node = LocalNode(id, str(eds))
        self.network.add_node(node)
        emulated_mpu = EmulatedMPU(node)
        self.devices[id] = emulated_mpu
        self.devices_configurations[id] = configurations
        return emulated_mpu

    def add_bmpu(
        self,
        id: int,
        configurations: Dict = None,
        eds: pathlib.Path = DEFAULT_BMPU_EDS_PATH,
    ) -> EmulatedDevice:
        """Add an emulated BMPU
        the emulated BMPU has an internal BMPU state machine and mimicks communication
        however it does not emulate real hardware
        """
        self._check_already_present(id)
        node = LocalNode(id, str(eds))
        self.network.add_node(node)
        emulated_bmpu = EmulatedBMPU(node)
        self.devices[id] = emulated_bmpu
        self.devices_configurations[id] = configurations
        return emulated_bmpu

    def add_pm(
        self,
        id: int,
        configurations: Dict = None,
        eds: pathlib.Path = DEFAULT_PM_EDS_PATH,
    ) -> EmulatedDevice:
        """Add an emulated PM"""
        self._check_already_present(id)
        node = LocalNode(id, str(eds))
        self.network.add_node(node)
        emulated_pm = EmulatedPM(node)
        self.devices[id] = emulated_pm
        self.devices_configurations[id] = configurations
        return emulated_pm

    def start(self) -> None:
        """Start simulation in background"""
        if self.tasks != []:
            raise SimulatorException("call stop before re-calling start")
        # Start optional sync
        if self.generate_sync:
            logger.info(f"simulator will generate sync with period {self.sync_period_ms}")
            self.network.sync.start(self.sync_period_ms)
        # Run all device state machines in threads
        for device in self.devices.values():
            device.node.start()
            if self.devices_configurations[device.node.id] is not None:
                self._apply_configurations(device, self.devices_configurations[device.node.id])
            thread = Thread(target=device.run_state_machine)
            thread.daemon = True
            self.tasks.append(thread)
            thread.start()

    def stop(self) -> None:
        """Stop simulation by stopping all device threads"""
        for device in self.devices.values():
            device._running = False
            device.node.stop()
        for task in self.tasks:
            task.join()
        self.devices.clear()
        self.tasks.clear()
        # Remove all network subscriptions
        self.network.subscribers.clear()
        self.network.scanner.reset()
        self.network.clear()

    def running(self) -> None:
        """Check whether simulator is running (at least one task)"""
        return len(self.tasks) != 0

    def task_failed(self) -> bool:
        """Test if one of thes tasks is not alive"""
        return any([not task.is_alive() for task in self.tasks])

    def _apply_configurations(self, device: EmulatedDevice, configurations: Dict):
        """Configure the device after it has started"""
        # Additional configuration step, this could probably use some sort of factory pattern to make it cleaner
        for property, value in configurations.items():
            setattr(device, property, value)


class SimulatorException(Exception):
    """Simulator exception"""


def main():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("canopen")
    logger.setLevel(logging.WARNING)
    logger = logging.getLogger("can")
    logger.setLevel(logging.ERROR)
    logger = logging.getLogger(__name__)
    args = parse_args()
    toml_dict = toml.load(args.config_file)
    network = Network(None)
    if args.receive_own:
        logger.info("[ENABLED] receiving own messages")
    if args.gen_sync:
        logger.info("[ENABLED] sync generation")
    network.connect(
        bustype=args.bustype,
        channel=args.channel,
        receive_own_messages=args.receive_own,
        bitrate=500_000,
    )
    # Parse the simulator configuration
    configuration = SimulatorConfiguration.from_toml(toml_dict)
    simulator = Simulator(network, toml_dict, args.gen_sync)
    # Add appropriate devices
    for node_info in configuration.node_infos:
        node_configuration = configuration.node_configurations[node_info.id]
        if node_info.type == NodeType.bmpu_pfc:
            simulator.add_bmpu(node_info.id, node_configuration)
        elif node_info.type == NodeType.pm:
            simulator.add_pm(node_info.id, node_configuration)
        elif node_info.type == NodeType.mpu:
            simulator.add_mpu(node_info.id, node_configuration)
    simulator.start()

    while True:
        time.sleep(0.1)
        for task in simulator.tasks:
            if not task.is_alive():
                logger.warning(f"thread {task} died")


def parse_args():
    parser = argparse.ArgumentParser(
        prog="W&W device emulator",
        description="This is an emulator for running fake canopen devices",
    )
    parser.add_argument("config_file")
    parser.add_argument("--channel", help="CAN channel", default=0)
    parser.add_argument("--bustype", help="CAN bus type (kvaser, socketcan, ...)", default="kvaser")
    parser.add_argument("--gen-sync", help="Sync is generated by simulator", action="store_true")
    parser.add_argument("--receive-own", help="Receive own messages", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
    main()
