
import threading
import time
from datetime import datetime, timedelta

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
    evi_system_mode_translator,
)
from settings import (
    can_fini,
    can_init,
    evi_baud_rate,
    evi_BMPU_ID,
    evi_can_channel,
    evi_can_interface,
    zeka_baud_rate,
    zeka_can_channel,
    zeka_can_interface,
)
from status_dictionaries import (
    evi_directives_dictionary,
    zeka_status_dictionary,
    zeka_status_dictionary_lock,
)
from utilities import orange_text, purple_text, read_UWORD, red_text, teal_text

chosen_zeka_device_mode = zeka_control.ZekaDeviceModes.BUCK_2Q_VOLTAGE_CONTROL_MODE

reference_control_function = {
    zeka_control.ZekaDeviceModes.BUCK_2Q_VOLTAGE_CONTROL_MODE : zeka_control.assemble_buck_2q_voltage_control_reference_command,
    zeka_control.ZekaDeviceModes.BOOST_2Q_VOLTAGE_CONTROL_MODE : zeka_control.assemble_boost_2q_voltage_control_reference_command,
}

zeka_lock = threading.Lock()


# spotted_evi_frames = set()


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
    print(purple_text("EVI_heartbeat thread started"))
    while not stop_evi_heartbeat.is_set():
        message = can.Message(arbitration_id=0x700+evi_BMPU_ID, data=[5], is_extended_id=False)
        evi_bus.send(message)
        # print("sent BMPU HB with arbitration id: " + teal_text(hex(0x700+evi_BMPU_ID)))
        time.sleep(0.9)
    print(purple_text("EVI_heartbeat thread stopped"))


