import logging
import struct
from abc import ABC, abstractclassmethod
from typing import Optional, Union, List
from io import BufferedReader
from enum import Enum
from dataclasses import dataclass, field
import time

import canopen
from canopen.sdo.client import BlockUploadStream
from canopen import LocalNode, RemoteNode

from ..node.datatypes import MPU_IDS, BMPU_IDS
from ..ui import BaseUI

logger = logging.getLogger(__name__)

DUMPABLE_NODES = list(set(MPU_IDS) | set(BMPU_IDS))
ERASE_EXTERNAL_MEMORY_COMMAND = 0x64616564


@dataclass
class LoggingIndexes:
    LOG_SETTINGS_INDEX = 0x2310
    LOG_DUMP_INDEX = 0x2311
    LOG_FLASH_ERASE_INDEX = 0x2312
    LOG_FAULT_COUNTERS_INDEX = 0x2313
    LOG_FAULT_ENTRIES_INDEX = 0x2314
    NB_ACQUISITIONS_TO_DOWNLOAD_SUBINDEX = 0x2
    FIRST_ACQUISITION_SUBINDEX = 0x1
    NUMBER_OF_ACQUISITIONS_SUBINDEX = 0x2
    CURRENT_LOG_SUBINDEX = 0x3
    LOG_PERIOD_SUBINDEX = 0x4
    MEMORY_FULL_SUBINDEX = 0x5
    ERASE_CODE = 0x01
    ERASE_STATE = 0x02
    ERASE_TOTAL_SUBBLOCKS = 0x03
    ERASE_CURRENT_SUBBLOCK = 0x04


class LogEraseStatus(Enum):
    """Log erase state machine states"""

    IDLE = 0
    CONFIGURE_ERASE = 1
    SEND_ERASE_TO_FLASH = 2
    ERASING = 3
    ERASE_FINISHED = 4


def logger_flash_gen(f: BlockUploadStream):
    while True:
        raw_data = f.read(4)
        if not raw_data:
            logger.info("no more data in file")
            break

        low_word = struct.unpack(">H", raw_data[:2])[0]
        high_word = struct.unpack(">H", raw_data[2:4])[0]
        value = (high_word << 16) + low_word
        yield value


@dataclass
class LoggingChannel:
    od_index: int
    od_subindex: int
    merged_index: int
    name: str = None
    values: List[float] = field(default_factory=list)


@dataclass
class LoggingData:
    """Logging data container, immutable"""

    channels: List[LoggingChannel]
    fields: List[str]
    lines: List[List[int]]

    @classmethod
    def from_channels(cls, channels: List[LoggingChannel]) -> "LoggingData":
        """Create LoggingData container from log channels"""
        total_lines = len(channels[0].values)
        lines = []
        for line_nb in range(total_lines):
            line = []
            for channel in channels:
                line.append(channel.values[line_nb])
            lines.append(line)
        fields = []
        for channel in channels:
            fields.append(channel.merged_index if channel.name is None else channel.name)
        return cls(channels=channels, fields=fields, lines=lines)


@dataclass
class LoggingSettings:
    """Logging settings"""

    first_acquisition: int
    number_of_acquisitions_to_dump: int
    current_log_index: int
    logging_period_us: int
    memory_full_flag: int
    erase_status: LogEraseStatus

    def __str__(self) -> str:
        return_str = f"Logging Information\n"
        return_str += f"*********************\n"
        return_str += f"First Acquisition : {self.first_acquisition}\n"
        return_str += f"Number of Acquisitions : {'{0:_}'.format(self.number_of_acquisitions_to_dump)}\n"
        return_str += f"Current log index : {'{0:_}'.format(self.current_log_index)}\n"
        return_str += f"Logging Period (us) : {'{0:_}'.format(self.logging_period_us)}\n"
        return_str += f"Memory Full : {bool(self.memory_full_flag)}\n"
        return_str += f"Erasing status : {self.erase_status.name}({self.erase_status.value})"
        return return_str


@dataclass
class LoggingStatus:
    """Container for logging status"""

    # Logger status state machine
    download_status: str  # init,downloading,finished,error
    download_progress_percent: int
    # Logger eraser status state machine
    erase_progress_percent: int
    erase_status: Optional[str] = None
    error_description: Optional[str] = None


