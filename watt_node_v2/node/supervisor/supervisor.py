import logging
import pathlib
import time
from enum import Enum, IntEnum
from pathlib import Path
from typing import Dict, List

import canopen

from ...local_node import LocalNode
from ..allocation_word import AllocationMode, AllocationWord
from ..base import ControllerException
from ..lu import LookupTable

logger = logging.getLogger()


EVIS_A_NODE_ID = 0x10
EVIS_B_NODE_ID = 0x20
EVIS_C_NODE_ID = 0x18
EVIS_D_NODE_ID = 0x28

SUP_EXTENDED_INTERFACE = 1 << 6


class ChargePointType(Enum):
    """Charge point names available"""

    EVIS_A_CCS = "EVIS_A_CCS"
    EVIS_B_CCS = "EVIS_B_CCS"
    EVIS_C_CCS = "EVIS_C_CCS"
    EVIS_D_CCS = "EVIS_D_CCS"
    EVIS_A_CHA = "EVIS_A_CHA"
    EVIS_B_CHA = "EVIS_B_CHA"
    EVIS_C_CHA = "EVIS_C_CHA"
    EVIS_D_CHA = "EVIS_D_CHA"


# Values contain [EVI ID, PM ID]
SECCSupervisor_IDS = {
    ChargePointType.EVIS_A_CCS: [EVIS_A_NODE_ID, EVIS_A_NODE_ID + 1],
    ChargePointType.EVIS_A_CHA: [EVIS_A_NODE_ID, EVIS_A_NODE_ID + 2],
    ChargePointType.EVIS_B_CCS: [EVIS_B_NODE_ID, EVIS_B_NODE_ID + 1],
    ChargePointType.EVIS_B_CHA: [EVIS_B_NODE_ID, EVIS_B_NODE_ID + 2],
    ChargePointType.EVIS_C_CCS: [EVIS_C_NODE_ID, EVIS_C_NODE_ID + 1],
    ChargePointType.EVIS_C_CHA: [EVIS_C_NODE_ID, EVIS_C_NODE_ID + 2],
    ChargePointType.EVIS_D_CCS: [EVIS_D_NODE_ID, EVIS_D_NODE_ID + 1],
    ChargePointType.EVIS_D_CHA: [EVIS_D_NODE_ID, EVIS_D_NODE_ID + 2],
}

CHARGEPOINT_IDS = [EVIS_A_NODE_ID, EVIS_B_NODE_ID, EVIS_C_NODE_ID, EVIS_D_NODE_ID]


class SupervisorStates(Enum):
    SUP0_Idle = 0
    SUP1_Approbation = 1
    SUP2_Cancellation = 2
    SUP3_AllocationDone = 3
    SUP4_SECCSupervisorStopChargeReq = 4
    SUP5_Terminate = 5
    SUP6_Reset = 6
    SUP7_RearmChargeWithoutUnplug = 7
    SUP15_DefaultValue = 15


# ---------------------------------------------------------------------------- #
#                Indexes for accessing specific chargepoint data               #
# ---------------------------------------------------------------------------- #
SUP_TO_SECCSupervisor_INDEX = {
    ChargePointType.EVIS_A_CCS: 0x6000,
    ChargePointType.EVIS_B_CCS: 0x6100,
    ChargePointType.EVIS_C_CCS: 0x6200,
    ChargePointType.EVIS_D_CCS: 0x6300,
    ChargePointType.EVIS_A_CHA: 0x6400,
    ChargePointType.EVIS_B_CHA: 0x6500,
    ChargePointType.EVIS_C_CHA: 0x6600,
    ChargePointType.EVIS_D_CHA: 0x6700,
}

SECCSupervisor_TO_SUP_INDEX = {
    ChargePointType.EVIS_A_CCS: 0x5000,
    ChargePointType.EVIS_B_CCS: 0x5100,
    ChargePointType.EVIS_C_CCS: 0x5200,
    ChargePointType.EVIS_D_CCS: 0x5300,
    ChargePointType.EVIS_A_CHA: 0x5400,
    ChargePointType.EVIS_B_CHA: 0x5500,
    ChargePointType.EVIS_C_CHA: 0x5600,
    ChargePointType.EVIS_D_CHA: 0x5700,
}


