from abc import ABC
from .utils import generate_progress_bar
import logging

# TODO create adapter to be able to use socket, gui, etc

logger = logging.getLogger(__name__)


class UIAdapter(ABC):
    def display(text: str, *args, **kwargs) -> None:
        raise NotImplementedError

    def display_no_nl(self, text: str, *args, **kwargs) -> None:
        raise NotImplementedError


class UITerminalAdapter(UIAdapter):
    def display(self, text: str, *args, **kwargs) -> None:
        logger.info(text)
        print(text)

    def display_no_nl(self, text: str, *args, **kwargs) -> None:
        logger.info(text)
        print(text)


class BaseUI(ABC):
    """Base abstract class for displaying ui information"""

    def __init__(self, adapter: UIAdapter) -> None:
        self.adapter = adapter

    def display_scan_result(self, scan_result, table_cls):
        """Display scan result"""
        table = table_cls(
            [
                "Node ID",
                "Device name",
                "Serial number",
                "Software version",
                "Software Build Nb",
                "NMT state",
            ]
        )
        for result in scan_result.results:
            sw_info = result[1]
            if sw_info is not None:
                table.add_row(
                    [
                        f"{result[0]} ({hex(result[0])})",
                        sw_info.device_name,
                        sw_info.serial_nb,
                        sw_info.sw_version,
                        sw_info.sw_build,
                        f"{result[2]}",
                    ]
                )
            elif result[2] != "NO HEARTBEAT RECEIVED":
                table.add_row(
                    [
                        f"{result[0]} ({hex(result[0])})",
                        None,
                        None,
                        None,
                        None,
                        f"{result[2]}",
                    ]
                )
            else:
                pass

        self.adapter.display(table)

    def display_progress(self, iteration: int, total: int, prefix: str, suffix: str):
        """Generate and display a progress bar"""
        progress_str = generate_progress_bar(iteration, total, prefix=prefix, suffix=suffix, length=50)
        # Display progress bar
        self.adapter.display_no_nl("\r" + progress_str)
