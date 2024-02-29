import logging
import threading
import json
import pathlib
import time
from functools import partial
import os
from typing import Dict
from ...ui import BaseUI
import canopen

from .datatypes import EvisIndexes, EvisReleases, ChargePointInterface
from ...node.bmpu.datatypes import BMPUIndexes
from .evis import EvisController, EvisNode


PDO_CONFIGURATION_PATH = os.path.join(os.path.dirname(__file__), "config_evis")

logger = logging.getLogger(__name__)


def add_eds_descriptions(
    od: canopen.ObjectDictionary,
    lookup_maps: Dict[str, str],
    eds_descriptions_dict: Dict[str, Dict[str, str]],
):
    """Adds information to object dictionnary like unit, and lookup value"""
    # Go through eds_descriptions dictionary and update relevant information
    for index, subindexes in eds_descriptions_dict["indexes"].items():
        # Get corresponding obj_record
        obj_record = od[index]
        for sub in subindexes:
            obj_var = obj_record[sub["subindex_name"]]
            if "unit" in sub:
                obj_var.unit = sub["unit"]
            if "lookup_name" in sub:
                obj_var.value_descriptions = lookup_maps.get(sub["lookup_name"], [])
            if "factor" in sub:
                obj_var.factor = sub["factor"]


def log_tpdo_od_var(
    receiver: str,
    mutual_od_var: canopen.objectdictionary.Variable,
    raw_value: float,
    prev_raw_value: float,
) -> bool:
    """Log an od variable in a comprehensible format
    Returns true if the value was logged, else returns false"""
    # Get the associated main variable (problem with variables that have the same index/subindex)
    # Only log if the value is different
    if raw_value == prev_raw_value:
        return False

    if mutual_od_var.value_descriptions:
        logger.info(f"{mutual_od_var.name} : {mutual_od_var.value_descriptions[raw_value]} ==> {receiver}")
        return True

    elif mutual_od_var.unit is not "":
        # Check if change is bigger than print threshold, otherwise don't print
        print_threshold = EvisTPDOUpdate.DEBUG_THRESHOLDS.get(mutual_od_var.unit)
        if abs(raw_value - prev_raw_value) >= print_threshold:
            logger.info(f"{mutual_od_var.name} : {raw_value / mutual_od_var.factor} {mutual_od_var.unit}")
            return True
    else:
        logger.info(f"{mutual_od_var.name} : {raw_value} ==> {receiver}")
        return True
    return False


# class EvisTPDOMonitor:
#     """Evis TPDO monitoring"""

#     DEBUG_THRESHOLDS = {
#         "A": 0.2 * EvisIndexes.CURRENT_GAIN,
#         "V": 1 * EvisIndexes.VOLTAGE_GAIN,
#         "degC": 5 * EvisIndexes.TEMPERATURE_GAIN,
#         "W": EvisIndexes.POWER_GAIN,
#         "Hz": 100,
#     }

#     def __init__(
#         self, evis: EvisNode, pdo_configuration_folder: str = PDO_CONFIGURATION_PATH
#     ):
#         """Initiliaze TPDO monitor with a pdo_configuration_folder that will be loaded"""
#         self._pdo_configuration_folder = pdo_configuration_folder
#         self.evis = evis
#         # Update evis with all the required information (maybe add all the lookup maps to this class ?)
#         self.evis.update()
#         self.thread = threading.Thread(target=self._monitoring)
#         self.thread.setDaemon(True)
#         self._running = False
#         self.ccs_data_store = {}

#         self.tpdo_values = {}
#         self.prev_tpdo_values = {}
#         self.tpdo_pointers = {}
#         self.rpdo_pointers = {}

#     def _init_tpdo_values(self):
#         for tpdo in self.evis.tpdo.values():
#             for obj in tpdo:
#                 key = str(obj.index) + "." + str(obj.subindex)
#                 if key not in self.tpdo_values:
#                     self.prev_tpdo_values[key] = [0, None, None]
#                     self.tpdo_values[key] = [0, None, None]
#                     self.tpdo_pointers[key] = obj

#     def _refresh_tpdo_values(self):
#         for tpdo in self.evis.tpdo.values():
#             for obj in tpdo:
#                 key = str(obj.index) + "." + str(obj.subindex)
#                 if key not in self.tpdo_values:
#                     self.prev_tpdo_values[key] = [0, None, None]
#                     self.tpdo_values[key] = [0, None, None]
#                     self.tpdo_pointers[key] = obj

