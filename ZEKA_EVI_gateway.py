
import threading
import time

import can

import zeka_control
import zeka_status
from evi_semantics import (
    EVIStates,
    assemble_x180,
    assemble_x360,
    assemble_x460,
    assembled_x280_message,
    evi_grid_conf_translator,
    evi_state_word_translator,
)
from settings import can_fini, can_init, evi_BMPU_ID, evi_bus, zeka_bus
from status_dictionaries import (
    evi_directives_dictionary,
    zeka_status_dictionary,
    zeka_status_dictionary_lock,
)
from utilities import orange_text, read_UWORD, red_text, teal_text

chosen_zeka_device_mode = zeka_control.ZekaDeviceModes.BUCK_2Q_VOLTAGE_CONTROL_MODE

reference_control_function = {
    zeka_control.ZekaDeviceModes.BUCK_2Q_VOLTAGE_CONTROL_MODE : zeka_control.assemble_buck_2q_voltage_control_reference_command,
    zeka_control.ZekaDeviceModes.BOOST_2Q_VOLTAGE_CONTROL_MODE : zeka_control.assemble_boost_2q_voltage_control_reference_command,
}

zeka_lock = threading.Lock()


def zeka_request_response_cycle(request):
    with zeka_lock:
        zeka_bus.send(request)
        response = zeka_bus.recv(1)
        if response is None:
            print(red_text("**** ATTENTION: FAILED TO READ FROM ZEKA! ****"))
            return None
        if request.data[0] in [0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x8B, 0x90]:
            if response.data != request.data:
                print(red_text("**** ATTENTION: ZEKA DID NOT CORRECTLY RECEIVE COMMAND OF TYPE " + hex(request.data[0]) + " ****"))
        return response.data


def ZEKA_heartbeat(stop_psu_heartbeat, verbose=False):
    print(orange_text("ZEKA_heartbeat thread started"))
    while not stop_psu_heartbeat.is_set():
        with zeka_status_dictionary_lock:
            message = can.Message(arbitration_id=zeka_status.zeka_status_message_id, data=zeka_status.main_status_request, is_extended_id=False)
            response = zeka_request_response_cycle(message)
            if response is not None:
                zeka_status.main_status_update(response)
            message = can.Message(arbitration_id=zeka_status.zeka_status_message_id, data=zeka_status.feedback_1_status_request, is_extended_id=False)
            response = zeka_request_response_cycle(message)
            if response is not None:
                zeka_status.feedback_1_status_update(response)
            message = can.Message(arbitration_id=zeka_status.zeka_status_message_id, data=zeka_status.feedback_2_status_request, is_extended_id=False)
            response = zeka_request_response_cycle(message)
            if response is not None:
                zeka_status.feedback_2_status_update(response)
            message = can.Message(arbitration_id=zeka_status.zeka_status_message_id, data=zeka_status.error_status_request, is_extended_id=False)
            response = zeka_request_response_cycle(message)
            if response is not None:
                zeka_status.error_status_update(response)
            message = can.Message(arbitration_id=zeka_status.zeka_status_message_id, data=zeka_status.IOs_status_request, is_extended_id=False)
            response = zeka_request_response_cycle(message)
            if response is not None:
                zeka_status.IOs_status_update(response)
            if verbose:
                zeka_status.print_global_state()
        time.sleep(1)
    print(orange_text("ZEKA_heartbeat thread stopped"))


def EVI_heartbeat(stop_evi_heartbeat, evi_bus):
    print(teal_text("EVI_heartbeat thread started"))
    while not stop_evi_heartbeat.is_set():
        message = can.Message(arbitration_id=0x700+evi_BMPU_ID, data=[5, 0, 0, 0, 0, 0, 0, 0], is_extended_id=False)
        evi_bus.send(message)
        time.sleep(0.9)
    print("EVI_heartbeat thread stopped")


