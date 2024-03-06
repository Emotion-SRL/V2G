import threading

import canopen

from evi_semantics import evi_BMPU_ID
from watt_node_v2.node.base import ControllerException
from watt_node_v2.node.supervisor import (
    AllocationMode,
    AllocationWord,
    ChargePointType,
    GlobalSupervisor,
    SupervisorInterface,
)

# from watt_node_v2.node.supervisor.supervisor import disable_securities

# Connect to CAN bus, to adpat (socketcan on linux, etc)
network = canopen.Network()
network.connect(interface="socketcan", channel='can1', bitrate=500_000)

# Create the global supervisor and add the desired SECCs
supervisor = GlobalSupervisor(
    network=network,
    chargepoints=[ChargePointType.EVIS_A_CHA],
    interface=SupervisorInterface.EXTENDED,
)
# Initialize CANopen specifics
supervisor.start()
supervisor.node.nmt.start_heartbeat(1000)  # force start of heartbeat with 1s period

# Get a specific charge point (SECC) supervisor
secc_evis_a = supervisor.SECCSupervisors[ChargePointType.EVIS_A_CHA]
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
allocation.bmpu_list = [evi_BMPU_ID-0x5E]  # <-- Change with the desired allocations
# allocation.mpu_list = [1]

# To use with caution, this can be used to disable securities on EVI
# Should not be used in normal operation

# ? Disabled
# evis_node = network.add_node(0x10)
# disable_securities(evis_node)

try:
    while True:
        print("Inserisci un comando:\n-0 per iniziare una ricarica\n-1 per terminare una ricarica\n-2 per l'emergency stop")
        command = input()
        if command == '0':
            secc_evis_a.launch_charge(allocation)
        elif command == '1':
            print("Vuoi anche staccare la presa o intendi lasciarla agganciata per iniziare una nuova ricarica dopo?\n-0 stacca la presa\n-1 non staccare la presa")
            command2 = input()
            unplug = True
            if command2 == '1':
                unplug = False
            elif command2 == '0':
                unplug = True
            else:
                print("Comando non valido. Riprovare.")
                continue
            secc_evis_a.stop_charge(unplug=unplug)
        elif command == '2':
            secc_evis_a.emergency_stop()
        else:
            print("Comando non valido. Riprovare.")
except KeyboardInterrupt:
    print("shutting down...")
except ControllerException:
    print(f"Controller Exception occurred. SECC status : {secc_evis_a.get_information()}")
