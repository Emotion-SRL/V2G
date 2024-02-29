import logging
import time
from .base import EmulatedDevice
from ..local_node import LocalNode
from ..node.pm.datatypes import PMState
from ..node.evis.datatypes import (
    ChargePointState,
)

logger = logging.getLogger(__name__)


# TODO:
# - add computation of interface via EVI
# - in particular EV_Target current reffers to either legacy or normal depending on the PM type


def v2g_compatible(f):
    def wrapper(*args):
        if args[0].evis.is_v2g():
            return f(*args)
        else:
            raise NotImplementedError("Evis needs to be v2g compatible to access this property")

    return wrapper


class EmulatedPM(EmulatedDevice):
    """Class for emulating PM behaviour on the bus"""

    VOLTAGE_GAIN = 10
    CURRENT_GAIN = 100
    POWER_GAIN = 1
    STATE_MACHINE_DELAY_MS = 0.3

    CCS_IDS = [0x11, 0x21, 0x19, 0x29]
    CHA_IDS = [0x13, 0x23, 0x1B, 0x2B]

    def __init__(self, node: LocalNode):
        """Initiliaze device with corresponding node"""
        self.node = node
        self._running = False
        self._check_id_validity()
        self.node.add_pdo_configuration_callback(self.configure_pdos)

    def __str__(self):
        return str(self.node.id)

    # Expose important Ev datas
    @property
    def EV_MaxDcVoltage(self):
        return self.node.sdo["PM_PowerLimitations"]["EV_MaxDcVoltage"].raw / self.VOLTAGE_GAIN

    @EV_MaxDcVoltage.setter
    def EV_MaxDcVoltage(self, voltage):
        self.node.sdo["PM_PowerLimitations"]["EV_MaxDcVoltage"].raw = voltage * self.VOLTAGE_GAIN

    @property
    def EV_MinDcChargeCurrent(self):
        return self.node.sdo["PM_PowerLimitations"]["EV_MinDcChargeCurrent"].raw / self.CURRENT_GAIN

    @EV_MinDcChargeCurrent.setter
    def EV_MinDcChargeCurrent(self, current):
        self.node.sdo["PM_PowerLimitations"]["EV_MinDcChargeCurrent"].raw = current * self.CURRENT_GAIN

    @property
    def EV_MaxDcChargeCurrent(self):
        return self.node.sdo["PM_PowerLimitations"]["EV_MaxDcChargeCurrent"].raw / self.CURRENT_GAIN

    @EV_MaxDcChargeCurrent.setter
    def EV_MaxDcChargeCurrent(self, current):
        self.node.sdo["PM_PowerLimitations"]["EV_MaxDcChargeCurrent"].raw = current * self.CURRENT_GAIN

    # @property
    # def EV_MinDcDischargeVoltage(self):
    #     return self.cp.EV_MinDcDischargeVoltage

    # @EV_MinDcDischargeVoltage.setter
    # def EV_MinDcDischargeVoltage(self, voltage):
    #     self.EV_MinDcDischargeVoltage = voltage

    # @property
    # def EV_MinDcDischargeCurrent(self):
    #     return self.cp.EV_MinDcDischargeCurrent

    # @EV_MinDcDischargeCurrent.setter
    # def EV_MinDcDischargeCurrent(self, current):
    #     self.cp.EV_MinDcDischargeCurrent = current

    # @property
    # def EV_MaxDcDischargeCurrent(self):
    #     return self.cp.EV_MaxDcDischargeCurrent

    # @EV_MaxDcDischargeCurrent.setter
    # def EV_MaxDcDischargeCurrent(self, current):
    #     self.cp.EV_MaxDcDischargeCurrent = current

    # @property
    # def EV_MinDcDischargePower(self):
    #     return self.cp.EV_MinDcDischargePower

    # @EV_MinDcDischargePower.setter
    # def EV_MinDcDischargePower(self, power):
    #     self.cp.EV_MinDcDischargePower = power

    # @property
    # def EV_MaxDcDischargePower(self):
    #     return self.EV_MaxDcDischargePower

    # @EV_MaxDcDischargePower.setter
    # def EV_MaxDcDischargePower(self, power):
    #     self.cp.EV_MaxDcDischargePower = power

    @property
    def EV_TargetDcVoltage(self):
        return self.node.sdo["PM_InChargeData"]["EV_TargetDcVoltage"].raw / self.VOLTAGE_GAIN

    @EV_TargetDcVoltage.setter
    def EV_TargetDcVoltage(self, voltage):
        self.node.sdo["PM_InChargeData"]["EV_TargetDcVoltage"].raw = voltage * self.VOLTAGE_GAIN

    @property
    def EV_TargetDcCurrent(self):
        return self.node.sdo["PM_InChargeData"]["EV_TargetDcCurrent_legacy"].raw / self.CURRENT_GAIN

    @EV_TargetDcCurrent.setter
    def EV_TargetDcCurrent(self, current: int):
        self.node.sdo["PM_InChargeData"]["EV_TargetDcCurrent_legacy"].raw = current * self.CURRENT_GAIN

    @property
    def infos(self):
        # Return information regarding PM state
        return_str = f"**************PM Node***************\n"
        return_str += f"INTERFACE : {self.cp.interface}\n"
        return_str += f"INTERNAL STATE : {self.state}\n"
        return_str += f"STATE MACHINE RUNNING : {self._running}\n"
        return return_str

    @property
    @v2g_compatible
    def EV_ChargeSettings(self):
        return self.cp.EV_ChargeSettings

    @EV_ChargeSettings.setter
    @v2g_compatible
    def EV_ChargeSettings(self, charge_setting):
        self.cp.EV_ChargeSettings = charge_setting

    @property
    def state(self):
        state = self.node.sdo["CS_ChargePoint"]["PM_StatusCode"].raw
        return PMState(state)

    @state.setter
    def state(self, state: PMState):
        self.node.sdo["CS_ChargePoint"]["PM_StatusCode"].raw = state.value

    @property
    def cp_state(self):
        """State of the associated charge point"""
        return ChargePointState(self.node.sdo["CS_ChargePoint"]["CP_StatusCode"].raw)

    def configure_pdos(self):
        "Configure PM TPDOs and RPDOs"

        self.node.nmt.state = "PRE-OPERATIONAL"
        self.node.pdo.read()
        self.node.tpdo[1].cob_id = 0x180 + self.node.id
        self.node.tpdo[1].add_variable("CS_ChargePoint", "PM_StatusCode")
        self.node.tpdo[1].add_variable("CS_ChargePoint", "PM_ErrorCode_EVSE")
        self.node.tpdo[1].add_variable("CS_ChargePoint", "PM_ErrorCode_EV")
        self.node.tpdo[1].add_variable("PM_ChargeParameters", "EV_BatteryCapacity")
        self.node.tpdo[1].trans_type = 1
        self.node.tpdo[1].enabled = True

        self.node.tpdo[2].cob_id = 0x280 + self.node.id
        self.node.tpdo[2].add_variable("PM_PowerLimitations", "EV_MinDcChargeCurrent")
        self.node.tpdo[2].add_variable("PM_PowerLimitations", "EV_MaxDcChargeCurrent")
        self.node.tpdo[2].add_variable("PM_PowerLimitations", "EV_MaxDcVoltage")
        self.node.tpdo[2].add_variable("PM_ChargeParameters", "EV_TargetStateOfCharge")
        self.node.tpdo[2].add_variable("PM_ChargeParameters", "EV_TargetStateOfChargeBulk_CCS")
        self.node.tpdo[2].trans_type = 1
        self.node.tpdo[2].enabled = True

        self.node.tpdo[3].cob_id = 0x380 + self.node.id
        self.node.tpdo[3].add_variable("PM_ChargeParameters", "EV_MaxChargeTime_CHA")
        self.node.tpdo[3].add_variable("PM_ChargeParameters", "EV_EstimatedChargeTime_CHA")
        self.node.tpdo[3].trans_type = 1
        self.node.tpdo[3].enabled = True

        self.node.tpdo[4].cob_id = 0x480 + self.node.id
        self.node.tpdo[4].add_variable("PM_InChargeData", "EV_TargetDcCurrent_legacy")
        self.node.tpdo[4].add_variable("PM_InChargeData", "EV_TargetDcVoltage")
        self.node.tpdo[4].add_variable("PM_InChargeData", "EVSE_MaxOutLimitationsReachedBits_CCS")
        self.node.tpdo[4].add_variable("PM_InChargeData", "EV_CurStateOfCharge")
        self.node.tpdo[4].trans_type = 1
        self.node.tpdo[4].enabled = True

        # TODO : finish adding all other variables

        self.node.rpdo[1].cob_id = 0x200 + self.node.id
        self.node.rpdo[1].enabled = True
        # self.node.rpdo[1].add_callback(self.node.on_rpdo)

        self.node.rpdo[2].cob_id = 0x300 + self.node.id
        self.node.rpdo[2].enabled = True
        self.node.rpdo[2].add_variable("CS_ChargePoint", "CP_StatusCode")
        self.node.rpdo[2].add_variable("PM_ChargeParameters", "EVSE_MaxPeakCurrentRipple_CCS")
        self.node.rpdo[2].add_variable("PM_PowerLimitations", "EVSE_MaxDcChargePower")
        # self.node.rpdo[2].add_callback(self.node.on_rpdo)

        self.node.rpdo[3].cob_id = 0x400 + self.node.id
        self.node.rpdo[3].enabled = True
        # self.node.rpdo[3].add_callback(self.node.on_rpdo)

        self.node.rpdo[4].cob_id = 0x500 + self.node.id
        self.node.rpdo[4].enabled = True
        # self.node.rpdo[4].add_callback(self.node.on_rpdo)

        # TODO: add support for v2g rpdos
        self.node.pdo.save()
        self.node.nmt.state = "OPERATIONAL"

    def _check_id_validity(self):
        """Check that given pm id and evis are valid"""
        if not self.node.id in (self.CCS_IDS + self.CHA_IDS):
            raise ValueError(f"{self.node.id} is not a valid pm id")

    def _next_step(self):
        """Perform a state machine iteration"""
        state = self.state
        cp_state = self.cp_state
        # Check for charge point fault
        if cp_state == ChargePointState.CP17_EmergencyStop:
            # Goto PM 11
            self.state = PMState.PM11_Fault
            return

        if state == PMState.PM0_Init:
            self.state = PMState.PM1_Idle

        elif state == PMState.PM1_Idle:
            if cp_state == ChargePointState.CP2_WaitForEV:
                # In old mode there is no cp2_s2 transition
                # if self.cp.substate == "CP2_S2_SetupPUs":
                self.state = PMState.PM2_EVWaitingToBeCharged

        # EV WAITING CHARGE
        elif state == PMState.PM2_EVWaitingToBeCharged:
            # CS needs to be in cp6
            if cp_state == ChargePointState.CP6_LockCableToEV:
                self.state = PMState.PM3_CableIsLocked

        # CABLE LOCKED
        elif state == PMState.PM3_CableIsLocked:
            # CS needs to be in cp7
            if cp_state == ChargePointState.CP7_CableCheck:
                self.state = PMState.PM4_EVWaitingForPower

        # EV WAITING FOR POWER
        elif state == PMState.PM4_EVWaitingForPower:
            # Two ways of leaving state machine : CP10 or stop request from vehicle
            if cp_state == ChargePointState.CP10_StopPUsAndPMs:
                self.state = PMState.PM6_ChargeIsStopped

        # EV STOP REQUEST
        elif state == PMState.PM5_EVChargeStopRequest:
            raise NotImplementedError("EV stop request state not implemented in PM")

        # CHARGE IS STOPPED
        elif state == PMState.PM6_ChargeIsStopped:
            # Leave when in cp11
            if cp_state == ChargePointState.CP11_SafetyChecks:
                self.state = PMState.PM7_PlugOutputIsOff

        # CHARGE PLUG OUTPUT IS OFF
        elif state == PMState.PM7_PlugOutputIsOff:
            # Leave when in cp12
            if cp_state == ChargePointState.CP12_StopCommWithEV:
                self.state = PMState.PM8_CommunicationTerminated

        # COMMUNICATION TERMINATED
        elif state == PMState.PM8_CommunicationTerminated:
            # Leave when in cp15 + cable unlocked
            if cp_state == ChargePointState.CP15_UnlockEvConnector:
                self.state = PMState.PM9_CableIsUnlocked

        # CABLE UNLOCKED
        elif state == PMState.PM9_CableIsUnlocked:
            if cp_state == ChargePointState.CP16_WaitForPMidle:
                self.state = PMState.PM1_Idle

        # CABLE UNPLUGGED BEFORE CHARGE
        elif state == PMState.PM10_CableUnpluggedBeforeCharge:
            raise ValueError(f"Cable unplugged before charge")

        # FAULT
        elif state == PMState.PM11_Fault:
            if cp_state == ChargePointState.CP18_Reset:
                self.state = PMState.PM1_Idle
        else:
            logger.warning(f"unknown PM {self.node.id} state {state}")

    def run_state_machine(self):
        """Internal state machine of PM, this is blocking"""
        prev_state = None
        self.state = PMState.PM0_Init
        self._running = True
        logger.info(f"starting emulated PM {self.node.id}")
        self.node.nmt.start_heartbeat(1000)
        while True:
            if self._running == False:
                self.node.nmt.stop_heartbeat()
                break
            if self.state != prev_state:
                logger.info(f"PM {self.node.id} | {prev_state} ==> {self.state}")
            prev_state = self.state
            self._next_step()
            time.sleep(self.STATE_MACHINE_DELAY_MS)
        logger.info(f"PM {self.node.id} exited state machine")

    def set_charge_setting(self, discharge_compatible=0, dynamic_mode=0, interface_type="efast"):
        raise NotImplementedError()
        # TODO reimplement this once V2G is added
        # if not self.cp.evis.is_v2g():
        #     return
        # if (not isinstance(interface_type, str)) or (
        #     interface_type not in ChargePoint.SUP_INTERFACES.keys()
        # ):
        #     raise TypeError(
        #         f"interface type must be one of {ChargePoint.SUP_INTERFACES.keys()} "
        #     )
        # interface_type_val = ChargePoint.SUP_INTERFACES[interface_type]
        # charge_setting = (
        #     (interface_type_val << 2) | (dynamic_mode << 1) | discharge_compatible
        # )
        # self.EV_ChargeSettings = charge_setting
