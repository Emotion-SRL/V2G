import os
import threading
import time

import can

from zeka_control import (
    assemble_buck_1q_voltage_control_reference_command,
    assemble_main_control_command,
)
from zeka_status import (
    feedback_2_status_request,
    human_readable_feedback_2_status_response,
)


def can_init():
    os.system('sudo ifconfig can0 down')
    os.system('sudo ifconfig can0 txqueuelen 1000')
    os.system('sudo ip link set can0 type can bitrate 250000')
    os.system('sudo ifconfig can0 up')

    os.system('sudo ifconfig can1 down')
    os.system('sudo ifconfig can1 txqueuelen 1000')
    os.system('sudo ip link set can1 type can bitrate 500000')
    os.system('sudo ifconfig can1 up')


def can_fini():
    os.system('sudo ifconfig can0 down')
    os.system('sudo ifconfig can1 down')


can_init()


psu_can_interface = 'socketcan'
psu_can_channel = 'can0'
psu_baud_rate = 250000

evi_can_interface = 'socketcan'
evi_can_channel = 'can1'
evi_baud_rate = 500000

psu_bus = can.interface.Bus(channel=psu_can_channel, bustype=psu_can_interface, bitrate=psu_baud_rate)
evi_bus = can.interface.Bus(channel=evi_can_channel, bustype=evi_can_interface, bitrate=evi_baud_rate)

psu_lock = threading.Lock()
evi_lock = threading.Lock()

psu_master_node_id = 0x001  # Master ID con cui scrivere al device come Master della comunicazione CAN
psu_slave_node_id = 0x004  # Slave ID con cui risonde il device
psu_device_ID = 0x1
psu_control_packet_id = 0x1  # ID del pacchetto control = 1 status = 4
psu_status_packet_id = 0x4  # ID del pacchetto control = 1 status = 4

psu_control_message_id = (psu_master_node_id << 8) | (psu_device_ID << 3) | psu_control_packet_id
psu_status_message_id = (psu_master_node_id << 8) | (psu_device_ID << 3) | psu_status_packet_id

evi_master_node_id = 0x001  # Master ID con cui scrivere al device come Master della comunicazione CAN
evi_slave_node_id = 0x004  # Slave ID con cui risonde il device
evi_device_ID = 0x1
evi_control_packet_id = 0x1  # ID del pacchetto control = 1 status = 4
evi_status_packet_id = 0x4  # ID del pacchetto control = 1 status = 4

evi_control_message_id = (evi_master_node_id << 8) | (evi_device_ID << 3) | evi_control_packet_id
evi_status_message_id = (evi_master_node_id << 8) | (evi_device_ID << 3) | evi_status_packet_id


def thread_safe_BLG_CAN_request_response_cycle(request):
    with psu_lock:
        psu_bus.send(request)
        response = psu_bus.recv(1)
    if response is None:
        return None
    else:
        return response.data


def initialize_BLG():
    data_bytes = assemble_main_control_command(
        precharge_delay=True,
        reset_faults=True,
        full_stop=False,
        run_device=False,
        set_device_mode="Buck 1Q voltage control mode"
    )
    message = can.Message(arbitration_id=psu_control_message_id, data=data_bytes, is_extended_id=False)
    response = thread_safe_BLG_CAN_request_response_cycle(message)
    if response is None:
        print("errore")
    data_bytes = assemble_buck_1q_voltage_control_reference_command(voltage_reference=50, current_limit=1)
    message = can.Message(arbitration_id=psu_control_message_id, data=data_bytes, is_extended_id=False)
    thread_safe_BLG_CAN_request_response_cycle(message)


def BLG_heartbeat(stop_psu_heartbeat, verbose=False):
    print("BLG_heartbeat thread started")
    message = can.Message(arbitration_id=psu_status_message_id, data=feedback_2_status_request, is_extended_id=False)
    while not stop_psu_heartbeat.is_set():
        response = thread_safe_BLG_CAN_request_response_cycle(message)
        if verbose and response is not None:
            human_readable_feedback_2_status_response(response)
        time.sleep(1.4)
    print("BLG_heartbeat thread stopped")


received_frame_IDs = set()


def EVI_CAN_server(stop_evi_server, evi_bus):
    print("EVI_CAN_server thread started")
    while not stop_evi_server.is_set():
        message = evi_bus.recv()
        if message is not None:
            print(f"ID: {message.arbitration_id} (dec), {hex(message.arbitration_id)} (hex)")
            print(f"EVI_CAN_server received:\n{message}")
            received_frame_IDs.add(f"ID: {message.arbitration_id} (dec), {hex(message.arbitration_id)} (hex)")
    print("EVI_CAN_server thread stopped")


try:
    stop_psu_heartbeat = threading.Event()
    stop_evi_server = threading.Event()
    initialize_BLG()
    blg_heartbeat_thread = threading.Thread(target=BLG_heartbeat, kwargs={'stop_psu_heartbeat': stop_psu_heartbeat, 'verbose': True})
    evi_server_thread = threading.Thread(target=EVI_CAN_server, kwargs={'stop_evi_server': stop_evi_server, 'evi_bus': evi_bus})
    blg_heartbeat_thread.start()
    evi_server_thread.start()
    keyboard_interrupt = threading.Event()
    keyboard_interrupt.wait()
except KeyboardInterrupt:
    # # Chiudi la connessione CAN
    stop_psu_heartbeat.set()
    stop_evi_server.set()
    blg_heartbeat_thread.join()
    evi_server_thread.join()
    psu_bus.shutdown()
    evi_bus.shutdown()
    can_fini()
    print("received_frame_IDs:")
    for frame_ID in received_frame_IDs:
        print(f"{frame_ID}")
