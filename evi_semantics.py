
from settings import (
    evi_BMPU_battery_max_current,
    evi_BMPU_battery_max_voltage,
    evi_BMPU_grid_max_current,
    evi_BMPU_grid_max_power,
)
from status_dictionaries import evi_directives_dictionary
from utilities import write_UWORD

evi_state_word_translator = {
    0 : "STATE_INIT (system is starting)",
    1 : "STATE_STANDBY (power is off, system waits a request)",
    2 : "STATE_POWER_ON (system ready to start)",
    3 : "STATE_CHARGE (charge is ongoing)",
    4 : "STATE_SAFE_D (critical fault, system halted untill user action)",
    5 : "STATE_RESERVED (for future use)",
    6 : "STATE_STOPPING (converter is stopping and power is being killed off)",
    7 : "STATE_FAULT_ACK (fault acknowledgement)"
}

evi_system_mode_translator = {
    0 : "MODE_UNKNOWN (Operation mode is not specified, system remains in stand by state)",
    1 : "MODE_VSI (Voltage source inverter (VSI) mode for V2L operation)",
    2 : "MODE_PFC_POWER (Power factor corrector (PFC) mode for G2V/V2G operations with constant current control on battery side)",
    3 : "MODE_PFC_VOLTAGE (Power factor corrector (PFC) mode for G2V/V2G operations with constant voltage control on battery side)",
}

evi_grid_conf_translator = {
    0 : "CONF_UNKNOWN (Grid configuration is not specified, system remains in stand by state.)",
    1 : "CONF_SINGLE_PHASE_TWO_WIRE (Single-phase configuration L1 as phase and L4 as neutral)",
    2 : "CONF_SINGLE_PHASE_FOUR_WIRE (Single-phase configuration with L1+L2 as phase and L3+L4 as neutral)",
    3 : "CONF_THREE_PHASE_THREE_WIRE (Three-phase configuration without neutral wire)",
    4 : "CONF_THREE_PHASE_FOUR_WIRE (Three-phase configuration with neutral wire)"
}


def assemble_x180(fault_detected, running_detected, ready_detected, precharging_detected, previously_faulted):
    if fault_detected is not None:
        evi_status = 4  # SAFE_D
    elif running_detected is not None:
        evi_status = 3  # CHARGE
    elif ready_detected is not None:
        evi_status = 2  # POWER_ON
    elif precharging_detected is not None:
        if previously_faulted:
            evi_status = 7  # FAULT_ACK
        else:
            evi_status = 1  # STANDBY
    DB0 = evi_status  # 0:3 bits are for system state
    DB1 = ((evi_directives_dictionary["pfc_mode_request"] << 5) | (evi_directives_dictionary["grid_conf_request"] << 3)) & 0xFF
    return [DB0, DB1, 0, 0, 0, 0, 0, 0]


x280_DB1, x280_DB0 = write_UWORD(value=evi_BMPU_battery_max_voltage, scale_factor=0.1)
x280_DB2, x280_DB3 = write_UWORD(value=evi_BMPU_battery_max_current, scale_factor=0.1)
x280_DB4, x280_DB5 = write_UWORD(value=evi_BMPU_grid_max_current, scale_factor=0.1)
x280_DB6, x280_DB7 = write_UWORD(value=evi_BMPU_grid_max_power, scale_factor=10)
assembled_x280_message = [x280_DB0, x280_DB1, x280_DB2, x280_DB3, x280_DB4, x280_DB5, x280_DB6, x280_DB7]


def assemble_x360(grid_voltage, grid_current, grid_power, grid_Q=0):
    DB1, DB0 = write_UWORD(value=grid_voltage, scale_factor=0.1)
    DB3, DB2 = write_UWORD(value=grid_current, scale_factor=0.1)
    DB5, DB4 = write_UWORD(value=grid_power, scale_factor=10)
    DB7, DB6 = write_UWORD(value=grid_Q, scale_factor=10)
    return [DB0, DB1, DB2, DB3, DB4, DB5, DB6, DB7]


def assemble_x460(battery_voltage, battery_current, battery_power, available_battery_current=None):
    DB1, DB0 = write_UWORD(value=battery_voltage, scale_factor=0.1)
    DB3, DB2 = write_UWORD(value=battery_current, scale_factor=0.1)
    DB5, DB4 = write_UWORD(value=battery_power, scale_factor=10)
    # ! TODO
    if available_battery_current is None:
        available_battery_current = battery_current
    DB7, DB6 = write_UWORD(value=available_battery_current, scale_factor=0.1)
    return [DB0, DB1, DB2, DB3, DB4, DB5, DB6, DB7]
