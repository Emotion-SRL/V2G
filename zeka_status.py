
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
    return (high_byte << 8) | low_byte * scale_factor


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
    BV1 = DB[1]
    BV0 = DB[2]
    BC1 = DB[3]
    BC0 = DB[4]
    HST1 = DB[5]
    HST0 = DB[6]
    message = "Side A (Battery) voltage: "
    voltage = read_SWORD(BV1, BV0, 0.1)
    if voltage < 0:
        message += violet_text(str(voltage) + " V")
    else:
        message += blue_text(str(voltage) + " V")
    print(message)
    message = "Side A (Battery) current: "
    current = read_SWORD(BC1, BC0, 0.1)
    if current < 0:
        message += violet_text(str(current) + " A")
    else:
        message += blue_text(str(current) + " A")
    message += " (Negative value -> towards Battery, Positive value -> towards DC-Link)"
    print(message)
    message = "Heat-sink temperature: "
    temperature = read_SWORD(HST1, HST0, 0.1)
    if temperature < 0:
        message += teal_text(str(temperature) + " °C")
    else:
        message += red_text(str(temperature) + " °C")
    print(message)


def human_readable_feedback_2_status_response(DB):
    print("FEEDBACK 2 STATUS RESPONSE:")
    DCV1 = DB[1]
    DCV0 = DB[2]
    DCI1 = DB[3]
    DCI0 = DB[4]
    HST1 = DB[5]
    HST0 = DB[6]
    message = "Side B (DC-Link) voltage: "
    voltage = read_SWORD(DCV1, DCV0, 0.1)
    if voltage < 0:
        message += violet_text(str(voltage) + " V")
    else:
        message += blue_text(str(voltage) + " V")
    print(message)
    message = "Side B (DC-Link) current: "
    current = read_SWORD(DCI1, DCI0, 0.1)
    if current < 0:
        message += violet_text(str(current) + " A")
    else:
        message += blue_text(str(current) + " A")
    message += " (Negative value -> towards Battery, Positive value -> towards DC-Link)"
    print(message)
    message = "Heat-sink temperature: "
    temperature = read_SWORD(HST1, HST0, 0.1)
    if temperature < 0:
        message += teal_text(str(temperature) + " °C")
    else:
        message += red_text(str(temperature) + " °C")
    print(message)
