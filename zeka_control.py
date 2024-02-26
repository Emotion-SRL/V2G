

def convert_to_UWORD(value, scale_factor=0.1):
    both_bytes = int(value / scale_factor)
    if both_bytes > 0xFFFF:
        print("In CONVERTING_TO_UWORD: Value too high, setting to 0xFFFF")
        both_bytes = 0xFFFF
    high_byte = (both_bytes >> 8) & 0xFF
    low_byte = both_bytes & 0xFF
    return high_byte, low_byte


def assemble_main_control_command(precharge_delay=False, reset_faults=False, full_stop=False, run_device=False, set_device_mode="No mode selected"):
    MCB_0 = 0x00
    if precharge_delay:
        MCB_0 |= 0x01  # 00000001
    if full_stop:
        MCB_0 |= 0x04  # 00000100
    if reset_faults:
        MCB_0 |= 0x80  # 10000000
    MCB_1 = 0x00
    if run_device:
        MCB_1 |= 0x01  # 00000001
    ACB_0 = 0x00
    ACB_1 = 0x00
    # ! Cosa significano i valori 0-1-2-3-4-5-6-8? E' un valore intero oppure il singolo bit da accendere?
    match set_device_mode:
        case "No mode selected":
            pass
        case "Buck 1Q voltage control mode":
            pass
        case "Buck 1Q current control mode":
            pass
        case "Boost 1Q voltage control mode":
            pass
        case "Boost 1Q current control mode":
            pass
        case "Buck 2Q voltage control mode":
            pass
        case "Boost 2Q voltage control mode":
            pass
        case "Boost A current B voltage control command":
            pass
        case _:
            pass
    return [0x80, MCB_1, MCB_0, ACB_1, ACB_0, 0xFF, 0xFF, 0xFF]


def assemble_buck_1q_voltage_control_reference_command(voltage_reference=0, current_limit=0):
    VBCK_1, VBCK_0 = convert_to_UWORD(value=voltage_reference, scale_factor=0.1)  # UWORD in 0.1V
    IBCK_1, IBCK_0 = convert_to_UWORD(value=current_limit, scale_factor=0.1)  # UWORD in 0.1A
    return [0x81, VBCK_1, VBCK_0, IBCK_1, IBCK_0, 0xFF, 0xFF, 0xFF]


def assemble_buck_1q_current_control_reference_command(current_reference=0):
    IBCK_1, IBCK_0 = convert_to_UWORD(value=current_reference, scale_factor=0.1)  # UWORD in 0.1V
    return [0x82, IBCK_1, IBCK_0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]


def assemble_boost_1q_voltage_control_reference_command(voltage_reference=0, current_limit=0):
    VBST_1, VBST_0 = convert_to_UWORD(value=voltage_reference, scale_factor=0.1)  # UWORD in 0.1V
    IBST_1, IBST_0 = convert_to_UWORD(value=current_limit, scale_factor=0.1)  # UWORD in 0.1A
    return [0x83, VBST_1, VBST_0, IBST_1, IBST_0, 0xFF, 0xFF, 0xFF]


def assemble_boost_1q_current_control_reference_command(current_reference=0):
    IBST_1, IBST_0 = convert_to_UWORD(value=current_reference, scale_factor=0.1)  # UWORD in 0.1V
    return [0x84, IBST_1, IBST_0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]


def assemble_buck_2q_voltage_control_reference_command(voltage_reference=0, current_limit_to_side_A=0, current_limit_to_side_B=0):
    VBK2Q_1, VBK2Q_0 = convert_to_UWORD(value=voltage_reference, scale_factor=0.1)  # UWORD in 0.1V
    IBK2QA_1, IBK2QA_0 = convert_to_UWORD(value=current_limit_to_side_A, scale_factor=0.1)  # UWORD in 0.1A, to side A (Battery)
    IBK2QB_1, IBK2QB_0 = convert_to_UWORD(value=current_limit_to_side_B, scale_factor=0.1)  # UWORD in 0.1A, to side B (DC-Link)
    return [0x85, VBK2Q_1, VBK2Q_0, IBK2QA_1, IBK2QA_0, IBK2QB_1, IBK2QB_0, 0xFF]


def assemble_boost_2q_voltage_control_reference_command(voltage_reference=0, current_limit_to_side_A=0, current_limit_to_side_B=0):
    VBS2Q_1, VBS2Q_0 = convert_to_UWORD(value=voltage_reference, scale_factor=0.1)  # UWORD in 0.1V
    IBS2QA_1, IBS2QA_0 = convert_to_UWORD(value=current_limit_to_side_A, scale_factor=0.1)  # UWORD in 0.1A, to side A (Battery)
    IBS2QB_1, IBS2QB_0 = convert_to_UWORD(value=current_limit_to_side_B, scale_factor=0.1)  # UWORD in 0.1A, to side B (DC-Link)
    return [0x86, VBS2Q_1, VBS2Q_0, IBS2QA_1, IBS2QA_0, IBS2QB_1, IBS2QB_0, 0xFF]


def assemble_boost_A_current_B_voltage_control_reference_command(voltage_reference=0, current_limit=0):
    VBST_1, VBST_0 = convert_to_UWORD(value=voltage_reference, scale_factor=0.1)  # UWORD in 0.1V
    IBST_1, IBST_0 = convert_to_UWORD(value=current_limit, scale_factor=0.1)  # UWORD in 0.1A
    return [0x8B, VBST_1, VBST_0, IBST_1, IBST_0, 0xFF, 0xFF, 0xFF]


def assemble_output_control_command(user_relay_4=False, user_relay_3=False, user_digital_output_8=False, user_digital_output_7=False, user_digital_output_6=False, user_digital_output_5=False, user_digital_output_4=False, user_digital_output_3=False):
    DORCB_0 = 0x00
    DORCB_1 = 0x00
    if user_relay_4:
        DORCB_1 |= 0x80  # 10000000
    if user_relay_3:
        DORCB_1 |= 0x40  # 01000000
    if user_digital_output_8:
        DORCB_0 |= 0x80  # 10000000
    if user_digital_output_7:
        DORCB_0 |= 0x40  # 01000000
    if user_digital_output_6:
        DORCB_0 |= 0x20  # 00100000
    if user_digital_output_5:
        DORCB_0 |= 0x10  # 00010000
    if user_digital_output_4:
        DORCB_0 |= 0x08  # 00001000
    if user_digital_output_3:
        DORCB_0 |= 0x04  # 00000100
    return [0x90, DORCB_1, DORCB_0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
