
main_status_request = [0xA0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
feedback_1_status_request = [0xA1, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
feedback_2_status_request = [0xA2, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
error_status_request = [0xA3, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
IOs_status_request = [0xA4, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]


def green_text(text):
    return '\033[92m' + text + '\033[0m'


def red_text(text):
    return '\033[91m' + text + '\033[0m'


def teal_text(text):
    return '\033[96m' + text + '\033[0m'


def blue_text(text):
    return '\033[94m' + text + '\033[0m'


def violet_text(text):
    return '\033[95m' + text + '\033[0m'


def read_SWORD(high_byte, low_byte, scale_factor):
    return round(((high_byte << 8) | low_byte) * scale_factor, 1)


def human_readable_main_status_response(DB):
    print("MAIN STATUS RESPONSE:")
    MSB_1 = DB[1]
    MSB_0 = DB[2]
    ASB_1 = DB[3]
    ASB_0 = DB[4]
    if (MSB_1 & 0x10) == 0:
        print("Phaseback: " + red_text("not active"))
    else:
        print("Phaseback: " + green_text("active"))
    if (MSB_1 & 0x08) == 0:
        print("Auto-boost: " + red_text("not running"))
    else:
        print("Auto-boost: " + green_text("running"))
    if (MSB_1 & 0x04) == 0:
        print("Power limit/setpoint: not reached")
    else:
        print("Power limit/setpoint: " + teal_text("reached") + " (within range of +/- 1W)")
    if (MSB_1 & 0x02) == 0:
        print("Current limit/setpoint: not reached")
    else:
        print("Current limit/setpoint: " + teal_text("reached") + " (within range of +/- 1A)")
    if (MSB_1 & 0x01) == 0:
        print("Voltage limit/setpoint: not reached")
    else:
        print("Voltage limit/setpoint: " + teal_text("reached") + " (within range of +/- 1V)")
    if (MSB_0 & 0x80) == 0:
        print("Device alarm/warning: " + green_text("no alarm / warning"))
    else:
        print("Device alarm/warning: " + red_text("alarm / warning"))
    if (MSB_0 & 0x40) == 0:
        print("Device full stop: " + green_text("full stop not active"))
    else:
        print("Device full stop: " + red_text("full stop active"))
    if (MSB_0 & 0x08) == 0:
        print("Device fault: " + green_text("no fault"))
    else:
        print("Device fault: " + red_text("fault"))
    if (MSB_0 & 0x04) == 0:
        print("Device running: " + red_text("not running"))
    else:
        print("Device running: " + green_text("running"))
    if (MSB_0 & 0x02) == 0:
        print("Device ready: " + red_text("not ready"))
    else:
        print("Device ready: " + green_text("ready"))
    if (MSB_0 & 0x01) == 0:
        print("Device precharging: " + green_text("complete / not started"))
    else:
        print("Device precharging: " + red_text("precharging"))
    # ! ASB ha lo stesso problema di interpretazione dell'auxiliary word


def human_readable_feedback_1_status_response(DB):
    print("FEEDBACK 1 STATUS RESPONSE:")
    BV_1 = DB[1]
    BV_0 = DB[2]
    BC_1 = DB[3]
    BC_0 = DB[4]
    HST_1 = DB[5]
    HST_0 = DB[6]
    message = "Side A (Battery) voltage: "
    voltage = read_SWORD(BV_1, BV_0, 0.1)
    if voltage < 0:
        message += violet_text(str(voltage) + " V")
    else:
        message += blue_text(str(voltage) + " V")
    print(message)
    message = "Side A (Battery) current: "
    current = read_SWORD(BC_1, BC_0, 0.1)
    if current < 0:
        message += violet_text(str(current) + " A")
    else:
        message += blue_text(str(current) + " A")
    message += " (Negative value -> towards Battery, Positive value -> towards DC-Link)"
    print(message)
    message = "Heat-sink temperature: "
    temperature = read_SWORD(HST_1, HST_0, 0.1)
    if temperature < 0:
        message += teal_text(str(temperature) + " °C")
    else:
        message += red_text(str(temperature) + " °C")
    print(message)


def human_readable_feedback_2_status_response(DB):
    print("FEEDBACK 2 STATUS RESPONSE:")
    DCV_1 = DB[1]
    DCV_0 = DB[2]
    DCI_1 = DB[3]
    DCI_0 = DB[4]
    HST_1 = DB[5]
    HST_0 = DB[6]
    message = "Side B (DC-Link) voltage: "
    voltage = read_SWORD(DCV_1, DCV_0, 0.1)
    if voltage < 0:
        message += violet_text(str(voltage) + " V")
    else:
        message += blue_text(str(voltage) + " V")
    print(message)
    message = "Side B (DC-Link) current: "
    current = read_SWORD(DCI_1, DCI_0, 0.1)
    if current < 0:
        message += violet_text(str(current) + " A")
    else:
        message += blue_text(str(current) + " A")
    message += " (Negative value -> towards Battery, Positive value -> towards DC-Link)"
    print(message)
    message = "Heat-sink temperature: "
    temperature = read_SWORD(HST_1, HST_0, 0.1)
    if temperature < 0:
        message += teal_text(str(temperature) + " °C")
    else:
        message += red_text(str(temperature) + " °C")
    print(message)


def human_readable_error_status_response(DB):
    FLT1_1 = DB[1]
    FLT1_0 = DB[2]
    FLT2_1 = DB[3]
    FLT2_0 = DB[4]
    # ALRM_1 = DB[5]
    ALRM_0 = DB[6]
    print("ERROR STATUS RESPONSE:")
    if (FLT1_1 & 0x10) == 0:
        print("General hardware fault: " + green_text("OK"))
    else:
        print("General hardware fault: " + red_text("FAULT"))
    if (FLT1_1 & 0x08) == 0:
        print("PWM fault: " + green_text("OK"))
    else:
        print("PWM fault: " + red_text("FAULT"))
    if (FLT1_1 & 0x04) == 0:
        print("Analog input fault: " + green_text("OK"))
    else:
        print("Analog input fault: " + red_text("FAULT"))
    if (FLT1_1 & 0x02) == 0:
        print("Digital output fault: " + green_text("OK"))
    else:
        print("Digital output fault: " + red_text("FAULT"))
    if (FLT1_1 & 0x01) == 0:
        print("Overcurrent or asymmetry fault: " + green_text("OK"))
    else:
        print("Overcurrent or asymmetry fault: " + red_text("FAULT"))
    if (FLT1_0 & 0x80) == 0:
        print("Side A (Battery) Undervoltage fault: " + green_text("OK"))
    else:
        print("Side A (Battery) Undervoltage fault: " + red_text("FAULT"))
    if (FLT1_0 & 0x40) == 0:
        print("Side A (Battery) Overvoltage fault: " + green_text("OK"))
    else:
        print("Side A (Battery) Overvoltage fault: " + red_text("FAULT"))
    if (FLT1_0 & 0x20) == 0:
        print("Side B (DC-Link) Undervoltage fault: " + green_text("OK"))
    else:
        print("Side B (DC-Link) Undervoltage fault: " + red_text("FAULT"))
    if (FLT1_0 & 0x10) == 0:
        print("Side B (DC-Link) Overvoltage fault: " + green_text("OK"))
    else:
        print("Side B (DC-Link) Overvoltage fault: " + red_text("FAULT"))
    if (FLT1_0 & 0x02) == 0:
        print("Heat sink Over-temperature fault: " + green_text("OK"))
    else:
        print("Heat sink Over-temperature fault: " + red_text("FAULT"))
    if (FLT2_1 & 0x80) == 0:
        print("DC-Link precharge timeout: " + green_text("OK"))
    else:
        print("DC-Link precharge timeout: " + red_text("FAULT"))
    if (FLT2_1 & 0x40) == 0:
        print("Battery precharge timeout: " + green_text("OK"))
    else:
        print("Battery precharge timeout: " + red_text("FAULT"))
    if (FLT2_1 & 0x20) == 0:
        print("DC-Link contactor opened during operation fault: " + green_text("OK"))
    else:
        print("DC-Link contactor opened during operation fault: " + red_text("FAULT"))
    if (FLT2_1 & 0x10) == 0:
        print("DC-Link contactor closing timeout fault: " + green_text("OK"))
    else:
        print("DC-Link contactor closing timeout fault: " + red_text("FAULT"))
    if (FLT2_1 & 0x08) == 0:
        print("DC-Link contactor not opening timeout fault: " + green_text("OK"))
    else:
        print("DC-Link contactor not opening timeout fault: " + red_text("FAULT"))
    if (FLT2_1 & 0x04) == 0:
        print("Battery contactor opened during operation fault: " + green_text("OK"))
    else:
        print("Battery contactor opened during operation fault: " + red_text("FAULT"))
    if (FLT2_1 & 0x02) == 0:
        print("Battery contactor closing timeout fault: " + green_text("OK"))
    else:
        print("Battery contactor closing timeout fault: " + red_text("FAULT"))
    if (FLT2_1 & 0x01) == 0:
        print("Battery contactor not opening timeout fault: " + green_text("OK"))
    else:
        print("Battery contactor not opening timeout fault: " + red_text("FAULT"))
    if (FLT2_0 & 0x02) == 0:
        print("Input/Output voltage difference: " + green_text("OK"))
    else:
        print("Input/Output voltage difference: " + red_text("Voltage difference is less than 10V FAULT"))
    if (FLT2_0 & 0x01) == 0:
        print("E-stop: " + green_text("OK"))
    else:
        print("E-stop: " + red_text("E-stop FAULT"))
    if (ALRM_0 & 0x20) == 0:
        print("No mode selected on start command: " + green_text("OK"))
    else:
        print("No mode selected on start command: " + red_text("ALARM"))
    if (ALRM_0 & 0x10) == 0:
        print("Reference setpoint adjusted: " + green_text("OK"))
    else:
        print("Reference setpoint adjusted: " + red_text("ALARM"))
    if (ALRM_0 & 0x08) == 0:
        print("CAN communication lost: " + green_text("OK"))
    else:
        print("CAN communication lost: " + red_text("ALARM"))
    if (ALRM_0 & 0x02) == 0:
        print("Temperature derating active: " + green_text("OK"))
    else:
        print("Temperature derating active: " + red_text("ALARM"))


def human_readable_IO_response(DB):
    DORRB_1 = DB[1]
    DORRB_0 = DB[2]
    # DIRB_1 = DB[3]
    DIRB_0 = DB[4]
    print("IOs STATUS RESPONSE:")
    if (DORRB_1 & 0x80) == 0:
        print("User Relay #4: " + red_text("OFF"))
    else:
        print("User Relay #4: " + red_text("ON"))
    if (DORRB_1 & 0x40) == 0:
        print("User Relay #3: " + red_text("OFF"))
    else:
        print("User Relay #3: " + red_text("ON"))
    if (DORRB_0 & 0x80) == 0:
        print("User Digital Output #8: " + red_text("OFF"))
    else:
        print("User Digital Output #8: " + red_text("ON"))
    if (DORRB_0 & 0x40) == 0:
        print("User Digital Output #7: " + red_text("OFF"))
    else:
        print("User Digital Output #7: " + red_text("ON"))
    if (DORRB_0 & 0x20) == 0:
        print("User Digital Output #6: " + red_text("OFF"))
    else:
        print("User Digital Output #6: " + red_text("ON"))
    if (DORRB_0 & 0x10) == 0:
        print("User Digital Output #5: " + red_text("OFF"))
    else:
        print("User Digital Output #5: " + red_text("ON"))
    if (DORRB_0 & 0x08) == 0:
        print("User Digital Output #4: " + red_text("OFF"))
    else:
        print("User Digital Output #4: " + red_text("ON"))
    if (DORRB_0 & 0x04) == 0:
        print("User Digital Output #3: " + red_text("OFF"))
    else:
        print("User Digital Output #3: " + red_text("ON"))
    if (DIRB_0 & 0x20) == 0:
        print("Digital Input #6: " + red_text("OFF"))
    else:
        print("Digital Input #6: " + red_text("ON"))
    if (DIRB_0 & 0x10) == 0:
        print("Digital Input #5: " + red_text("OFF"))
    else:
        print("Digital Input #5: " + red_text("ON"))
    if (DIRB_0 & 0x08) == 0:
        print("Digital Input #4: " + red_text("OFF"))
    else:
        print("Digital Input #4: " + red_text("ON"))