#     def _init_rpdo_pointers(self):
#         # If RPDOs have overlapping indecies, rpdo_pointers will point to
#         # the first RPDO that has that index configured.
#         for rpdo in self.evis.rpdo.values():
#             if rpdo.enabled:
#                 for obj in rpdo:
#                     key = str(obj.index) + "." + str(obj.subindex)
#                     if obj.index not in self.rpdo_pointers:
#                         self.rpdo_pointers[obj.index] = obj

#     def _update_dynamic_pdos(self):
#         if self.evis.release == EvisReleases.EFAST:
#             self.evis.tpdo[self.tpdo_sup_base].read()
#             self.evis.tpdo[self.tpdo_sup_base + 2].read()
#             self.evis.tpdo[self.tpdo_sup_base].save()
#             self.evis.tpdo[self.tpdo_sup_base + 2].save()
#         elif self.evis.release == EvisReleases.V2G:
#             self.evis.tpdo[self.tpdo_sup_base].read()
#             self.evis.tpdo[self.tpdo_sup_base + 2].read()
#             self.evis.tpdo[self.tpdo_sup_base + 3].read()
#             self.evis.tpdo[self.tpdo_sup_base].save()
#             self.evis.tpdo[self.tpdo_sup_base + 2].save()
#             self.evis.tpdo[self.tpdo_sup_base + 3].save()

#         self._refresh_tpdo_values()

#     def _configure_tpdo_handlers(self, config=None):
#         """configure callbacks on EVIS TPDO
#         Args:
#         """
#         if config is None:
#             raise ValueError("No configuration given in configure_tpdo_handlers")
#         else:
#             cha_pdos = config.get("CHA_TPDO_List")
#             ccs_pdos = config.get("CCS_TPDO_List")
#             mpu_pdos = config.get("MPU_TPDO_List")
#             bmpu_pdos = config.get("BMPU_TPDO_List")
#             for i in cha_pdos:
#                 self.evis.tpdo[i].enabled = True
#                 # Hacky way of forcing to add subscription, because pdos are sometimes disables inside evis
#                 cob_id = self.evis.tpdo[i].cob_id
#                 pdo_callback = self.evis.tpdo[i].on_message
#                 self.evis.network.subscribe(cob_id, pdo_callback)
#                 self.evis.tpdo[i].add_callback(
#                     partial(
#                         self.on_TPDOs_update_callback,
#                         interface=ChargePointInterface.CHA,
#                     )
#                 )
#             for i in ccs_pdos:
#                 self.evis.tpdo[i].enabled = True
#                 cob_id = self.evis.tpdo[i].cob_id
#                 pdo_callback = self.evis.tpdo[i].on_message
#                 self.evis.network.subscribe(cob_id, pdo_callback)
#                 self.evis.tpdo[i].add_callback(
#                     partial(
#                         self.on_TPDOs_update_callback,
#                         interface=ChargePointInterface.CCS,
#                     )
#                 )
#             for i in mpu_pdos:
#                 self.evis.tpdo[i].enabled = True
#                 cob_id = self.evis.tpdo[i].cob_id
#                 pdo_callback = self.evis.tpdo[i].on_message
#                 self.evis.network.subscribe(cob_id, pdo_callback)
#                 self.evis.tpdo[i].add_callback(
#                     partial(self.on_TPDOs_update_callback, index=i - mpu_pdos[0] + 1)
#                 )
#             if bmpu_pdos is not None:
#                 for i in bmpu_pdos:
#                     cob_id = self.evis.tpdo[i].cob_id
#                     if cob_id > BMPUIndexes.THIRD_RPDO_INDEX:
#                         pu_index = (
#                             cob_id
#                             - BMPUIndexes.THIRD_RPDO_INDEX
#                             - BMPUIndexes.BASE_ADDRESS
#                         )
#                     elif cob_id > BMPUIndexes.SECOND_RPDO_INDEX:
#                         pu_index = (
#                             cob_id
#                             - BMPUIndexes.SECOND_RPDO_INDEX
#                             - BMPUIndexes.BASE_ADDRESS
#                         )
#                     else:
#                         pu_index = (
#                             cob_id
#                             - BMPUIndexes.FIRST_RPDO_INDEX
#                             - BMPUIndexes.BASE_ADDRESS
#                         )
#                     self.evis.tpdo[i].enabled = True
#                     cob_id = self.evis.tpdo[i].cob_id
#                     pdo_callback = self.evis.tpdo[i].on_message
#                     self.evis.network.subscribe(cob_id, pdo_callback)
#                     self.evis.tpdo[i].add_callback(
#                         partial(self.on_TPDOs_update_callback, index=pu_index + 3)
#                     )