def EVI_CAN_server(stop_evi_server, evi_bus, evi_heartbeat_thread):
    print(teal_text("EVI_CAN_server thread started"))
    while not stop_evi_server.is_set():
        message = evi_bus.recv()
        if message is not None:
            # ? PDO 1
            if message.arbitration_id == 0x200 + evi_BMPU_ID:
                DB = message.data
                pfc_state_request = DB[0]
                if pfc_state_request != evi_directives_dictionary["pfc_state_request"]:
                    print("EVI updated STATE_REQUEST to: " + teal_text(evi_state_word_translator(pfc_state_request)))
                    evi_directives_dictionary["pfc_state_request"] = pfc_state_request
                    evi_directives_dictionary["UPDATE_COMMAND"] = True
                pfc_mode_request = DB[1]
                if pfc_mode_request != evi_directives_dictionary["pfc_mode_request"]:
                    print("EVI updated MODE_REQUEST to: " + teal_text(pfc_mode_request))
                    evi_directives_dictionary["pfc_mode_request"] = pfc_mode_request
                grid_conf_request = DB[2]
                if grid_conf_request != evi_directives_dictionary["grid_conf_request"]:
                    print("EVI updated GRID_CONF_REQUEST to: " + teal_text(evi_grid_conf_translator[grid_conf_request]))
                    evi_directives_dictionary["grid_conf_request"] = grid_conf_request
                battery_voltage_setpoint = read_UWORD(high_byte=DB[3], low_byte=DB[4], scale_factor=0.1)
                if battery_voltage_setpoint != evi_directives_dictionary["battery_voltage_setpoint"]:
                    print("EVI updated BATTERY_VOLTAGE_SETPOINT to: " + teal_text(battery_voltage_setpoint))
                    evi_directives_dictionary["battery_voltage_setpoint"] = battery_voltage_setpoint
                    evi_directives_dictionary["UPDATE_REFERENCE"] = True
            # ? PDO 2
            elif message.arbitration_id == 0x300 + evi_BMPU_ID:
                DB = message.data
                i_charge_limit = read_UWORD(high_byte=DB[0], low_byte=DB[1], scale_factor=0.1)
                if i_charge_limit != evi_directives_dictionary["i_charge_limit"]:
                    print("EVI updated I_CHARGE_LIMIT to: " + teal_text(i_charge_limit))
                    evi_directives_dictionary["i_charge_limit"] = i_charge_limit
                    evi_directives_dictionary["UPDATE_REFERENCE"] = True
                i_discharge_limit = read_UWORD(high_byte=DB[2], low_byte=DB[3], scale_factor=0.1)
                if i_discharge_limit != evi_directives_dictionary["i_discharge_limit"]:
                    print("EVI updated I_DISCHARGE_LIMIT to: " + teal_text(i_discharge_limit))
                    evi_directives_dictionary["i_discharge_limit"] = i_discharge_limit
                    evi_directives_dictionary["UPDATE_REFERENCE"] = True
            elif message.arbitration_id == 0x600 + evi_BMPU_ID:
                # EVI is requesting PU heartbeat start
                message = can.Message(arbitration_id=0x580+evi_BMPU_ID, data=[60, 16, 10, 1, 0, 0, 0, 0], is_extended_id=False)
                evi_bus.send(message)
                if not evi_heartbeat_thread.is_alive():
                    evi_heartbeat_thread.start()
            # ? SYNC
            elif message.arbitration_id == 0x80:
                with zeka_status_dictionary_lock:
                    side_A_voltage = zeka_status_dictionary["Side A (Battery) voltage"]
                    side_B_voltage = zeka_status_dictionary["Side B (DC-Link) voltage"]
                    side_A_current = zeka_status_dictionary["Side A (Battery) current"]
                    side_B_current = zeka_status_dictionary["Side B (DC-Link) current"]
                    side_A_power = side_A_voltage * side_A_current
                    side_B_power = side_B_voltage * side_B_current
                    fault_detected = zeka_status_dictionary["Device fault"]
                    running_detected = zeka_status_dictionary["Device running"]
                    ready_detected = zeka_status_dictionary["Device ready"]
                    precharging_detected = zeka_status_dictionary["Device precharging"]
                    '''Previously faulted is used when in state "precharging" to decide if
                    we need to signal STAND_BY or FAULT_ACK to the EVI'''
                    previously_faulted = zeka_status_dictionary["PREVIOUSLY_FAULTED"]
                    '''If the EVI is asking a transition to STAND_BY after a fault has
                    been reset, we set previously_faulted to False'''
                    if previously_faulted and fault_detected is None and evi_directives_dictionary["pfc_state_request"] == 1:
                        zeka_status_dictionary["PREVIOUSLY_FAULTED"] = False
                    # If a fault is detected, previously_faulted is also set
                    if fault_detected is not None:
                        zeka_status_dictionary["PREVIOUSLY_FAULTED"] = True
                # ! PDO 5 (x280)
                message = can.Message(arbitration_id=0x280+evi_BMPU_ID, data=assembled_x280_message, is_extended_id=False)
                evi_bus.send(message)
                # ! PDO 10 (x380)
                data_bytes = assemble_x360(grid_voltage=side_B_voltage, grid_current=side_B_current, grid_power=side_B_power)
                message = can.Message(arbitration_id=0x360+evi_BMPU_ID, data=data_bytes, is_extended_id=False)
                evi_bus.send(message)
                # ! PDO 11 (x480)
                data_bytes = assemble_x460(battery_voltage=side_A_voltage, battery_current=side_A_current, battery_power=side_A_power)
                message = can.Message(arbitration_id=0x460+evi_BMPU_ID, data=data_bytes, is_extended_id=False)
                evi_bus.send(message)
                # ! PDO 4 (x180)
                data_bytes = assemble_x180(
                    fault_detected=fault_detected,
                    running_detected=running_detected,
                    ready_detected=ready_detected,
                    precharging_detected=precharging_detected,
                    previously_faulted=previously_faulted
                )
                message = can.Message(arbitration_id=0x180+evi_BMPU_ID, data=data_bytes, is_extended_id=False)
                evi_bus.send(message)
            if evi_directives_dictionary["UPDATE_REFERENCE"]:
                if evi_directives_dictionary["battery_voltage_setpoint"] is not None and evi_directives_dictionary["i_charge_limit"] is not None and evi_directives_dictionary["i_discharge_limit"] is not None:
                    data_bytes = (reference_control_function[chosen_zeka_device_mode])(
                        voltage_reference=evi_directives_dictionary["battery_voltage_setpoint"],
                        current_limit_to_side_A=evi_directives_dictionary["i_charge_limit"],
                        current_limit_to_side_B=evi_directives_dictionary["i_discharge_limit"]
                    )
                    psu_message = can.Message(arbitration_id=zeka_control.zeka_control_message_id, data=data_bytes, is_extended_id=False)
                    zeka_request_response_cycle(psu_message)
                    evi_directives_dictionary["UPDATE_REFERENCE"] = False
            if evi_directives_dictionary["UPDATE_COMMAND"]:
                precharge_delay = False
                reset_faults = False
                run_device = False
                set_device_mode = chosen_zeka_device_mode
                if evi_directives_dictionary["pfc_state_request"] == EVIStates.STATE_STANDBY:
                    precharge_delay = True
                    run_device = False
                elif evi_directives_dictionary["pfc_state_request"] == EVIStates.STATE_POWER_ON:
                    run_device = True
                    set_device_mode = "No mode selected"
                elif evi_directives_dictionary["pfc_state_request"] == EVIStates.STATE_CHARGE:
                    run_device = True
                    set_device_mode = chosen_zeka_device_mode
                elif evi_directives_dictionary["pfc_state_request"] == EVIStates.STATE_FAULT_ACK:
                    reset_faults = True
                    run_device = False
                    precharge_delay = True
                    set_device_mode = chosen_zeka_device_mode
                data_bytes = zeka_control.assemble_main_control_command(
                    precharge_delay=precharge_delay,
                    reset_faults=reset_faults,
                    full_stop=False,
                    run_device=run_device,
                    set_device_mode=set_device_mode
                )
                psu_message = can.Message(arbitration_id=zeka_control.zeka_control_message_id, data=data_bytes, is_extended_id=False)
                zeka_request_response_cycle(psu_message)
                evi_directives_dictionary["UPDATE_COMMAND"] = False
    print(teal_text("EVI_CAN_server thread stopped"))


