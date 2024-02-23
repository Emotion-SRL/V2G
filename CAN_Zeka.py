import os
import time

import can


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


def byte_to_temperature(high_byte, low_byte):
    # Combinare i byte per ottenere il valore a 16 bit
    value = (high_byte << 8) | low_byte

    # Moltiplicare per 0.1 per ottenere la temperatura in gradi Celsius
    temperature = round(value * 0.1, 1)

    return temperature


def bytes_to_temperature(feedback_array):
    # Estrai i penultimi due byte
    high_byte = feedback_array[-2]
    low_byte = feedback_array[-1]

    # Combinare i byte per ottenere il valore a 16 bit
    value = (high_byte << 8) | low_byte

    # Moltiplicare per 0.1 per ottenere la temperatura in gradi Celsius
    temperature = round(value * 0.1, 2)

    return temperature


def boost_1Q_voltage_control(voltage, current):
    # Calcola i byte per la tensione
    voltage_value = int(voltage / 0.1)
    voltage_high_byte = (voltage_value >> 8) & 0xFF
    voltage_low_byte = voltage_value & 0xFF

    # Calcola i byte per la corrente
    current_value = int(current / 0.1)
    current_high_byte = (current_value >> 8) & 0xFF
    current_low_byte = current_value & 0xFF

    # Crea il messaggio da inviare sul bus CAN
    command = [0x83, voltage_high_byte, voltage_low_byte, current_high_byte, current_low_byte, 0x00, 0x00, 0x00]

    return command


can_init()

psu_can_interface = 'socketcan'
psu_can_channel = 'can0'
psu_baud_rate = 250000

evi_can_interface = 'socketcan'
evi_can_channel = 'can1'
evi_baud_rate = 500000

psu_bus = can.interface.Bus(channel=psu_can_channel, bustype=psu_can_interface, bitrate=psu_baud_rate)
evi_bus = can.interface.Bus(channel=evi_can_channel, bustype=evi_can_interface, bitrate=evi_baud_rate)

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

# Status registers 0xA0 >>> 0xA4
Main_Status_Request = [0xA0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
Feedback_1_Status_Request = [0xA1, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
Feedback_2_Status_Request = [0xA2, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
Error_Status_Request = [0xA3, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
IOs_Status_Request = [0xA4, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]


# Control registers 0x80 >>> 0x90
Main_Control_Command = [0x80, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]  #
Buck_1Q_Voltage_Control_Reference_Command = [0x81, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]  #
Buck_1Q_Current_Control_Reference_Command = [0x82, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]  #
Boost_1Q_Voltage_Control_Reference_Command = [0x83, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]  #
Boost_1Q_Current_Control_Reference_Command = [0x84, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]  #
Buck_2Q_Voltage_Control_Reference_Command = [0x85, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]  #
Boost_2Q_Voltage_Control_Reference_Command = [0x86, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]  #
Boost_A_current_B_Voltage_Control_Reference_Command = [0x8B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]  #
Outputs_Control_Command = [0x90, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]  #

converter_setup = [0x80, 0x01, 0x81, 0x00, 0x02, 0x00, 0x00, 0x00]  # 60V low side buck

# register = open("Registers.txt", "r")
# print(register.readline())


# Crea il messaggio di controllo
psu_status_message = can.Message(arbitration_id=psu_status_message_id, data=Feedback_2_Status_Request, is_extended_id=False)


# Invia il messaggio di controllo
# psu_bus.send(psu_control_message)
# response1 = psu_bus.recv(1.5)
# print(response1)
# psu_bus.send(psu_status_message)
# response2 = psu_bus.recv(1.5)
# print(response2)
# time.sleep(0.5) # Attendi un breve periodo di tempo per assicurarti che il messaggio venga inviato
try:
    voltage = 200
    current = 3
    voltage_message = boost_1Q_voltage_control(voltage, current)
    psu_setup_message = can.Message(arbitration_id=psu_control_message_id, data=converter_setup, is_extended_id=False)
    psu_voltage_control_message = can.Message(arbitration_id=psu_control_message_id, data=voltage_message, is_extended_id=False)
    print(psu_setup_message)
    psu_bus.send(psu_setup_message)
    time.sleep(0.2)
    psu_bus.send(psu_voltage_control_message)

    while True:
        psu_bus.send(psu_status_message)
        response2 = psu_bus.recv(1.5)
        data = response2.data.hex()
        high_byte = int(data[-6:-4], 16)
        low_byte = int(data[-4:-2], 16)

        temperatura = byte_to_temperature(high_byte, low_byte)
        print("La temperatura è:", temperatura, "°C")
        # print(data,high_byte,low_byte)
        time.sleep(0.5)
except KeyboardInterrupt:
    # # Chiudi la connessione CAN
    psu_bus.shutdown()
    evi_bus.shutdown()
    can_fini()
