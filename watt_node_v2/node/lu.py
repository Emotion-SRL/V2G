import json
import pathlib
import logging
from typing import Any, Dict, Union


logger = logging.getLogger(__name__)

DEFAULT_LU_PATH = pathlib.Path(__file__).parent.joinpath("lu_data.json")


def create_two_way_dict(d):
    ivd = {v: k for k, v in d.items()}
    return {**d, **ivd}


EE_error_mapping = {
    "EE_NO_ERROR_CATEGORY": "extended_error_no_error_errors_e",
    "EE_SUP_CATEGORY": "extended_error_sup_errors",
    "EE_PM_CATEGORY": "extended_error_pm_errors",
    "EE_CS_CATEGORY": "extended_error_cs_errors",
    "EE_MPU_CATEGORY": "extended_error_mpu_errors",
    "EE_BMPU_CATEGORY": "extended_error_bmpu_errors",
    "EE_MULTIPLE_PU_CATEGORY": "extended_error_multiple_pu_errors",
}


class LookupTable:
    """Container for lookup table, with utils to get values from names (cp errors, node states, etc)"""

    def __init__(
        self,
        lu_path: pathlib.Path = DEFAULT_LU_PATH,
    ) -> None:
        """Initialize lookup table"""

        self.enum_dicts: Dict[str, Any] = None
        self.lookups: Dict[Any, Any] = {}

        with open(lu_path, "r") as f:
            self.enum_dicts = json.load(f)
            logger.debug("Loaded common lookups")

        for key, d in self.enum_dicts.items():
            # Key is name of enum, d is dictionary
            self.lookups[key] = create_two_way_dict(d)

        # Merge substatus dictionaries into one big substate dictionnary
        self.lookups["CS_ChPt_SubStatusCode_e"] = {}
        substatus_dict = self.lookups["CS_ChPt_SubStatusCode_e"]
        substatus_dict.update(self.lookups["CS_ChPt_CP8SubStates_e"])
        substatus_dict.update(self.lookups["CS_ChPt_CP2SubStates_e"])
        substatus_dict.update(self.lookups["CS_ChPt_CP7SubStates_e"])
        substatus_dict.update(self.lookups["CS_ChPt_CP4SubStates_e"])
        substatus_dict.update(self.lookups["CS_ChPt_CP17SubStates_e"])
        substatus_dict.update(self.lookups["CS_ChPt_CP10SubStates_e"])

    def get_cp_state(self, state: Union[int, str]):
        return self.lookups["CS_ChPt_StatusCode_e"].get(state, f"Uknown State {state}")

    def get_cp_substate(self, substate: Union[int, str]):
        return self.lookups["CS_ChPt_SubStatusCode_e"].get(substate, f"Unknown Substate {substate}")

    def get_pm_state(self, state):
        return self.lookups["PM_StatusCode_e"].get(state, f"Uknown PM State {state}")

    def get_sup_request_code(self, code):
        return self.lookups["SUP_RequestCode_e"].get(code, f"Uknown SUP request code {code}")

    def get_error(self, code):
        return self.lookups["CS_ChPt_error_e"].get(code, f"Unknown error code {code}")

    def get_extended_error(self, extended_error):
        """Construct extended error"""
        category = extended_error & (0b1111)
        index = (extended_error >> 4) & (0b11111)
        error = (extended_error >> 9) & (0b1111111)
        # Get category
        category_str = self.lookups["extended_error_category_e"].get(category)
        if category_str is None:
            return f"Unknown category ee {category}"
        # Get type
        error_type = EE_error_mapping.get(category_str)
        # Then get error
        error_str = self.lookups[error_type].get(error)
        if error_str is None:
            return f"Unknown error {error} in ({category_str},{index})"

        return f"{category_str} | {index} | {error_str}"
