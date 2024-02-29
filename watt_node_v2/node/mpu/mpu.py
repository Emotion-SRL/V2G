from typing import Union
import canopen
import time

from .datatypes import MPUState
from ..base import WattNodeController, ControllerException


class MPUController(WattNodeController):
    """Controller for an MPU
    implements helper functions for easily interacting with a power unit
    """

    VOLTAGE_GAIN = 10
    CURRENT_GAIN = 100
    POWER_GAIN = 1

    def __init__(self, node: Union["canopen.RemoteNode", "canopen.LocalNode"], *args, **kwargs):
        super().__init__(node, *args, **kwargs)

    @property
    def current_state(self) -> MPUState:
        """Return the current MPU state"""
        return MPUState(self.node.tpdo[1]["measurements.state_Current"].raw)

    @property
    def output_voltage(self) -> float:
        """Return the current output voltage"""
        return self.node.tpdo[3]["measurements.pu_outVoltage"].raw / self.VOLTAGE_GAIN

    @property
    def output_current(self) -> float:
        """Return the current output current"""
        return self.node.tpdo[3]["measurements.pu_outCurrent"].raw / self.CURRENT_GAIN

    @property
    def output_power(self) -> float:
        """Return the current output power"""
        return self.node.tpdo[3]["measurements.pu_outPower"].raw / self.POWER_GAIN

    @property
    def target_state(self) -> MPUState:
        """Return the target MPU state"""
        return MPUState(self.node.rpdo[1]["setPoints.state_Request"].raw)

    @target_state.setter
    def target_state(self, state: MPUState):
        """Target state"""
        self.node.rpdo[1]["setPoints.state_Request"].raw = MPUState.value
        self.node.rpdo[1].transmit()

    def wait_for_state(self, state: MPUState, timeout_s=10) -> None:
        """Wait for a power unit state"""
        start_time = time.time()
        while time.time() - start_time < timeout_s:
            if self.current_state == state:
                return True
            time.sleep(0.1)
        raise ControllerException(
            f"MPU did not go in {state} after {timeout_s}s (still in {self.current_state})"
        )

    def turn_on(self, clear_faults: bool = True) -> None:
        """Turn ON power unit by sending a charge command
        This will first clear any faults on power unit by going into idle
        This function is blocking and waits for the power unit to be turned on
        raises a controller exception if a timeout occurs
        """
        if clear_faults:
            # First clear the faults by going to idle
            self.node.rpdo[1]["setPoints.state_Request"].raw = MPUState.IDLE.value
            self.node.rpdo[1].transmit()
            self.wait_for_state(MPUState.IDLE)
        self.node.rpdo[1]["setPoints.state_Request"].raw = MPUState.CHARGING.value
        self.node.rpdo[1].transmit()
        self.wait_for_state(MPUState.CHARGING)

    def turn_off(self) -> None:
        """Turn OFF power unit by sending a stop command
        This is blocking and checks that power unit is in IDLE state after command
        raises a controller exception if a timeout occurs
        """
        self.node.rpdo[1]["setPoints.state_Request"].raw = MPUState.IDLE.value
        self.node.rpdo[1].transmit()
        self.wait_for_state(state=MPUState.IDLE)

    def update_setpoints(self, voltage: float = None, current: float = None, max_grid_power: float = None):
        """Update voltage ,current and power setpoints of power unit"""
        if voltage is not None:
            self.node.rpdo[1]["setPoints.dcdc_voltageOutSP"].raw = voltage * self.VOLTAGE_GAIN
        if current is not None:
            self.node.rpdo[1]["setPoints.dcdc_currentOutSP"].raw = current * self.CURRENT_GAIN
        if max_grid_power is not None:
            self.node.rpdo[1]["setPoints.pfc_iGridMaxSP"].raw = max_grid_power * self.POWER_GAIN
        self.node.rpdo[1].transmit()

    def trigger_fault(self, fault: int, mask: int = 2**32 - 1) -> None:
        """Trigger a fault on the power unit : this is only available on simulated power units
        Power unit should be charging before requesting to trigger a fault
        """
        if self.current_state != MPUState.CHARGING:
            raise ControllerException("MPU should be charging before requesting to trigger a fault")
        self.node.sdo["measurements"]["faultWord"].raw = fault
        self.node.sdo["limitation"]["criticalFaultMask"].raw = mask

    def open_contactors(self):
        """Fake opening power unit contactors (this only works on emulated devices)"""
        self.node.sdo["simulation"]["relays_open"].raw = 1

    def close_contactors(self):
        """Fake closing power unit contactors (this only works on emulated devices)"""
        self.node.sdo["simulation"]["relays_open"].raw = 0

    def init(self):
        """Initialize controller by reading the PDO configuration"""
        self.node.pdo.read()