class LoggingObserver(ABC):
    """Abstract logging observer"""

    @abstractclassmethod
    def update(self, controller: "LoggingController"):
        """New information from parent notifier"""
        raise NotImplementedError()


class LoggingObserverCLI(LoggingObserver):
    """Observer for simple CLI printing"""

    def __init__(self, ui: BaseUI) -> None:
        self.ui = ui

    def update(self, controller: "LoggingController"):
        """Print some information to stdout"""
        status = controller.status
        # Only print information when downloading or erasing
        if status.download_status == "downloading":
            self.ui.display_progress(
                status.download_progress_percent,
                100,
                prefix="Downloading",
                suffix="Complete",
            )
        elif status.erase_status == "erasing":
            self.ui.display_progress(
                status.erase_progress_percent,
                100,
                prefix="Erasing",
                postfix="Complete",
            )


class LoggingController:
    """Controller for using a Logging module"""

    def __init__(
        self,
        node: Union[LocalNode, RemoteNode],
        index_offset: int = 0,
        preop: bool = False,
        indexes=LoggingIndexes(),
    ) -> None:
        self.node = node
        # Update node parameters
        self.node.sdo.MAX_RETRIES = 5
        self.node.sdo.RESPONSE_TIMEOUT = 0.5
        self.index_offset = index_offset
        self.indexes = indexes
        self.preop = preop
        self.status = LoggingStatus("init", "", 0, "", 0)
        self._observers: List[LoggingObserver] = []

    def _to_int(self, value: bytes) -> int:
        """Helper function to convert bytes to int"""
        return int.from_bytes(value, byteorder="little")

    @property
    def total_fault_counter_channels(self) -> int:
        return self._to_int(
            self.node.sdo.upload(self.indexes.LOG_FAULT_COUNTERS_INDEX + self.index_offset, 0)
        )

    @property
    def total_fault_entry_channels(self) -> int:
        return self._to_int(
            self.node.sdo.upload(self.indexes.LOG_FAULT_ENTRIES_INDEX + self.index_offset, 0)
        )

    @property
    def total_nb_channels(self) -> int:
        logger.info("Getting number of channels")
        return self.total_fault_counter_channels + self.total_fault_entry_channels

    @property
    def first_acquisition(self) -> int:
        return self._to_int(
            self.node.sdo.upload(
                self.indexes.LOG_SETTINGS_INDEX + self.index_offset,
                self.indexes.FIRST_ACQUISITION_SUBINDEX,
            )
        )

    @first_acquisition.setter
    def first_acquisition(self, value: int) -> None:
        self.node.sdo.download(
            self.indexes.LOG_SETTINGS_INDEX + self.index_offset,
            self.indexes.FIRST_ACQUISITION_SUBINDEX,
            int.to_bytes(value, length=4, byteorder="little"),
        )

    @property
    def number_of_acquisitions_to_dump(self) -> int:
        return self._to_int(
            self.node.sdo.upload(
                self.indexes.LOG_SETTINGS_INDEX + self.index_offset,
                self.indexes.NUMBER_OF_ACQUISITIONS_SUBINDEX,
            )
        )

    @number_of_acquisitions_to_dump.setter
    def number_of_acquisitions_to_dump(self, nb: int) -> None:
        self.node.sdo.download(
            self.indexes.LOG_SETTINGS_INDEX + self.index_offset,
            self.indexes.NUMBER_OF_ACQUISITIONS_SUBINDEX,
            int.to_bytes(nb, length=4, byteorder="little"),
        )

    @property
    def current_log_index(self) -> int:
        return self._to_int(
            self.node.sdo.upload(
                self.indexes.LOG_SETTINGS_INDEX + self.index_offset,
                self.indexes.CURRENT_LOG_SUBINDEX,
            )
        )

    @property
    def log_period(self) -> int:
        return self._to_int(
            self.node.sdo.upload(
                self.indexes.LOG_SETTINGS_INDEX + self.index_offset,
                self.indexes.LOG_PERIOD_SUBINDEX,
            )
        )

    @property
    def memory_full_flag(self) -> int:
        return self._to_int(
            self.node.sdo.upload(
                self.indexes.LOG_SETTINGS_INDEX + self.index_offset,
                self.indexes.MEMORY_FULL_SUBINDEX,
            )
        )

    @property
    def max_dump_size(self) -> int:
        """Max dump size in bytes, if start = 0 and end = current index"""
        return self.current_log_index * self.total_nb_channels * 4

    @property
    def erase_status(self) -> LogEraseStatus:
        """Get the erase state machine status"""
        return LogEraseStatus(
            self._to_int(
                self.node.sdo.upload(
                    self.indexes.LOG_FLASH_ERASE_INDEX + self.index_offset,
                    self.indexes.ERASE_STATE,
                )
            )
        )

    @property
    def nb_subblocks_erased(self) -> int:
        """Get the current number of erased subblocks"""
        return self._to_int(
            self.node.sdo.upload(
                self.indexes.LOG_FLASH_ERASE_INDEX + self.index_offset,
                self.indexes.ERASE_CURRENT_SUBBLOCK,
            )
        )

    @property
    def total_nb_subblocks(self) -> int:
        """Get the total number of subblocks"""
        return self._to_int(
            self.node.sdo.upload(
                self.indexes.LOG_FLASH_ERASE_INDEX + self.index_offset,
                self.indexes.ERASE_TOTAL_SUBBLOCKS,
            )
        )

    def _open_flash(self) -> BufferedReader:
        """Open flash as a file object"""
        BlockUploadStream.blksize = 30
        return self.node.sdo.open(
            index=self.indexes.LOG_DUMP_INDEX + self.index_offset,
            mode="rb",
            buffering=1000,
            block_transfer=True,
            request_crc_support=True,
        )

    def read_dump_size(self) -> int:
        """Dump size in bytes"""
        return (self.number_of_acquisitions_to_dump - self.first_acquisition) * self.total_nb_channels * 4

    def read_settings(self) -> LoggingSettings:
        """Read and return LoggingSettings"""
        return LoggingSettings(
            self.first_acquisition,
            self.number_of_acquisitions_to_dump,
            self.current_log_index,
            self.log_period,
            self.memory_full_flag,
            self.erase_status,
        )

    def _create_channel(
        self,
        merged_index: int,
        total_fault_counters: int,
        total_channels: int,
    ) -> LoggingChannel:
        """Create a logging channel and return it"""
        # If object dictionnary is loaded then also read the name from eds (keep only subindex name)
        # Get the total number of channels
        if 1 <= merged_index <= total_fault_counters:
            od_index, od_subindex = (
                self.indexes.LOG_FAULT_COUNTERS_INDEX + self.index_offset,
                merged_index,
            )
            try:
                od_var = self.node.sdo[od_index][od_subindex]
                name = od_var.od.name
            except (canopen.sdo.exceptions.SdoError, KeyError):
                name = None
        elif total_fault_counters + 1 <= merged_index <= total_channels + 1:
            od_index, od_subindex = (
                self.indexes.LOG_FAULT_ENTRIES_INDEX + self.index_offset,
                merged_index - total_fault_counters,
            )
            try:
                od_var = self.node.sdo[od_index][od_subindex]
                name = od_var.od.name
            except (canopen.sdo.exceptions.SdoError, KeyError):
                name = None
        else:
            raise ValueError("Index should be between 1 and total_nb_channels")

        return LoggingChannel(
            od_index=od_index,
            od_subindex=od_subindex,
            merged_index=merged_index,
            name=name,
        )

    def _create_channels(self) -> List[LoggingChannel]:
        """Create all the logging channels"""
        total_fault_counters = self.total_fault_counter_channels
        total_fault_entries = self.total_fault_entry_channels
        total_channels = total_fault_counters + total_fault_entries
        # Create the channels
        channels: List[LoggingChannel] = []
        for channel_idx in range(total_channels):
            channels.append(self._create_channel(channel_idx + 1, total_fault_counters, total_channels))
        return channels

    def read_lines(self, start: int, end: int, ui=None, preop_node: bool = True) -> LoggingData:
        """Read lines of flash file inside logging module"""
        try:
            channels = self._create_channels()
            self.number_of_acquisitions_to_dump = end - start
            dump_size = self.read_dump_size()

            if dump_size == 0:
                self.status.download_status = "error"
                self.status.download_progress_percent = 0
                self.status.error_description = "Nothing to dump, dump size is 0"
                self.notify()
                raise RuntimeError("Nothing to dump, dump size is 0")

            # we should have
            # 0 <= start < end <= total nb lines

            with self._open_flash() as infile:
                # Put Node in preoperational before dumping
                if preop_node:
                    self.node.nmt.state = "PRE-OPERATIONAL"

                # Update internal status to downloading & notify parent
                self.status.download_status = "downloading"
                self.status.download_progress_percent = 0
                self.notify()

                for index, channel_data in enumerate(logger_flash_gen(infile)):
                    channels[index % len(channels)].values.append(channel_data)
                    # Update download percentage
                    progress_percent = (infile.tell() / dump_size) * 100
                    self.status.download_progress_percent = progress_percent
                    if (index / (len(channels))) % 100 == 0:
                        # Notify every 100 lines
                        self.notify()
                        logger.debug(f"Dumped a total of {infile.tell()/dump_size*100}")

        except Exception as e:
            self.status.download_status = "error"
            self.status.download_progress_percent = 0
            self.status.error_description = e
            self.notify()
            raise

        # Notify when the download finishes
        self.status.download_status = "finished"
        self.status.download_progress_percent = 100
        self.notify()
        if preop_node:
            self.node.nmt.wait_for_heartbeat(3)  # max 3 seconds
            self.node.nmt.state = "OPERATIONAL"
        return LoggingData.from_channels(channels)

    def read_last_line(self) -> LoggingData:
        """Read last logging module line, this does NOT use block transfer, only segmented"""
        channels = self._create_channels()
        for channel in channels:
            value = int.from_bytes(
                self.node.sdo.upload(channel.od_index, channel.od_subindex),
                byteorder="little",
                signed=False,
            )
            channel.values = [value]
        return LoggingData.from_channels(channels)

    def read_all_lines(self, ui=None) -> LoggingData:
        """Read all log lines (simple helper)"""
        return self.read_lines(start=0, end=self.current_log_index)

    def erase(self) -> None:
        """Erase Logging data"""
        self.node.sdo.download(
            self.indexes.LOG_FLASH_ERASE_INDEX + self.index_offset,
            self.indexes.ERASE_CODE,
            int.to_bytes(ERASE_EXTERNAL_MEMORY_COMMAND, length=4, byteorder="little"),
        )

    def start_erase_and_wait(self) -> None:
        """Launch an erase sequence and wait for the erase to complete
        This can be a long blocking function
        """
        self.erase()
        # Get the number of subblocks
        try:
            self.status.erase_progress_percent = 0
            self.status.erase_status = self.erase_status.value
            total = self.total_nb_subblocks
            if total == 0:
                self.status.error_description = "number of sub-blocks should not be 0"
                raise canopen.SdoCommunicationError("number of sub-blocks should not be 0")
        except canopen.sdo.exceptions.SdoError:
            logger.warning(
                "flash erase progress not implemented for this sw version,user will just have to wait"
            )
        self.notify()
        # Poll for erase status
        while True:
            erase_status_enum = self.erase_status
            self.status.erase_status = erase_status_enum.value
            if erase_status_enum == LogEraseStatus.IDLE:
                self.status.erase_status = "finished"
                self.notify()
                return
            time.sleep(0.2)
            # Update the progress :
            self.status.erase_progress_percent = self.nb_subblocks_erased
            self.notify()

    def notify(self) -> None:
        """Notify observers of changes"""
        for observer in self._observers:
            observer.update(self)

    def attach(self, observer: LoggingObserver) -> None:
        """Attach an observer"""
        self._observers.append(observer)

    def detach(self, observer: LoggingObserver) -> None:
        """Remove an observer"""
        self._observers.remove(observer)


class LoggingException(Exception):
    """Logging exception"""
