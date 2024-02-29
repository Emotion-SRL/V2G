from enum import Enum


class PMState(Enum):
    PM0_Init = 0
    PM1_Idle = 1
    PM2_EVWaitingToBeCharged = 2
    PM3_CableIsLocked = 3
    PM4_EVWaitingForPower = 4
    PM5_EVChargeStopRequest = 5
    PM6_ChargeIsStopped = 6
    PM7_PlugOutputIsOff = 7
    PM8_CommunicationTerminated = 8
    PM9_CableIsUnlocked = 9
    PM10_CableUnpluggedBeforeCharge = 10
    PM11_Fault = 11