SUP_EVIS_A_CCS_INDEX = 0x6000
SUP_EVIS_B_CCS_INDEX = 0x6100

SUP_EVIS_A_CHA_INDEX = 0x6400
SUP_EVIS_B_CHA_INDEX = 0x6500


CP_EVIS_A_CCS_INDEX = 0x5000
CP_EVIS_B_CCS_INDEX = 0x5100

CP_EVIS_A_CHA_INDEX = 0x5400
CP_EVIS_B_CHA_INDEX = 0x5500

NUM_TPDOS_CP = 3
NUM_RPDOS_CP = 7

DEFAULT_SUP_EDS_PATH = pathlib.Path(__file__).parent.parent.parent.joinpath("eds/supervisor.eds")


class GlobalSupervisor:
    """Class for generating a canopen supervisor
    A supervisor can be composed of multiple sub supervisors, each responsible for one charge point
    """

    EVIS_CCS_TPDO_OFFSETS = [0x200, 0x300, 0x205]
    EVIS_CHA_TPDO_OFFSETS = [0x400, 0x500, 0x305]
    EVIS_CCS_RPDO_OFFSETS = [0x180, 0x280]
    EVIS_CHA_RPDO_OFFSETS = [0x380, 0x480]
    PM_CCS_PDO_OFFSETS = [0x500, 0x280, 0x480, 0x181]
    PM_CHA_PDO_OFFSETS = [0x501, 0x281, 0x481, 0x182]

    def __init__(
        self,
        network: canopen.Network,
        chargepoints: List[ChargePointType],
        interface: 'SupervisorInterface',
        node_id: int = 0x2,
        eds_path: Path = DEFAULT_SUP_EDS_PATH,
        lookup_table=LookupTable(),
    ) -> None:
        self.network = network
        self.lookup_table = lookup_table
        # Create supervisor node, adds it automatically to the network
        self.node_id = node_id
        self.node = LocalNode(node_id=node_id, object_dictionary=str(eds_path))
        self.network.add_node(self.node)
        # Chargepoints with which we shall communicate
        self.SECCSupervisors: Dict[ChargePointType, SECCSupervisor] = {}
        self._validate_args(chargepoints)
        for chargepoint in chargepoints:
            logger.info(f"Initializing SECCSupervisor handler for {chargepoint}")
            self.SECCSupervisors[chargepoint] = SECCSupervisor(
                sdo=self.node.sdo,
                chargepoint_type=chargepoint,
                used_interface=interface,
                lookup_table=lookup_table,
            )

    @staticmethod
    def _validate_args(chargepoints: List[ChargePointType]) -> None:
        """Validate the given charge points"""
        for chargepoint in chargepoints:
            if not isinstance(chargepoint, ChargePointType):
                logger.error(f"Unknwon chargepoint {chargepoint}")
                raise ValueError(f"Unknwon chargepoint {chargepoint}")
        if len(chargepoints) == 0:
            raise ValueError("Expecting at least one charge point")

    def start(self) -> None:
        self.node.nmt.state = "PRE-OPERATIONAL"
        logger.info(f"is supervisor heartbeat started : {self.node.nmt._heartbeat_time_ms}")
        self._configure_pdos()
        self.node.nmt.state = "OPERATIONAL"

        self.node.start()
        logger.info(
            f"supervisor has been started at address {self.node_id} with the following chargepoints {self.SECCSupervisors.keys()}"
        )

    def _configure_pdos(self) -> None:
        """Configure PDOs with the correct node ids"""
        # Read the configuration
        self.node.pdo.read()

        # Enable the desired PDOs for CCS chargepoints
        for index, cp in enumerate(ChargePointType):
            if cp in list(self.SECCSupervisors.keys()):
                logger.info(f"Configuring PDOs for chargepoint : {cp}")
                # If cp is in the selected chargepoints, then enable the associated TPDOs
                for i in range(NUM_TPDOS_CP):
                    tpdo_no = i + 1 + (index * NUM_TPDOS_CP)
                    self.node.tpdo[tpdo_no].enabled = True
                    logger.info(
                        f"Added CCS TPDO {tpdo_no}, cob_id {hex(self.node.tpdo[tpdo_no].cob_id)} cp : {cp}"
                    )

                # Also enable the associated RPDOs and add a callback
                for i in range(NUM_RPDOS_CP):
                    rpdo_no = i + 1 + (index * NUM_RPDOS_CP)
                    self.node.rpdo[rpdo_no].enabled = True
                logger.info(f"Configured PDOs for chargepoint : {cp}")

        # Save the configuration
        self.node.pdo.save()


