from pathlib import Path

import pandas as pd
from linkml_runtime import SchemaView

from odm_map.enum_hierarchy.enum_hierarchy_selector import EnumHierarchySelector
from odm_map.utils.logger import get_logger

logger = get_logger(__name__)


def action_select_enum_hierarchy(
    data_frames: dict[str, list[pd.DataFrame]],
    schema: str | Path | SchemaView,
    config: str | Path | None,
) -> dict[str, list[pd.DataFrame]]:
    """For multivalued enum slots keep only the enumeration values that have the deepest enum value in
    the hierarchy for the enumeration as specified in a LinkML schema. That is, if the slot has multiple
    values, then remove any of the values that is a parent (via the is_a attribute in the LinkML schema)
    of any of the other values.

    Args:
        data_frames (dict[str, list[pd.DataFrame]]): Dictionary of DataFrames to select from, where the
            keys are the class names and the values are lists of DataFrames belonging to the class.
            All DataFrames from the same class are merged then filtered. Note that the DataFrames get
            modified in place.
        schema (str | Path | SchemaView): The LinkML schema that the DataFrames belong to. The keys
            of data_frames should be classes within this schema.
        config (str | Path | None): Path to the config file to use for EnumHierarchySelector.
            If specified then it lists all the classes/slots to select enum values from. If not specified
            then all classes/slots that have multivalued enum ranges are selected from.

    Returns:
        dict[str, list[pd.DataFrame]]: The selected DataFrames. Keys are the class names and values
            are lists of filtered DataFrames for that class.
    """
    selector = EnumHierarchySelector(schema, config=config)
    data_frames = selector.select(data_frames=data_frames)

    return data_frames
