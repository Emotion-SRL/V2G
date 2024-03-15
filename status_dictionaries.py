
import threading
from datetime import datetime

zeka_status_dictionary_lock = threading.Lock()

evi_directives_dictionary = {
    "pfc_state_request" : 1,
    "pfc_mode_request" : None,
    "grid_conf_request" : None,
    "battery_voltage_setpoint" : None,  # Voltage reference
    "i_charge_limit" : None,  # Current limit to Side A
    "i_discharge_limit" : None,  # Current limit to Side B
    "UPDATE_COMMAND" : False,
    "UPDATE_REFERENCE" : False,
    "COMMAND_TIMESTAMP": datetime.now()
}

zeka_status_dictionary = {
    # Main Status Request
    "Phaseback": None,
    "Auto-boost": None,
    "Power limit/setpoint": None,
    "Current limit/setpoint": None,
    "Voltage limit/setpoint": None,
    "Device alarm/warning": None,
    "Device full stop": None,
    "Device fault": None,
    "Device running": None,
    "Device ready": None,
    "Device precharging": None,
    "Device mode": "No mode selected",
    # Feedback 1 Status Request
    "Side A (Battery) voltage": "0",
    "Side A (Battery) current": "0",
    "Heat-sink temperature (Side A)": "0",
    # Feedback 2 Status Request
    "Side B (DC-Link) voltage": "0",
    "Side B (DC-Link) current": "0",
    "Heat-sink temperature (Side B)": "0",
    # Error Status Request
    "General hardware fault": None,
    "PWM fault": None,
    "Analog input fault": None,
    "Digital output fault": None,
    "Overcurrent or asymmetry fault": None,
    "Side A (Battery) Undervoltage fault": None,
    "Side A (Battery) Overvoltage fault": None,
    "Side B (DC-Link) Undervoltage fault": None,
    "Side B (DC-Link) Overvoltage fault": None,
    "Heat sink Over-temperature fault": None,
    "DC-Link precharge timeout": None,
    "Battery precharge timeout": None,
    "DC-Link contactor opened during operation fault": None,
    "DC-Link contactor closing timeout fault": None,
    "DC-Link contactor not opening timeout fault": None,
    "Battery contactor opened during operation fault": None,
    "Battery contactor closing timeout fault": None,
    "Battery contactor not opening timeout fault": None,
    "Input/Output voltage difference": None,
    "E-stop": None,
    "No mode selected on start command": None,
    "Reference setpoint adjusted": None,
    "CAN communication lost": None,
    "Temperature derating active": None,
    # IO Status Request
    "User Relay #4": None,
    "User Relay #3": None,
    "User Digital Output #8": None,
    "User Digital Output #7": None,
    "User Digital Output #6": None,
    "User Digital Output #5": None,
    "User Digital Output #4": None,
    "User Digital Output #3": None,
    "Digital Input #6": None,
    "Digital Input #5": None,
    "PREVIOUSLY_FAULTED": False,
}
