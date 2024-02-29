import logging
from typing import Union
import time
import canopen
from watt_node_v2.network import Network
from watt_node_v2.node.evis.evis import EvisController

from .datatypes import (
    EvisReleases,
    EvisIndexes,
    ChargePointInterface,
    ChargePointState,
    ChargePointSubState,
    SupervisorInterface,
    SupervisorRequestCode,
)
from .evis import EvisNode, v2g_compatible
from ..allocation_word import AllocationWord

logger = logging.getLogger(__name__)


class ChargePoint:
    RECEPTION_TIMEOUT = 0.2

    CCS_IDS = [0x11, 0x21, 0x19, 0x29]
    CHA_IDS = [0x13, 0x23, 0x1B, 0x2B]

    PM_VOLTAGE_GAIN = 10
    PM_CURRENT_GAIN = 10
    PM_POWER_GAIN = 0.1

    DEFAULT_LIMITS = {
        "SUP_MaxDcChargePower": 10000,
        "SUP_MaxDcChargeVoltage": 920,
        "SUP_MaxDcChargeCurrent": 40,
        "SUP_MaxAcChargeCurrent": 120,
    }

    def __init__(self, evis: EvisNode, interface: ChargePointInterface):
        self.evis: EvisNode = evis
        self.evis_controller = EvisController(evis)
        self.network: Network = evis.network
        self._interface = interface
        # Read evis release
        self.evis_release = self.evis_controller.release

        # Determine SUP and PM pdo offsets
        if self.evis_release == EvisReleases.LEGACY:
            self.tpdo_offset_sup = 15 + 2 * self._interface.value
            self.rpdo_sup_base = 41
            self.rpdo_offset_sup = 3 * self._interface.value  # 0 or 3
            self.pm_pdo_offset = 7 * self._interface.value  # 0 or 7
        elif self.evis_release == EvisReleases.EFAST:
            self.tpdo_offset_sup = 71 + 2 * self._interface.value
            self.rpdo_sup_base = 135
            self.rpdo_offset_sup = 3 * self._interface.value  # 0 or 3
            self.pm_pdo_offset = 7 * self._interface.value  # 0 or 7
        elif self.evis_release == EvisReleases.V2G:
            self.tpdo_offset_sup = 77 + 3 * self._interface.value
            self.rpdo_sup_base = 143
            self.rpdo_offset_sup = 5 * self._interface.value  # 0 or 5
            self.pm_pdo_offset = 11 * self._interface.value  # 0 or 7

        # Chargepoint properties
        self._extended_error = None
        self._error = None
        self._puAllocationCurrent = None
        self._puAllocationTarget = None
        self._cp_state = None
        self._cp_substate = None
        self._SUP_RequestCode = None
        self._SUP_Interface = 0  # by default legacy

    @property
    def interface(self):
        return self._interface

    @property
    def SUP_Interface(self) -> SupervisorInterface:
        request_code = self.evis.rpdo[self.rpdo_offset_sup + self.rpdo_sup_base][
            "CS_ChargePoint.SUP_RequestCode"
        ].raw
        return SupervisorInterface((request_code & 0b1100_0000) >> 6)

    @SUP_Interface.setter
    def SUP_Interface(self, interface: SupervisorInterface):
        pdo = self.rpdo_offset_sup + self.rpdo_sup_base
        self.evis.rpdo[pdo]["CS_ChargePoint.SUP_RequestCode"].raw = (
            interface.value << 6
        ) | self.SUP_RequestCode.value
        self.evis.rpdo[pdo].transmit()
        logger.info(f"Supervisor set to interface = {interface}")
        self.evis.rpdo[pdo].wait_for_reception(timeout=self.RECEPTION_TIMEOUT)

    @property
    def SUP_RequestCode(self) -> SupervisorRequestCode:
        request_code = self.evis.rpdo[self.rpdo_offset_sup + self.rpdo_sup_base][
            "CS_ChargePoint.SUP_RequestCode"
        ].raw
        return SupervisorRequestCode(request_code & 0b0000_1111)

    @SUP_RequestCode.setter
    def SUP_RequestCode(self, request_code: SupervisorRequestCode):
        """Set the sup request code"""
        computed_sup_request_code = (self.SUP_Interface.value << 6) | request_code.value
        pdo = self.rpdo_offset_sup + self.rpdo_sup_base
        self.evis.rpdo[pdo]["CS_ChargePoint.SUP_RequestCode"].raw = computed_sup_request_code
        self.evis.rpdo[pdo].transmit()

        logger.info(f"Sent SUP_Request_code : {request_code}")
        # Blocking wait reception with timeout
        self.evis.rpdo[pdo].wait_for_reception(timeout=self.RECEPTION_TIMEOUT)

    @property
    def SUP_MaxDcChargeCurrent(self):
        po = self.rpdo_sup_base + self.rpdo_offset_sup + 1
        if self.is_v2g():
            return (
                self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxDcChargeCurrent"].raw / EvisIndexes.CURRENT_GAIN
            )
        else:
            return self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxOutCurrent"].raw / EvisIndexes.CURRENT_GAIN

    @SUP_MaxDcChargeCurrent.setter
    def SUP_MaxDcChargeCurrent(self, current):
        po = self.rpdo_sup_base + self.rpdo_offset_sup + 1
        if self.is_v2g():
            self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxDcChargeCurrent"].raw = int(
                current * EvisIndexes.CURRENT_GAIN
            )
        else:
            self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxOutCurrent"].raw = int(
                current * EvisIndexes.CURRENT_GAIN
            )
        self.evis.rpdo[po].transmit()
        # Blocking wait reception with timeout
        self.evis.rpdo[po].wait_for_reception(timeout=self.RECEPTION_TIMEOUT)

    @property
    def SUP_MaxDcChargeVoltage(self):
        po = self.rpdo_sup_base + self.rpdo_offset_sup + 1
        if self.is_v2g():
            return (
                self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxDcChargeVoltage"].raw / EvisIndexes.VOLTAGE_GAIN
            )
        else:
            return self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxOutVoltage"].raw / EvisIndexes.VOLTAGE_GAIN

    @SUP_MaxDcChargeVoltage.setter
    def SUP_MaxDcChargeVoltage(self, voltage):
        po = self.rpdo_sup_base + self.rpdo_offset_sup + 1
        if self.is_v2g():
            self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxDcChargeVoltage"].raw = int(
                voltage * EvisIndexes.VOLTAGE_GAIN
            )
        else:
            self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxOutVoltage"].raw = int(
                voltage * EvisIndexes.VOLTAGE_GAIN
            )
        self.evis.rpdo[po].transmit()
        # Blocking wait reception with timeout
        self.evis.rpdo[po].wait_for_reception(timeout=self.RECEPTION_TIMEOUT)

    @property
    def SUP_MaxAcChargeCurrent(self):
        po = self.rpdo_sup_base + self.rpdo_offset_sup + 1
        if self.is_v2g():
            return (
                self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxAcChargeCurrent"].raw / EvisIndexes.CURRENT_GAIN
            )
        else:
            return self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxGridCurrent"].raw / EvisIndexes.CURRENT_GAIN

    @SUP_MaxAcChargeCurrent.setter
    def SUP_MaxAcChargeCurrent(self, current):
        po = self.rpdo_sup_base + self.rpdo_offset_sup + 1
        if self.is_v2g():
            self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxAcChargeCurrent"].raw = int(
                current * EvisIndexes.CURRENT_GAIN
            )
        else:
            self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxGridCurrent"].raw = int(
                current * EvisIndexes.CURRENT_GAIN
            )
        self.evis.rpdo[po].transmit()
        # Blocking wait reception with timeout
        self.evis.rpdo[po].wait_for_reception(timeout=self.RECEPTION_TIMEOUT)

    @property
    def SUP_MaxDcChargePower(self):
        po = self.rpdo_sup_base + self.rpdo_offset_sup
        if self.is_v2g():
            return self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxDcChargePower"].raw
        else:
            return self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxOutPower"].raw

    @SUP_MaxDcChargePower.setter
    def SUP_MaxDcChargePower(self, power):
        po = self.rpdo_sup_base + self.rpdo_offset_sup
        if self.is_v2g():
            self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxDcChargePower"].raw = power
        else:
            self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxOutPower"].raw = power
        self.evis.rpdo[po].transmit()
        # Blocking wait reception with timeout
        self.evis.rpdo[po].wait_for_reception(timeout=self.RECEPTION_TIMEOUT)

    # ---------------------------------------------------------------------------- #
    #                                   Only V2G                                   #
    # ---------------------------------------------------------------------------- #
    @property
    @v2g_compatible
    def SUP_MaxDcDischargeCurrent(self):
        po = self.rpdo_sup_base + self.rpdo_offset_sup + 3
        return self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxDcDischargeCurrent"].raw / EvisIndexes.CURRENT_GAIN

    @SUP_MaxDcDischargeCurrent.setter
    @v2g_compatible
    def SUP_MaxDcDischargeCurrent(self, current):
        po = self.rpdo_sup_base + self.rpdo_offset_sup + 3
        self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxDcDischargeCurrent"].raw = int(
            current * EvisIndexes.CURRENT_GAIN
        )
        self.evis.rpdo[po].transmit()
        # Blocking wait reception with timeout
        self.evis.rpdo[po].wait_for_reception(timeout=self.RECEPTION_TIMEOUT)

    @property
    @v2g_compatible
    def SUP_MaxDcDischargeVoltage(self):
        po = self.rpdo_sup_base + self.rpdo_offset_sup + 3
        return self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxDcDischargeVoltage"].raw / EvisIndexes.VOLTAGE_GAIN

    @SUP_MaxDcDischargeVoltage.setter
    @v2g_compatible
    def SUP_MaxDcDischargeVoltage(self, voltage):
        po = self.rpdo_sup_base + self.rpdo_offset_sup + 3
        self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxDcDischargeVoltage"].raw = int(
            voltage * EvisIndexes.VOLTAGE_GAIN
        )
        self.evis.rpdo[po].transmit()
        # Blocking wait reception with timeout
        self.evis.rpdo[po].wait_for_reception(timeout=self.RECEPTION_TIMEOUT)

    @property
    @v2g_compatible
    def SUP_MaxDcDischargePower(self):
        po = self.rpdo_sup_base + self.rpdo_offset_sup + 3
        return self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxDcDischargePower"].raw

    @SUP_MaxDcDischargePower.setter
    @v2g_compatible
    def SUP_MaxDcDischargePower(self, power):
        po = self.rpdo_sup_base + self.rpdo_offset_sup + 3
        self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxDcDischargePower"].raw = power
        self.evis.rpdo[po].transmit()
        # Blocking wait reception with timeout
        self.evis.rpdo[po].wait_for_reception(timeout=self.RECEPTION_TIMEOUT)

    @property
    @v2g_compatible
    def SUP_MaxDcDischargePower(self):
        po = self.rpdo_sup_base + self.rpdo_offset_sup + 3
        return self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxDcDischargePower"].raw

    @SUP_MaxDcDischargePower.setter
    @v2g_compatible
    def SUP_MaxDcDischargePower(self, power):
        po = self.rpdo_sup_base + self.rpdo_offset_sup + 3
        self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxDcDischargePower"].raw = power
        self.evis.rpdo[po].transmit()
        # Blocking wait reception with timeout
        self.evis.rpdo[po].wait_for_reception(timeout=self.RECEPTION_TIMEOUT)

    @property
    @v2g_compatible
    def SUP_MaxAcDischargeCurrent(self):
        po = self.rpdo_sup_base + self.rpdo_offset_sup + 4
        return self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxAcDischargeCurrent"].raw / EvisIndexes.CURRENT_GAIN

    @SUP_MaxAcDischargeCurrent.setter
    @v2g_compatible
    def SUP_MaxAcDischargeCurrent(self, current):
        po = self.rpdo_sup_base + self.rpdo_offset_sup + 4
        self.evis.rpdo[po]["CS_ChargePoint.SUP_MaxAcDischargeCurrent"].raw = int(
            current * EvisIndexes.CURRENT_GAIN
        )
        self.evis.rpdo[po].transmit()
        # Blocking wait reception with timeout
        self.evis.rpdo[po].wait_for_reception(timeout=self.RECEPTION_TIMEOUT)

    @property
    @v2g_compatible
    def chargeSetting(self):
        po = self.rpdo_sup_base + self.rpdo_offset_sup + 4
        return self.evis.rpdo[po]["CS_ChargePoint.SUP_ChargeSettingWord"].raw

    @chargeSetting.setter
    @v2g_compatible
    def chargeSetting(self, charge_setting):
        po = self.rpdo_sup_base + self.rpdo_offset_sup + 4
        self.evis.rpdo[po]["CS_ChargePoint.SUP_ChargeSettingWord"].raw = charge_setting
        self.evis.rpdo[po].transmit()

    # TODO pu allocations depend on the release and on the interface type

    def _get_allocation_current(self) -> canopen.pdo.Variable:
        release = self.evis_release
        rpdo = self.evis.rpdo
        if release == EvisReleases.LEGACY:
            puAllocationCurrent = rpdo[self.rpdo_sup_base + self.rpdo_offset_sup][
                "CS_ChargePoint.PowerUnitsAllocationCurrent_undebounced_legacy"
            ]
        elif release == EvisReleases.EFAST:
            puAllocationCurrent = rpdo[self.rpdo_sup_base + self.rpdo_offset_sup + 2][
                "CS_ChargePoint.PowerUnitsAllocationCurrent_undebounced_efast"
            ]
        elif release == EvisReleases.V2G:
            puAllocationCurrent = rpdo[self.rpdo_sup_base + self.rpdo_offset_sup + 2][
                "CS_ChargePoint.PowerUnitsAllocationCurrent_undebounced_extended"
            ]
        elif release == EvisReleases.OLD:
            puAllocationCurrent = rpdo[self.rpdo_sup_base + self.rpdo_offset_sup][
                "CS_ChargePoint.PowerUnitsAllocationCurrent_undebounced"
            ]
        else:
            raise ValueError(f"Evis release not known : {release}")
        return puAllocationCurrent

    def _get_allocation_target(self) -> canopen.objectdictionary.Variable:
        release = self.evis_release
        rpdo = self.evis.rpdo
        if release == EvisReleases.LEGACY:
            puAllocationTarget = rpdo[self.rpdo_sup_base + self.rpdo_offset_sup][
                "CS_ChargePoint.PowerUnitsAllocationTarget_undebounced_legacy"
            ]
        elif release == EvisReleases.EFAST:
            puAllocationTarget = rpdo[self.rpdo_sup_base + self.rpdo_offset_sup + 2][
                "CS_ChargePoint.PowerUnitsAllocationTarget_undebounced_efast"
            ]
        elif release == EvisReleases.V2G:
            puAllocationTarget = rpdo[self.rpdo_sup_base + self.rpdo_offset_sup + 2][
                "CS_ChargePoint.PowerUnitsAllocationTarget_undebounced_extended"
            ]
        elif release == EvisReleases.OLD:
            puAllocationTarget = rpdo[self.rpdo_sup_base + self.rpdo_offset_sup][
                "CS_ChargePoint.PowerUnitsAllocationTarget_undebounced"
            ]
        else:
            raise ValueError(f"Evis release not known : {release}")
        return puAllocationTarget

    @property
    def puAllocationCurrent(self) -> AllocationWord:
        return AllocationWord(self._get_allocation_current().raw)

    @puAllocationCurrent.setter
    def puAllocationCurrent(self, puAllocationCurrent: AllocationWord):
        current = self._get_allocation_current()
        current.raw = puAllocationCurrent.raw

    @property
    def puAllocationTarget(self) -> AllocationWord:
        return AllocationWord(self._get_allocation_target().raw)

    @puAllocationTarget.setter
    def puAllocationTarget(self, puAllocationTarget: AllocationWord):
        current = self._get_allocation_target()
        current.raw = puAllocationTarget.raw

    @property
    def error(self):
        error_code = self.evis.tpdo[self.tpdo_offset_sup]["CS_ChargePoint.CP_ErrorCode"].raw
        return self.network.db_handler.lut.get_error(error_code)

    @property
    def extended_error(self):
        # Check if extended error is available, otherwise return 0
        if "CS_ChargePoint.CP_ExtendedErrorCode" in self.evis.tpdo[self.tpdo_offset_sup + 1]:
            return self.network.db_handler.lut.get_extended_error(
                self.evis.tpdo[self.tpdo_offset_sup + 1]["CS_ChargePoint.CP_ExtendedErrorCode"].raw
            )
        else:
            return "Extended error not mapped"

    @property
    def state(self) -> ChargePointState:
        state = self.evis.tpdo[self.tpdo_offset_sup]["CS_ChargePoint.CP_StatusCode"].raw
        return ChargePointState(state)

    @property
    def substate(self) -> str:
        substate = self.evis.tpdo[self.tpdo_offset_sup]["CS_ChargePoint.CP_SubStatusCode"].raw
        return self.network.db_handler.lut.get_cp_substate(substate)

    @property
    def error_from_state(self):
        error_from_state = self.evis.tpdo[self.tpdo_offset_sup]["CS_ChargePoint.CP_error_from_state"].raw
        return self.network.db_handler.lut.get_cp_state(error_from_state)

    @property
    def error_from_substate(self):
        error_from_substate = self.evis.tpdo[self.tpdo_offset_sup][
            "CS_ChargePoint.CP_error_from_sub_state"
        ].raw
        return self.network.db_handler.lut.get_cp_substate(error_from_substate)

    def __str__(self):
        """Chargepoint main information"""
        # Return chargepoint informations
        info_attrs = [
            "interface",
            "state",
            "substate",
            "error",
            "extended_error",
            "error_from_state",
            "error_from_substate",
        ]
        return_str = ""
        for attr in info_attrs:
            return_str += f"{attr}\t : {getattr(self,attr)}\n"

        return return_str

    # ---------------------------------------------------------------------------- #
    #                                  EV(PM) settings                             #
    # ---------------------------------------------------------------------------- #

    @property
    def EV_MaxDcVoltage(self):
        po = self.pm_pdo_offset
        if self.is_v2g():
            return self.evis.rpdo[2 + po]["PM_PowerLimitations.EV_MaxDcVoltage"].raw / self.PM_VOLTAGE_GAIN
        else:
            return self.evis.rpdo[2 + po]["PM_PowerLimitations.EV_MaxInVoltage"].raw / self.PM_VOLTAGE_GAIN

    @EV_MaxDcVoltage.setter
    def EV_MaxDcVoltage(self, voltage):
        po = self.pm_pdo_offset
        if self.is_v2g():
            self.evis.rpdo[2 + po]["PM_PowerLimitations.EV_MaxDcVoltage"].raw = int(
                voltage * self.PM_VOLTAGE_GAIN
            )
        else:
            self.evis.rpdo[2 + po]["PM_PowerLimitations.EV_MaxInVoltage"].raw = int(
                voltage * self.PM_VOLTAGE_GAIN
            )

    @property
    def EV_MinDcChargeCurrent(self):
        po = self.pm_pdo_offset
        if self.is_v2g():
            return (
                self.evis.rpdo[2 + po]["PM_PowerLimitations.EV_MinDcChargeCurrent"].raw
                / self.PM_CURRENT_GAIN
            )
        else:
            return (
                self.evis.rpdo[2 + po]["PM_PowerLimitations.EV_MinInCurrent_CHA"].raw / self.PM_CURRENT_GAIN
            )

    @EV_MinDcChargeCurrent.setter
    def EV_MinDcChargeCurrent(self, current):
        po = self.pm_pdo_offset
        if self.is_v2g():
            self.evis.rpdo[2 + po]["PM_PowerLimitations.EV_MinDcChargeCurrent"].raw = int(
                current * self.PM_CURRENT_GAIN
            )
        else:
            self.evis.rpdo[2 + po]["PM_PowerLimitations.EV_MinInCurrent_CHA"].raw = int(
                current * self.PM_CURRENT_GAIN
            )

    @property
    def EV_MaxDcChargeCurrent(self):
        po = self.pm_pdo_offset
        if self.is_v2g():
            return (
                self.evis.rpdo[2 + po]["PM_PowerLimitations.EV_MaxDcChargeCurrent"].raw
                / self.PM_CURRENT_GAIN
            )
        else:
            return (
                self.evis.rpdo[2 + po]["PM_PowerLimitations.EV_MaxInCurrent_CCS"].raw / self.PM_CURRENT_GAIN
            )

    @EV_MaxDcChargeCurrent.setter
    def EV_MaxDcChargeCurrent(self, current):
        po = self.pm_pdo_offset
        if self.is_v2g():
            self.evis.rpdo[2 + po]["PM_PowerLimitations.EV_MaxDcChargeCurrent"].raw = int(
                current * self.PM_CURRENT_GAIN
            )
        else:
            self.evis.rpdo[2 + po]["PM_PowerLimitations.EV_MaxInCurrent_CCS"].raw = int(
                current * self.PM_CURRENT_GAIN
            )

    # V2G only

    @property
    @v2g_compatible
    def EV_MinDcDischargeVoltage(self):
        po = self.pm_pdo_offset + 9
        return self.evis.rpdo[po]["PM_PowerLimitations.EV_MinDcDischargeVoltage"].raw / self.PM_VOLTAGE_GAIN

    @EV_MinDcDischargeVoltage.setter
    @v2g_compatible
    def EV_MinDcDischargeVoltage(self, voltage):
        po = self.pm_pdo_offset + 9
        self.evis.rpdo[po]["PM_PowerLimitations.EV_MinDcDischargeVoltage"].raw = int(
            voltage * self.PM_VOLTAGE_GAIN
        )

    @property
    @v2g_compatible
    def EV_MinDcDischargeCurrent(self):
        po = self.pm_pdo_offset + 9
        return self.evis.rpdo[po]["PM_PowerLimitations.EV_MinDcDischargeCurrent"].raw / self.PM_CURRENT_GAIN

    @EV_MinDcDischargeCurrent.setter
    @v2g_compatible
    def EV_MinDcDischargeCurrent(self, current):
        po = self.pm_pdo_offset + 9
        self.evis.rpdo[po]["PM_PowerLimitations.EV_MinDcDischargeCurrent"].raw = int(
            current * self.PM_CURRENT_GAIN
        )

    @property
    @v2g_compatible
    def EV_MaxDcDischargeCurrent(self):
        po = self.pm_pdo_offset + 9
        return self.evis.rpdo[po]["PM_PowerLimitations.EV_MaxDcDischargeCurrent"].raw / self.PM_CURRENT_GAIN

    @EV_MaxDcDischargeCurrent.setter
    @v2g_compatible
    def EV_MaxDcDischargeCurrent(self, current):
        po = self.pm_pdo_offset + 9
        self.evis.rpdo[po]["PM_PowerLimitations.EV_MaxDcDischargeCurrent"].raw = int(
            current * self.PM_CURRENT_GAIN
        )

    @property
    @v2g_compatible
    def EV_MinDcDischargePower(self):
        po = self.pm_pdo_offset + 8
        return self.evis.rpdo[po]["PM_PowerLimitations.EV_MinDcDischargePower"].raw / self.PM_POWER_GAIN

    @EV_MinDcDischargePower.setter
    @v2g_compatible
    def EV_MinDcDischargePower(self, power):
        po = self.pm_pdo_offset + 8
        self.evis.rpdo[po]["PM_PowerLimitations.EV_MinDcDischargePower"].raw = int(
            power * self.PM_POWER_GAIN
        )

    @property
    @v2g_compatible
    def EV_MaxDcDischargePower(self):
        po = self.pm_pdo_offset + 8
        return self.evis.rpdo[po]["PM_PowerLimitations.EV_MaxDcDischargePower"].raw / self.PM_POWER_GAIN

    @EV_MaxDcDischargePower.setter
    @v2g_compatible
    def EV_MaxDcDischargePower(self, power):
        po = self.pm_pdo_offset + 8
        self.evis.rpdo[po]["PM_PowerLimitations.EV_MaxDcDischargePower"].raw = int(
            power * self.PM_POWER_GAIN
        )
        self.evis.rpdo[po].transmit()

    @property
    def EV_TargetDcVoltage(self):
        po = self.pm_pdo_offset + 4
        if self.is_v2g():
            return self.evis.rpdo[po]["PM_InChargeData.EV_TargetDcVoltage"].raw / self.PM_VOLTAGE_GAIN
        else:
            return self.evis.rpdo[po]["PM_InChargeData.EV_TargetInVoltage"].raw / self.PM_VOLTAGE_GAIN

    @EV_TargetDcVoltage.setter
    def EV_TargetDcVoltage(self, voltage):
        po = self.pm_pdo_offset + 4
        if self.is_v2g():
            self.evis.rpdo[po]["PM_InChargeData.EV_TargetDcVoltage"].raw = int(
                voltage * self.PM_VOLTAGE_GAIN
            )
        else:
            self.evis.rpdo[po]["PM_InChargeData.EV_TargetInVoltage"].raw = int(
                voltage * self.PM_VOLTAGE_GAIN
            )

    @property
    def EV_TargetDcCurrent(self):
        if self.is_v2g():
            if self.SUP_Interface == SupervisorInterface.V2G:
                po = self.pm_pdo_offset + 11
                return self.evis.rpdo[po]["PM_InChargeData.EV_TargetDcCurrent"].raw / self.PM_CURRENT_GAIN
            else:
                po = self.pm_pdo_offset + 4
                return (
                    self.evis.rpdo[po]["PM_InChargeData.EV_TargetDcCurrent_legacy"].raw
                    / self.PM_CURRENT_GAIN
                )
        else:
            po = self.pm_pdo_offset + 4
            return self.evis.rpdo[po]["PM_InChargeData.EV_TargetInCurrent"].raw / self.PM_CURRENT_GAIN

    @EV_TargetDcCurrent.setter
    def EV_TargetDcCurrent(self, current):
        if self.is_v2g():
            if self.SUP_Interface == SupervisorInterface.V2G:
                po = self.pm_pdo_offset + 11
                self.evis.rpdo[po]["PM_InChargeData.EV_TargetDcCurrent"].raw = int(
                    current * self.PM_CURRENT_GAIN
                )
            else:
                po = self.pm_pdo_offset + 4
                self.evis.rpdo[po]["PM_InChargeData.EV_TargetDcCurrent_legacy"].raw = int(
                    current * self.PM_CURRENT_GAIN
                )
        else:
            po = self.pm_pdo_offset + 4
            self.evis.rpdo[po]["PM_InChargeData.EV_TargetInCurrent"].raw = int(
                current * self.PM_CURRENT_GAIN
            )

    @property
    @v2g_compatible
    def EV_ChargeSettings(self):
        po = self.pm_pdo_offset + 9
        return self.evis.rpdo[po]["CS_ChargePoint.PM_ChargeSettingWord"].raw

    @EV_ChargeSettings.setter
    @v2g_compatible
    def EV_ChargeSettings(self, charge_setting):
        po = self.pm_pdo_offset + 9
        self.evis.rpdo[po]["CS_ChargePoint.PM_ChargeSettingWord"].raw = charge_setting
        self.evis.rpdo[po].transmit()

    # ----------------------------------------------------------------------------- #
    #                              Chargepoint public methods                       #
    # ----------------------------------------------------------------------------- #

    def goto_state(self, cp_state: ChargePointState, **kwargs):
        """Put Chargepoint inside a cp state"""
        # First check if already in requested state
        actual_state = self.state

        if self.state == cp_state:
            return

        logger.info(f"Transition from state {actual_state} to {cp_state}")

        if cp_state == ChargePointState.CP0_Init:
            pass

        elif cp_state == ChargePointState.CP1_WaitForSupApprob:
            self.goto_state(ChargePointState.CP18_Reset, **kwargs)
            # Two conditions : sup0_idle and pm1_idle
            self.SUP_RequestCode = SupervisorRequestCode.SUP0_Idle

        elif cp_state == ChargePointState.CP2_WaitForEV:
            self.goto_state(ChargePointState.CP1_WaitForSupApprob, **kwargs)
            self.SUP_RequestCode = SupervisorRequestCode.SUP1_Approbation

        elif cp_state == ChargePointState.CP4_WaitForPUs:
            self.goto_state(ChargePointState.CP2_WaitForEV, **kwargs)
            self.EV_MaxDcVoltage = 810
            allocation_word = AllocationWord(raw=0)
            # This Supposes that an mpu is present on the bus of course
            allocation_word.mpu_list = [1]
            self.update_allocations(allocation_word, allocation_word)
            self.SUP_RequestCode = SupervisorRequestCode.SUP3_AllocationDone

        elif cp_state == ChargePointState.CP6_LockCableToEV:
            self.goto_state(ChargePointState.CP4_WaitForPUs, **kwargs)

        elif cp_state == ChargePointState.CP7_CableCheck:
            self.goto_state(ChargePointState.CP6_LockCableToEV, **kwargs)

        elif cp_state == ChargePointState.CP8_ChargeLoop:
            self.goto_state(ChargePointState.CP7_CableCheck, **kwargs)

        elif cp_state == ChargePointState.CP10_StopPUsAndPMs:
            self.goto_state(ChargePointState.CP8_ChargeLoop, **kwargs)
            self.SUP_RequestCode = SupervisorRequestCode.SUP4_EVSEStopChargeReq

        elif cp_state == ChargePointState.CP11_SafetyChecks:
            self.goto_state(ChargePointState.CP10_StopPUsAndPMs, **kwargs)

        elif cp_state == ChargePointState.CP12_StopCommWithEV:
            self.goto_state(ChargePointState.CP11_SafetyChecks, **kwargs)

        elif cp_state == ChargePointState.CP14_ReleasePUs:
            self.goto_state(ChargePointState.CP12_StopCommWithEV, **kwargs)

        elif cp_state == ChargePointState.CP15_UnlockEvConnector:
            self.goto_state(ChargePointState.CP14_ReleasePUs, **kwargs)
            self.SUP_RequestCode = SupervisorRequestCode.SUP5_Terminate

        elif cp_state == ChargePointState.CP16_WaitForPMidle:
            self.goto_state(ChargePointState.CP15_UnlockEvConnector, **kwargs)

        elif cp_state == ChargePointState.CP17_EmergencyStop:
            # If in cp18 go in cp17 otherwise can't trigger fault
            self.update_allocations(AllocationWord(0), AllocationWord(0))
            if self.state == ChargePointState.CP18_Reset:
                # Goto CP1 and trigger fault
                self.goto_state(ChargePointState.CP1_WaitForSupApprob, **kwargs)
            # trigger fault
            self.SUP_RequestCode = SupervisorRequestCode.SUP2_Cancellation

        elif cp_state == ChargePointState.CP18_Reset:
            self.goto_state(ChargePointState.CP17_EmergencyStop, **kwargs)
            self.SUP_RequestCode = SupervisorRequestCode.SUP6_Reset

        else:
            raise ValueError("Unknwown CP state")

        # Wait for the state
        self.wait_for_state(cp_state)
        # Goes here only if wait_for_state does not create exception
        return cp_state

    def set_charge_setting(self, discharge_compatible=0, dynamic_mode=0, discharge_mode=0):
        if not self.is_v2g():
            return
        charge_setting = (discharge_mode << 2) | (dynamic_mode << 1) | discharge_compatible
        logger.success(
            f"Set Supervisor Charge Settings to : Discharge Mode = {discharge_mode:=} | Dynamic Mode = {dynamic_mode:=} | Discharge Compatibility = {discharge_compatible:=}"
        )
        self.chargeSetting = charge_setting

    def update_limitations(
        self,
        max_dc_charge_power: int = 10_000,
        max_dc_charge_voltage: int = 920,
        max_dc_charge_current: int = 40,
        max_ac_charge_current: int = 120,
    ):
        """Update chargepoint limitations with standard units (Watt,Amp,Volt)"""
        self.SUP_MaxDcChargePower = max_dc_charge_power
        self.SUP_MaxDcChargeVoltage = max_dc_charge_voltage
        self.SUP_MaxDcChargeCurrent = max_dc_charge_current
        self.SUP_MaxAcChargeCurrent = max_ac_charge_current

    def update_allocations(
        self,
        puAllocationCurrent: Union[AllocationWord, None] = None,
        puAllocationTarget: Union[AllocationWord, None] = None,
    ):
        """Update chargepoint allocated power units, at the same time or independently"""
        if puAllocationCurrent is not None:
            self.puAllocationCurrent = puAllocationCurrent
        if puAllocationTarget is not None:
            self.puAllocationTarget = puAllocationTarget
        # Get the pdo parent and send
        self._get_allocation_target().pdo_parent.transmit()

    def wait_for_state(
        self,
        cp_state_or_substate: Union[ChargePointState, ChargePointSubState],
        timeout_s: int = 20,
    ) -> None:
        """Wait for chargepoint to reach a certain state or substate"""
        time_start = time.time()
        # Very fast because we don't want to miss a transition
        while True:
            self.evis.tpdo[self.tpdo_offset_sup].wait_for_reception(timeout_s)
            actual_state = self.state
            actual_substate = self.substate
            if actual_state == cp_state_or_substate or actual_substate == cp_state_or_substate:
                break
            if time.time() - time_start > timeout_s:
                raise ChargePointException(
                    f"The chargepoint is not in {cp_state_or_substate} after {timeout_s} {str(self)}"
                )

    def wait_for_state_different(
        self,
        cp_state_or_substate: Union[ChargePointState, ChargePointSubState],
        timeout_s: int = 20,
    ) -> None:
        """Wait until chargepoint changes to a different state"""
        time_start = time.time()
        while True:
            self.evis.tpdo[self.tpdo_offset_sup].wait_for_reception(timeout_s)
            actual_state = self.state
            actual_substate = self.substate
            if actual_state == cp_state_or_substate or actual_substate == cp_state_or_substate:
                pass
            else:
                break
            if time.time() - time_start > timeout_s:
                raise ChargePointException(
                    f"The chargepoint state did not change after {timeout_s} {str(self)}"
                )

    def is_v2g(self):
        return self.evis_release == EvisReleases.V2G


class ChargePointException(Exception):
    """Chargepoint exception"""