class SupervisorInterface(Enum):
    LEGACY = 0
    EXTENDED = 1
    V2G = 2


class SupervisorRequestCode(Enum):
    SUP0_Idle = 0
    SUP1_Approbation = 1
    SUP2_Cancellation = 2
    SUP3_AllocationDone = 3
    SUP4_SECCSupervisorStopChargeReq = 4
    SUP5_Terminate = 5
    SUP6_Reset = 6
    SUP7_RearmChargeWithoutUnplug = 7
    SUP15_DefaultValue = 15


class SECCSupervisorState(IntEnum):
    CP0_Init = 0
    CP1_WaitForSupApprob = 1
    CP2_WaitForEV = 2
    CP4_WaitForPUs = 4
    CP6_LockCableToEV = 6
    CP7_CableCheck = 7
    CP8_ChargeLoop = 8
    CP10_StopPUsAndPMs = 10
    CP11_SafetyChecks = 11
    CP12_StopCommWithEV = 12
    CP14_ReleasePUs = 14
    CP15_UnlockEvConnector = 15
    CP16_WaitForPMidle = 16
    CP17_EmergencyStop = 17
    CP18_Reset = 18
    CP255_No_State = 255


class SECCSupervisor:
    """Class used for accessing a single SECC chargepoint
    EVI can have up to two chargepoints : 1 CHAdeMO and 1 CCS
    """

    CURRENT_GAIN = 100
    VOLTAGE_GAIN = 10
    POWER_GAIN = 1
    TEMPERATURE_GAIN = 1

    def __init__(
        self,
        sdo: canopen.sdo.SdoClient,
        chargepoint_type: ChargePointType,
        used_interface: SupervisorInterface,
        lookup_table: LookupTable,
    ) -> None:
        self.chargepoint_type = chargepoint_type
        self.sdo = sdo
        self.supervisor_to_SECCSupervisor_index = SUP_TO_SECCSupervisor_INDEX[chargepoint_type]
        self.SECCSupervisor_to_supervisor_index = SECCSupervisor_TO_SUP_INDEX[chargepoint_type]
        self.pm_to_supervisor_index = SECCSupervisor_TO_SUP_INDEX[chargepoint_type] + 0x10
        self.SUP_Interface = used_interface
        self.lookup_table = lookup_table

    @property
    def SUP_Interface(self) -> SupervisorInterface:
        request_code = self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_RequestCode"].raw
        return SupervisorInterface((request_code & 0b1100_0000) >> 6)

    @SUP_Interface.setter
    def SUP_Interface(self, interface: SupervisorInterface):
        self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_RequestCode"].raw = (
            interface.value << 6
        ) | self.SUP_RequestCode.value

    @property
    def SUP_RequestCode(self) -> SupervisorRequestCode:
        request_code = self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_RequestCode"].raw
        return SupervisorRequestCode(request_code & 0b0000_1111)

    @SUP_RequestCode.setter
    def SUP_RequestCode(self, request_code: SupervisorRequestCode):
        """Set the sup request code"""
        computed_sup_request_code = (self.SUP_Interface.value << 6) | request_code.value
        self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_RequestCode"].raw = computed_sup_request_code

    @property
    def SUP_MaxDcChargeCurrent(self):
        return (
            self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_MaxDcChargeCurrent"].raw
            / self.CURRENT_GAIN
        )

    @SUP_MaxDcChargeCurrent.setter
    def SUP_MaxDcChargeCurrent(self, current):
        self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_MaxDcChargeCurrent"].raw = (
            current * self.CURRENT_GAIN
        )

    @property
    def SUP_MaxDcChargeVoltage(self):
        return (
            self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_MaxDcChargeVoltage"].raw
            / self.VOLTAGE_GAIN
        )

    @SUP_MaxDcChargeVoltage.setter
    def SUP_MaxDcChargeVoltage(self, voltage):
        self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_MaxDcChargeVoltage"].raw = (
            voltage * self.VOLTAGE_GAIN
        )

    @property
    def SUP_MaxAcChargeCurrent(self):
        return (
            self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_MaxAcChargeCurrent"].raw
            / self.CURRENT_GAIN
        )

    @SUP_MaxAcChargeCurrent.setter
    def SUP_MaxAcChargeCurrent(self, current):
        self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_MaxAcChargeCurrent"].raw = (
            current * self.CURRENT_GAIN
        )

    @property
    def SUP_MaxDcChargePower(self):
        return (
            self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_MaxDcChargePower"].raw / self.POWER_GAIN
        )

    @SUP_MaxDcChargePower.setter
    def SUP_MaxDcChargePower(self, power):
        self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_MaxDcChargePower"].raw = (
            power * self.POWER_GAIN
        )

    # ---------------------------------------------------------------------------- #
    #                                   Only V2G                                   #
    # ---------------------------------------------------------------------------- #
    @property
    def SUP_MaxDcDischargeCurrent(self):
        return (
            self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_MaxDcDischargeCurrent"].raw
            / self.CURRENT_GAIN
        )

    @SUP_MaxDcDischargeCurrent.setter
    def SUP_MaxDcDischargeCurrent(self, current):
        self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_MaxDcDischargeCurrent"].raw = (
            current * self.CURRENT_GAIN
        )

    @property
    def SUP_MaxDcDischargeVoltage(self):
        return (
            self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_MaxDcDischargeVoltage"].raw
            / self.VOLTAGE_GAIN
        )

    @SUP_MaxDcDischargeVoltage.setter
    def SUP_MaxDcDischargeVoltage(self, voltage):
        self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_MaxDcDischargeVoltage"].raw = (
            voltage * self.VOLTAGE_GAIN
        )

    @property
    def SUP_MaxDcDischargePower(self):
        return (
            self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_MaxDcDischargePower"].raw
            / self.POWER_GAIN
        )

    @SUP_MaxDcDischargePower.setter
    def SUP_MaxDcDischargePower(self, power):
        self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_MaxDcDischargePower"].raw = (
            power * self.POWER_GAIN
        )

    @property
    def SUP_MaxAcDischargeCurrent(self):
        return (
            self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_MaxAcDischargeCurrent"].raw
            / self.CURRENT_GAIN
        )

    @SUP_MaxAcDischargeCurrent.setter
    def SUP_MaxAcDischargeCurrent(self, current):
        self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_MaxAcDischargeCurrent"].raw = (
            current * self.CURRENT_GAIN
        )

    @property
    def chargeSetting(self):
        return self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_ChargeSettingWord"].raw

    @chargeSetting.setter
    def chargeSetting(self, charge_setting):
        self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_ChargeSettingWord"].raw = charge_setting

    @property
    def charged_energy(self):
        return (
            self.sdo[self.SECCSupervisor_to_supervisor_index]["ChargeTransferredEnergy"].raw
            / self.POWER_GAIN
        )

    @property
    def discharged_energy(self):
        return (
            self.sdo[self.SECCSupervisor_to_supervisor_index]["DischargeTransferredEnergy"].raw
            / self.POWER_GAIN
        )

    @property
    def SoC(self):
        return self.sdo[self.pm_to_supervisor_index]["EV_CurStateOfCharge"].raw

    @property
    def control_pilot(self):
        return self.sdo[self.SECCSupervisor_to_supervisor_index]["CCS_PilotStatusCode"].raw

    @property
    def state(self) -> SECCSupervisorState:
        return SECCSupervisorState(self.sdo[self.SECCSupervisor_to_supervisor_index]["CP_StatusCode"].raw)

    @property
    def substate(self) -> int:
        return self.sdo[self.SECCSupervisor_to_supervisor_index]["CP_SubStatusCode"].raw

    @property
    def error(self) -> str:
        return self.lookup_table.get_error(
            self.sdo[self.SECCSupervisor_to_supervisor_index]["CP_ErrorCode"].raw
        )

    @property
    def extended_error(self) -> str:
        try:
            return self.lookup_table.get_extended_error(
                self.sdo[self.SECCSupervisor_to_supervisor_index]["CP_ExtendedErrorCode"].raw
            )
        except canopen.ObjectDictionaryError:
            return 0

    @property
    def error_from_state(self):
        return SECCSupervisorState(
            self.sdo[self.SECCSupervisor_to_supervisor_index]["CP_error_from_state"].raw
        )

    @property
    def error_from_substate(self):
        return self.lookup_table.get_cp_substate(
            self.sdo[self.SECCSupervisor_to_supervisor_index]["CP_error_from_sub_state"].raw
        )

    @property
    def puAllocationCurrent(self):
        """Allocations depend on the interface (not the same location in OD)"""
        if self.SUP_Interface == SupervisorInterface.LEGACY:
            return AllocationWord(
                raw=self.sdo[self.supervisor_to_SECCSupervisor_index][
                    "PowerUnitsAllocationCurrent_undebounced_legacy"
                ].raw
            )
        else:
            return AllocationWord(
                raw=self.sdo[self.supervisor_to_SECCSupervisor_index][
                    "PowerUnitsAllocationCurrent_undebounced_extended"
                ].raw
            )

    @puAllocationCurrent.setter
    def puAllocationCurrent(self, allocation: AllocationWord):
        if self.SUP_Interface == SupervisorInterface.LEGACY:
            self.sdo[self.supervisor_to_SECCSupervisor_index][
                "PowerUnitsAllocationCurrent_undebounced_legacy"
            ].raw = allocation.raw
        else:
            self.sdo[self.supervisor_to_SECCSupervisor_index][
                "PowerUnitsAllocationCurrent_undebounced_extended"
            ].raw = allocation.raw

    @property
    def puAllocationTarget(self):
        """Allocations depend on the interface (not the same location in OD)"""
        if self.SUP_Interface == SupervisorInterface.LEGACY:
            return AllocationWord(
                raw=self.sdo[self.supervisor_to_SECCSupervisor_index][
                    "PowerUnitsAllocationTarget_undebounced_legacy"
                ].raw
            )
        else:
            return AllocationWord(
                raw=self.sdo[self.supervisor_to_SECCSupervisor_index][
                    "PowerUnitsAllocationTarget_undebounced_extended"
                ].raw
            )

    @puAllocationTarget.setter
    def puAllocationTarget(self, allocation: AllocationWord):
        if self.SUP_Interface == SupervisorInterface.LEGACY:
            self.sdo[self.supervisor_to_SECCSupervisor_index][
                "PowerUnitsAllocationTarget_undebounced_legacy"
            ].raw = allocation.raw
        else:
            self.sdo[self.supervisor_to_SECCSupervisor_index][
                "PowerUnitsAllocationTarget_undebounced_extended"
            ].raw = allocation.raw

    @property
    def discharge_mode(self):
        """Discharge mode is bit 0 of charge setting word"""
        return self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_ChargeSettingWord"].raw & 0b1

    @discharge_mode.setter
    def discharge_mode(self, mode: bool):
        charge_setting = self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_ChargeSettingWord"]
        if mode:
            charge_setting.raw |= 1
        else:
            charge_setting.raw &= ~1

    @property
    def dynamic_mode(self):
        return (self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_ChargeSettingWord"].raw & 0b10) >> 1

    @dynamic_mode.setter
    def dynamic_mode(self, mode: bool):
        charge_setting = self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_ChargeSettingWord"]
        if mode:
            charge_setting.raw |= 1 << 1
        else:
            charge_setting.raw &= ~(1 << 1)

    @property
    def discharge_compatible(self):
        """Dicharge compatibility is bit 2 of charge setting word"""
        return (self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_ChargeSettingWord"].raw & 0b100) >> 2

    @discharge_compatible.setter
    def discharge_compatible(self, mode: bool):
        charge_setting = self.sdo[self.supervisor_to_SECCSupervisor_index]["SUP_ChargeSettingWord"]
        if mode:
            charge_setting.raw |= 1 << 2
        else:
            charge_setting.raw &= ~(1 << 2)

    def wait_for_substate(self, substate: int, timeout_s: int = 10):
        """Wait for the charge point to be in a specific sub state"""
        start_time = time.time()
        while time.time() - start_time < timeout_s:
            if self.substate == substate:
                return
            time.sleep(0.1)
        raise ControllerException(
            f"Charge point did not go in state {substate} after {timeout_s}s (in {self.substate})"
        )

    def wait_for_state(self, state: SECCSupervisorState, timeout_s: int = 10):
        """Wait for the charge point to be in a specific state
        This will raise a timeout after waiting fo timeout_s seconds
        """
        start_time = time.time()
        current_state = None
        while time.time() - start_time < timeout_s:
            if self.state == state:
                return
            else:
                print("current state: " + str(self.state) + " current substate: " + str(self.substate))
            time.sleep(0.1)
        raise ControllerException(
            f"Charge point did not go in state {state} after {timeout_s}s (in {self.state})"
        )

    def launch_charge(self, allocation: AllocationWord):
        """Launch a charge with the requested allocation, this function is blocking
        If a charge is already on going this method will finish the charge and start a new one
        """
        logger.info(f"current state of chargepoint is {self.state}")
        if not (self.state == SECCSupervisorState.CP18_Reset):
            print("CP state is not 18, sending SUP2_Cancellation")
            logger.info("cancelling any ongoing charge")
            self.SUP_RequestCode = SupervisorRequestCode.SUP2_Cancellation
            self.wait_for_state(SECCSupervisorState.CP17_EmergencyStop)
            print("CP state is 17, sending SUP6_Reset")
        logger.info("sending a reset")
        self.SUP_RequestCode = SupervisorRequestCode.SUP6_Reset
        self.wait_for_state(SECCSupervisorState.CP18_Reset)
        print("CP state is 18, sending SUP0_Idle")
        self.SUP_RequestCode = SupervisorRequestCode.SUP0_Idle
        self.wait_for_state(SECCSupervisorState.CP1_WaitForSupApprob)
        print("CP state is 1, sending SUP1_Approbation")
        self.SUP_RequestCode = SupervisorRequestCode.SUP1_Approbation
        self.puAllocationCurrent = allocation
        self.puAllocationTarget = allocation
        self.wait_for_substate(31)
        self.SUP_RequestCode = SupervisorRequestCode.SUP3_AllocationDone
        self.wait_for_state(SECCSupervisorState.CP8_ChargeLoop, timeout_s=20)
        print("CP state is 8, charge loop started")

    def stop_charge(self, unplug=True):
        if not (self.state == SECCSupervisorState.CP8_ChargeLoop):
            print(f"CP state is {self.state} and not 8, can't operate normal stop.")
            return
        self.SUP_RequestCode = SupervisorRequestCode.SUP4_SECCSupervisorStopChargeReq
        self.wait_for_state(SECCSupervisorState.CP14_ReleasePUs)
        print("CP state is 14, sending SUP5_Terminate")
        self.SUP_RequestCode = SupervisorRequestCode.SUP5_Terminate
        self.wait_for_state(SECCSupervisorState.CP15_UnlockEvConnector)
        if unplug:
            self.wait_for_state(SECCSupervisorState.CP16_WaitForPMidle)
            print("CP state is 16, sending SUP0_Idle")
            self.SUP_RequestCode = SupervisorRequestCode.SUP0_Idle
            self.wait_for_state(SECCSupervisorState.CP1_WaitForSupApprob)
            print("CP state is 1, waiting for SUP1_Approbation.")
            print("Charge successfully stopped.")
            return
        else:
            print("CP state is 15, sending SUP7_RearmChargeWithoutUnplug")
            self.SUP_RequestCode = SupervisorRequestCode.SUP7_RearmChargeWithoutUnplug
            self.wait_for_state(SECCSupervisorState.CP19_WaitForPMidle)
            print("CP state is 19, waiting for SUP0_Idle.")
            self.SUP_RequestCode = SupervisorRequestCode.SUP0_Idle
            self.wait_for_state(SECCSupervisorState.CP1_WaitForSupApprob)
            print("CP state is 1, waiting for SUP1_Approbation.")
            print("Charge successfully stopped.")
            return

    def emergency_stop(self):
        print("sending SUP2_Cancellation")
        self.SUP_RequestCode = SupervisorRequestCode.SUP2_Cancellation
        self.wait_for_state(SECCSupervisorState.CP17_EmergencyStop)
        print("CP state is 17, sending SUP6_Reset")
        self.SUP_RequestCode = SupervisorRequestCode.SUP6_Reset
        self.wait_for_state(SECCSupervisorState.CP18_Reset)
        print("CP state is 18, waiting for SUP0_Idle")
        print("emergency stop completed")

    def update_charge_settings(
        self,
        discharge_compatible: bool = 0,
        dynamic_mode: bool = 0,
        discharge_mode: bool = 0,
    ):
        self.discharge_compatible = discharge_compatible
        self.dynamic_mode = dynamic_mode
        self.discharge_mode = discharge_mode

    def update_limitations(
        self,
        max_dc_charge_power: int = 50000,
        max_dc_charge_voltage: int = 920,
        max_dc_charge_current: int = 100,
        max_ac_charge_current: int = 120,
    ):
        """Update chargepoint limitations with standard units (Watt,Amp,Volt)"""
        self.SUP_MaxDcChargePower = max_dc_charge_power
        self.SUP_MaxDcChargeVoltage = max_dc_charge_voltage
        self.SUP_MaxDcChargeCurrent = max_dc_charge_current
        self.SUP_MaxAcChargeCurrent = max_ac_charge_current

    def get_information(self) -> str:
        """Get error information and return as string for printing"""
        return_str = f"""
        Current state : {self.state.value}
        Error : {self.error}
        Extended error : {self.extended_error}
        Error from state : {self.error_from_state.value}
        Error from substate : {self.error_from_substate}
        """
        return return_str


def disable_securities(evis: canopen.RemoteNode):
    """Disable securities of EVIS, used when simulating EV/PM
    Must be used with caution !
    """
    # Unlock IMD
    IMD_PASS = 0x21646D69
    evis.sdo.download(
        0x3100,
        0,
        IMD_PASS.to_bytes(length=4, byteorder="little"),
    )
    # Put IMD in force OK mode
    try:
        evis.sdo.download(0x3140, 0x1, int(1).to_bytes(length=1, byteorder="little"))
    except canopen.SdoAbortedError:
        # On older sw versions (<5.x) not at the same location
        evis.sdo.download(0x3140, 0x37, int(1).to_bytes(length=1, byteorder="little"))
    # Disable Emergency input check
    evis.sdo.download(0x3040, 0x5, int(1).to_bytes(length=1, byteorder="little"))
    # Disable ControlPilot check
    evis.sdo.download(0x3040, 0x6, int(1).to_bytes(length=1, byteorder="little"))
