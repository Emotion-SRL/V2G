import time
from typing import Callable, Optional
import pathlib
from enum import Enum
from dataclasses import dataclass
import canopen
from typing import Union
from ...ui import generate_progress_bar
from ..base import WattNodeController

import logging

logger = logging.getLogger(__name__)


CAN_BYTES_SIZE = 8
SLEEP_PRESCALER = 4
ERASE_FLASH_TIMEOUT = 30  # 30 seconds max
MAX_RETRIES = 10
CHUNK_SIZE = 7


class BootloaderState(Enum):
    NO_STATE = 0
    WAITING_FW_UPGRADE = 1
    ERASE_FLASH_ONGOING = 2
    ERASE_FLASH_SUCCESS = 3
    ERASE_FLASH_FAILED = 4
    PROGRAM_FLASH_ONGONG = 5
    PROGRAM_FLASH_SUCCESS = 6
    PROGRAM_FLASH_FAILED = 7
    PROGRAM_FLASH_TIMEOUT = 8
    APPLI_CRC_ERROR = 9
    FW_IS_APPLICATION = 255
    UNKNOWN = 256


@dataclass
class BootloaderIndexes:
    BOOTLOADER_DOWNLOAD_PROGRAM_DATA_INDEX = 0x1F50
    BOOTLOADER_DOWNLOAD_PROGRAM_DATA_SUBINDEX = 0x1
    BOOTLOADER_CONTROL_INDEX = 0x1F51
    BOOTLOADER_CONTROL_SUBINDEX = 0x1
    BOOTLOADER_STATUS_INDEX = 0x1F57
    BOOTLOADER_STATUS_SUBINDEX = 0x1
    BOOTLOADER_PASSWORD_INDEX = 0x2105
    START_PROGRAM = 1
    ERASE_FLASH = 3


def sleep_ms(delay_ms: float) -> None:
    """Precise delay in milliseconds time.sleep is not used because precision is low ~10ms"""
    _ = time.perf_counter() + delay_ms / 1000
    while time.perf_counter() < _:
        pass


def notify(status: "BootloaderStatus") -> "BootloaderStatus":
    """Notify of bootloader state change to parent
    Used as parameter to BootloaderController so easily changeable
    """
    if status.new_state != None:
        logger.info(f"Bootloader changed to state {status.new_state}")
    if (status.download_progress_current is not None) and (status.download_progress_total is not None):
        logger.info(
            generate_progress_bar(
                iteration=status.download_progress_current,
                total=status.download_progress_total,
                prefix="Uploading firmware",
                suffix="Complete",
            )
        )
    return status


@dataclass
class BootloaderStatus:
    new_state: Optional[BootloaderState] = None
    download_progress_current: Optional[int] = None
    download_progress_total: Optional[int] = None