def EVI_CAN_server(stop_evi_server, evi_bus):
    print(teal_text("EVI_CAN_server thread started"))
    while not stop_evi_server.is_set():
        message = evi_bus.recv()
        if message is not None:
            # if message.arbitration_id not in spotted_evi_frames:
            #     print(red_text(hex(message.arbitration_id)) + " spotted for the first time!")
            #     spotted_evi_frames.add(message.arbitration_id)
            # ? PDO 1
            if message.arbitration_id == 0x200 + evi_BMPU_ID:
                DB = message.data
                pfc_state_request = DB[0]
                if pfc_state_request != evi_directives_dictionary["pfc_state_request"]:
                    print("EVI updated STATE_REQUEST to: " + teal_text(evi_state_word_translator[pfc_state_request]))
                    evi_directives_dictionary["UPDATE_COMMAND"] = True
                    evi_directives_dictionary["COMMAND_TIMESTAMP"] = datetime.now()
                    evi_directives_dictionary["pfc_state_request"] = pfc_state_request
                    if pfc_state_request != EVIStates.STATE_POWER_ON.value:
                        evi_directives_dictionary["INSULATION_TEST"] = False
                    # if pfc_state_request in [EVIStates.STATE_POWER_ON.value, EVIStates.STATE_CHARGE.value]:
                    #     evi_directives_dictionary["CURRENT_SETPOINT_SENT"] = False
                pfc_mode_request = DB[1]
                if pfc_mode_request != evi_directives_dictionary["pfc_mode_request"]:
                    print("EVI updated MODE_REQUEST to: " + teal_text(evi_system_mode_translator[pfc_mode_request]))
                    evi_directives_dictionary["pfc_mode_request"] = pfc_mode_request
                grid_conf_request = DB[2]
                if grid_conf_request != evi_directives_dictionary["grid_conf_request"]:
                    print("EVI updated GRID_CONF_REQUEST to: " + teal_text(evi_grid_conf_translator[grid_conf_request]))
                    evi_directives_dictionary["grid_conf_request"] = grid_conf_request
                battery_voltage_setpoint = read_UWORD(high_byte=DB[7], low_byte=DB[6], scale_factor=0.1)
                if battery_voltage_setpoint != evi_directives_dictionary["battery_voltage_setpoint"]:
                    print("EVI updated BATTERY_VOLTAGE_SETPOINT to: " + teal_text(battery_voltage_setpoint))
                    evi_directives_dictionary["battery_voltage_setpoint"] = battery_voltage_setpoint
                    evi_directives_dictionary["UPDATE_REFERENCE"] = True
            # ? PDO 2
            elif message.arbitration_id == 0x300 + evi_BMPU_ID:
                DB = message.data
                i_charge_limit = read_UWORD(high_byte=DB[1], low_byte=DB[0], scale_factor=0.1)
                # changed = False
                if i_charge_limit != evi_directives_dictionary["i_charge_limit"]:
                    print("EVI updated I_CHARGE_LIMIT to: " + teal_text(i_charge_limit))
                    evi_directives_dictionary["i_charge_limit"] = i_charge_limit
                    evi_directives_dictionary["UPDATE_REFERENCE"] = True
                    # changed = True
                i_discharge_limit = read_UWORD(high_byte=DB[3], low_byte=DB[2], scale_factor=0.1)
                if i_discharge_limit != evi_directives_dictionary["i_discharge_limit"]:
                    print("EVI updated I_DISCHARGE_LIMIT to: " + teal_text(i_discharge_limit))
                    evi_directives_dictionary["i_discharge_limit"] = i_discharge_limit
                    evi_directives_dictionary["UPDATE_REFERENCE"] = True
                #     changed = True
                # if changed:
                #     evi_directives_dictionary["UPDATE_REFERENCE"] = True
                #     if evi_directives_dictionary["UPDATE_COMMAND"] and evi_directives_dictionary["pfc_state_request"] in [EVIStates.STATE_POWER_ON.value, EVIStates.STATE_CHARGE.value]:
                #         evi_directives_dictionary["CURRENT_SETPOINT_SENT"] = True
            # ? HB start request
            elif message.arbitration_id == 0x600 + evi_BMPU_ID:
                # Se viene richiesto lo start dell'HB della PU, confermiamo lo start (in realtà era già partito)
                message = can.Message(arbitration_id=0x580+evi_BMPU_ID, data=[60, 16, 10, 1, 0, 0, 0, 0], is_extended_id=False)
                evi_bus.send(message)
            # ? SYNC
            elif message.arbitration_id == 0x80:
                with zeka_status_dictionary_lock:
                    side_A_voltage = zeka_status_dictionary["Side A (Battery) voltage"]
                    side_B_voltage = zeka_status_dictionary["Side B (DC-Link) voltage"]
                    side_A_current = zeka_status_dictionary["Side A (Battery) current"]
                    side_B_current = zeka_status_dictionary["Side B (DC-Link) current"]
                    side_A_power = round(side_A_voltage * side_A_current, 1)
                    side_B_power = round(side_B_voltage * side_B_current, 1)
                    fault_detected = zeka_status_dictionary["Device fault"]
                    running_detected = zeka_status_dictionary["Device running"]
                    ready_detected = zeka_status_dictionary["Device ready"]
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
                # ! PDO 4 (x180)
                data_bytes = assemble_x180(
                    fault_detected=fault_detected,
                    running_detected=running_detected,
                    previously_faulted=previously_faulted,
                    ready_detected=ready_detected
                )
                if data_bytes is None:
                    continue
                message = can.Message(arbitration_id=0x180+evi_BMPU_ID, data=data_bytes, is_extended_id=False)
                evi_bus.send(message)
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
            if (
                evi_directives_dictionary["UPDATE_REFERENCE"] and
                evi_directives_dictionary["battery_voltage_setpoint"] is not None and
                evi_directives_dictionary["i_charge_limit"] is not None and
                evi_directives_dictionary["i_discharge_limit"] is not None
            ):
                update_zeka_references(
                    voltage=evi_directives_dictionary["battery_voltage_setpoint"],
                    current_a=evi_directives_dictionary["i_charge_limit"],
                    current_b=evi_directives_dictionary["i_discharge_limit"]
                )
                evi_directives_dictionary["UPDATE_REFERENCE"] = False
                if (
                    evi_directives_dictionary["INSULATION_TEST"] and
                    evi_directives_dictionary["battery_voltage_setpoint"] != 0
                ):
                    print(teal_text("***** ENDING INSULATION TEST *****"))
                    evi_directives_dictionary["INSULATION_TEST"] = False
                    command_zeka(
                        argument="START",
                        precharge_delay=True,
                        reset_faults=False,
                        full_stop=False,
                        run_device=True,
                        set_device_mode=chosen_zeka_device_mode
                    )
                if (
                    evi_directives_dictionary["pfc_state_request"] == EVIStates.STATE_POWER_ON.value and
                    evi_directives_dictionary["battery_voltage_setpoint"] == 0
                ):
                    print(teal_text("***** STARTING INSULATION TEST *****"))
                    evi_directives_dictionary["INSULATION_TEST"] = True
                    command_zeka(
                        argument="INSULATION TEST",
                        precharge_delay=True,
                        reset_faults=False,
                        full_stop=False,
                        run_device=False,
                        set_device_mode=chosen_zeka_device_mode
                    )
            if evi_directives_dictionary["UPDATE_COMMAND"]:
                if evi_directives_dictionary["pfc_state_request"] == EVIStates.STATE_STANDBY.value:
                    command_zeka(
                        argument="STOP",
                        precharge_delay=True,
                        reset_faults=True,
                        full_stop=False,
                        run_device=False,
                        set_device_mode=chosen_zeka_device_mode
                    )
                elif evi_directives_dictionary["pfc_state_request"] == EVIStates.STATE_POWER_ON.value:
                    # TODO VARIANTE 1
                    # command_zeka(
                    #     argument="PRECHARGE",
                    #     precharge_delay=True,
                    #     reset_faults=False,
                    #     full_stop=False,
                    #     run_device=False,
                    #     set_device_mode=chosen_zeka_device_mode
                    # )
                    # TODO VARIANTE 2 (precharging simulato)
                    command_zeka(
                        argument="START",
                        precharge_delay=True,
                        reset_faults=False,
                        full_stop=False,
                        run_device=True,
                        set_device_mode=chosen_zeka_device_mode
                    )
                elif evi_directives_dictionary["pfc_state_request"] == EVIStates.STATE_CHARGE.value:
                    # TODO VARIANTE 1
                    # command_zeka(
                    #     argument="START",
                    #     precharge_delay=True,
                    #     reset_faults=False,
                    #     full_stop=False,
                    #     run_device=True,
                    #     set_device_mode=chosen_zeka_device_mode
                    # )
                    # TODO VARIANTE 2 (precharging simulato)
                    pass
                elif evi_directives_dictionary["pfc_state_request"] == EVIStates.STATE_FAULT_ACK.value:
                    command_zeka(
                        argument="RESET",
                        precharge_delay=True,
                        reset_faults=True,
                        full_stop=False,
                        run_device=False,
                        set_device_mode=chosen_zeka_device_mode
                    )
                evi_directives_dictionary["UPDATE_COMMAND"] = False
    print(teal_text("EVI_CAN_server thread stopped"))


