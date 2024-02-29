from ..node.base import WattRemoteNode
import pathlib
from typing import List, Tuple
from abc import ABC
from ..utils import generic_node_filename
import datetime
import csv
import time
import canopen
import logging

logger = logging.getLogger()
# Started adding abstraction for ui outputs in order to use this in a GUI
class UI(ABC):
    def display_header(self, field_names: List[str]) -> None:
        raise NotImplementedError()

    def display_row(self, row: List[int]) -> None:
        raise NotImplementedError()


S_TO_MS = 1000


def sdo_monitor(
    output_path: pathlib.Path,
    node: WattRemoteNode,
    vars_to_monitor: List[str],
    period_ms: int,
    nb_points: int,
    ui: UI = UI(),
) -> None:
    """Blocking function that monitors sdo values and displays them"""
    monitoring_list: List[Tuple[str, canopen.objectdictionary.Variable]] = []

    for var in vars_to_monitor:
        var_splited = var.split(".")
        if "0x" in var:
            # Hex format given
            sdo_val = node.sdo[int(var_splited[0], 0)][int(var_splited[1], 0)]
        else:
            sdo_val = node.sdo[var_splited[0]][var_splited[1]]
        monitoring_list.append((var, sdo_val))

    total_points_measuread = 0
    # Read software information of the node
    sw_info = node.controller.read_software_information()
    file_name = f'SDO-MONITORING-{generic_node_filename(sw_info)}-{datetime.datetime.now().strftime("%d%m%Y-%H-%M-%S")}.csv'
    output_file = pathlib.Path(output_path, file_name)

    field_names = [var_name for var_name in vars_to_monitor] + [
        "Elapsed time (ms)",
    ]

    with open(output_file, "w+", newline="") as csv_file:
        writer = csv.writer(csv_file)
        ui.display_header(field_names)
        writer.writerow(field_names)

        elapsed_time = 0
        prev_time = time.time()
        while total_points_measuread < nb_points:
            block_sample = []
            for obj in monitoring_list:
                sample = obj[1].raw
                block_sample.append(sample)
            row = block_sample
            current_time = time.time()
            delta_time = (current_time - prev_time) * S_TO_MS
            elapsed_time += delta_time
            prev_time = current_time
            row.append(elapsed_time)
            writer.writerow(row)
            ui.display_row(row)
            total_points_measuread += 1
            time.sleep(float(period_ms / S_TO_MS))