#     def _load_pdo_configuration(self):
#         """Load pdo configuration, depends on the evis version"""

#         pdo_config = f"{self.evis.release.name.lower()}_config.json"
#         pdo_variables = f"{self.evis.release.name.lower()}_variable_defs.json"

#         config = pathlib.Path(self._pdo_configuration_folder, pdo_config)
#         if config.is_file():
#             # Configure tpdo callbacks
#             with open(config) as config_file:
#                 config_pdo_dict = json.load(config_file)
#             self._configure_tpdo_handlers(config_pdo_dict)
#             eds_descriptions = pathlib.Path(
#                 self._pdo_configuration_folder, pdo_variables
#             )
#             # Add EDS descriptions
#             with open(eds_descriptions) as eds_descriptions_file:
#                 eds_descriptions_dict = json.load(eds_descriptions_file)
#                 self._add_eds_descriptions(
#                     self.evis.object_dictionary,
#                     self.evis.lookup_maps,
#                     eds_descriptions_dict,
#                 )

#         else:
#             raise FileNotFoundError(f"Evis pdo configuration {config} was not found")

#     def on_TPDOs_update_callback(
#         self, mapobject, interface: ChargePointInterface = None, index=None
#     ):
#         """Cache updated values from a TPDO received from this node.
#         :param mapobject: The received PDO message.
#         :type mapobject: canopen.pdo.Map
#         :param interface: Interface type (cha or ccs)
#         :type interface: int
#         """
#         interface = interface
#         index = index
#         for obj in mapobject:
#             key = str(obj.index) + "." + str(obj.subindex)
#             tpdo_value = self.tpdo_values.get(key)
#             # if value is different then update current value
#             if tpdo_value is not None:
#                 self.tpdo_values[key][0] = obj.raw
#                 self.tpdo_values[key][1] = interface
#                 self.tpdo_values[key][2] = index

#     def _add_eds_descriptions(self, od, lookup_maps, eds_descriptions_dict):
#         """Adds information to object dictionnary"""
#         # Go through eds_descriptions dictionary and update relevant information
#         for index, subindexes in eds_descriptions_dict["indexes"].items():
#             # Get corresponding obj_record
#             obj_record = od.get(index)
#             for sub in subindexes:
#                 obj_var = obj_record.get(sub["subindex_name"])
#                 if obj_var is None:
#                     raise KeyError(
#                         "Variable configuration was not found inside Evis object dictionary"
#                     )
#                 if "unit" in sub:
#                     obj_var.unit = sub["unit"]
#                 if "lookup_name" in sub:
#                     obj_var.value_descriptions = lookup_maps.get(sub["lookup_name"], [])
#                 if "factor" in sub:
#                     obj_var.factor = sub["factor"]

#     def start(self, sync_auto_start=True):
#         """Start tpdo monitoring, evis mapping needs to known (i.e read_rpdos and read_tpdos)"""
#         # Get release
#         release = self.evis.release

#         # Define rpdo_sup_base and tpdo_sup_base
#         if release == EvisReleases.V2G:
#             self.rpdo_sup_base = 143
#             self.tpdo_sup_base = 78
#         elif release == EvisReleases.EFAST:
#             self.rpdo_sup_base = 135
#             self.tpdo_sup_base = 72
#         else:
#             self.rpdo_sup_base = 41

#         self.evis.read_pdos()

#         self._init_tpdo_values()
#         self._init_rpdo_pointers()
#         self._load_pdo_configuration()

#         self._running = True
#         self.thread.name = "evis-monitor"
#         self.thread.start()

#     def _monitoring(self):
#         """Monitoring thread for evis logging