def update_zeka_references(voltage, current_a, current_b):
    data_bytes = (reference_control_function[chosen_zeka_device_mode])(
        voltage_reference=voltage,
        current_limit_to_side_A=current_a,
        current_limit_to_side_B=current_b
    )
    psu_message = can.Message(arbitration_id=zeka_control.zeka_control_message_id, data=data_bytes, is_extended_id=False)
    zeka_request_response_cycle(psu_message)
    print("*****" + " SENT " + red_text("REFERENCE") + " COMMAND TO ZEKA! Voltage: " + red_text(voltage) + " Cur_A: " + red_text(current_a) + " Cur_B: " + red_text(current_b) + "*****")


def command_zeka(argument, precharge_delay, reset_faults, full_stop, run_device, set_device_mode):
    data_bytes = zeka_control.assemble_main_control_command(
        precharge_delay=precharge_delay,
        reset_faults=reset_faults,
        full_stop=full_stop,
        run_device=run_device,
        set_device_mode=set_device_mode
    )
    message = can.Message(arbitration_id=zeka_control.zeka_control_message_id, data=data_bytes, is_extended_id=False)
    print("*****" + " SENT " + red_text(argument) + " COMMAND TO ZEKA! " + "*****")
    response = zeka_request_response_cycle(message)
    return response


can_init()
zeka_bus = can.thread_safe_bus.ThreadSafeBus(channel=zeka_can_channel, bustype=zeka_can_interface, bitrate=zeka_baud_rate)
evi_bus = can.thread_safe_bus.ThreadSafeBus(channel=evi_can_channel, bustype=evi_can_interface, bitrate=evi_baud_rate)
try:
    reset_zeka = command_zeka(
        argument="RESET",
        precharge_delay=True,
        reset_faults=True,
        full_stop=False,
        run_device=False,
        set_device_mode=chosen_zeka_device_mode
    )
    if reset_zeka is None:
        print(red_text("BLG initialization failed!"))
        exit(1)
    stop_zeka_heartbeat = threading.Event()
    zeka_heartbeat_thread = threading.Thread(target=ZEKA_heartbeat, kwargs={'stop_psu_heartbeat': stop_zeka_heartbeat, 'verbose': True})
    zeka_heartbeat_thread.start()
    time.sleep(1)
    # Si comincia ad ascoltare sull'EVI solo un secondo dopo l'avvio dello Zeka
    stop_evi_server = threading.Event()
    stop_evi_heartbeat = threading.Event()
    evi_heartbeat_thread = threading.Thread(target=EVI_heartbeat, kwargs={'stop_evi_heartbeat': stop_evi_heartbeat, 'evi_bus': evi_bus})
    evi_server_thread = threading.Thread(target=EVI_CAN_server, kwargs={'stop_evi_server': stop_evi_server, 'evi_bus': evi_bus})
    evi_heartbeat_thread.start()
    evi_server_thread.start()
    keyboard_interrupt = threading.Event()
    keyboard_interrupt.wait()
except KeyboardInterrupt:
    command_zeka(
        argument="RESET",
        precharge_delay=True,
        reset_faults=True,
        full_stop=False,
        run_device=False,
        set_device_mode=chosen_zeka_device_mode
    )
    stop_zeka_heartbeat.set()
    stop_evi_server.set()
    stop_evi_heartbeat.set()
    if evi_heartbeat_thread.is_alive():
        evi_heartbeat_thread.join()
    if zeka_heartbeat_thread.is_alive():
        zeka_heartbeat_thread.join()
    if evi_server_thread.is_alive():
        evi_server_thread.join()
    zeka_bus.shutdown()
    evi_bus.shutdown()
    can_fini()
