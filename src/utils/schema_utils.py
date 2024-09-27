# %%
"""
Utility functions for LinkML schemas.
"""

from typing import Dict, List
from dataclasses import asdict
import yaml

from linkml_runtime import SchemaView


def get_slot_definition(cls: str, slot: str, schema: SchemaView) -> Dict:
    """Get the full definition for the slot. This includes fields that are attributes of the class.
    If a slot is modified with a slot_usage, then we also update the returned dictionary with the
    slot usage information.

    Args:
        cls (str): The class that contains the slot.
        slot (str): The slot name to get the definition for.
        schema (SchemaView): The Schema the class and slot belong to.

    Returns:
        Dict: The dictionary with all information about the slot (eg. the name, range, pattern, etc).
            If the slot is not a member of the class then None is returned.
    """
    class_definition = schema.induced_class(cls)
    if slot in class_definition.attributes:
        return asdict(class_definition.attributes[slot])
    return None


def get_ranges_of_slot(cls: str, slot: str, schema: SchemaView) -> List[str]:
    """Get the range(s) (if any) of the slot in the specified class.

    Args:
        cls (str): The class that the slot belongs to.
        slot (str): The slot to get the range for.
        schema (SchemaView): The Schema to retrieve the slot info from.

    Returns:
        List[str]: A list of range(s) for the specified slot, if at least one range exists. If
            no range is found (eg. the class or slot are invalid) then None is returned.
    """
    defn = get_slot_definition(cls, slot, schema)

    if defn is not None:
        defn = defn.get("range", None)
        if defn is not None:
            # defn is of type linkml_runtime.linkml_model.meta.ElementName
            # We need to convert it to either type str or type List[str]
            defn = yaml.safe_load(str(defn))

    if isinstance(defn, str):
        defn = [defn]

    return defn
