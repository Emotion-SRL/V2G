from .base import EmulatedDevice
from ..node.mpu import MPUController, MPUState
from ..local_node import LocalNode
import time
import logging

logger = logging.getLogger(__name__)


class EmulatedMPU(EmulatedDevice):
    """Emulated MPU device"""

    VOLTAGE_GAIN = 10
    CURRENT_GAIN = 100
    POWER_GAIN = 1
    STATE_MACHINE_DELAY_MS = 0.5

    def __init__(self, node: LocalNode):
        """Initiliaze device with corresponding node"""
        self.node = node
        self.internal_state = None
        self.prev_internal_state = None
        self._running = False
        self.node.add_pdo_configuration_callback(self.configure_pdos)

    @property
    def state(self) -> MPUState:
        """Get MPU current state"""
        return MPUState(self.node.sdo["measurements"]["state_Current"].raw)

    @state.setter
    def state(self, new_state: MPUState):
        """Update MPU current state"""
        self.node.sdo["measurements"]["state_Current"].raw = new_state.value

    @property
    def state_request(self) -> MPUState:
        """Get MPU state request"""
        return MPUState(self.node.sdo["setPoints"]["state_Request"].raw)

    @property
    def fault(self):
        """Get current MPU fault"""
        return self.node.sdo["measurements"]["faultWord"].raw

    @fault.setter
    def fault(self, fault: int):
        """Set a new MPU fault, this will trigger the MPU
        to go into fault on next state machine iteration
        The critical fault mask must be correctly set
        """
        self.node.sdo["measurements"]["faultWord"].raw = fault

    @property
    def critical_fault_mask(self):
        """Get critical fault mask"""
        return self.node.sdo["limitation"]["criticalFaultMask"].raw

    @property
    def relays_open(self) -> bool:
        return self.node.sdo["simulation"]["relays_open"].raw == 1

    @relays_open.setter
    def relays_open(self, val: bool):
        self.node.sdo["simulation"]["relays_open"] = val

    def configure_pdos(self):
        logger.info(f"configuring PDOs for MPU {self.node.id}")
        self.node.nmt.state = "PRE-OPERATIONAL"
        self.node.pdo.read()
        self.node.rpdo[1].cob_id = self.node.rpdo[1].cob_id + self.node.id
        self.node.rpdo[1].enabled = True

        self.node.tpdo[1].cob_id = self.node.tpdo[1].cob_id + self.node.id
        self.node.tpdo[1].enabled = True
        self.node.tpdo[1]["measurements.state_Current"].raw = MPUState.STARTUP.value

        self.node.tpdo[2].cob_id = self.node.tpdo[2].cob_id + self.node.id
        self.node.tpdo[2].enabled = True
        self.node.tpdo[2]["measurements.dcdc_availableCurrentOut"].raw = 63.0 * self.CURRENT_GAIN

        self.node.tpdo[3].cob_id = self.node.tpdo[3].cob_id + self.node.id
        self.node.tpdo[3].enabled = True
        self.node.tpdo[3]["measurements.pu_outVoltage"].raw = 0
        self.node.tpdo[3]["measurements.pu_outCurrent"].raw = 0
        self.node.tpdo[3]["measurements.pu_outPower"].raw = 0
        self.node.tpdo[3]["limitation.pfc_iGridMaxSPmax"].raw = 45.0 * self.CURRENT_GAIN

        self.node.tpdo[4].cob_id = self.node.tpdo[4].cob_id + self.node.id
        self.node.tpdo[4].enabled = True
        self.node.tpdo[4]["limitation.dcdc_vOutSPmin"].raw = 0.0 * self.VOLTAGE_GAIN
        self.node.tpdo[4]["limitation.dcdc_vOutSPmax"].raw = 500.0 * self.VOLTAGE_GAIN
        self.node.tpdo[4]["limitation.dcdc_iOutSPmax"].raw = 63.0 * self.CURRENT_GAIN
        self.node.tpdo[4]["limitation.dcdc_pOutSPmax"].raw = 25000.0 * self.POWER_GAIN

        self.node.pdo.save()
        self.node.nmt.state = "OPERATIONAL"

    def _next_step(self):
        """Perform next step of state machine"""
        state = self.state
        requested_state = self.state_request

        # Check for faults
        critical_fault = self.fault & int(self.critical_fault_mask)
        if critical_fault != 0 and state != MPUState.FAULT:
            logger.info(f"MPU {self.node.id} going into fault")
            self.state = MPUState.FAULT
            # Send emergency once
            self.node.emcy.send(
                0xFF01,
                register=0,
                data=b"\x00" + int.to_bytes(critical_fault, byteorder="little", length=4),
            )

        # Update limitations
        self.node.sdo["measurements"]["dcdc_availableCurrentOut"].raw = 63.0 * self.CURRENT_GAIN

        # STARTUP
        if state == MPUState.STARTUP:
            self.state = MPUState.IDLE

        # IDLE
        elif state == MPUState.IDLE:
            if requested_state == MPUState.CHARGING:
                self.state = MPUState.PASSIVE_PRECHARGE

        # PASSIVE_PRECHARGE
        elif state == MPUState.PASSIVE_PRECHARGE:
            self.state = MPUState.ACTIVE_PRECHARGE

        # ACTIVE_PRECHARGE
        elif state == MPUState.ACTIVE_PRECHARGE:
            self.state = MPUState.CHARGING

        # CHARGING
        elif state == MPUState.CHARGING:
            # Voltage is always updated (with max.)
            self.node.sdo["measurements"]["pu_outVoltage"].raw = min(
                self.node.sdo["setPoints"]["dcdc_voltageOutSP"].raw,
                self.node.sdo["limitation"]["dcdc_vOutSPmax"].raw,
            )
            # Update the current, depending on the use case
            if self.relays_open:
                self.node.sdo["measurements"]["pu_outCurrent"].raw = 0
                self.node.sdo["measurements"]["pu_outPower"].raw = 0
            else:
                self.node.sdo["measurements"]["pu_outCurrent"].raw = self.node.sdo["setPoints"][
                    "dcdc_currentOutSP"
                ].raw
                self.node.sdo["measurements"]["pu_outPower"].raw = (
                    (self.node.sdo["setPoints"]["dcdc_currentOutSP"].raw / self.CURRENT_GAIN)
                    * (self.node.sdo["measurements"]["pu_outVoltage"].raw / self.VOLTAGE_GAIN)
                ) * self.POWER_GAIN
            if requested_state == MPUState.IDLE:
                self.state = MPUState.STOP

        # STOP
        elif state == MPUState.STOP:
            # Output current and output voltage set back to 0
            self.node.sdo["measurements"]["pu_outCurrent"].raw = 0
            self.node.sdo["measurements"]["pu_outVoltage"].raw = 0
            self.node.sdo["measurements"]["pu_outPower"].raw = 0
            self.state = MPUState.IDLE

        # FAULT
        elif state == MPUState.FAULT:
            if requested_state == MPUState.IDLE:
                # Clear any faults before going to IDLE
                self.fault = 0
                self.state = MPUState.IDLE

        else:
            raise ValueError(f"unknown MPU state {state}")

    def run_state_machine(self):
        """Mimicks a basic internal mpu state machine"""
        logger.info(f"Internal State Machine of MPU with node id {self.node.id} has been started")
        self.node.nmt.start_heartbeat(1000)
        self._running = True
        prev_state = None
        self.state = MPUState.STARTUP
        while True:
            if self._running == False:
                self.node.nmt.stop_heartbeat()
                break
            self.state = self.state
            if self.state_request != self.state:
                logger.info(
                    f"MPU {self.node.id} | state request : {self.state_request} (current : {self.state})"
                )
            if prev_state != self.state:
                logger.info(f"MPU {self.node.id} | {prev_state} ==> {self.state}")
            prev_state = self.state
            try:
                self._next_step()
            except Exception as e:
                logger.error(e)
                raise
            time.sleep(self.STATE_MACHINE_DELAY_MS)
        logger.info(f"MPU {self.node.id} exited state machine")
