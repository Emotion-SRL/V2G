class ProgrammerException(Exception):
    """Programmer exception"""

    def __init__(self, error, excpt=None):
        message = PROGRAMMING_ERRORS[error]
        super().__init__(message)
        self.error = error
        self.message = message
        self.excpt = excpt


class BootloaderException(Exception):
    def __init__(self, error):
        message = BOOTLOADER_ERRORS[error]
        super().__init__(message)
        self.error = error


(
    PROGRAMMING_SUCCESS,
    ERROR_CURRENT_EDS_NOT_FOUND,
    ERROR_CURRENT_FIRMWARE_NOT_FOUND,
    ERROR_UPDATE_EDS_NOT_FOUND,
    ERROR_UPDATE_FIRMWARE_NOT_FOUND,
    ERROR_READING_NODE_INFORMATION,
    ERROR_CREATING_BACKUP,
    ERROR_INCONSISTENT_NODE_TYPE,
    ERROR_READING_NODE_INFORMATION,
    ERROR_NODE_ALREADY_ON_NETWORK,
    ERROR_CURRENT_FIRMWARE_NOT_FOUND,
    ERROR_FIRMWARE_NOT_FOUND,
    ERROR_DURING_PROGRAMMING,
    ERROR_BOOTLOADER,
    ERROR_UPLOADING_CALIBRATIONS,
    ERROR_DOWNLOADING_CALIBRATIONS,
    ERROR_VALIDATING_FIRMWARE,
    ERROR_NO_HEARTBEAT_DETECTED,
    ERROR_RESTORING_FACTORY_SETTINGS,
    ERROR_NODE_NOT_RESPONDING_AFTER_REPROGRAM,
    ERROR_BOOTLOADER_ALREADY_ON_NETWORK,
    ERROR_RESTORE_PARAMETER,
    ERROR_BOOTLOADER_NOT_FOUND,
    ERROR_UNABLE_TO_DETERMINE_NODE_ID,
) = range(24)

(ERROR_BOOTLOADER_STATE, ERROR_FIRMWARE_DOWNLOAD) = range(2)


PROGRAMMING_ERRORS = {
    PROGRAMMING_SUCCESS: "Node was programmed successfully !",
    ERROR_INCONSISTENT_NODE_TYPE: "Node type between configuration and read node type is inconsistent",
    ERROR_CURRENT_FIRMWARE_NOT_FOUND: "Current firmware was not found, needed in case something goes wrong",
    ERROR_CURRENT_EDS_NOT_FOUND: "The EDS of the current node version was not found",
    ERROR_UPDATE_EDS_NOT_FOUND: "The EDS of the version to program was not found",
    ERROR_UPDATE_FIRMWARE_NOT_FOUND: "The firmware of the version to program was not found",
    ERROR_READING_NODE_INFORMATION: "Could not read device information, probably because node is not online. Is node id correct ?",
    ERROR_FIRMWARE_NOT_FOUND: "Could not find the firmware to reprogram. Is it the correct version and build number ?",
    ERROR_BOOTLOADER: "Error with bootloader",
    ERROR_UPLOADING_CALIBRATIONS: "Error whilst trying to get device calibrations",
    ERROR_DOWNLOADING_CALIBRATIONS: "Error whilst trying to re-upload the device calibrations",
    ERROR_VALIDATING_FIRMWARE: "Error trying validating the programmed firmware.",
    ERROR_NO_HEARTBEAT_DETECTED: "Error, no heartbeat detected after reprogramming node",
    ERROR_CREATING_BACKUP: "Error occured during backup creation, will not proceed in case programming fails",
    ERROR_RESTORING_FACTORY_SETTINGS: "Error trying to restore factory settings",
    ERROR_BOOTLOADER_ALREADY_ON_NETWORK: "A bootloader node is already on the network, first program the bootloader",
    ERROR_BOOTLOADER_NOT_FOUND: "Bootloader was not found on the network",
    ERROR_NODE_NOT_RESPONDING_AFTER_REPROGRAM: "Could not communicate with node after reprogramming",
    ERROR_RESTORE_PARAMETER: "Error with store parameter",
    ERROR_UNABLE_TO_DETERMINE_NODE_ID: "Error, programmer was unable to determine the node id of the node to restore",
    ERROR_NODE_ALREADY_ON_NETWORK: "Error, the node cannot be already on the network if we are recovering from bootloader",
}


def bootloader_state_error(expected_state: str, current_state: str) -> str:
    return f"Bootloader is in an unexpected state should be in {expected_state} but is in {current_state}"


BOOTLOADER_ERRORS = {
    ERROR_BOOTLOADER_STATE: "Bootloader is in an unexpected state",
    ERROR_FIRMWARE_DOWNLOAD: bootloader_state_error,
}
