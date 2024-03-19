import os

zeka_can_interface = 'socketcan'
zeka_can_channel = 'can0'
zeka_baud_rate = 250000

evi_can_interface = 'socketcan'
evi_can_channel = 'can1'
evi_baud_rate = 500000


# ? EVI RELATED SETTINGS (used in x280 frame)
evi_BMPU_ID = 0x5E  # ID of BMPU 0
evi_BMPU_battery_max_voltage = 700
evi_BMPU_battery_max_current = 100
evi_BMPU_grid_max_current = 60
evi_BMPU_grid_max_power = 40000  # 750 x 60, lowered to 40kW for better safety

# ? ZEKA RELATED SETTINGS
zeka_master_node_id = 0x001  # Master ID con cui scrivere al device come Master della comunicazione CAN
zeka_slave_node_id = 0x004  # Slave ID con cui risonde il device
zeka_device_ID = 0x1
zeka_control_packet_id = 0x1  # ID del pacchetto control = 1 status = 4
zeka_status_packet_id = 0x4  # ID del pacchetto control = 1 status = 4


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
