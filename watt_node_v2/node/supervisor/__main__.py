import logging
import time
import canopen
import pathlib
from .supervisor import LocalSupervisor, ChargePointType


"""Simple example for creating a supervisor on the network"""
import argparse

logging.basicConfig(level=logging.DEBUG)
parser = argparse.ArgumentParser(
    prog="Launch a simple supervisor that sends and receives PDOs, no internal logic"
)
supervisor_eds = pathlib.Path(__file__).parent.joinpath("supervisor.eds")
parser.add_argument("--eds", help="eds path", default=str(supervisor_eds))
parser.add_argument("--bus_type", help="bus type (kvaser or socketcan)", required=True)
parser.add_argument("--channel", help="CAN channel to use", required=True)
args = parser.parse_args()

eds_path = args.eds
logger = logging.getLogger(__name__)
network = canopen.Network()

with network.connect(
    bustype=args.bus_type,
    bitrate=500000,
    channel=args.channel,
    receive_own_messages=True,
):
    supervisor = LocalSupervisor(
        network,
        eds_path=str(eds_path),
        chargepoints=[ChargePointType.EVIS_A_CCS],
        interface="EXTENDED",
    )
    supervisor.start()
    time.sleep(10)