#         Raises:
#             KeyError: If unknown unit is used inside object dictionary
#         """
#         while True:
#             if self._running == False:
#                 break
#             time.sleep(0.1)
#             for key, val in self.tpdo_values.items():
#                 try:
#                     if val[0] != self.prev_tpdo_values[key][0]:
#                         value_to_print = val[0]
#                         # Problem with object dictionary that doesn't link multiple objects with same name, retreive object with good name
#                         obj: canopen.objectdictionary = self.tpdo_pointers[key]
#                         od_index = obj.od.parent.name
#                         od_subindex = obj.od.name
#                         mutual_variable = self.evis.object_dictionary.get_variable(
#                             od_index, od_subindex
#                         )
#                         # Get interface if any and get index if any
#                         interface_str = (
#                             "" if val[1] is None else f"INTERFACE : {val[1].name}  "
#                         )
#                         index_str = (
#                             "" if val[2] is None else "INDEX : " + str(val[2]) + "  "
#                         )
#                         before_val_str = interface_str + index_str
#                         if mutual_variable.value_descriptions:
#                             logger.info(
#                                 before_val_str
#                                 + f"{obj.name} changed to {mutual_variable.value_descriptions[value_to_print]}"
#                             )
#                             # update previous value once it has been read and outputed
#                             self.prev_tpdo_values[key][0] = value_to_print

#                         elif mutual_variable.unit is not "":
#                             # Check if change is bigger than print threshold
#                             print_threshold = self.DEBUG_THRESHOLDS.get(
#                                 mutual_variable.unit
#                             )
#                             if print_threshold is None:
#                                 raise KeyError(
#                                     f"Unknown unit in object dictionary : {mutual_variable.unit}"
#                                 )
#                             if (
#                                 abs(value_to_print - self.prev_tpdo_values[key][0])
#                                 >= print_threshold
#                             ):
#                                 logger.info(
#                                     before_val_str
#                                     + f"{obj.name} changed to {value_to_print / mutual_variable.factor} {mutual_variable.unit}"
#                                 )
#                                 # update previous value once it has been read and outputed
#                                 self.prev_tpdo_values[key][0] = value_to_print
#                         else:
#                             # Extended error is constructed on the fly
#                             if od_subindex == "CP_ExtendedErrorCode":
#                                 logger.error(
#                                     f"{before_val_str} {self.evis.construct_extended_error_message(value_to_print,self.evis.lookup_maps,EvisIndexes.EE_error_mapping)}"
#                                 )
#                             else:
#                                 logger.info(
#                                     before_val_str
#                                     + f"{obj.name} changed to {value_to_print}"
#                                 )
#                             # update previous value once it has been read and outputed
#                             self.prev_tpdo_values[key][0] = value_to_print
#                 except Exception as e:
#                     # There should'nt be an exception
#                     logger.error(f"An error occured in thread with exception {e}")
#                     raise ValueError(f"Problem inside monitoring thread, {e}")


