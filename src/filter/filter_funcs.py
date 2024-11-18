"""
All filtering functions/operations.

Filtering involves creating boolean filters for the various different DataFrames (that represent the classes in our
dataset). Once the filters are created, we can apply them to the DataFrames and then use the filtered data.

Within the filtering functions, the `filters` dictionary contains the boolean filters, which are initialized to all True.
The keys of this dictionary are filter names (which are typically not class names). We build up the filters and when we're
done we apply these filters to the DataFrames in the `data` parameter, by specifying a filter name (in the `filters`
dictionary) and a class to apply the filter to (a DataFrame in `data`).

Filtering functions can take the following keyword arguments:

- filters (Dict[str, pd.Series]): All filters. Keys are the filter names and values are the boolean filters.
- data (Dict[str, pd.DataFrame]): The data. Keys are the classes and values are the DataFrames.
- input_name (str): The input filter name. We use this as the initial filter.
- output_name (str): The output filter name to save the filter as.
- cls (str): The class we are applying the filter to.
- slot (str): The slot (in the class) we are performing the operation on.
- value (Any): The value, whose meaning depends on which operation we're performing.

All the arguments above are optional, to avoid errors each filtering function should also include the parameter **kwargs.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from typing import Dict, Any
import pandas as pd
from functools import reduce

from utils.general_utils import get_logger

logger = get_logger(__name__)


def call_filter_func(op: str, **kwargs):
    """Call the filtering function corresponding to the specified operation.

    Args:
        op (str): The operation to call. eg. "exclude_equals". This operation receives
            the keyword arguments in kwargs.
    """
    if op not in FILTER_FUNCS:
        raise ValueError(f"Unrecognized filter operation: '{op}'")
    FILTER_FUNCS[op](**kwargs)


def set_named_filter(filt: pd.Series, name: str, filters: Dict[str, pd.Series]):
    """Set the current filter for the specified filter name. The filter is a boolean series
    that specifies which rows are selected in the table.

    Args:
        filt (pd.Series): The filter.
        name (int): The name to save the filter as.
        filters (Dict[str, pd.Series]): The dictionary containing all filters (values) for all names (keys).
            The value for the name gets modified with filt.
    """
    filters[name] = filt


def get_named_filter(name: str, filters: Dict[str, pd.Series]) -> pd.Series:
    """Get the filter with the specified name. The filter must have been previously created, using the create_filter operation or as an
    outputFilter in the configuration file.

    Args:
        name (str): The name of the filter to get.
        filters (Dict[str, pd.Series]): All the named filters. We retrieve the filter form this.

    Returns:
        pd.Series: The current filter with the specified name.
    """
    if name not in filters:
        raise ValueError(
            f"Filter named '{name}' does not exist. Make sure it has been created with the create_filter operation or created as an outputFilter."
        )
    return filters[name]


def do_drop_duplicates(
    filters: Dict[str, pd.Series],
    data: Dict[str, pd.DataFrame],
    input_name: str,
    output_name: str,
    cls: str,
    slot: str,
    value: str,
    **kwargs,
):
    """Drop all duplicates in a class and slot, keeping either the first or last duplicate for each set of duplicates,
    according to value.

    Args:
        filters (Dict[str, pd.Series]): All filters. Keys are the names and values are the boolean filters.
        data (Dict[str, pd.DataFrame]): The data. Keys are the classes and values are the DataFrames.
        input_name (str): The input name. We use this as the initial filter.
        output_name (str): The output name. After ANDing with the input filter we save the resulting filter to this name.
        cls (str): The class to drop duplicates in.
        slot (str): The slot in the class to drop duplicates in.
        value (str): If "keep_first" (default) then keep the first row among all duplicates. If "keep_last" then keep the
            last row among all duplicates.
    """
    filt = get_named_filter(input_name, filters)

    df = data[cls]
    if value == "keep_first":
        keep = "first"
    elif value == "keep_last":
        keep = "last"
    else:
        raise ValueError(f"Unrecognized value for drop_duplicates: '{value}'")
    new_filt = ~df[slot][filt].duplicated(keep=keep)
    filt = filt & new_filt

    set_named_filter(filt, output_name, filters)


def do_exclude_equals(
    filters: Dict[str, pd.Series],
    data: Dict[str, pd.DataFrame],
    input_name: str,
    output_name: str,
    cls: str,
    slot: str,
    value: Any,
    **kwargs,
):
    """Exclude operation. Exclude any row where the slot is equal to the value.

    Args:
        filters (Dict[str, pd.Series]): All filters. Keys are the names and values are the boolean filters.
        data (Dict[str, pd.DataFrame]): The data. Keys are the classes and values are the DataFrames.
        input_name (str): The input name. We use this as the initial filter.
        output_name (str): The output name. After ANDing with the input filter we save the resulting filter to this name.
        cls (str): The class to create the new filter based on.
        slot (str): The slot. Any row where this slot is equal to value will be excluded.
        value (Any): The value. Any row where the slot is equal to this value will be excluded.
    """
    filt = get_named_filter(input_name, filters)
    df = data[cls]

    # Convert the value into a list if it isn't already a list
    if not isinstance(value, list):
        value = [value]

    # Calculate the filter that includes any row where the slot is found in value (which is an array).
    # We will negate this filter and AND it with filt.
    if len([v for v in value if pd.isna(v) or v == ""]) > 0:
        # Treat NAs and "" as the same
        cur_filt = pd.isna(df[slot]) | (df[slot] == "")
    else:
        cur_filt = pd.Series([False] * len(filt))
    cur_filt = cur_filt | df[slot].isin(value)

    # Apply the filter
    init_num_rows = filt.sum()
    exclude_rows = cur_filt.sum()
    filt = filt & ~cur_filt
    num_rows = filt.sum()
    logger.debug(
        f"Excluded rows, number of rows changed from {init_num_rows} to {num_rows} (Change: {num_rows - init_num_rows}). Filter matched {exclude_rows} row(s)"
    )

    set_named_filter(filt, output_name, filters)


def do_include_equals(
    filters: Dict[str, pd.Series],
    data: Dict[str, pd.DataFrame],
    input_name: str,
    output_name: str,
    cls: str,
    slot: str,
    value: Any,
    **kwargs,
):
    """Include operation. Include any row where the slot is equal to the value.

    Args:
        filters (Dict[str, pd.Series]): All filters. Keys are the names and values are the boolean filters.
        data (Dict[str, pd.DataFrame]): The data. Keys are the classes and values are the DataFrames.
        input_name (str): The input name. We use this as the initial filter.
        output_name (str): The output name. After ORing with the input filter we save the resulting filter to this name.
        cls (str): The class to create the new filter based on.
        slot (str): The slot. Any row where this slot is equal to value will be included.
        value (Any): The value. Any row where the slot is equal to this value will be included.
    """
    filt = get_named_filter(input_name, filters)
    df = data[cls]

    # Convert the value into a list if it isn't already a list
    if not isinstance(value, list):
        value = [value]

    # Calculate the filter that includes any row where the slot is found in value (which is an array).
    if len([v for v in value if pd.isna(v) or v == ""]) > 0:
        # Treat NAs and "" as the same
        cur_filt = pd.isna(df[slot]) | (df[slot] == "")
    else:
        cur_filt = pd.Series([False] * len(filt))
    cur_filt = cur_filt | df[slot].isin(value)

    # Apply the filter
    init_num_rows = filt.sum()
    exclude_rows = cur_filt.sum()
    filt = filt | cur_filt
    num_rows = filt.sum()
    logger.debug(
        f"Included rows, number of rows changed from {init_num_rows} to {num_rows} (Change: {num_rows - init_num_rows}). Filter matched {exclude_rows} row(s)"
    )

    set_named_filter(filt, output_name, filters)


def do_delete_filter(filters: Dict[str, pd.Series], input_name: str, **kwargs):
    """Delete the filter named input_name. After deleting, the filter will no longer exist
    but can be reacreated by a subsequent row that references the filter by the same name.

    Args:
        filters (Dict[str, pd.Series]): All filters. Keys are the names and values are the boolean filters.
        input_name (str): Name of the filter to delete.
    """
    if input_name in filters:
        del filters[input_name]


def do_apply_filter(
    filters: Dict[str, pd.Series],
    data: Dict[str, pd.DataFrame],
    input_name: str,
    cls: str,
    value: Any,
    **kwargs,
):
    """Apply the filter from the input name to the DataFrame for class cls, and save the resulting DataFrame to the class
    specified in value.

    Args:
        filters (Dict[str, pd.Series]): All filters. Keys are the names and values are the boolean filters.
        data (Dict[str, pd.DataFrame]): The data. Keys are the classes and values are the DataFrames.
        input_name (str): The filter to apply to the input DataFrame.
        cls (str): The class to apply the filter to (in data)
        value (Any): The class to save the filtered DataFrame to (in data).
    """
    # Save the data by applying the current name's filter to the data for class cls
    filt = get_named_filter(input_name, filters)
    init_num_rows = len(data[cls])
    data[value] = data[cls][filt]
    num_rows = len(data[value])
    logger.debug(
        f"Saved data from filter {input_name} to class {cls}, number of rows changed from {init_num_rows} to {num_rows} (Change: {num_rows - init_num_rows})"
    )


def do_copy_filter(
    filters: Dict[str, pd.Series], input_name: str, output_name: str, **kwargs
):
    """Copy a named filter (called input_name) to a new name (output_name). If input_name does not exist
    then a ValueError exception is thrown. If a filter with name output_name already exists it is overwritten.

    Args:
        filters (Dict[str, pd.Series]): All filters. Keys are the names and values are the boolean filters.
        input_name (str): The filter to copy. A filter with this name must already exist.
        output_name (str): The name to copy the filter to. If a filter with this name already exists it is overwritten.

    Raises:
        ValueError: A filter with name input_name does not exist.
    """
    if input_name not in filters:
        raise ValueError(f"No filter with name '{input_name}' found.")
    filt = get_named_filter(input_name, filters)
    set_named_filter(filt, output_name, filters)


def do_delete_class(data: Dict[str, pd.DataFrame], cls: str, **kwargs):
    """Delete the class (DataFrame) named cls.

    Args:
        data (Dict[str, pd.DataFrame]): The data. Keys are the classes and values are the DataFrames.
        cls (str): The class to delete from the data. If no such class exists then nothing is changed.
    """
    if cls in data:
        del data[cls]


def do_copy_class(data: Dict[str, pd.DataFrame], cls: str, value: str, **kwargs):
    """Copy a class (DataFrame) to a new name in the data.

    Args:
        data (Dict[str, pd.DataFrame]): The data. Keys are the classes and values are the DataFrames.
        cls (str): The class to copy.
        value (str): The name to copy the class to. If a DataFrame/class already exists with this name
            it is overwritten.
    """
    data[value] = data[cls].copy()


def do_invert_filter(
    filters: Dict[str, pd.Series],
    input_name: str,
    output_name: str,
    **kwargs,
):
    """Negate/invert a filter.

    Args:
        filters (Dict[str, pd.Series]): All filters. Keys are the names and values are the boolean filters.
        data (Dict[str, pd.DataFrame]): The data. Keys are the classes and values are the DataFrames.
        input_name (str): The input filter to invert.
        output_name (str): The filter name to save the inverted filter to.
        cls (str): The class the filter applies to.
    """
    filt = ~get_named_filter(input_name, filters)
    set_named_filter(filt, output_name, filters)


def do_or_filters(
    filters: Dict[str, pd.Series],
    output_name: str,
    value: Any,
    **kwargs,
):
    """OR all the filters in the value array and save to the output_name.

    Args:
        filters (Dict[str, pd.Series]): All filters. Keys are the names and values are the boolean filters.
        data (Dict[str, pd.DataFrame]): The data. Keys are the classes and values are the DataFrames.
        output_name (str): The name to save the OR'd filter to.
        value (Any): Array of all filter names to OR together.
        cls (str): The class the filter applies to.
    """
    filts = [get_named_filter(str(f), filters) for f in value]
    filt = reduce(lambda x, y: x | y, filts)
    set_named_filter(filt, output_name, filters)


def do_and_filters(
    filters: Dict[str, pd.Series],
    output_name: str,
    value: Any,
    **kwargs,
):
    """AND all the filters in the value array and save to the output_name.

    Args:
        filters (Dict[str, pd.Series]): All filters. Keys are the names and values are the boolean filters.
        data (Dict[str, pd.DataFrame]): The data. Keys are the classes and values are the DataFrames.
        output_name (str): The name to save the AND'd filter to.
        value (Any): Array of all filter names to AND together.
        cls (str): The class the filter applies to.
    """
    filts = [get_named_filter(str(f), filters) for f in value]
    filt = reduce(lambda x, y: x & y, filts)
    set_named_filter(filt, output_name, filters)


def do_create_filter(
    filters: Dict[str, pd.Series],
    data: Dict[str, pd.DataFrame],
    output_name: str,
    cls: str,
    value: Any,
    **kwargs,
):
    """Create a filter named output_name, using the specified boolean value. A boolean value of True means that all rows
    are initially included. A boolean value of False means that none of the rows are initially included.

    Args:
        filters (Dict[str, pd.Series]): All filters. Keys are the names and values are the boolean filters.
        data (Dict[str, pd.DataFrame]): The data. Keys are the classes and values are the DataFrames.
        output_name (str): The name to give the filter.
        cls (str): The class the filter applies to.
        value (Any): Either True or False. If True then the new filter will include all rows, if False then the
            new filter will include none of the rows.
    """
    if not isinstance(value, bool):
        raise ValueError(
            f"value must be a boolean for the create_filter operation. Found '{value}' (of type {type(value)})"
        )
    filters[output_name] = pd.Series([value] * len(data[cls].index))


# Map specifying which function to call for each operation.
FILTER_FUNCS = {
    "and_filters": do_and_filters,
    "apply_filter": do_apply_filter,
    "copy_filter": do_copy_filter,
    "copy_class": do_copy_class,
    "create_filter": do_create_filter,
    "delete_class": do_delete_class,
    "drop_duplicates": do_drop_duplicates,
    "delete_filter": do_delete_filter,
    "exclude_equals": do_exclude_equals,
    "include_equals": do_include_equals,
    "invert_filter": do_invert_filter,
    "or_filters": do_or_filters,
}