can_init()
try:
    data_bytes = zeka_control.assemble_main_control_command(
        precharge_delay=True,
        reset_faults=True,
        full_stop=False,
        run_device=False,
        set_device_mode=chosen_zeka_device_mode
    )
    message = can.Message(arbitration_id=zeka_control.zeka_control_message_id, data=data_bytes, is_extended_id=False)
    response = zeka_request_response_cycle(message)
    if response is None:
        print(red_text("BLG initialization failed!"))
        exit(1)
    stop_zeka_heartbeat = threading.Event()
    stop_evi_server = threading.Event()
    stop_evi_heartbeat = threading.Event()
    zeka_heartbeat_thread = threading.Thread(target=ZEKA_heartbeat, kwargs={'stop_psu_heartbeat': stop_zeka_heartbeat, 'verbose': True})
    evi_heartbeat_thread = threading.Thread(target=EVI_heartbeat, kwargs={'stop_evi_heartbeat': stop_evi_heartbeat, 'evi_bus': evi_bus})
    evi_server_thread = threading.Thread(target=EVI_CAN_server, kwargs={'stop_evi_server': stop_evi_server, 'evi_bus': evi_bus, 'evi_heartbeat_thread': evi_heartbeat_thread})
    zeka_heartbeat_thread.start()
    evi_server_thread.start()
    keyboard_interrupt = threading.Event()
    keyboard_interrupt.wait()
except KeyboardInterrupt:
    # # Chiudi la connessione CAN
    stop_zeka_heartbeat.set()
    stop_evi_server.set()
    stop_evi_heartbeat.set()
    evi_heartbeat_thread.join()
    zeka_heartbeat_thread.join()
    evi_server_thread.join()
    zeka_bus.shutdown()
    evi_bus.shutdown()
    can_fini()