class EvisTPDOUpdate:
    """Evis TPDO monitoring"""

    DEBUG_THRESHOLDS = {
        "A": 0.2 * EvisIndexes.CURRENT_GAIN,
        "V": 1 * EvisIndexes.VOLTAGE_GAIN,
        "degC": 5 * EvisIndexes.TEMPERATURE_GAIN,
        "W": EvisIndexes.POWER_GAIN,
        "Hz": 100,
    }

    def __init__(
        self,
        evis_controller: EvisController,
        pdo_configuration_folder: str = PDO_CONFIGURATION_PATH,
        skip_pdo_read: bool = False,
    ):
        """Initiliaze TPDO monitor with a pdo_configuration_folder that will be loaded"""
        self._pdo_configuration_folder = pdo_configuration_folder
        self.controller = evis_controller
        self.node = evis_controller.node
        # Update evis with all the required information (maybe add all the lookup maps to this class ?)
        self._rpdo_sup_base = self.controller.rpdo_sup_base
        self._tpdo_sup_base = self.controller.tpdo_sup_base
        self._release = self.controller.release
        self._running = False

        self.tpdo_values = {}
        self.prev_tpdo_values = {}
        self.tpdo_pointers = {}
        self.rpdo_pointers = {}

        self.ccs_data_store = {}
        self.ccs_tpdo_values = {}
        self.ccs_prev_tpdo_values = {}
        self.ccs_tpdo_pointers = {}
        self.ccs_rpdo_pointers = {}

        self.cha_data_store = {}
        self.cha_tpdo_values = {}
        self.cha_prev_tpdo_values = {}
        self.cha_tpdo_pointers = {}
        self.cha_rpdo_pointers = {}

        # This is long and should only be done once
        if not skip_pdo_read:
            self.node.pdo.read()
        else:
            logger.info("Skipped reading pdos config via sdo")
        self._init_tpdo_values()
        self._init_rpdo_pointers()
        self._load_pdo_configuration()

    def _init_tpdo_values(self):
        for tpdo in self.controller.node.tpdo.values():
            for obj in tpdo:
                key = str(obj.index) + "." + str(obj.subindex)
                if key not in self.tpdo_values:
                    self.prev_tpdo_values[key] = [0, None, None]
                    self.tpdo_values[key] = [0, None, None]
                    self.tpdo_pointers[key] = obj

    def _refresh_tpdo_values(self):
        for tpdo in self.controller.node.tpdo.values():
            for obj in tpdo:
                key = str(obj.index) + "." + str(obj.subindex)
                if key not in self.tpdo_values:
                    self.prev_tpdo_values[key] = [0, None, None]
                    self.tpdo_values[key] = [0, None, None]
                    self.tpdo_pointers[key] = obj

    def _init_rpdo_pointers(self):
        # If RPDOs have overlapping indecies, rpdo_pointers will point to
        # the first RPDO that has that index configured.
        for rpdo in self.controller.node.rpdo.values():
            if rpdo.enabled:
                for obj in rpdo:
                    key = str(obj.index) + "." + str(obj.subindex)
                    if obj.index not in self.rpdo_pointers:
                        self.rpdo_pointers[obj.index] = obj

    def _update_dynamic_pdos(self):
        if self._release == EvisReleases.EFAST:
            self.controller.node.tpdo[self._tpdo_sup_base].read()
            self.controller.node.tpdo[self._tpdo_sup_base + 2].read()
            self.controller.node.tpdo[self._tpdo_sup_base].save()
            self.controller.node.tpdo[self._tpdo_sup_base + 2].save()
        elif self._release == EvisReleases.V2G:
            self.controller.node.tpdo[self._tpdo_sup_base].read()
            self.controller.node.tpdo[self._tpdo_sup_base + 2].read()
            self.controller.node.tpdo[self._tpdo_sup_base + 3].read()
            self.controller.node.tpdo[self._tpdo_sup_base].save()
            self.controller.node.tpdo[self._tpdo_sup_base + 2].save()
            self.controller.node.tpdo[self._tpdo_sup_base + 3].save()

        self._refresh_tpdo_values()

    def _configure_tpdo_callbacks(self, config):
        """configure callbacks on EVIS TPDO
        Args:
        """
        cha_pdos = config.get("CHA_TPDO_List")
        ccs_pdos = config.get("CCS_TPDO_List")
        mpu_pdos = config.get("MPU_TPDO_List")
        bmpu_pdos = config.get("BMPU_TPDO_List")
        for i in cha_pdos:
            self.controller.node.tpdo[i].enabled = True
            # Hacky way of forcing to add subscription, because pdos are sometimes disables inside evis
            cob_id = self.node.tpdo[i].cob_id
            pdo_callback = self.node.tpdo[i].on_message
            self.node.network.subscribe(cob_id, pdo_callback)
            self.node.tpdo[i].add_callback(
                self.on_cha_update_callback,
            )
            for obj in self.node.tpdo[i]:
                self.cha_data_store.setdefault(obj.index, {})
                self.cha_data_store[obj.index][obj.subindex] = obj

        for i in ccs_pdos:
            self.node.tpdo[i].enabled = True
            cob_id = self.node.tpdo[i].cob_id
            pdo_callback = self.node.tpdo[i].on_message
            self.node.network.subscribe(cob_id, pdo_callback)
            self.node.tpdo[i].add_callback(
                self.on_ccs_update_callback,
            )
            for obj in self.node.tpdo[i]:
                self.ccs_data_store.setdefault(obj.index, {})
                self.ccs_data_store[obj.index][obj.subindex] = obj

        for i in mpu_pdos:
            self.node.tpdo[i].enabled = True
            cob_id = self.node.tpdo[i].cob_id
            pdo_callback = self.node.tpdo[i].on_message
            self.node.network.subscribe(cob_id, pdo_callback)
            self.node.tpdo[i].add_callback(
                partial(self.on_TPDOs_update_callback, index=i - mpu_pdos[0] + 1)
            )
        # if bmpu_pdos is not None:
        #     for i in bmpu_pdos:
        #         cob_id = self.node.tpdo[i].cob_id
        #         if cob_id > BMPUIndexes.THIRD_RPDO_INDEX:
        #             pu_index = (
        #                 cob_id - BMPUIndexes.THIRD_RPDO_INDEX - BMPUIndexes.BASE_ADDRESS
        #             )
        #         elif cob_id > BMPUIndexes.SECOND_RPDO_INDEX:
        #             pu_index = (
        #                 cob_id
        #                 - BMPUIndexes.SECOND_RPDO_INDEX
        #                 - BMPUIndexes.BASE_ADDRESS
        #             )
        #         else:
        #             pu_index = (
        #                 cob_id - BMPUIndexes.FIRST_RPDO_INDEX - BMPUIndexes.BASE_ADDRESS
        #             )
        #         self.node.tpdo[i].enabled = True
        #         cob_id = self.node.tpdo[i].cob_id
        #         pdo_callback = self.node.tpdo[i].on_message
        #         self.node.network.subscribe(cob_id, pdo_callback)
        #         self.node.tpdo[i].add_callback(
        #             partial(self.on_TPDOs_update_callback, index=pu_index + 3)
        #         )

    def _load_pdo_configuration(self):
        """Load pdo configuration, depends on the evis version"""

        pdo_config = f"{self._release.name.lower()}_config.json"
        pdo_variables = f"{self._release.name.lower()}_variable_defs.json"

        config = pathlib.Path(self._pdo_configuration_folder, pdo_config)
        try:
            # Configure tpdo callbacks
            with open(config) as config_file:
                config_pdo_dict = json.load(config_file)
            self._configure_tpdo_callbacks(config_pdo_dict)
            eds_descriptions = pathlib.Path(self._pdo_configuration_folder, pdo_variables)
            # Add EDS descriptions
            with open(eds_descriptions) as eds_descriptions_file:
                eds_descriptions_dict = json.load(eds_descriptions_file)
                add_eds_descriptions(
                    od=self.node.object_dictionary,
                    lookup_maps=self.node.network.db_handler.lut.lookups,
                    eds_descriptions_dict=eds_descriptions_dict,
                )
        except FileNotFoundError:
            raise FileNotFoundError(f"Evis configuration file was not found")

    def on_TPDOs_update_callback(self, mapobject, interface: ChargePointInterface = None, index=None):
        """Cache updated values from a TPDO received from this node.
        :param mapobject: The received PDO message.
        :type mapobject: canopen.pdo.Map
        :param interface: Interface type (cha or ccs)
        :type interface: int
        """
        interface = interface
        index = index
        for obj in mapobject:
            key = str(obj.index) + "." + str(obj.subindex)
            tpdo_value = self.tpdo_values.get(key)
            # if value is different then update current value
            if tpdo_value is not None:
                self.tpdo_values[key][0] = obj.raw
                self.tpdo_values[key][1] = interface
                self.tpdo_values[key][2] = index

    def _add_eds_descriptions(self, od, lookup_maps, eds_descriptions_dict):
        """Adds information to object dictionnary"""
        # Go through eds_descriptions dictionary and update relevant information
        for index, subindexes in eds_descriptions_dict["indexes"].items():
            # Get corresponding obj_record
            obj_record = od.get(index)
            for sub in subindexes:
                obj_var = obj_record.get(sub["subindex_name"])
                if obj_var is None:
                    raise KeyError("Variable configuration was not found inside Evis object dictionary")
                if "unit" in sub:
                    obj_var.unit = sub["unit"]
                if "lookup_name" in sub:
                    # obj_var.value_descriptions = lookup_maps.get(sub["lookup_name"], [])
                    obj_var.value_descriptions = self.node.network.db_handler.lut.lookups["lookup_name", []]
                if "factor" in sub:
                    obj_var.factor = sub["factor"]

    def start(self, sync_auto_start=True):
        """Start tpdo monitoring, evis mapping needs to known (i.e read_rpdos and read_tpdos)"""
        # This is long and should only be done once
        self.node.pdo.read()

        self._init_tpdo_values()
        self._init_rpdo_pointers()
        self._load_pdo_configuration()

    def on_ccs_update_callback(self, mapobject):
        """Cache updated values from a TPDO received from this node.
        :param mapobject: The received PDO message.
        :type mapobject: canopen.pdo.Map
        :param interface: Interface type (cha or ccs)
        :type interface: int
        """
        for obj in mapobject:
            self.ccs_data_store[obj.index][obj.subindex] = obj

    def on_cha_update_callback(self, mapobject):
        """Cache updated values from a TPDO received from this node.
        :param mapobject: The received PDO message.
        :type mapobject: canopen.pdo.Map
        :param interface: Interface type (cha or ccs)
        :type interface: int
        """
        for obj in mapobject:
            self.cha_data_store[obj.index][obj.subindex] = obj

    # def start_monitoring(self, ui: BaseUI):
    #     """Monitoring for evis

    #     Raises:
    #         KeyError: If unknown unit is used inside object dictionary
    #     """
    #     while True:
    #         if self._running == False:
    #             break
    #         time.sleep(0.1)
    #         for key, val in self.tpdo_values.items():
    #             try:
    #                 if val[0] != self.prev_tpdo_values[key][0]:
    #                     value_to_print = val[0]
    #                     # Problem with object dictionary that doesn't link multiple objects with same name, retreive object with good name
    #                     obj = self.tpdo_pointers[key]
    #                     od_index = obj.od.parent.name
    #                     od_subindex = obj.od.name
    #                     mutual_variable = self.evis.object_dictionary.get_variable(
    #                         od_index, od_subindex
    #                     )
    #                     # Get interface if any and get index if any
    #                     interface_str = (
    #                         "" if val[1] is None else f"INTERFACE : {val[1].name}  "
    #                     )
    #                     index_str = (
    #                         "" if val[2] is None else "INDEX : " + str(val[2]) + "  "
    #                     )
    #                     before_val_str = interface_str + index_str
    #                     if mutual_variable.value_descriptions:
    #                         logger.info(
    #                             before_val_str
    #                             + f"{obj.name} changed to {mutual_variable.value_descriptions[value_to_print]}"
    #                         )
    #                         # update previous value once it has been read and outputed
    #                         self.prev_tpdo_values[key][0] = value_to_print

    #                     elif mutual_variable.unit is not "":
    #                         # Check if change is bigger than print threshold
    #                         print_threshold = self.DEBUG_THRESHOLDS.get(
    #                             mutual_variable.unit
    #                         )
    #                         if print_threshold is None:
    #                             raise KeyError(
    #                                 f"Unknown unit in object dictionary : {mutual_variable.unit}"
    #                             )
    #                         if (
    #                             abs(value_to_print - self.prev_tpdo_values[key][0])
    #                             >= print_threshold
    #                         ):
    #                             logger.info(
    #                                 before_val_str
    #                                 + f"{obj.name} changed to {value_to_print / mutual_variable.factor} {mutual_variable.unit}"
    #                             )
    #                             # update previous value once it has been read and outputed
    #                             self.prev_tpdo_values[key][0] = value_to_print
    #                     else:
    #                         # Extended error is constructed on the fly
    #                         if od_subindex == "CP_ExtendedErrorCode":
    #                             logger.error(
    #                                 f"{before_val_str} {self.evis.construct_extended_error_message(value_to_print,self.evis.lookup_maps,EvisIndexes.EE_error_mapping)}"
    #                             )
    #                         else:
    #                             logger.info(
    #                                 before_val_str
    #                                 + f"{obj.name} changed to {value_to_print}"
    #                             )
    #                         # update previous value once it has been read and outputed
    #                         self.prev_tpdo_values[key][0] = value_to_print
    #             except Exception as e:
    #                 # There should'nt be an exception
    #                 logger.error(f"An error occured in thread with exception {e}")
    #                 raise ValueError(f"Problem inside monitoring thread, {e}")

    def start_monitoring(self):
        """Monitor tpdo values"""
        while True:
            # if self._running == False:
            #     break
            time.sleep(0.1)
            for key, val in self.tpdo_values.items():
                raw_value, receiver = val[0], val[1]
                prev_raw_value = self.prev_tpdo_values[key][0]
                # Problem with object dictionary that doesn't link multiple objects with same name, retreive object with good name
                obj = self.tpdo_pointers[key]
                od_index = obj.od.parent.name
                od_subindex = obj.od.name
                mutual_variable = self.node.object_dictionary.get_variable(od_index, od_subindex)
                if log_tpdo_od_var(receiver, mutual_variable, raw_value, prev_raw_value):
                    # If value was logged, update previous value
                    prev_raw_value = raw_value
