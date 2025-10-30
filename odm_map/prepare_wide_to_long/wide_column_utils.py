from typing import Optional, Tuple, List, Union
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

# Separates the flags from the column name. eg. with qr_qualityReports.o123, the dot is the separator.
COLUMN_FLAG_SEPARATOR = "."

# Group names (as a flag) start with this string
COLUMN_GROUP_PREFIX = "o"

# The extra column, in all mapped DataFrames, where the group name is added. This can be used
# for downstream linking of IDs
EXTRA_GROUP_COLUMN = f"{EXTRA_SLOT_PREFIX}group{EXTRA_SLOT_SUFFIX}"


def column_flags(
    col: str,
    flag_prefix: Optional[Union[List[str], str]] = None,
    remove_flag_prefix: bool = False,
) -> List[str]:
    """Get all flags associated with the column. Flags are separated by COLUMN_FLAGPSEPARATOR.
    For example, qr_qualityFlag.o123.t_sample has the flags o123 and t_sample.

    Args:
        col (str): The column name to get the flags from.
        flag_prefix (Optional[Union[List[str], str]]): If set, then only return flags that begin
            with this string or begin with any of the strings (if a list).
        remove_flag_prefix (bool): If True then remove the prefix from all flags. For example,
            the prefix for a column group is "o", and the column is mr_measure.o123, then
            instead of returning ["o123"], ["123"] will be returned instead. If flag_prefix
            is empty then remove_flag_prefix is ignored (ie. treated as False).

    Returns:
        List[str]: A list of flags. If no flags then the empty array [] is returned.
    """
    if COLUMN_FLAG_SEPARATOR in col:
        if isinstance(flag_prefix, str):
            flag_prefix = [flag_prefix]
        # Get all flags that are not integers
        flags = col.split(COLUMN_FLAG_SEPARATOR)[1:]
        flags = [f for f in flags if not f.isdigit()]
        if flag_prefix:

            def _get_flag(val: str) -> str:
                if not flag_prefix:
                    return val
                for cur_prefix in flag_prefix:
                    if val.startswith(cur_prefix):
                        if remove_flag_prefix:
                            return val[len(cur_prefix) :]
                        return val
                return None

            flags = [_get_flag(f) for f in flags]
            flags = [f for f in flags if f]

        return flags
    return []


def group_of_column(col: str, remove_flag_prefix: bool = False) -> Optional[str]:
    """Get the group of the specified column.

    The group is the string that follows the colon in the column name. For example,
    mr_protocolID.o12 has the group o12. If the column does not have a group then None
    is returned.

    Args:
        col (str): The column name to get the group of.
        remove_flag_prefix (bool): If True then remove the group flag prefix from the returned
            group. For example, for mr_protocolID.o12 will return "12" if remove_flag_prefix is
            True, but will return "o12" if remove_flag_prefix is False.

    Returns:
        Optional[str]: The group of the column, or None if no group exists.
    """
    return column_and_group_of_column(col, remove_flag_prefix=remove_flag_prefix)[1]


def column_and_group_of_column(
    col: str, remove_flag_prefix: bool = False
) -> Tuple[str, Optional[str]]:
    """Get the column name (without group) and the group of the specified column.
    For example, "qr_qualityFlag.o1" will return ("qr_qualityFlag", "o1"), and
    "qr_qualityFlag" will return ("qr_qualityFlag", None).

    Args:
        col (str): The column to get the ungrouped column name and the group from.
        remove_flag_prefix (bool): If True then remove the group flag prefix from the returned
            group. For example, for mr_protocolID.o12 will return "12" if remove_flag_prefix is
            True, but will return "o12" if remove_flag_prefix is False.

    Returns:
        Tuple[str, Optional[str]]: The ungrouped column name and the group of col.
            If there is no group, then the group is returned as None.
    """
    if COLUMN_FLAG_SEPARATOR in col:
        flags = column_flags(
            col, flag_prefix=COLUMN_GROUP_PREFIX, remove_flag_prefix=remove_flag_prefix
        )
        if flags:
            return col, flags[0]
    return col, None


def column_without_flags(col: str) -> str:
    """Get the column name with all flags removed.

    For example, mr_measure.o123.t_sample will be converted to mr_measure.

    Args:
        col (str): The column to remove the flags from.

    Returns:
        str: The column with all flags removed.
    """
    if COLUMN_FLAG_SEPARATOR in col:
        return col.split(COLUMN_FLAG_SEPARATOR, maxsplit=1)[0]
    return col


def column_with_flags(col: str, flags: Union[str, List[str]]) -> str:
    """Create the column name consisting of the specified base column name with all
    the specified flags added to the column name. For example, if col is mr_measure and
    the flags are ["o123", "t_sampleID"], then the result will be mr_measure.o123.t_sampleID.

    Args:
        col (str): The column name to add the flags to.
        flags (Union[str, List[str]]): A single flag (string) or a list of flags to add to the
            column.

    Returns:
        str: The column name with the flags added.
    """
    if not flags:
        return col
    if isinstance(flags, str):
        flags = [flags]
    return f"{col}{COLUMN_FLAG_SEPARATOR}{COLUMN_FLAG_SEPARATOR.join(flags)}"
