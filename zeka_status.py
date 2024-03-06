
from settings import zeka_device_ID, zeka_master_node_id, zeka_status_packet_id
from status_dictionaries import zeka_status_dictionary
from utilities import orange_text, read_SWORD
from zeka_control import ZekaDeviceModes

zeka_status_message_id = (zeka_master_node_id << 8) | (zeka_device_ID << 3) | zeka_status_packet_id

main_status_request = [0xA0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
feedback_1_status_request = [0xA1, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
feedback_2_status_request = [0xA2, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
error_status_request = [0xA3, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
IOs_status_request = [0xA4, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]


def print_global_state():
    print("GLOBAL STATE:")
    for key, value in zeka_status_dictionary.items():
        if value is not None:
            if key in ["Side A (Battery) voltage", "Side B (DC-Link) voltage"]:
                output = str(value) + " V"
            elif key in ["Side A (Battery) current", "Side B (DC-Link) current"]:
                output = str(value) + " A"
            elif key in ["Heat-sink temperature (Side A)", "Heat-sink temperature (Side B)"]:
                output = str(value) + " °C"
            else:
                output = value
            print(key + ": " + orange_text(str(output)))


def main_status_update(DB):
    MSB_1 = DB[1]
    MSB_0 = DB[2]
    ASB_1 = DB[3]
    ASB_0 = DB[4]
    if (MSB_1 & 0x10) == 0:
        zeka_status_dictionary["Phaseback"] = None
    else:
        zeka_status_dictionary["Phaseback"] = "active"
    if (MSB_1 & 0x08) == 0:
        zeka_status_dictionary["Auto-boost"] = None
    else:
        zeka_status_dictionary["Auto-boost"] = "running"
    if (MSB_1 & 0x04) == 0:
        zeka_status_dictionary["Power limit/setpoint"] = None
    else:
        zeka_status_dictionary["Power limit/setpoint"] = "reached"
    if (MSB_1 & 0x02) == 0:
        zeka_status_dictionary["Current limit/setpoint"] = None
    else:
        zeka_status_dictionary["Current limit/setpoint"] = "reached"
    if (MSB_1 & 0x01) == 0:
        zeka_status_dictionary["Voltage limit/setpoint"] = None
    else:
        zeka_status_dictionary["Voltage limit/setpoint"] = "reached"
    if (MSB_0 & 0x80) == 0:
        zeka_status_dictionary["Device alarm/warning"] = None
    else:
        zeka_status_dictionary["Device alarm/warning"] = "alarm / warning"
    if (MSB_0 & 0x40) == 0:
        zeka_status_dictionary["Device full stop"] = None
    else:
        zeka_status_dictionary["Device full stop"] = "full stop active"
    if (MSB_0 & 0x08) == 0:
        zeka_status_dictionary["Device fault"] = None
    else:
        zeka_status_dictionary["Device fault"] = "fault"
    if (MSB_0 & 0x04) == 0:
        zeka_status_dictionary["Device running"] = None
    else:
        zeka_status_dictionary["Device running"] = "running"
    if (MSB_0 & 0x02) == 0:
        zeka_status_dictionary["Device ready"] = None
    else:
        zeka_status_dictionary["Device ready"] = "ready"
    if (MSB_0 & 0x01) == 0:
        zeka_status_dictionary["Device precharging"] = None
    else:
        zeka_status_dictionary["Device precharging"] = "precharging"
    if ASB_0 == 0:  # 0
        zeka_status_dictionary["Device mode"] = ZekaDeviceModes.NO_MODE_SELECTED.value
    elif ASB_0 == 1:  # (ASB_0 & 0x01) != 0:  # 1
        zeka_status_dictionary["Device mode"] = ZekaDeviceModes.BUCK_1Q_VOLTAGE_CONTROL_MODE.value
    elif ASB_0 == 2:  # (ASB_0 & 0x02) != 0:  # 2
        zeka_status_dictionary["Device mode"] = ZekaDeviceModes.BUCK_1Q_CURRENT_CONTROL_MODE.value
    elif ASB_0 == 3:  # (ASB_0 & 0x04) != 0:  # 3
        zeka_status_dictionary["Device mode"] = ZekaDeviceModes.BOOST_1Q_VOLTAGE_CONTROL_MODE.value
    elif ASB_0 == 4:  # (ASB_0 & 0x08) != 0:  # 4
        zeka_status_dictionary["Device mode"] = ZekaDeviceModes.BOOST_1Q_CURRENT_CONTROL_MODE.value
    elif ASB_0 == 5:  # (ASB_0 & 0x10) != 0:  # 5
        zeka_status_dictionary["Device mode"] = ZekaDeviceModes.BUCK_2Q_VOLTAGE_CONTROL_MODE.value
    elif ASB_0 == 6:  # (ASB_0 & 0x20) != 0:
        zeka_status_dictionary["Device mode"] = ZekaDeviceModes.BOOST_2Q_VOLTAGE_CONTROL_MODE.value
    elif ASB_0 == 8:  # (ASB_0 & 0x80) != 0:  # 8
        zeka_status_dictionary["Device mode"] = ZekaDeviceModes.BOOST_A_CURRENT_B_VOLTAGE_CONTROL_COMMAND.value


def feedback_1_status_update(DB):
    BV_1 = DB[1]
    BV_0 = DB[2]
    BC_1 = DB[3]
    BC_0 = DB[4]
    HST_1 = DB[5]
    HST_0 = DB[6]
    zeka_status_dictionary["Side A (Battery) voltage"] = read_SWORD(BV_1, BV_0, 0.1)
    zeka_status_dictionary["Side A (Battery) current"] = read_SWORD(BC_1, BC_0, 0.1)
    zeka_status_dictionary["Heat-sink temperature (Side A)"] = read_SWORD(HST_1, HST_0, 0.1)


def feedback_2_status_update(DB):
    DCV_1 = DB[1]
    DCV_0 = DB[2]
    DCI_1 = DB[3]
    DCI_0 = DB[4]
    HST_1 = DB[5]
    HST_0 = DB[6]
    zeka_status_dictionary["Side B (DC-Link) voltage"] = read_SWORD(DCV_1, DCV_0, 0.1)
    zeka_status_dictionary["Side B (DC-Link) current"] = read_SWORD(DCI_1, DCI_0, 0.1)
    zeka_status_dictionary["Heat-sink temperature (Side B)"] = read_SWORD(HST_1, HST_0, 0.1)


def error_status_update(DB):
    FLT1_1 = DB[1]
    FLT1_0 = DB[2]
    FLT2_1 = DB[3]
    FLT2_0 = DB[4]
    # ALRM_1 = DB[5]
    ALRM_0 = DB[6]
    if (FLT1_1 & 0x10) == 0:
        zeka_status_dictionary["General hardware fault"] = None
    else:
        zeka_status_dictionary["General hardware fault"] = "FAULT"
    if (FLT1_1 & 0x08) == 0:
        zeka_status_dictionary["PWM fault"] = None
    else:
        zeka_status_dictionary["PWM fault"] = "FAULT"
    if (FLT1_1 & 0x04) == 0:
        zeka_status_dictionary["Analog input fault"] = None
    else:
        zeka_status_dictionary["Analog input fault"] = "FAULT"
    if (FLT1_1 & 0x02) == 0:
        zeka_status_dictionary["Digital output fault"] = None
    else:
        zeka_status_dictionary["Digital output fault"] = "FAULT"
    if (FLT1_1 & 0x01) == 0:
        zeka_status_dictionary["Overcurrent or asymmetry fault"] = None
    else:
        zeka_status_dictionary["Overcurrent or asymmetry fault"] = "FAULT"
    if (FLT1_0 & 0x80) == 0:
        zeka_status_dictionary["Side A (Battery) Undervoltage fault"] = None
    else:
        zeka_status_dictionary["Side A (Battery) Undervoltage fault"] = "FAULT"
    if (FLT1_0 & 0x40) == 0:
        zeka_status_dictionary["Side A (Battery) Overvoltage fault"] = None
    else:
        zeka_status_dictionary["Side A (Battery) Overvoltage fault"] = "FAULT"
    if (FLT1_0 & 0x20) == 0:
        zeka_status_dictionary["Side B (DC-Link) Undervoltage fault"] = None
    else:
        zeka_status_dictionary["Side B (DC-Link) Undervoltage fault"] = "FAULT"
    if (FLT1_0 & 0x10) == 0:
        zeka_status_dictionary["Side B (DC-Link) Overvoltage fault"] = None
    else:
        zeka_status_dictionary["Side B (DC-Link) Overvoltage fault"] = "FAULT"
    if (FLT1_0 & 0x02) == 0:
        zeka_status_dictionary["Heat sink Over-temperature fault"] = None
    else:
        zeka_status_dictionary["Heat sink Over-temperature fault"] = "FAULT"
    if (FLT2_1 & 0x80) == 0:
        zeka_status_dictionary["DC-Link precharge timeout"] = None
    else:
        zeka_status_dictionary["DC-Link precharge timeout"] = "FAULT"
    if (FLT2_1 & 0x40) == 0:
        zeka_status_dictionary["Battery precharge timeout"] = None
    else:
        zeka_status_dictionary["Battery precharge timeout"] = "FAULT"
    if (FLT2_1 & 0x20) == 0:
        zeka_status_dictionary["DC-Link contactor opened during operation fault"] = None
    else:
        zeka_status_dictionary["DC-Link contactor opened during operation fault"] = "FAULT"
    if (FLT2_1 & 0x10) == 0:
        zeka_status_dictionary["DC-Link contactor closing timeout fault"] = None
    else:
        zeka_status_dictionary["DC-Link contactor closing timeout fault"] = "FAULT"
    if (FLT2_1 & 0x08) == 0:
        zeka_status_dictionary["DC-Link contactor not opening timeout fault"] = None
    else:
        zeka_status_dictionary["DC-Link contactor not opening timeout fault"] = "FAULT"
    if (FLT2_1 & 0x04) == 0:
        zeka_status_dictionary["Battery contactor opened during operation fault"] = None
    else:
        zeka_status_dictionary["Battery contactor opened during operation fault"] = "FAULT"
    if (FLT2_1 & 0x02) == 0:
        zeka_status_dictionary["Battery contactor closing timeout fault"] = None
    else:
        zeka_status_dictionary["Battery contactor closing timeout fault"] = "FAULT"
    if (FLT2_1 & 0x01) == 0:
        zeka_status_dictionary["Battery contactor not opening timeout fault"] = None
    else:
        zeka_status_dictionary["Battery contactor not opening timeout fault"] = "FAULT"
    if (FLT2_0 & 0x02) == 0:
        zeka_status_dictionary["Input/Output voltage difference"] = None
    else:
        zeka_status_dictionary["Input/Output voltage difference"] = "Voltage difference is less than 10V FAULT"
    if (FLT2_0 & 0x01) == 0:
        zeka_status_dictionary["E-stop"] = None
    else:
        zeka_status_dictionary["E-stop"] = "E-stop FAULT"
    if (ALRM_0 & 0x20) == 0:
        zeka_status_dictionary["No mode selected on start command"] = None
    else:
        zeka_status_dictionary["No mode selected on start command"] = "ALARM"
    if (ALRM_0 & 0x10) == 0:
        zeka_status_dictionary["Reference setpoint adjusted"] = None
    else:
        zeka_status_dictionary["Reference setpoint adjusted"] = "ALARM"
    if (ALRM_0 & 0x08) == 0:
        zeka_status_dictionary["CAN communication lost"] = None
    else:
        zeka_status_dictionary["CAN communication lost"] = "ALARM"
    if (ALRM_0 & 0x02) == 0:
        zeka_status_dictionary["Temperature derating active"] = None
    else:
        zeka_status_dictionary["Temperature derating active"] = "ALARM"


def IOs_status_update(DB):
    DORRB_1 = DB[1]
    DORRB_0 = DB[2]
    # DIRB_1 = DB[3]
    DIRB_0 = DB[4]
    if (DORRB_1 & 0x80) == 0:
        zeka_status_dictionary["User Relay #4"] = None
    else:
        zeka_status_dictionary["User Relay #4"] = "ON"
    if (DORRB_1 & 0x40) == 0:
        zeka_status_dictionary["User Relay #3"] = None
    else:
        zeka_status_dictionary["User Relay #3"] = "ON"
    if (DORRB_0 & 0x80) == 0:
        zeka_status_dictionary["User Digital Output #8"] = None
    else:
        zeka_status_dictionary["User Digital Output #8"] = "ON"
    if (DORRB_0 & 0x40) == 0:
        zeka_status_dictionary["User Digital Output #7"] = None
    else:
        zeka_status_dictionary["User Digital Output #7"] = "ON"
    if (DORRB_0 & 0x20) == 0:
        zeka_status_dictionary["User Digital Output #6"] = None
    else:
        zeka_status_dictionary["User Digital Output #6"] = "ON"
    if (DORRB_0 & 0x10) == 0:
        zeka_status_dictionary["User Digital Output #5"] = None
    else:
        zeka_status_dictionary["User Digital Output #5"] = "ON"
    if (DORRB_0 & 0x08) == 0:
        zeka_status_dictionary["User Digital Output #4"] = None
    else:
        zeka_status_dictionary["User Digital Output #4"] = "ON"
    if (DORRB_0 & 0x04) == 0:
        zeka_status_dictionary["User Digital Output #3"] = None
    else:
        zeka_status_dictionary["User Digital Output #3"] = "ON"
    if (DIRB_0 & 0x20) == 0:
        zeka_status_dictionary["Digital Input #6"] = None
    else:
        zeka_status_dictionary["Digital Input #6"] = "ON"
    if (DIRB_0 & 0x10) == 0:
        zeka_status_dictionary["Digital Input #5"] = None
    else:
        zeka_status_dictionary["Digital Input #5"] = "ON"
    if (DIRB_0 & 0x08) == 0:
        zeka_status_dictionary["Digital Input #4"] = None
    else:
        zeka_status_dictionary["Digital Input #4"] = "ON"
