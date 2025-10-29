from typing import Optional, Tuple
from odm_map.utils.extra_and_tracking_slots import EXTRA_SLOT_PREFIX, EXTRA_SLOT_SUFFIX


class ConfigKeys:
    TABLES_TO_SHORTNAMES = "tables_to_shortnames"
    PARTID_TO_MMASET = "partid_to_mmaset"
    SEE_HEADERS = "see_headers"


class WideColumnValues:
    COLUMN_PART_SEPARATOR = "_"
    COLUMN_MEASURE_TAG = "mes"
    COLUMN_METHOD_TAG = "met"
    COLUMN_PROTOCOL_STEPS_TAG = "ps"
    AND_TAG = "AND"
    OR_TAG = "OR"
    NR_TAG = "NR"
    VALUE_TAG = "value"


class MeasureTableColumns:
    COMPARTMENT = "mr_compartment"
    SPECIMEN = "mr_specimen"
    FRACTION = "mr_fraction"
    MEASURE = "mr_measure"
    UNIT = "mr_unit"
    AGGREGATION = "mr_aggregation"
    INDEX = "mr_index"
    VALUE = "mr_value"


class ProtocolStepsTableColumns:
    METHOD = "ps_method"
    MEASURE = "ps_measure"
    VALUE = "ps_value"
    UNIT = "ps_unit"
    AGGREGATION = "ps_aggregation"
    INDEX = "ps_index"


# For columns that have multiple values (eg. in_2_AND_name_insType), the value in the row for the
# column has multiple sub-values, each separated by AND_VALUE_SEPARATOR (eg. 24.12 has the values
# 24 and 12, if the AND_VALUE_SEPARATOR is ".")
AND_VALUE_SEPARATOR = "."

# Separates the group name from the column name. eg. with qr_qualityReports.o123, the dot is the separator.
# Note that the group name must begin with COLUMN_GROUP_PREFIX.
COLUMN_GROUP_SEPARATOR = "."

# Group names start with this string
COLUMN_GROUP_PREFIX = "o"

# The extra column, in all mapped DataFrames, where the group name is added. This can be used
# for downstream linking of IDs
EXTRA_GROUP_COLUMN = f"{EXTRA_SLOT_PREFIX}group{EXTRA_SLOT_SUFFIX}"


def group_of_column(col: str) -> Optional[str]:
    """Get the group of the specified column.

    The group is the string that follows the colon in the column name. For example,
    mr_protocolID:12 has the group 12. If the column does not have a group then None
    is returned.

    Args:
        col (str): The column name to get the group of.

    Returns:
        Optional[str]: The group of the column, or None if no group exists.
    """
    return column_and_group_of_column(col)[1]


def remove_column_group(col: str) -> str:
    """Get the column name with the group removed, if there is one.

    The group is the string that follows the colon in the column name. For example,
    mr_protocolID:12 has the group 12. If the column does not have a group then None
    is returned.

    Args:
        col (str): The column to remove the group from.

    Returns:
        str: The column with the group removed.
    """
    return column_and_group_of_column(col)[0]


def column_and_group_of_column(col: str) -> Tuple[str, Optional[str]]:
    """Get the column name (without group) and the group of the specified column.
    For example, "qr_qualityFlag.o1" will return ("qr_qualityFlag", "o1"), and
    "qr_qualityFlag" will return ("qr_qualityFlag", None).

    Args:
        col (str): The column to get the ungrouped column name and the group from.

    Returns:
        Tuple[str, Optional[str]]: The ungrouped column name and the group of col.
            If there is no group, then the group is returned as None.
    """
    if (
        f"{COLUMN_GROUP_SEPARATOR}{COLUMN_GROUP_PREFIX}" in col
        and not col.rsplit(COLUMN_GROUP_SEPARATOR, maxsplit=1)[-1].isdigit()
    ):
        return col.rsplit(COLUMN_GROUP_SEPARATOR, maxsplit=1)
    return col, None
