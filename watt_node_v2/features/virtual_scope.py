from dataclasses import dataclass
import struct
import logging
import time
from typing import Tuple, Union, List, Any
import canopen
from canopen.sdo.client import BlockUploadStream
from ..node.base import WattNodeController
from enum import Enum


logger = logging.getLogger(__name__)

US_TO_SEC = 1e-6

# ---------------------------------------------------------------------------- #
#                                Helper methods                                #
# ---------------------------------------------------------------------------- #


def Q3_12_to_float(value: int):
    """Convert Q3.12 to float"""
    return value / 4096


def create_list_of_selected_indexes(selection: int, max_nb_selection: int) -> List[int]:
    """Returns a list containing the set bits position in selection"""
    return [index for index in range(max_nb_selection) if (selection & (0b1 << index))]


def create_timeseries(nb_measurements: int, settings: "VirtualScopeSettings") -> List[float]:
    """This creates a timeseries in seconds before and after trig"""
    # Get the reference timestamp index (shift left or righr depending on the phase sample nb)
    # If phase sample nb is 0, then timeseries is only negative, if phase sample nb is = sample nb then timeseries is only positive
    ref_timestamp_index = round(nb_measurements * settings.phase_sample_nb / settings.sample_nb)
    # Return timeseries
    sampling_time_s = settings.sampling_time_us * US_TO_SEC
    timeseries = []
    # Prescaler starts at 0 and not 1
    for i in range(0, nb_measurements):
        timeseries.append(-sampling_time_s * (settings.prescaler + 1) * (ref_timestamp_index - i))
    return timeseries


def create_plot(
    settings: "VirtualScopeSettings",
    timeseries: List[float],
    channels_data: List[Tuple["Channel", List[float]]],
) -> "VirtualScopePlot":
    """Create a virtual scope plot object from what was read"""
    return VirtualScopePlot(timeseries=timeseries, channels_data=channels_data, settings=settings)


@dataclass
class VirtualScopeIndexes:
    """Virtual scope od indexes"""

    COMMAND_INDEX = 0x2320
    GET_DATA_INDEX = 0x2321
    SETTINGS_INDEX = 0x2322
    SIGNALS_INDEX = 0x2323
    SAMPLING_TIME_SUBINDEX = 0x1
    LOG_CHANNEL_SUBINDEX = 0x3
    PRESCALER_SUBINDEX = 0x4
    SAMPLES_NB_SUBINDEX = 0x5
    PHASE_SAMPLES_NB_SUBINDEX = 0x6
    STATE_SUBINDEX = 0x7
    LOG_CHANNEL_ASYM_ONLY_SUBINDEX = 0x8
    UNDERSAMPLING_ASYM_ONLY_SUBINDEX = 0x9


class VirtualScopeStates(Enum):
    """Possible virtual scope states"""

    RUN: int = 0
    STOP: int = 1
    TRIGGER: int = 2
    TRIGGERED: int = 3


@dataclass
class Channel:
    """Virtual scope channel"""

    gain: float
    index: int
    name: str = None
    unit: str = None


@dataclass
class VirtualScopeSettings:
    """Virtual scope settings parameters"""

    prescaler: int
    sample_nb: int
    phase_sample_nb: int
    sampling_time_us: int
    state: VirtualScopeStates
    index_offset: int

    def __str__(self):
        return f"""
Virtual scope settings :
    prescaler : {self.prescaler}
    sample_nb : {self.sample_nb}
    phase_sample_nb : {self.phase_sample_nb}
    sampling_time : {self.sampling_time_us}
    state : {self.state}
    index_offset : {self.index_offset}
        """

    def as_lines(self) -> Tuple[List[str], List[float]]:
        header = [
            "Prescaler",
            "Sample nb",
            "Phase sample nb",
            "Sampling time (us)",
            "State",
        ]
        data = [
            self.prescaler,
            self.sample_nb,
            self.phase_sample_nb,
            self.sampling_time_us,
            self.state.name,
        ]

        return [header, data]


@dataclass
class VirtualScopePlot:
    """Container for storing a virtual scope plot and state"""

    timeseries: List[float]
    channels_data: List[Tuple[Channel, List[float]]]
    settings: VirtualScopeSettings

    def as_lines(self, only_data=False) -> List[List[Any]]:
        """Export as lines for easy csv integration"""
        lines = []
        if not only_data:
            # Virtual scope settings ?
            settings_lines = self.settings.as_lines()
            lines.append(settings_lines[0])
            lines.append(settings_lines[1])
        # Header of virtual scope data
        line = []
        line.append("Time (s)")
        for channel, channel_data in self.channels_data:
            line.append(channel.name if (channel.name is not None) else channel.index)
        lines.append(line)
        # Data part
        channel_data_length = len(self.channels_data[0][1])
        for index in range(channel_data_length):
            new_line = []
            # Add timestamp
            new_line.append(self.timeseries[index])
            for _, channel_data in self.channels_data:
                new_line.append(channel_data[index])
            lines.append(new_line)
        return lines


