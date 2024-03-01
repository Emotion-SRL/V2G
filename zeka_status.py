import threading

main_status_request = [0xA0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
feedback_1_status_request = [0xA1, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
feedback_2_status_request = [0xA2, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
error_status_request = [0xA3, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
IOs_status_request = [0xA4, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]

status_dictionary_lock = threading.Lock()

status_dictionary = {
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
}


def red_text(text):
    return '\033[91m' + text + '\033[0m'


def read_SWORD(high_byte, low_byte, scale_factor):
    return round(((high_byte << 8) | low_byte) * scale_factor, 1)


def print_global_state():
    print("GLOBAL STATE:")
    for key, value in status_dictionary.items():
        if value is not None:
            print(key + ": " + red_text(str(value)))


def main_status_update(DB):
    MSB_1 = DB[1]
    MSB_0 = DB[2]
    ASB_1 = DB[3]
    ASB_0 = DB[4]
    if (MSB_1 & 0x10) == 0:
        status_dictionary["Phaseback"] = None
    else:
        status_dictionary["Phaseback"] = "active"
    if (MSB_1 & 0x08) == 0:
        status_dictionary["Auto-boost"] = None
    else:
        status_dictionary["Auto-boost"] = "running"
    if (MSB_1 & 0x04) == 0:
        status_dictionary["Power limit/setpoint"] = None
    else:
        status_dictionary["Power limit/setpoint"] = "reached"
    if (MSB_1 & 0x02) == 0:
        status_dictionary["Current limit/setpoint"] = None
    else:
        status_dictionary["Current limit/setpoint"] = "reached"
    if (MSB_1 & 0x01) == 0:
        status_dictionary["Voltage limit/setpoint"] = None
    else:
        status_dictionary["Voltage limit/setpoint"] = "reached"
    if (MSB_0 & 0x80) == 0:
        status_dictionary["Device alarm/warning"] = None
    else:
        status_dictionary["Device alarm/warning"] = "alarm / warning"
    if (MSB_0 & 0x40) == 0:
        status_dictionary["Device full stop"] = None
    else:
        status_dictionary["Device full stop"] = "full stop active"
    if (MSB_0 & 0x08) == 0:
        status_dictionary["Device fault"] = None
    else:
        status_dictionary["Device fault"] = "fault"
    if (MSB_0 & 0x04) == 0:
        status_dictionary["Device running"] = None
    else:
        status_dictionary["Device running"] = "running"
    if (MSB_0 & 0x02) == 0:
        status_dictionary["Device ready"] = None
    else:
        status_dictionary["Device ready"] = "ready"
    if (MSB_0 & 0x01) == 0:
        status_dictionary["Device precharging"] = None
    else:
        status_dictionary["Device precharging"] = "precharging"
    if ASB_0 == 0:  # 0
        status_dictionary["Device mode"] = "No mode selected"
    elif ASB_0 == 1:  # (ASB_0 & 0x01) != 0:  # 1
        status_dictionary["Device mode"] = "Buck 1Q voltage control mode"
    elif ASB_0 == 2:  # (ASB_0 & 0x02) != 0:  # 2
        status_dictionary["Device mode"] = "Buck 1Q current control mode"
    elif ASB_0 == 3:  # (ASB_0 & 0x04) != 0:  # 3
        status_dictionary["Device mode"] = "Boost 1Q voltage control mode"
    elif ASB_0 == 4:  # (ASB_0 & 0x08) != 0:  # 4
        status_dictionary["Device mode"] = "Boost 1Q current control mode"
    elif ASB_0 == 5:  # (ASB_0 & 0x10) != 0:  # 5
        status_dictionary["Device mode"] = "Buck 2Q voltage control mode"
    elif ASB_0 == 6:  # (ASB_0 & 0x20) != 0:
        status_dictionary["Device mode"] = "Boost 2Q voltage control mode"
    elif ASB_0 == 8:  # (ASB_0 & 0x80) != 0:  # 8
        status_dictionary["Device mode"] = "Boost A current B voltage control mode"


def feedback_1_status_update(DB):
    BV_1 = DB[1]
    BV_0 = DB[2]
    BC_1 = DB[3]
    BC_0 = DB[4]
    HST_1 = DB[5]
    HST_0 = DB[6]
    voltage = read_SWORD(BV_1, BV_0, 0.1)
    current = read_SWORD(BC_1, BC_0, 0.1)
    temperature = read_SWORD(HST_1, HST_0, 0.1)
    status_dictionary["Side A (Battery) voltage"] = str(voltage) + " V"
    status_dictionary["Side A (Battery) current"] = str(current) + " A"
    status_dictionary["Heat-sink temperature (Side A)"] = str(temperature) + " °C"


def feedback_2_status_update(DB):
    DCV_1 = DB[1]
    DCV_0 = DB[2]
    DCI_1 = DB[3]
    DCI_0 = DB[4]
    HST_1 = DB[5]
    HST_0 = DB[6]
    voltage = read_SWORD(DCV_1, DCV_0, 0.1)
    current = read_SWORD(DCI_1, DCI_0, 0.1)
    temperature = read_SWORD(HST_1, HST_0, 0.1)
    status_dictionary["Side B (DC-Link) voltage"] = str(voltage) + " V"
    status_dictionary["Side B (DC-Link) current"] = str(current) + " A"
    status_dictionary["Heat-sink temperature (Side B)"] = str(temperature) + " °C"


def error_status_update(DB):
    FLT1_1 = DB[1]
    FLT1_0 = DB[2]
    FLT2_1 = DB[3]
    FLT2_0 = DB[4]
    # ALRM_1 = DB[5]
    ALRM_0 = DB[6]
    if (FLT1_1 & 0x10) == 0:
        status_dictionary["General hardware fault"] = None
    else:
        status_dictionary["General hardware fault"] = "FAULT"
    if (FLT1_1 & 0x08) == 0:
        status_dictionary["PWM fault"] = None
    else:
        status_dictionary["PWM fault"] = "FAULT"
    if (FLT1_1 & 0x04) == 0:
        status_dictionary["Analog input fault"] = None
    else:
        status_dictionary["Analog input fault"] = "FAULT"
    if (FLT1_1 & 0x02) == 0:
        status_dictionary["Digital output fault"] = None
    else:
        status_dictionary["Digital output fault"] = "FAULT"
    if (FLT1_1 & 0x01) == 0:
        status_dictionary["Overcurrent or asymmetry fault"] = None
    else:
        status_dictionary["Overcurrent or asymmetry fault"] = "FAULT"
    if (FLT1_0 & 0x80) == 0:
        status_dictionary["Side A (Battery) Undervoltage fault"] = None
    else:
        status_dictionary["Side A (Battery) Undervoltage fault"] = "FAULT"
    if (FLT1_0 & 0x40) == 0:
        status_dictionary["Side A (Battery) Overvoltage fault"] = None
    else:
        status_dictionary["Side A (Battery) Overvoltage fault"] = "FAULT"
    if (FLT1_0 & 0x20) == 0:
        status_dictionary["Side B (DC-Link) Undervoltage fault"] = None
    else:
        status_dictionary["Side B (DC-Link) Undervoltage fault"] = "FAULT"
    if (FLT1_0 & 0x10) == 0:
        status_dictionary["Side B (DC-Link) Overvoltage fault"] = None
    else:
        status_dictionary["Side B (DC-Link) Overvoltage fault"] = "FAULT"
    if (FLT1_0 & 0x02) == 0:
        status_dictionary["Heat sink Over-temperature fault"] = None
    else:
        status_dictionary["Heat sink Over-temperature fault"] = "FAULT"
    if (FLT2_1 & 0x80) == 0:
        status_dictionary["DC-Link precharge timeout"] = None
    else:
        status_dictionary["DC-Link precharge timeout"] = "FAULT"
    if (FLT2_1 & 0x40) == 0:
        status_dictionary["Battery precharge timeout"] = None
    else:
        status_dictionary["Battery precharge timeout"] = "FAULT"
    if (FLT2_1 & 0x20) == 0:
        status_dictionary["DC-Link contactor opened during operation fault"] = None
    else:
        status_dictionary["DC-Link contactor opened during operation fault"] = "FAULT"
    if (FLT2_1 & 0x10) == 0:
        status_dictionary["DC-Link contactor closing timeout fault"] = None
    else:
        status_dictionary["DC-Link contactor closing timeout fault"] = "FAULT"
    if (FLT2_1 & 0x08) == 0:
        status_dictionary["DC-Link contactor not opening timeout fault"] = None
    else:
        status_dictionary["DC-Link contactor not opening timeout fault"] = "FAULT"
    if (FLT2_1 & 0x04) == 0:
        status_dictionary["Battery contactor opened during operation fault"] = None
    else:
        status_dictionary["Battery contactor opened during operation fault"] = "FAULT"
    if (FLT2_1 & 0x02) == 0:
        status_dictionary["Battery contactor closing timeout fault"] = None
    else:
        status_dictionary["Battery contactor closing timeout fault"] = "FAULT"
    if (FLT2_1 & 0x01) == 0:
        status_dictionary["Battery contactor not opening timeout fault"] = None
    else:
        status_dictionary["Battery contactor not opening timeout fault"] = "FAULT"
    if (FLT2_0 & 0x02) == 0:
        status_dictionary["Input/Output voltage difference"] = None
    else:
        status_dictionary["Input/Output voltage difference"] = "Voltage difference is less than 10V FAULT"
    if (FLT2_0 & 0x01) == 0:
        status_dictionary["E-stop"] = None
    else:
        status_dictionary["E-stop"] = "E-stop FAULT"
    if (ALRM_0 & 0x20) == 0:
        status_dictionary["No mode selected on start command"] = None
    else:
        status_dictionary["No mode selected on start command"] = "ALARM"
    if (ALRM_0 & 0x10) == 0:
        status_dictionary["Reference setpoint adjusted"] = None
    else:
        status_dictionary["Reference setpoint adjusted"] = "ALARM"
    if (ALRM_0 & 0x08) == 0:
        status_dictionary["CAN communication lost"] = None
    else:
        status_dictionary["CAN communication lost"] = "ALARM"
    if (ALRM_0 & 0x02) == 0:
        status_dictionary["Temperature derating active"] = None
    else:
        status_dictionary["Temperature derating active"] = "ALARM"


def IOs_status_update(DB):
    DORRB_1 = DB[1]
    DORRB_0 = DB[2]
    # DIRB_1 = DB[3]
    DIRB_0 = DB[4]
    if (DORRB_1 & 0x80) == 0:
        status_dictionary["User Relay #4"] = None
    else:
        status_dictionary["User Relay #4"] = "ON"
    if (DORRB_1 & 0x40) == 0:
        status_dictionary["User Relay #3"] = None
    else:
        status_dictionary["User Relay #3"] = "ON"
    if (DORRB_0 & 0x80) == 0:
        status_dictionary["User Digital Output #8"] = None
    else:
        status_dictionary["User Digital Output #8"] = "ON"
    if (DORRB_0 & 0x40) == 0:
        status_dictionary["User Digital Output #7"] = None
    else:
        status_dictionary["User Digital Output #7"] = "ON"
    if (DORRB_0 & 0x20) == 0:
        status_dictionary["User Digital Output #6"] = None
    else:
        status_dictionary["User Digital Output #6"] = "ON"
    if (DORRB_0 & 0x10) == 0:
        status_dictionary["User Digital Output #5"] = None
    else:
        status_dictionary["User Digital Output #5"] = "ON"
    if (DORRB_0 & 0x08) == 0:
        status_dictionary["User Digital Output #4"] = None
    else:
        status_dictionary["User Digital Output #4"] = "ON"
    if (DORRB_0 & 0x04) == 0:
        status_dictionary["User Digital Output #3"] = None
    else:
        status_dictionary["User Digital Output #3"] = "ON"
    if (DIRB_0 & 0x20) == 0:
        status_dictionary["Digital Input #6"] = None
    else:
        status_dictionary["Digital Input #6"] = "ON"
    if (DIRB_0 & 0x10) == 0:
        status_dictionary["Digital Input #5"] = None
    else:
        status_dictionary["Digital Input #5"] = "ON"
    if (DIRB_0 & 0x08) == 0:
        status_dictionary["Digital Input #4"] = None
    else:
        status_dictionary["Digital Input #4"] = "ON"
