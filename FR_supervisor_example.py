import canopen
import logging
from watt_node_v2.node.supervisor import (
    GlobalSupervisor,
    ChargePointType,
    SupervisorInterface,
    AllocationWord,
    AllocationMode,
)
from watt_node_v2.node.base import ControllerException
from watt_node_v2.node.supervisor.supervisor import disable_securities
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    # Connect to CAN bus, to adpat (socketcan on linux, etc)
    network = canopen.Network()
    network.connect(interface="kvaser", channel=0, bitrate=500_000)

    # Create the global supervisor and add the desired SECCs
    supervisor = GlobalSupervisor(
        network=network,
        chargepoints=[ChargePointType.EVIS_A_CCS],
        interface=SupervisorInterface.EXTENDED,
    )
    # Initialize CANopen specifics
    supervisor.start()
    supervisor.node.nmt.start_heartbeat(1000)  # force start of heartbeat with 1s period

    # Get a specific charge point (SECC) supervisor
    secc_evis_a = supervisor.SECCSupervisors[ChargePointType.EVIS_A_CCS]
    # ---------------------------------------------------------------------------- #
    #                            Update the limitations                            #
    # ---------------------------------------------------------------------------- #
    secc_evis_a.SUP_MaxDcChargePower = 150_000
    secc_evis_a.SUP_MaxDcChargeVoltage = 500
    secc_evis_a.SUP_MaxDcChargeCurrent = 200
    secc_evis_a.SUP_MaxAcChargeCurrent = 100

    # ---------------------------------------------------------------------------- #
    #                              Update allocations                              #
    # ---------------------------------------------------------------------------- #
    allocation = AllocationWord()
    allocation.bmpu_list = [1]  # <-- Change with the desired allocations
    # allocation.mpu_list = [1]

    # To use with caution, this can be used to disable securities on EVI
    # Should not be used in normal operation
    evis_node = network.add_node(0x10)
    disable_securities(evis_node)

    try:
        secc_evis_a.launch_charge(allocation)
    except ControllerException as e:
        logger.error(e)
        logger.error(f"failed to start the charge. SECC status : {secc_evis_a.get_information()}")
        return

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
