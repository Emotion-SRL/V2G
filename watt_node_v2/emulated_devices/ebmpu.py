import time
from .base import EmulatedDevice
from ..local_node import LocalNode
from ..node.bmpu.datatypes import BMPUStates, BMPUStateWord

import logging

logger = logging.getLogger(__name__)


class EmulatedBMPU(EmulatedDevice):
    """Emulated BMPU device"""

    VOLTAGE_GAIN = 10
    CURRENT_GAIN = 10
    POWER_GAIN = 0.1
    MAX_CHARGE_CURRENT = 50 * CURRENT_GAIN
    MAX_DISCHARGE_CURRENT = MAX_CHARGE_CURRENT
    STATE_MACHINE_DELAY_MS = 0.5

    def __init__(self, node: LocalNode):
        """Initiliaze device with corresponding node"""
        self.node = node
        self._running: bool = False
        self._configure_pdos()
        self._populate_initial_pdo_values()

    @property
    def current_state_word(self) -> BMPUStateWord:
        """Get current state word"""
        raw_state = self.node.sdo["measurements"]["itfc_current_state"].raw
        return BMPUStateWord.from_raw(raw_state)

    @current_state_word.setter
    def current_state_word(self, state_word: BMPUStateWord):
        """Update current state"""
        self.node.sdo["measurements"]["itfc_current_state"].raw = state_word.raw

    @property
    def current_state(self) -> BMPUStates:
        """Get current state (not to be confused with state word)"""
        state_word = self.current_state_word
        return state_word.state

    @current_state.setter
    def current_state(self, new_state: BMPUStates):
        """Update current state"""
        current_state_word = self.current_state_word
        current_state_word.state = new_state
        self.current_state_word = current_state_word

    @property
    def current_mode(self) -> int:
        """Get current mode"""
        return self.current_state_word.mode

    @current_mode.setter
    def current_mode(self, new_mode: int) -> int:
        """Update current mode"""
        current_state_word = self.current_state_word
        current_state_word.mode = new_mode
        self.current_state_word = current_state_word

    @property
    def current_conf(self) -> int:
        """Get current conf"""
        state_word = self.current_state_word
        return state_word.conf

    @current_conf.setter
    def current_conf(self, new_conf: int):
        """Update current conf"""
        current_state_word = self.current_state_word
        current_state_word.conf = new_conf
        self.current_state_word = current_state_word

    @property
    def requested_state_word(self) -> BMPUStateWord:
        """Get requested state"""
        state = self.node.sdo["setPoints"]["itfc_pfc_state_request"].raw
        mode = self.node.sdo["setPoints"]["itfc_pfc_mode_request"].raw
        conf = self.node.sdo["setPoints"]["itfc_grid_conf_request"].raw
        state_word = BMPUStateWord(state=BMPUStates(state), conf=conf, mode=mode)
        return state_word

    def _configure_pdos(self):
        """Configure RPDOs and TPDOs
        BMPUs PDOs are dynamically populated
        """
        pfc_node = self.node
        pfc_node_id = self.node.id
        # Put node in OPERATIONAL

        pfc_node.rpdo.read()
        pfc_node.tpdo.read()

        # Configure bmpu tpdos
        pfc_node.tpdo[1].clear()
        pfc_node.tpdo[1].cob_id = pfc_node_id + 0x180
        pfc_node.tpdo[1].add_variable("measurements", "itfc_current_state")
        pfc_node.tpdo[1].add_variable("measurements", "itfc_critical_fault_word")
        pfc_node.tpdo[1].trans_type = 1
        pfc_node.tpdo[1].enabled = True
        pfc_node.tpdo[1].transmit()

        pfc_node.tpdo[2].clear()
        pfc_node.tpdo[2].cob_id = pfc_node_id + 0x280
        pfc_node.tpdo[2].add_variable("measurements", "itfc_v_batt_max")
        pfc_node.tpdo[2].add_variable("measurements", "itfc_i_batt_max")
        pfc_node.tpdo[2].add_variable("measurements", "itfc_i_grid_max")
        pfc_node.tpdo[2].add_variable("measurements", "itfc_P_grid_max")
        pfc_node.tpdo[2].trans_type = 1
        pfc_node.tpdo[2].enabled = True

        pfc_node.tpdo[7].clear()
        pfc_node.tpdo[7].cob_id = pfc_node_id + 0x360
        pfc_node.tpdo[7].add_variable("measurements", "itfc_v_grid")
        pfc_node.tpdo[7].add_variable("measurements", "itfc_i_grid")
        pfc_node.tpdo[7].add_variable("measurements", "itfc_P_grid")
        pfc_node.tpdo[7].add_variable("measurements", "itfc_Q_grid")
        pfc_node.tpdo[7].trans_type = 1
        pfc_node.tpdo[7].enabled = True

        pfc_node.tpdo[8].clear()
        pfc_node.tpdo[8].cob_id = pfc_node_id + 0x460
        pfc_node.tpdo[8].add_variable("measurements", "itfc_v_batt")
        pfc_node.tpdo[8].add_variable("measurements", "itfc_i_batt")
        pfc_node.tpdo[8].add_variable("measurements", "itfc_P_batt")
        pfc_node.tpdo[8].add_variable("measurements", "itfc_available_i_batt")
        pfc_node.tpdo[8].trans_type = 1
        pfc_node.tpdo[8].enabled = True

        # Configure bmpu rpdos
        pfc_node.rpdo[1].clear()
        pfc_node.rpdo[1].cob_id = pfc_node_id + 0x200
        pfc_node.rpdo[1].add_variable("setPoints", "itfc_pfc_state_request")
        pfc_node.rpdo[1].add_variable("setPoints", "itfc_pfc_mode_request")
        pfc_node.rpdo[1].add_variable("setPoints", "itfc_grid_conf_request")
        pfc_node.rpdo[1].add_variable("setPoints", "itfc_v2l_frequency_setpoint")
        pfc_node.rpdo[1].add_variable("setPoints", "itfc_v2l_voltage_setpoint")
        pfc_node.rpdo[1].add_variable("setPoints", "itfc_output_voltage_setpoint")
        pfc_node.rpdo[1].add_callback(self.node.on_rpdo)
        pfc_node.rpdo[1].enabled = True

        pfc_node.rpdo[2].clear()
        pfc_node.rpdo[2].cob_id = pfc_node_id + 0x300
        pfc_node.rpdo[2].add_variable("setPoints", "itfc_i_charge_limit")
        pfc_node.rpdo[2].add_variable("setPoints", "itfc_i_discharge_limit")
        pfc_node.rpdo[2].add_variable("setPoints", "itfc_active_power_setpoint")
        pfc_node.rpdo[2].add_variable("setPoints", "itfc_reactive_power_setpoint")
        pfc_node.rpdo[2].add_callback(self.node.on_rpdo)
        pfc_node.rpdo[2].add_callback(self._bmpu_callback_tpdo2)
        pfc_node.rpdo[2].enabled = True

        pfc_node.rpdo[3].clear()
        pfc_node.rpdo[3].cob_id = pfc_node_id + 0x400
        pfc_node.rpdo[3].add_variable("setPoints", "itfc_i_L1_limit")
        pfc_node.rpdo[3].add_variable("setPoints", "itfc_i_L2_limit")
        pfc_node.rpdo[3].add_variable("setPoints", "itfc_i_L3_limit")
        pfc_node.rpdo[3].add_callback(self.node.on_rpdo)
        pfc_node.rpdo[3].enabled = True
        pfc_node.nmt.state = "OPERATIONAL"
        # Add calbacks for tpdos
        for pdo_map in self.node.tpdo.map.values():
            for od_var in pdo_map.map:
                self.node.pdo_data_store.setdefault(od_var.index, {})
                self.node.pdo_data_store[od_var.index][od_var.subindex] = od_var
        pfc_node.pdo.save()

    def _populate_initial_pdo_values(self):
        """Initialize pdo values"""
        pfc_node = self.node
        pfc_node.tpdo[8]["measurements.itfc_available_i_batt"].raw = 32.76 * self.CURRENT_GAIN

        pfc_node.tpdo[2]["measurements.itfc_v_batt_max"].raw = 500.0 * self.VOLTAGE_GAIN
        pfc_node.tpdo[2]["measurements.itfc_i_batt_max"].raw = 32.76 * self.CURRENT_GAIN
        pfc_node.tpdo[2]["measurements.itfc_i_grid_max"].raw = 18.0 * self.CURRENT_GAIN
        pfc_node.tpdo[2]["measurements.itfc_P_grid_max"].raw = 11000 * self.POWER_GAIN

        pfc_node.tpdo[7]["measurements.itfc_v_grid"].raw = 400.0 * self.VOLTAGE_GAIN
        pfc_node.tpdo[7]["measurements.itfc_i_grid"].raw = 50.0 * self.CURRENT_GAIN
        pfc_node.tpdo[7]["measurements.itfc_P_grid"].raw = 10000 * self.POWER_GAIN
        pfc_node.tpdo[7]["measurements.itfc_Q_grid"].raw = 10000 * self.POWER_GAIN

    def _bmpu_callback_tpdo2(self, message):
        """Callback on evis tpdo transmission"""
        node = self.node
        if (
            message["setPoints.itfc_i_charge_limit"].raw != 0
            and message["setPoints.itfc_i_discharge_limit"].raw != 0
        ):
            logger.debug("Received a discharge limit and a charge limit, putting charge limit positive")
            node.sdo["measurements"]["itfc_i_batt"].raw = min(
                message["setPoints.itfc_i_charge_limit"].raw, self.MAX_CHARGE_CURRENT
            )
        elif message["setPoints.itfc_i_charge_limit"].raw != 0:
            # Charge limit received, bmpu is controlled in charge mode
            node.sdo["measurements"]["itfc_i_batt"].raw = min(
                message["setPoints.itfc_i_charge_limit"].raw, self.MAX_CHARGE_CURRENT
            )
        elif message["setPoints.itfc_i_discharge_limit"].raw != 0:
            # Discharge limit received, bmpu is controlled in discharge mode
            node.sdo["measurements"]["itfc_i_batt"].raw = -min(
                message["setPoints.itfc_i_discharge_limit"].raw,
                self.MAX_DISCHARGE_CURRENT,
            )

    def _next_step(self):
        """Perform a state machine iteration
        this implements BMPU specific state machine transitions
        """
        requested_state = self.requested_state_word.state
        # INIT
        if self.current_state == BMPUStates.INIT:
            self.current_state = BMPUStates.LOCK_DSP

        # LOCK_DSP
        elif self.current_state == BMPUStates.LOCK_DSP:
            self.current_state = BMPUStates.STANDBY

        # STANDBY
        elif self.current_state == BMPUStates.STANDBY:
            # Requested state has to be either charge,or power on
            if requested_state == BMPUStates.CHARGE:
                self.current_state = BMPUStates.CHARGE
            elif requested_state == BMPUStates.POWER_ON:
                self.current_state = BMPUStates.POWER_ON

        # POWER ON
        elif self.current_state == BMPUStates.POWER_ON:
            if requested_state == BMPUStates.CHARGE:
                self.current_state = BMPUStates.CHARGE

        # CHARGE
        elif self.current_state == BMPUStates.CHARGE:
            if requested_state == BMPUStates.STANDBY:
                self.current_state = BMPUStates.STOPPING

        # STOPPING
        elif self.current_state == BMPUStates.STOPPING:
            if requested_state == BMPUStates.STANDBY:
                self.current_state = BMPUStates.STANDBY

        # FAULT ACK
        elif self.current_state == BMPUStates.FAULT_ACK:
            if requested_state == BMPUStates.STANDBY:
                self.current_state = BMPUStates.STANDBY

        # SAFE_C or SAFE_D
        elif self.current_state == BMPUStates.SAFE_C or self.current_state == BMPUStates.SAFE_D:
            if requested_state == BMPUStates.FAULT_ACK:
                self.current_state = BMPUStates.FAULT_ACK
                return

        else:
            # The state is unknown
            logger.warning(f"BMPU {self.node.id} unknown state {self.current_state}")
        time.sleep(0.1)

    def run_state_machine(self):
        """Mimicks a basic internal bmpu state machine"""
        prev_current_state = None
        prev_requested_state = None
        logger.info(f"started emulated BMPU {self.node.id}")
        self.node.nmt.start_heartbeat(1000)
        self._running = True
        while True:
            if self._running == False:
                self.node.nmt.stop_heartbeat()
                break
            # Mode and conf are updated with no condition
            self.current_conf = self.requested_state_word.conf
            self.current_mode = self.requested_state_word.mode
            requested_state_word = self.requested_state_word

            if (requested_state_word.state != self.current_state) and (
                requested_state_word.state != prev_requested_state
            ):
                logger.info(f"new BMPU state request : {requested_state_word.state}")

            if prev_current_state != self.current_state:
                logger.info(f"BMPU {self.node.id} | {prev_current_state} ==> {self.current_state}")
            prev_current_state = self.current_state
            prev_requested_state = requested_state_word.state
            self._next_step()
            time.sleep(self.STATE_MACHINE_DELAY_MS)
        logger.info(f"BMPU {self.node.id} exited state machine")