class BootloaderController(WattNodeController):
    """Bootloader specific controller"""

    # Delay before communicating with bootloader after a reboot
    BOOT_DELAY: int = 1.0
    # Required delay after erasing flash before uploading new firmware
    # Don't know exactly why
    DELAY_AFTER_ERASE: int = 1.5
    # Code for unlocking the bootloader ('boot' in ASCII)
    UNLOCK_BOOTLOADER: int = 0x626F6F74
    # Start program command
    START_PROGRAM = 1
    # Erase flash command
    ERASE_FLASH = 3

    def __init__(
        self,
        node: Union["canopen.RemoteNode", "canopen.LocalNode"],
        indexes: BootloaderIndexes = BootloaderIndexes(),
        notify: Callable[[BootloaderStatus], BootloaderStatus] = notify,
        *args,
        **kwargs,
    ):
        """Initialize controller, with default bootloader indexes"""
        super().__init__(node, *args, **kwargs)
        self.indexes = indexes
        self.notify = notify

    @property
    def state(self) -> Union[BootloaderState, None]:
        """Get bootloader state"""
        try:
            state = int.from_bytes(
                self.node.sdo.upload(
                    self.indexes.BOOTLOADER_STATUS_INDEX,
                    self.indexes.BOOTLOADER_STATUS_SUBINDEX,
                ),
                byteorder="little",
            )
            return BootloaderState(state)
        except ValueError:
            logger.error(f"Unknown bootloader state {state}")
            return BootloaderState.UNKNOWN

        except canopen.SdoCommunicationError:
            logger.warning("Couln't read bootloader state (normal if bootloader is erasing flash)")
            return None

    def unlock(self):
        """Unlock the bootloader"""
        logger.info("Unlocking bootloader")
        self.node.sdo.download(
            self.indexes.BOOTLOADER_PASSWORD_INDEX,
            0,
            self.UNLOCK_BOOTLOADER.to_bytes(length=4, byteorder="little"),
        )

    def erase_flash(self):
        """Erase flash of DSP"""
        logger.info("Erasing flash")
        self.notify(BootloaderStatus(new_state=BootloaderState.ERASE_FLASH_ONGOING))
        try:
            self.node.sdo.download(
                self.indexes.BOOTLOADER_CONTROL_INDEX,
                self.indexes.BOOTLOADER_CONTROL_SUBINDEX,
                self.indexes.ERASE_FLASH.to_bytes(length=1, byteorder="little"),
            )
        except canopen.sdo.SdoCommunicationError:
            logger.error("Error while trying to initiate flash erase")
            self.notify(BootloaderStatus(new_state=BootloaderState.ERASE_FLASH_FAILED))

    def start_program(self):
        """Enable programming by sending a start program command"""
        self.node.sdo.download(
            self.indexes.BOOTLOADER_CONTROL_INDEX,
            self.indexes.BOOTLOADER_CONTROL_SUBINDEX,
            self.indexes.START_PROGRAM.to_bytes(length=1, byteorder="little"),
        )

    def wait_for_state(self, state: BootloaderState, timeout_s: float) -> None:
        """Blocking call until bootloader is in a certain state with a timeout"""
        time_start = time.time()
        elapsed_time = 0
        period = 0.1  # 0.1 s
        current_state = self.state
        while current_state != state and elapsed_time < timeout_s:
            elapsed_time = time.time() - time_start
            time.sleep(period)
            current_state = self.state
        current_state = self.state
        if current_state == state:
            return True
        else:
            raise BootloaderStateTimeoutException(
                f"Bootloader state timeout exception. Expected state {state} but got {current_state}"
            )

    def _workaround(self):
        """workaround for bootloader 0001 and 0003 to allow to program correctly
        it provokes a SDO abort on server side
        """
        try:
            logger.info("Launch Workaround")
            # Reading password provokes sdo abort
            self.node.sdo.upload(index=self.indexes.BOOTLOADER_PASSWORD_INDEX, subindex=0)
        except canopen.sdo.exceptions.SdoError as e:
            logger.info(f"Workaround with exception {e}")

    def _prepare_for_firmware_download(self, timeout_s: float = 30) -> None:
        """Prepare bootloader before downloading new firmware
        this will put bootloader in erase flash success"""

        # Get the current bootloader state
        bootloader_state = self.state
        logger.info(f"Preparing bootloader for programming. Current state is {bootloader_state}")

        if bootloader_state == BootloaderState.ERASE_FLASH_SUCCESS:
            pass

        elif bootloader_state == BootloaderState.ERASE_FLASH_ONGOING:
            # Wait for erasing to finish before uploading
            self.wait_for_state(BootloaderState.ERASE_FLASH_SUCCESS, timeout_s)

        elif bootloader_state == BootloaderState.WAITING_FW_UPGRADE:
            self.unlock()
            self.erase_flash()
            self.wait_for_state(BootloaderState.ERASE_FLASH_SUCCESS, timeout_s)

        elif bootloader_state in [
            BootloaderState.PROGRAM_FLASH_ONGONG,
            BootloaderState.PROGRAM_FLASH_FAILED,
            BootloaderState.PROGRAM_FLASH_TIMEOUT,
            BootloaderState.ERASE_FLASH_FAILED,
            BootloaderState.APPLI_CRC_ERROR,
        ]:
            self.reboot()
            time.sleep(self.BOOT_DELAY)
            self.unlock()
            self.erase_flash()
            self.wait_for_state(BootloaderState.ERASE_FLASH_SUCCESS, timeout_s)

        else:
            raise BootloaderException(f"Bootloader shouldn't be in state : {bootloader_state}")

        # Add little delay before uploading, otherwise it can cause errors
        time.sleep(1.5)
        logger.debug("Prepared bootloader for firmware upload")

    def _open_flash(self, filesize):
        """Open bootloader flash for writing"""
        return canopen.sdo.client.BlockDownloadStream(
            self.node.sdo,
            self.indexes.BOOTLOADER_DOWNLOAD_PROGRAM_DATA_INDEX,
            self.indexes.BOOTLOADER_DOWNLOAD_PROGRAM_DATA_SUBINDEX,
            filesize,
            request_crc_support=True,
        )

    def _is_old(self) -> bool:
        """Determine if bootloader is older than v0.4, in order to use workaround and limit download speed"""
        # Read software information if not been read before
        if self.sw_info is not None:
            info = self.sw_info
        else:
            info = self.read_software_information()
        # Old type of bootloader
        if "000" in info.sw_version or "1.0.0" in info.sw_version:
            return True
        return False

    def download_fw(
        self,
        firmware_path: str,
        upload_delay_ms: int = 1,
        max_retries: int = 10,
    ) -> None:
        """Download new firmware to DSP bootloader via SDO block transfer
        This includes a retry mechanism in case the download fails
        """
        self._prepare_for_firmware_download()
        old_bootloader = self._is_old()

        for retry in range(max_retries + 1):
            try:
                if old_bootloader:
                    logger.warning("Old version of bootloader, usage is not recommended !")
                    self._workaround()

                # Enable programmming
                self.start_program()

                # Get the filesize
                filesize = pathlib.Path(firmware_path).stat().st_size
                pointer = 0
                # Emit a program is ongoing
                self.notify(BootloaderStatus(new_state=BootloaderState.PROGRAM_FLASH_ONGONG))
                with open(firmware_path, "rb") as f:
                    with self._open_flash(filesize=filesize) as outstream:
                        while True:
                            pointer += 1
                            chunk = f.read(CHUNK_SIZE)
                            # Break if no chunks left
                            if not chunk:
                                break
                            outstream.write(chunk)
                            if pointer % 300 == 0:
                                # Notify of download progress
                                self.notify(
                                    BootloaderStatus(
                                        download_progress_current=outstream.tell(),
                                        download_progress_total=filesize,
                                    )
                                )
                                # Display upload information every 1000 chunks
                            if old_bootloader:
                                # If old version, sleep for upload_delay_ms, this is to reduce upload speed
                                sleep_ms(upload_delay_ms)

            except canopen.sdo.exceptions.SdoError as e:
                logger.error(f"Block download failed {e}, retry attempt nb {retry + 1}")
                self.reboot()
                time.sleep(self.BOOT_DELAY)
                self.unlock()
            else:
                # Notify of program success
                self.notify(BootloaderStatus(new_state=BootloaderState.PROGRAM_FLASH_SUCCESS))
                logger.debug("Programming was successful !")
                return
        raise BootloaderException(f"Failed to program node after {max_retries} attempts")


(
    ERROR_BOOTLOADER_STATE,
    ERROR_FIRMWARE_DOWNLOAD,
) = range(2)

BOOTLOADER_ERRORS = {
    ERROR_BOOTLOADER_STATE: "Bootloader is in an unexpected state",
    ERROR_FIRMWARE_DOWNLOAD: "A fatal error occurred when trying to download firmware",
}


class BootloaderException(Exception):
    """Bootloader exception"""


class BootloaderStateTimeoutException(BootloaderException):
    """Bootloader state exception"""