class VirtualScopeController:
    """Control a virtual scope"""

    def __init__(
        self,
        node_controller: WattNodeController,
        index_offset: int = 0,
        indexes: VirtualScopeIndexes = VirtualScopeIndexes(),
    ):
        self.node = node_controller.node
        self.node_controller = node_controller
        self.index_offset = index_offset
        self.indexes = indexes
        self.channels: List[Channel] = [
            self.create_channel(index + 1) for index in range(self.total_nb_channels)
        ]
        # Get the hardware revision
        self.hardware_revision = self.node_controller.hardware_revision

    def _to_int(self, value: bytes) -> int:
        """Helper function to convert bytes to int"""
        return int.from_bytes(value, byteorder="little")

    # ---------------------------------------------------------------------------- #
    #                            VIRTUAL SCOPE CHANNELS                            #
    # ---------------------------------------------------------------------------- #

    @property
    def total_nb_channels(self):
        return self._to_int(self.node.sdo.upload(self.indexes.SIGNALS_INDEX + self.index_offset, 0))

    @property
    def channel_selection_raw(self) -> int:
        """Returns a list of the selected channels"""
        # Channel selection differs for evis
        if self.hardware_revision == "EVIS_001101":
            # Old hardware revision so get ohter channel selection
            logger.info("Old hardware revision so getting other channel selection")
            channel_select = self.indexes.LOG_CHANNEL_ASYM_ONLY_SUBINDEX
        else:
            logger.info("Recent hardware revision")
            channel_select = self.indexes.LOG_CHANNEL_SUBINDEX

        return self._to_int(
            self.node.sdo.upload(
                self.indexes.SETTINGS_INDEX + self.index_offset,
                channel_select,
            )
        )

    @property
    def channel_selection(self) -> List[Channel]:
        channel_selection_list = create_list_of_selected_indexes(
            self.channel_selection_raw, self.total_nb_channels
        )
        return [channel for channel in self.channels if channel.index in channel_selection_list]

    # ---------------------------------------------------------------------------- #
    #                            VIRTUAL SCOPE SETTINGS                            #
    # ---------------------------------------------------------------------------- #

    @property
    def prescaler(self):
        if self.hardware_revision == "EVIS_001101":
            prescaler_subindex = self.indexes.UNDERSAMPLING_ASYM_ONLY_SUBINDEX
        else:
            prescaler_subindex = self.indexes.PRESCALER_SUBINDEX
        return self._to_int(
            self.node.sdo.upload(
                self.indexes.SETTINGS_INDEX + self.index_offset,
                prescaler_subindex,
            )
        )

    @prescaler.setter
    def prescaler(self, prescaler: int):
        self.node.sdo.download(
            self.indexes.SETTINGS_INDEX + self.index_offset,
            self.indexes.PRESCALER_SUBINDEX,
            prescaler.to_bytes(4, byteorder="little"),
        )

    @property
    def sample_nb(self):
        return self._to_int(
            self.node.sdo.upload(
                self.indexes.SETTINGS_INDEX + self.index_offset,
                self.indexes.SAMPLES_NB_SUBINDEX,
            )
        )

    @sample_nb.setter
    def sample_nb(self, sample_nb: int):
        self.node.sdo.download(
            self.indexes.SETTINGS_INDEX + self.index_offset,
            self.indexes.SAMPLES_NB_SUBINDEX,
            sample_nb.to_bytes(4, byteorder="little"),
        )

    @property
    def phase_sample_nb(self):
        return self._to_int(
            self.node.sdo.upload(
                self.indexes.SETTINGS_INDEX + self.index_offset,
                self.indexes.PHASE_SAMPLES_NB_SUBINDEX,
            )
        )

    @phase_sample_nb.setter
    def phase_sample_nb(self, phase_sample_nb: int):
        self.node.sdo.download(
            self.indexes.SETTINGS_INDEX + self.index_offset,
            self.indexes.PHASE_SAMPLES_NB_SUBINDEX,
            phase_sample_nb.to_bytes(4, byteorder="little"),
        )

    @property
    def sampling_time(self):
        return struct.unpack(
            "f",
            self.node.sdo.upload(
                self.indexes.SETTINGS_INDEX + self.index_offset,
                self.indexes.SAMPLING_TIME_SUBINDEX,
            ),
        )[0]

    @property
    def state(self):
        return VirtualScopeStates(
            self._to_int(
                self.node.sdo.upload(
                    self.indexes.SETTINGS_INDEX + self.index_offset,
                    self.indexes.STATE_SUBINDEX,
                )
            )
        )

    @state.setter
    def state(self, state: VirtualScopeStates):
        states = [
            VirtualScopeStates.RUN,
            VirtualScopeStates.STOP,
            VirtualScopeStates.TRIGGER,
        ]
        if state not in states:
            raise ValueError(f"Invalid state given : {state}")
        logger.info(state.value)
        self.node.sdo.download(
            self.indexes.COMMAND_INDEX + self.index_offset,
            0,
            int(state.value).to_bytes(4, byteorder="little"),
        )

    @staticmethod
    def process_raw_data(
        raw_data: bytes, selected_channels: List[Channel]
    ) -> List[Tuple[Channel, List[float]]]:
        """Processes raw data and a channel selection word and returns a list containing the values per channel"""
        words = []
        for word in struct.iter_unpack(">h", raw_data):
            words.append(word[0])
        nb_selected_channels = len(selected_channels)
        # Create a list for each selected channel
        channels_data = [(selected_channel, []) for selected_channel in selected_channels]
        # Remove the words that do not correspond to a complete set of channel measurements :
        nb_words = len(words) % nb_selected_channels
        useful_words = words[:-nb_words]

        for (
            index,
            word,
        ) in enumerate(useful_words):
            selected_channels_index = index % nb_selected_channels
            # Get the associated selected channel
            selected_channel = selected_channels[selected_channels_index]
            # Format is Q3.12, so divide by 2^12
            channels_data[selected_channels_index][1].append(Q3_12_to_float(word) * selected_channel.gain)
        return channels_data

    def read_settings(self) -> VirtualScopeSettings:
        logger.info(f"HW revision : {self.hardware_revision}")
        return VirtualScopeSettings(
            self.prescaler,
            self.sample_nb,
            self.phase_sample_nb,
            self.sampling_time,
            self.state,
            self.index_offset,
        )

    def create_channel(self, channel_nb: int):
        """Create all the available virtual scope channels"""
        gain = self.read_channel_gain(channel_nb)
        # If object dictionnary is loaded then also read the name from eds (keep only subindex name)
        try:
            name = self.node.sdo[self.indexes.SIGNALS_INDEX + self.index_offset][channel_nb].od.name
        except (canopen.sdo.exceptions.SdoError, KeyError):
            name = None
        return Channel(gain, channel_nb - 1, name)

    def read_channel_gain(self, channel_nb: int):
        """Read channel gain of specific channel, should be between 1 and nb channels"""
        if channel_nb <= 0:
            raise ValueError("Channel nb should be between 1 and nb_channels")
        return struct.unpack(
            "f",
            self.node.sdo.upload(
                self.indexes.SIGNALS_INDEX + self.index_offset,
                channel_nb,
            ),
        )[0]

    def read_raw_buffer(self) -> bytes:
        """Read virtual scope raw buffer as a byte array and return it"""
        prev_blksize = BlockUploadStream.blksize
        # Change the blk size
        BlockUploadStream.blksize = 30
        logger.info("Reading virtual scope buffer via block transfer")
        infile: BlockUploadStream
        try:
            with self.node.sdo.open(
                index=self.indexes.GET_DATA_INDEX + self.index_offset,
                mode="rb",
                block_transfer=True,
            ) as infile:
                buffer = b"".join(infile.readlines())
        except canopen.sdo.exceptions.SdoError as e:
            raise VirtualScopeException(f"Error when reading raw buffer caused by sdo exception : {e}")
        logger.info(f"Buffer size : {len(buffer)}")
        BlockUploadStream.blksize = prev_blksize
        return buffer

    def wait_for_state(self, state: VirtualScopeStates, timeout_s: float = 10.0) -> None:
        """Wait for the virtual scope to be in a specific state"""
        time_start = time.time()
        period = 0.5
        while True:
            actual_state = self.state
            if actual_state == state:
                break
            if time.time() - time_start > timeout_s:
                raise VirtualScopeException(
                    f"Scope didn't go in expected state {state} after {timeout_s}s (scope is in {actual_state})"
                )
            time.sleep(period)

    def dump_plot(self, max_retries: int = 5) -> VirtualScopePlot:
        """Create a virtual scope plot"""
        # Read the settings
        logger.info("Reading Virtual Scope settings")
        settings = self.read_settings()
        # Read channel data
        logger.info("Reading Virtual Scope buffer")
        channels_data = None
        for i in range(max_retries + 1):
            try:
                channels_data = self.process_raw_data(self.read_raw_buffer(), self.channel_selection)
            except (canopen.sdo.exceptions.SdoError, VirtualScopeException) as e:
                logger.error(f"Error when reading scope buffer retrying : {e}")
            else:
                break
        if channels_data is None:
            raise VirtualScopeException(f"Failed to read after {max_retries+1} attempts")

        timeseries = create_timeseries(nb_measurements=len(channels_data[0][1]), settings=settings)
        return create_plot(settings, timeseries=timeseries, channels_data=channels_data)


class VirtualScopeException(Exception):
    """Virtual scope exception"""
