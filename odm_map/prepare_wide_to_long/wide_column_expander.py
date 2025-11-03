"""
# Wide Column Expander

Expand wide column names (with values) to a format that is more usable by LinkML-Map. The target format
of the columns is tableShortName_attribute.group.

For example, the following data with a measure wide column:

| wat_sa_liq_covN1_gch_me_1_value |
|---------------------------------|
| 100                             |
| 120                             |

Would get expanded into:

| mr_compartment.o1 | mr_specimen.o1 | mr_fraction.o1 | mr_measure.o1 | mr_unit.o1 | mr_aggregation.o1 | mr_index.o1 | mr_value.o1 |
|-------------------|----------------|----------------|---------------|------------|-------------------|-------------|-------------|
| wat               | sa             | liq            | covN1         | gch        | me                | 1           | 100         |
| wat               | sa             | liq            | covN1         | gch        | me                | 1           | 120         |

Once we have the resulting expanded DataFrame, we can then use WideColumnMapMaker to generate:

1. A LinkML schema describing the expanded wide format. This schema is specific to the resulting expanded DataFrame, and
will contain all the tableShortName_attribute.group columns as well as tracking columns.
2. A group of LinkML-Map schemas that will map the expanded DataFrame to an ODM long format.

## Usage

```python
# First expand the columns to be in tableShortName_attribute.group format
expander = WideColumnExpander(
    config="wide_column_config.yaml", source_class_name="odm_wide", target_schema="odm_v3.yaml"
)
data_frames = [b for a in data_frames.values() for b in a]
df = expander.expand(data_files=None, data_frames=[df], output_file=None)
data_frames = {"odm_wide": [df]}

# Create the LinkML-Map schemas and the LinkML schema for the prepared data in data_frames.
maker = WideColumnMapMaker(
    config="wide_column_config.yaml", source_class_name="odm_wide", target_schema="odm_v3.yaml"
)
input_data_frame = data_frames[SOURCE_CLASS_NAME][0]
maker.make(data_file=None, data_frame=input_data_frame, output_dir="wide_to_long_mappers")

# The directory "wide_to_long_mappers" contains the LinkML-Map schemas for mapping the expanded
# data indata_frames to long format, and the LinkML schema for the expanded wide format is at
# "wide_to_long_mappers/schema/schema.yaml".
```

"""

from typing import List, Union, Dict, Optional, Generator, Any, Tuple
from pathlib import Path
import pandas as pd
import yaml
from enum import Enum, auto
from tqdm import tqdm
import os

from linkml_runtime import SchemaView

from odm_map.utils.logger import get_logger
from odm_map.utils.general_utils import save_data_frame
from odm_map.utils.extra_and_tracking_slots import (
    load_data_with_source_tracking_columns,
    is_tracking_slot,
)
from odm_map.prepare_wide_to_long.wide_column_utils import (
    ConfigKeys,
    WideColumnValues,
    MeasureTableColumns,
    ProtocolStepsTableColumns,
    AND_VALUE_SEPARATOR,
    GROUP_FLAG_PREFIX,
    group_of_column,
    column_without_flags,
    column_with_flags,
    get_column_flags,
)

logger = get_logger(__name__)


class ColumnType(str, Enum):
    ATTRIBUTE = auto()
    PROTOCOL_STEP_MEASURE = auto()
    PROTOCOL_STEP_METHOD = auto()
    MEASURE = auto()
    TRACKING_SLOT = auto()


# Columns in a DataFrame that have duplicate names will have DUPLICATE_COLUMNS_SEPARATOR
# in the name, followed by an integer. For example, "myColumn.1" has the same name as
# "myColumn" (the ".1" was added when loading the data from disk)
DUPLICATE_COLUMNS_SEPARATOR = "."

# If output_dir is specified when calling WideColumnExpander.expand, then save the
# expanded DataFrame to EXPANDED_OUTPUT_DATA_FILE and the configuration information
# for the data file to EXPANDED_OUTPUT_CONFIG_FILE
EXPANDED_OUTPUT_DATA_FILE = "expanded.csv"
EXPANDED_OUTPUT_CONFIG_FILE = "expanded_config.yaml"


class WideColumnExpander:
    def __init__(
        self,
        config: Union[str, Path, Dict],
        source_class_name: str,
        target_schema: Union[str, Path],
    ):
        self.source_class_name = source_class_name

        # Load the config
        if isinstance(config, (str, Path)):
            with open(config, "r") as f:
                config = yaml.safe_load(f)
        self.config = config

        # Load the LinkML schema
        if target_schema is not None:
            target_schema = SchemaView(target_schema)
        self.target_schema: SchemaView = target_schema

    def get_column_type(self, col: str) -> Optional[ColumnType]:
        """Get the type of wide column of the specified column.

        Args:
            col (str): The column to get the type of.

        Returns:
            Optional[ColumnType]: The ColumnType associated with the column. None if the column type could
                not be determined.
        """
        if is_tracking_slot(col):
            return ColumnType.TRACKING_SLOT

        col_parts = self.get_all_parts(col)
        if col_parts is None:
            return None

        num_parts = len(col_parts)

        if num_parts == 0:
            logger.warning(
                f"Column must have at least one part, the column will be ignored: {col}"
            )
            return None

        if (
            len(col_parts[0]) == 1
            and col_parts[0][0] in self.config[ConfigKeys.TABLES_TO_SHORTNAMES].values()
        ):
            # Column starts with a table short name (eg. "sm_..."). Could be a protocol step (measure/ps_mes or method/ps_met)
            # or an attribute.
            if num_parts <= 1:
                logger.warning(
                    f"Column that starts with a table short name must have at least 2 parts, the column will be ignored: {col}"
                )
                return None

            if self.is_part_equal_at_index(
                col_parts, WideColumnValues.COLUMN_PROTOCOL_STEPS_TAG, 0
            ):
                # Possibly a protocol step. Check for second part equal to met or mes
                if self.is_part_equal_at_index(
                    col_parts, WideColumnValues.COLUMN_MEASURE_TAG, 1
                ):
                    if num_parts != 7:
                        logger.warning(
                            f"Protocol steps measure must have 7, instead {num_parts} parts were found. Column ignored: {col}"
                        )
                        return None
                    return ColumnType.PROTOCOL_STEP_MEASURE
                elif self.is_part_equal_at_index(
                    col_parts, WideColumnValues.COLUMN_METHOD_TAG, 1
                ):
                    if num_parts != 4:
                        logger.warning(
                            f"Protocol steps measure must have 4 parts, instead {num_parts} parts were found. Column ignored: {col}"
                        )
                        return None
                    return ColumnType.PROTOCOL_STEP_METHOD
            if num_parts == 2:
                # This is an attribute column (eg. or_organizationID)
                return ColumnType.ATTRIBUTE
        elif num_parts == 8:
            return ColumnType.MEASURE

        logger.warning(f"Unrecognized column type. Ignoring column: {col}")
        return None

    def is_part_equal_at_index(
        self, col_parts: List[List[str]], equals: Union[str, List[str]], index: int
    ) -> bool:
        """Check if the part at the index, in col_parts, is equal to equals.

        The part at col_parts[index] is equal if it is the same length as equals and if each item in the
        array col_parts[index] is equal to each corresponding item in equals.

        Args:
            col_parts (List[str]): The parts to test, as retrieved with get_all_parts.
            equals (Union[str, List[str]]): The value or list of values to compare to col_parts[index]. Can be
                a string or a list of strings. If a string then it is converted to an array of size 1 with the
                single item been the string.
            index (int): The index of the part in col_parts to test. ie. we test if col_parts[index] == equals.

        Returns:
            bool: True if col_parts[index] == equals. That is, col_parts[index][i] == equals[i] for all i.
        """
        if isinstance(equals, str):
            equals = [equals]

        return col_parts[index] == equals

    def expand(
        self,
        data_files: List[Path],
        data_frames: List[pd.DataFrame],
        output_dir: Optional[Union[str, Path]],
        max_rows: Optional[int] = None,
    ) -> Tuple[pd.DataFrame, Dict]:
        """Expand the files and/or DataFrames to the expanded wide format, so that it's ready to map from
        wide to long format. After expanding the data, WideColumnMapMaker should be run on the returned
        DataFrame.

        Args:
            data_files (List[Path]): A list of data files to load and expand. These data files are concatenated
                together (along with the DataFrames in data_frames). TrackingSlots will also be added.
            data_frames (List[pd.DataFrame]): A list of DataFrames to expand. These DataFrames are concatenated
                to the DataFrames loaded from data_files. TrackingSlots should already have been added to these
                DataFrames.
            output_dir (Optional[Union[str, Path]]): If set then save the expanded DataFrame result as well as
                configuration information to this directory. The file is saved as expanded.csv and the configuration
                as expanded_config.yaml.
            max_rows (Optional[int]): Maximum number of rows to load from all files in data_files. If 0 or None
                then all rows are loaded.

        Returns:
            Tuple[pd.DataFrame, Dict]: The expanded DataFrame and the configuration information about the DataFrame.
                This configuration includes information such as which groups in the expanded DataFrame are explicitly
                specified in the input data file and which are implicitly (and generated at runtime).
        """
        # Load the data to expand
        input_df: List[pd.DataFrame] = []
        if data_frames:
            input_df.extend(data_frames)
        if data_files:
            for f in data_files:
                dfs = load_data_with_source_tracking_columns(
                    {self.source_class_name: [f]}, max_rows=max_rows
                )
                # df = read_data_frame(f, keep_default_na=False, na_values=None)
                cur_dfs = dfs[self.source_class_name]
                input_df.extend(cur_dfs)
        input_df = pd.concat(input_df, ignore_index=True)

        # Expand the DataFrame
        expanded_df = self.expand_single(input_df)
        output_config = self.get_expanded_config()

        # Save expanded data and meta data to disk if required
        if output_dir is not None:
            output_data_file = os.path.join(output_dir, EXPANDED_OUTPUT_DATA_FILE)
            output_config_file = os.path.join(output_dir, EXPANDED_OUTPUT_CONFIG_FILE)
            logger.info(f"Saving expanded data to {output_data_file}")
            save_data_frame(expanded_df, output_data_file, index=False)
            logger.info(f"Saving expanded data configuration to {output_config_file}")
            with open(output_config_file, "w") as f:
                yaml.safe_dump(output_config, f)

        return expanded_df, output_config

    def get_expanded_config(self) -> Dict:
        """Get the configuration information about the expanded DataFrame. This includes information
        such as which groups in the expanded DataFrame are explicitly specified in the input data
        file and which are implicitly (and generated at runtime).

        Returns:
            Dict: The configuration information about the expanded DataFrame.
        """
        return {
            "explicit_groups": self.explicit_groups,
            "implicit_groups": self.implicit_groups,
        }

    def get_all_parts(self, col: str) -> Optional[List[List[str]]]:
        """Get a list of all parts of the specified wide-name column. The parts are separated
        by commas, and can include #_AND and #_OR parts. Each part is a list of strings. Most
        parts will only have one string. #_AND and #_OR parts will contain multiple strings,
        the first being the number (#), the second the boolean operator AND/OR, and the
        remaining is # parts. For example, sm_2_AND_collPer_collNum would be returned as
        the part [['sm'], ['2', 'AND', 'collPer', 'collNum']].

        Args:
            col (str): The wide column name to get all the parts of.

        Returns:
            Optional[List[List[str]]]: A list of lists of strings. Each sub-list is a separate part
                of col. If the sub-list is for a part that has #_AND or #_OR, then the sub-list
                will have 2+# strings, where # is the value preceding _AND or _OR. None is returned
                if there is an error in the column, and the column should be ignored.
        """
        col = column_without_flags(col)
        try:
            parts = list(self.get_next_part(col))
        except Exception:
            return None
        return parts

    def get_next_part(self, col: str) -> Generator[List[str], None, None]:
        """Generator to retrieve all parts of the specified column. See get_all_parts for details.

        Args:
            col (str): The column to get the parts of.

        Raises:
            ValueError: An error was found in the column. For example, if a #_OR or #_AND tag is found
                but the specified number of parts (#) is not found after the tag, or an underscored
                value (eg. "_myvalue_") is missing one of the underscores. In these cases an warning
                is logged and the exception raised with the same warning. The caller does not need
                to re-log the warning.

        Yields:
            Generator[List[str], None, None]: Returns each part in order. Each part is a list of strings.
                Most parts will have one string, but parts with #_AND and #_OR tags have multiple strings
                and will result in the part list ['#', 'AND', 'part1', 'part2', ...].
        """
        col_parts = col.split(WideColumnValues.COLUMN_PART_SEPARATOR)
        idx = 0
        while idx < len(col_parts):
            # Current part is a digit, so it might be in the form #_AND or #_OR, in which case we will
            # return multiple parts
            cur_part = col_parts[idx]
            if cur_part.isdigit():
                num = int(cur_part)
                if idx == len(col_parts) - 1 or num == 0:
                    # The current part is either the last part, or is the number 0, so treat the
                    # current part as a single part
                    idx += 1
                    yield [cur_part]
                else:
                    next_part = col_parts[idx + 1]
                    if next_part in [WideColumnValues.AND_TAG, WideColumnValues.OR_TAG]:
                        # The next part (after the digit), is an AND or OR tag, in which case we need
                        # to return multiple parts. In total, we return the current part, the AND/OR tag, plus
                        # an additional int(cur_part) number of parts
                        try:
                            expected_parts = int(cur_part)
                        except Exception:
                            msg = f"Boolean aggregation ({next_part}) must be preceded by a number, instead '{cur_part}' was found. Ignoring column: {col}"
                            logger.warning(msg)
                            raise ValueError(msg)
                        parts = [cur_part, next_part]

                        # Skip the number and the boolean part (ie. cur_part and next_part)
                        idx += 2

                        # We need to add expected_parts number of parts
                        num_parts_added = 0
                        while idx < len(col_parts):
                            if col_parts[idx] == "":
                                # The next part to add is in the form _partValue_ (ie. with leading and trailing underscore)
                                # This does not contribute to num_parts_added, it just represents the value that the previous part
                                # should take on in the row
                                idx += 1
                                if (
                                    idx + 1 < len(col_parts)
                                    and col_parts[idx + 1] == ""
                                ):
                                    parts.append(f"_{col_parts[idx]}_")
                                    idx += 2
                                else:
                                    msg = f"The underscored value '{col_parts[idx]}' must have both a preceding and trailing underscore. Ignoring column: {col}"
                                    logger.warning(msg)
                                    raise ValueError(msg)
                            else:
                                if num_parts_added >= expected_parts:
                                    break
                                parts.append(col_parts[idx])
                                idx += 1
                                num_parts_added += 1
                        yield parts
                    else:
                        # There is no AND/OR tag, so return the current part as a single part
                        idx += 1
                        yield [cur_part]
            else:
                # The current part is not a digit, so return it as a single part
                idx += 1
                yield [cur_part]

    def get_table_long_name(self, table_short_name: str) -> Optional[str]:
        """Get the long table name of the specified short table name.

        Args:
            table_short_name (str): The short table name to get the long table name of.

        Returns:
            Optional[str]: The long table name of table_short_name, or None if table_short_name
                is unrecognized.
        """
        tables = self.config.get(ConfigKeys.TABLES_TO_SHORTNAMES, {})
        tables = [k for k, v in tables.items() if v == table_short_name]
        return tables[0] if len(tables) > 0 else None

    def get_table_short_name(self, table_long_name: str) -> Optional[str]:
        """Get the short name of the specified table.

        For example, the short name for the "measures" table might be "mr".

        Args:
            table_long_name (str): The table name to get the short name of.

        Returns:
            Optional[str]: The short name of the table, or None if the table is not recognized.
        """
        return self.config.get(ConfigKeys.TABLES_TO_SHORTNAMES, {}).get(
            table_long_name, None
        )

    def get_resolved_single_part_at_index(
        self, col_parts: List[List[str]], index: int, row: pd.Series
    ) -> Any:
        """Get the value of the part at the index of the list of column parts (as returned
        by get_all_parts). If the part at the index has a list of values, then only the
        first value is returned.

        This function will also resolve to other values if required. If it is NR, then
        None is retrieved. If it is a "see other header" part, such as hCo, hUn, hAg, etc.,
        then it will retrieve the value at the header in the row.

        Args:
            col_parts (List[List[str]]): The list of parts, as retrieved from get_all_parts.
            index (int): The index in col_parts to get the value of.
            row (pd.Series): The input row, where we can retrieve values from if the
                resulting part refers to another header (eg. if the part is hCo, hUn, hAg, etc.)

        Returns:
            Any: The single value at the index in the column parts. This might be the string
                value in the column part, or another value retrieved from the row.
        """
        val = col_parts[index][0]
        if val == WideColumnValues.NR_TAG:
            return None
        see_column = self.config.get(ConfigKeys.SEE_HEADERS, {}).get(val, None)
        if see_column:
            return row.get(see_column, None)
        return val

    def get_and_values(self, val: Any, num_values: int) -> List[Any]:
        """From the specified value (cast to a string), split the value up into num_values values
        using the separator AND_VALUE_SEPARATOR (a period). For example, 24.12 will be split
        into two values and returned as ["24", "12"].

        Args:
            val (Any): The value to split. If None then a list of size num_values, consisting only
                of None, is returned.
            num_values (int): The number of values to split val into.

        Returns:
            List[Any]: The value val split into num_values values. If val is None then a list of size
                num_values consisting only of None is returned. If fewer then num_values is available,
                then the returned list is expanded with None values so that the list is of size num_values.
                If more than num_values are available, only the first num_values splits are returned.
        """
        if val is None:
            return [None] * num_values

        if num_values == 1:
            return [val]
        elif num_values == 0:
            return []

        values = str(val).split(AND_VALUE_SEPARATOR)
        if len(values) < num_values:
            logger.warning(
                f"Tried to parse AND value into {num_values} values, but {len(values)} value{'s were' if len(values) != 1 else ' was'} found. Using 'None' for all missing values. Original value is: '{val}'."
            )
            values = values + [None] * (num_values - len(values))

        return values[:num_values]

    def expand_column_type_attribute(
        self,
        col: str,
        row: pd.Series,
        column_flags: Optional[List[str]],
        column_group: Optional[str],
        always_use_group: bool,
    ) -> bool:
        """Expand the specified column, treating it as an attribute. Attributes are in the form tableShortName_attribute or
        tableShortName_#_AND_a_b_c_...

        Args:
            col (str): The column name to expand.
            row (pd.Series): The row of input data that we are expanding. It contains a column with name col.
            column_flags (Optional[List[str]]): If set then add all of these flags (eg. "l123") to all of the columns being added.
                This should NOT include a group flag, which is specified by the column_group parameter.
            column_group (Optional[str]): The group that the expansion belongs to. A group is assigned to each expanded
                column, and allows us to ensure all the resulting columns, after expanding, can be grouped together.
                If it is not None, then it is added to the end of the expanded column(s), eg.
                sm_sampleID:1 (1 is the group).
            always_use_group (bool): If True then we should always assign the specified column_group to the data. If False
                then this function may or may not assign the specified column_group, depending on how processing occurs.
                This is usually set to True if the original data had the column group explicitly specified, rather than
                the group name being generated at runtime due to it not being present in the original column name.

        Returns:
            bool: True if the column is in a good format and we should continue expanding the column for later rows.
                False if there is an error in the column (eg. too many parts, unrecognized parts, etc.) and it should
                no longer be expanded for later rows. Note that if the column is in the correct format, but something
                is wrong with a value in the column for the current row, then True should still be returned, since
                later rows might have valid values and we would want to continue processing those later values.
        """
        value = row[col]

        col_parts = self.get_all_parts(col)
        if col_parts is None:
            return False

        # First part must be of size 1 (ie. a single table short name)
        if len(col_parts[0]) != 1:
            logger.warning(
                f"An attribute column must have exactly one value for the first part, instead the values {col_parts[0]} were found. Ignoring column: {col}"
            )
            return False

        use_column_group = always_use_group
        table_short_name = col_parts[0][0]
        if len(col_parts[1]) == 1:
            # The column is in the format tableShortName_column[_#]
            table_long_name = self.get_table_long_name(table_short_name)
            if not table_long_name:
                logger.warning(
                    f"Attribute column {col} has an unknown table short name: {table_short_name}"
                )
                return False

            # Make sure value is an actual slot for the table in the target schema
            try:
                slot_defn = self.target_schema.induced_slot(
                    col_parts[1][0], table_long_name
                )
            except Exception:
                slot_defn = None
            if not slot_defn:
                logger.warning(
                    f"The slot {col_parts[1][0]} does not exist in the table {table_long_name}. Ignoring column: {col}"
                )

            # Expand the attribute
            self.update_current_expanded_rows(
                {
                    f"{table_short_name}{WideColumnValues.COLUMN_PART_SEPARATOR}{col_parts[1][0]}": value,
                },
                row_index=None,
                column_flags=column_flags,
                column_group=column_group if always_use_group else None,
            )

            return True
        else:
            # The column has an AND tag (ie. tableShortName_#_AND_a_b_c[_#])
            bool_part = col_parts[1][1]
            use_column_group = True

            # For attribute columns, only the AND_TAG is allowed
            if bool_part != WideColumnValues.AND_TAG:
                logger.warning(
                    f"Boolean in attribute column must be '{WideColumnValues.AND_TAG}'. Ignoring column: {col}"
                )
                return False

            # Get the column names which are in the parts, and the underscored values which are in the parts (eg. _myvalue_)
            col_names = [c for c in col_parts[1][2:] if not c.startswith("_")]
            col_values = [c for c in col_parts[1][2:] if c not in col_names]
            # Get the dot-separated values in the value
            values = self.get_and_values(
                value, num_values=len(col_names) - len(col_values)
            )

            # Get all the columns and the values associated with the columns, assign these to new_row
            new_row = {}
            col_info = col_parts[1][2:]
            values_idx = 0
            for idx in range(len(col_info)):
                if col_info[idx].startswith("_"):
                    continue
                cur_col = f"{table_short_name}{WideColumnValues.COLUMN_PART_SEPARATOR}{col_info[idx]}"
                if idx + 1 < len(col_info) and col_info[idx + 1].startswith("_"):
                    # The next value (at idx+1) is an underscored value, so use it for the current column
                    new_row[cur_col] = col_info[idx + 1].strip("_")
                else:
                    # There is no underscored value, so get the value from values
                    new_row[cur_col] = values[values_idx]
                    values_idx += 1

            self.update_current_expanded_rows(
                new_row,
                row_index=None,
                column_flags=column_flags,
                column_group=column_group if use_column_group else None,
            )

            return True

    def expand_column_type_protocol_step_measure(
        self,
        col: str,
        row: pd.Series,
        column_flags: Optional[List[str]],
        column_group: Optional[str],
        always_use_group: bool,
    ) -> bool:
        """Expand the specified column, treating it as a protocolSteps measure. protocolSteps measures are in the format
        tableShortName_partTypeShortName_measure_unit_aggregation_index_attribute. It results in multiple output
        columns, each containing the same column index (to help keep them grouped together).

        Args:
            col (str): The column name to expand.
            row (pd.Series): The row of input data that we are expanding. It contains a column with name col.
            column_flags (Optional[List[str]]): If set then add all of these flags (eg. "l123") to all of the columns being added.
                This should NOT include a group flag, which is specified by the column_group parameter.
            column_group (Optional[str]): The group that the expansion belongs to. A group is assigned to each expanded
                column, and allows us to ensure all the resulting columns, after expanding, can be grouped together.
                If it is not None, then it is added to the end of the expanded column(s), eg.
                sm_sampleID:1 (1 is the group).
            always_use_group (bool): If True then we should always assign the specified column_group to the data. If False
                then this function may or may not assign the specified column_group, depending on how processing occurs.
                This is usually set to True if the original data had the column group explicitly specified, rather than
                the group name being generated at runtime due to it not being present in the original column name.

        Returns:
            bool: True if the column is in a good format and we should continue expanding the column for later rows.
                False if there is an error in the column (eg. too many parts, unrecognized parts, etc.) and it should
                no longer be expanded for later rows. Note that if the column is in the correct format, but something
                is wrong with a value in the column for the current row, then True should still be returned, since
                later rows might have valid values and we would want to continue processing those later values.
        """
        value = row[col]

        col_parts = self.get_all_parts(col)
        if col_parts is None:
            return False

        # First part must be of size 1 (ie. a single table short name)
        if len(col_parts[0]) != 1:
            logger.warning(
                f"Protocol step measure column must have exactly one value for the first part, instead the values {col_parts[0]} were found. Ignoring column: {col}"
            )
            return False

        table_short_name = col_parts[0][0]
        attribute = col_parts[6][0]
        ps_unit = self.get_resolved_single_part_at_index(col_parts, 3, row)
        ps_aggregation = self.get_resolved_single_part_at_index(col_parts, 4, row)
        ps_index = self.get_resolved_single_part_at_index(col_parts, 5, row)

        # Make sure the table short name is for protocolSteps
        if table_short_name != WideColumnValues.COLUMN_PROTOCOL_STEPS_TAG:
            logger.warning(
                f"Protocol steps measure column must start with '{WideColumnValues.COLUMN_PROTOCOL_STEPS_TAG}'. Ignoring column: {col}"
            )
            return False

        # Make sure the second part is for measures
        if not self.is_part_equal_at_index(
            col_parts, WideColumnValues.COLUMN_MEASURE_TAG, 1
        ):
            logger.warning(
                f"Protocol steps measure column must have a second part equal to '{WideColumnValues.COLUMN_MEASURE_TAG}', instead '{col_parts[1][0]}' was found. Ignoring column: {col}"
            )
            return False

        if len(col_parts[2]) > 1:
            # The third part is a boolean part
            bool_part = col_parts[2][1]

            # Only OR tags are allowed for protocolSteps measures
            if bool_part != WideColumnValues.OR_TAG:
                logger.warning(
                    f"Protocol steps measure column with a boolean third part must be '{WideColumnValues.OR_TAG}'. Ignoring column: {col}"
                )
                return False
            if not col_parts[2][0].isdigit():
                logger.warning(
                    f"An OR aggregation requires a preceding integer value, instead '{col_parts[2][0]}' was found. Ignoring column: {col}"
                )
                return False

            num_candidate_enums = int(col_parts[2][0])

            if num_candidate_enums != len(col_parts[2]) - 2:
                logger.warning(
                    f"Specified OR aggregation must have {num_candidate_enums} parts, instead {len(col_parts[2] - 2)} were given. Ignoring column: {col}"
                )
                return False

            # Get the measure to use, out of the candidate_enums
            candidate_enums = col_parts[2][2:]
            ps_measure = self.select_matching_enum(value, candidate_enums)
        elif len(col_parts[2]) == 1:
            # Get the measure
            ps_measure = self.get_resolved_single_part_at_index(col_parts, 2, row)
        else:
            logger.warning(f"Measure part of protocol steps column is missing: {col}")
            return False

        self.update_current_expanded_rows(
            {
                ProtocolStepsTableColumns.MEASURE: ps_measure,
                ProtocolStepsTableColumns.UNIT: ps_unit,
                ProtocolStepsTableColumns.AGGREGATION: ps_aggregation,
                ProtocolStepsTableColumns.INDEX: ps_index,
                f"{table_short_name}{WideColumnValues.COLUMN_PART_SEPARATOR}{attribute}": value,
            },
            row_index=None,
            column_flags=column_flags,
            column_group=column_group,
        )

        return True

    def expand_column_type_protocol_step_method(
        self,
        col: str,
        row: pd.Series,
        column_flags: Optional[List[str]],
        column_group: Optional[str],
        always_use_group: bool,
    ) -> bool:
        """Expand the specified column, treating it as a protocolSteps method. protocolSteps methods are in the format
        tableShortName_partTypeShortName_method_attribute. It results in multiple output columns, each containing the
        same column index (to help keep them grouped together).

        Args:
            col (str): The column name to expand.
            row (pd.Series): The row of input data that we are expanding. It contains a column with name col.
            column_flags (Optional[List[str]]): If set then add all of these flags (eg. "l123") to all of the columns being added.
                This should NOT include a group flag, which is specified by the column_group parameter.
            column_group (Optional[str]): The group that the expansion belongs to. A group is assigned to each expanded
                column, and allows us to ensure all the resulting columns, after expanding, can be grouped together.
                If it is not None, then it is added to the end of the expanded column(s), eg.
                sm_sampleID:1 (1 is the group).
            always_use_group (bool): If True then we should always assign the specified column_group to the data. If False
                then this function may or may not assign the specified column_group, depending on how processing occurs.
                This is usually set to True if the original data had the column group explicitly specified, rather than
                the group name being generated at runtime due to it not being present in the original column name.

        Returns:
            bool: True if the column is in a good format and we should continue expanding the column for later rows.
                False if there is an error in the column (eg. too many parts, unrecognized parts, etc.) and it should
                no longer be expanded for later rows. Note that if the column is in the correct format, but something
                is wrong with a value in the column for the current row, then True should still be returned, since
                later rows might have valid values and we would want to continue processing those later values.
        """
        value = row[col]

        col_parts = self.get_all_parts(col)
        if col_parts is None:
            return False

        # First part must be of size 1 (ie. a single table short name)
        if len(col_parts[0]) != 1:
            logger.warning(
                f"Protocol step method column must have exactly one value for the first part, instead the values {col_parts[0]} were found. Ignoring column: {col}"
            )
            return False

        table_short_name = col_parts[0][0]
        attribute = col_parts[3][0]

        # Make sure the table short name is for protocolSteps
        if table_short_name != WideColumnValues.COLUMN_PROTOCOL_STEPS_TAG:
            logger.warning(
                f"Protocol steps method column must start with '{WideColumnValues.COLUMN_PROTOCOL_STEPS_TAG}'. Ignoring column: {col}"
            )
            return False

        # Make sure the second part is for methods
        if not self.is_part_equal_at_index(
            col_parts, WideColumnValues.COLUMN_METHOD_TAG, 1
        ):
            logger.warning(
                f"Protocol steps method column must have a second part equal to '{WideColumnValues.COLUMN_MEASURE_TAG}', instead '{col_parts[1][0]}' was found. Ignoring column: {col}"
            )
            return False

        if len(col_parts[2]) > 1:
            bool_part = col_parts[2][1]

            # Only OR tags are allowed for protocolSteps methods
            if bool_part != WideColumnValues.OR_TAG:
                logger.warning(
                    f"Protocol steps method column with a boolean third part must be '{WideColumnValues.OR_TAG}'. Ignoring column: {col}"
                )
                return False

            num_candidate_enums = int(col_parts[2][0])

            if num_candidate_enums != len(col_parts[2]) - 2:
                logger.warning(
                    f"Specified OR aggregation must have {num_candidate_enums} parts, instead {len(col_parts[2] - 2)} were given. Ignoring column: {col}"
                )
                return False

            # Get the method to use, out of the candidate_enums
            candidate_enums = col_parts[2][2:]
            ps_method = self.select_matching_enum(value, candidate_enums)
        elif len(col_parts[2]) == 1:
            # Third part has only one aprt, get the method
            ps_method = self.get_resolved_single_part_at_index(col_parts, 2, row)
        else:
            logger.warning(f"Method part of protocol steps column is missing: {col}")
            return False

        self.update_current_expanded_rows(
            {
                ProtocolStepsTableColumns.METHOD: ps_method,
                f"{table_short_name}{WideColumnValues.COLUMN_PART_SEPARATOR}{attribute}": value,
            },
            row_index=None,
            column_flags=column_flags,
            column_group=column_group,
        )

        return True

    # def get_aggregate_part(self, col_parts: List[List[str]]) -> Tuple[List[str], List[str]]:
    #     # Return: bool_part, list of columns, list of values in column
    #     bool_part = None

    #     if len(col_parts[0]) == 1 and col_parts[0][0].isdigit():
    #         num_aggregate_parts = int(col_parts[0][0])
    #     else:
    #         num_aggregate_parts = 0

    #     if num_aggregate_parts > 0:
    #         if len(col_parts)

    #     if self.is_part_equal_at_index(col_parts, WideColumnValues.OR_TAG, 1):
    #         bool_part = WideColumnValues.OR_TAG
    #     elif self.is_part_equal_at_index(col_parts, WideColumnValues.AND_TAG, 1):
    #         bool_part = WideColumnValues.AND_TAG

    #     if bool_part == WideColumnValues.OR_TAG:
    #         pass
    #     elif bool_part == WideColumnValues.AND_TAG:
    #         pass
    #     else:

    def expand_column_type_measure(
        self,
        col: str,
        row: pd.Series,
        column_flags: Optional[List[str]],
        column_group: Optional[str],
        always_use_group: bool,
    ) -> bool:
        """Expand the specified column, treating it as a measure. Measures are in the format
        compartment_specimen_fraction_measure_unit_aggregation_index_attribute. It results in multiple output columns,
        each containing the same column index (to help keep them grouped together).

        Args:
            col (str): The column name to expand.
            row (pd.Series): The row of input data that we are expanding. It contains a column with name col.
            column_flags (Optional[List[str]]): If set then add all of these flags (eg. "l123") to all of the columns being added.
                This should NOT include a group flag, which is specified by the column_group parameter.
            column_group (Optional[str]): The group that the expansion belongs to. A group is assigned to each expanded
                column, and allows us to ensure all the resulting columns, after expanding, can be grouped together.
                If it is not None, then it is added to the end of the expanded column(s), eg.
                sm_sampleID:1 (1 is the group).
            always_use_group (bool): If True then we should always assign the specified column_group to the data. If False
                then this function may or may not assign the specified column_group, depending on how processing occurs.
                This is usually set to True if the original data had the column group explicitly specified, rather than
                the group name being generated at runtime due to it not being present in the original column name.

        Returns:
            bool: True if the column is in a good format and we should continue expanding the column for later rows.
                False if there is an error in the column (eg. too many parts, unrecognized parts, etc.) and it should
                no longer be expanded for later rows. Note that if the column is in the correct format, but something
                is wrong with a value in the column for the current row, then True should still be returned, since
                later rows might have valid values and we would want to continue processing those later values.
        """
        value = row[col]

        col_parts = self.get_all_parts(col)
        if col_parts is None:
            return False

        mr_compartment = self.get_resolved_single_part_at_index(col_parts, 0, row)
        mr_specimen = self.get_resolved_single_part_at_index(col_parts, 1, row)
        mr_fraction = self.get_resolved_single_part_at_index(col_parts, 2, row)
        mr_measure = None
        mr_unit = self.get_resolved_single_part_at_index(col_parts, 4, row)
        mr_aggregation = self.get_resolved_single_part_at_index(col_parts, 5, row)
        mr_index = self.get_resolved_single_part_at_index(col_parts, 6, row)
        attribute = self.get_resolved_single_part_at_index(col_parts, 7, row)
        table_short_name = self.get_table_short_name("measures")

        if len(col_parts[3]) == 1:
            # The measure part has a single value, so get the value
            mr_measure = self.get_resolved_single_part_at_index(col_parts, 3, row)
        else:
            # The measure part has multiple values, so it is a boolean part.
            bool_part = col_parts[3][1]

            # For measure columns, only the OR_TAG is allowed
            if bool_part != WideColumnValues.OR_TAG:
                logger.warning(
                    f"Measure column with a boolean fourth part must be '{WideColumnValues.OR_TAG}'. Ignoring column: {col}"
                )
                return False

            candidate_enums = col_parts[3][2:]
            mr_measure = self.select_matching_enum(value, candidate_enums)

        self.update_current_expanded_rows(
            {
                MeasureTableColumns.COMPARTMENT: mr_compartment,
                MeasureTableColumns.SPECIMEN: mr_specimen,
                MeasureTableColumns.FRACTION: mr_fraction,
                MeasureTableColumns.MEASURE: mr_measure,
                MeasureTableColumns.UNIT: mr_unit,
                MeasureTableColumns.AGGREGATION: mr_aggregation,
                MeasureTableColumns.INDEX: mr_index,
                f"{table_short_name}{WideColumnValues.COLUMN_PART_SEPARATOR}{attribute}": value,
            },
            row_index=None,
            column_flags=column_flags,
            column_group=column_group,
        )

        return True

    def expand_column_type_tracking(
        self,
        col: str,
        row: pd.Series,
    ) -> bool:
        """Expand the specified column, treating it as a tracking column. Tracking columns provide information about which
        file and row number that the current row was loaded from. Tracking columns get expanded by keeping the same column
        name and copying the value over unchanged.

        Args:
            col (str): The column name to expand.
            row (pd.Series): The row of input data that we are expanding. It contains a column with name col.

        Returns:
            bool: True if the column is in a good format and we should continue expanding the column for later rows.
                False if there is an error in the column (eg. too many parts, unrecognized parts, etc.) and it should
                no longer be expanded for later rows. Note that if the column is in the correct format, but something
                is wrong with a value in the column for the current row, then True should still be returned, since
                later rows might have valid values and we would want to continue processing those later values.
        """
        for row_index in self.current_expanded_rows.keys():
            self.update_current_expanded_rows(
                {col: row[col]},
                row_index=row_index,
                column_flags=None,
                column_group=None,
            )
        return True

    def select_matching_enum(
        self, val: Any, candidate_enums: List[str]
    ) -> Optional[str]:
        """Given the specified value, find the enumeration in candidate_enums that contains the value.

        Args:
            val (Any): The enumeration value to find the enumeration for.
            candidate_enums (List[str]): A list of enumeration names to test. These enumerations must be
                present in the target schema as passed to the constructor.

        Returns:
            Optional[str]: The enumeration in candidate_enums that val belongs to. If val does not belong
                to any of the enumerations then None is returned.
        """
        for check_enum in candidate_enums:
            candidate_set = self.config.get(ConfigKeys.PARTID_TO_MMASET, {}).get(
                check_enum, None
            )
            if candidate_set is None:
                continue
            enum_defn = self.target_schema.get_enum(candidate_set)
            if val in enum_defn.permissible_values:
                return check_enum
        return None

    def update_current_expanded_rows(
        self,
        data: Dict[str, Any],
        row_index: Optional[int],
        column_flags: Optional[List[str]] = None,
        column_group: Optional[int] = None,
    ):
        """Update the expanded row that we're currently working on with new values.

        This function should be called multiple times when expanding a row after new_current_expanded_rows is called.

        Args:
            data (Dict[str, Any]): The columns (keys) and values (values) to update the current row with. If column_group is
                not None, then the column_group is appended to the column names.
            source_column (str): The original wide-column name that generated this data. We use this to copy over the column
                flags to the new target columns in data.
            row_index (Optional[int]): The output expanded row index to update. When expanding a given input row, we might have
                multiple output expanded rows (ie. a 1-to-many relationship). The row_index specifies which of these output rows
                to update. When there is a 1-to-1 relationship from input to output rows, then row_index should be None.
            column_flags (Optional[List[str]]): If set then add all of these flags (eg. "l123") to all of the columns being added.
                This should NOT include a group flag, which is specified by the column_group parameter.
            column_group (Optional[str]): The group that the expansion belongs to. This meant for
                grouping all the columns together, with columns that have the same group value belonging to the same group. For example,
                a measure might have a compartment, unit, aggregation, etc. all specified in different columns. By adding a
                group to these columns we know which of the columns belong to the same measure. Columns with no group
                (ie. column_group is None) usually represent global columns that apply to all groups. Defaults to None.
        """
        if row_index not in self.current_expanded_rows:
            self.current_expanded_rows[row_index] = {}
        current_row = self.current_expanded_rows[row_index]

        # Get all the flags to add to the columns.
        flags = column_group
        if pd.isna(flags):
            flags = []
        if isinstance(flags, str):
            flags = [flags]
        if column_flags:
            flags = flags + column_flags

        # Add all the columns (along with the flags) to the current row
        for key, val in data.items():
            key = column_with_flags(key, flags)
            if key in current_row:
                logger.warning(
                    f"The column {key} has already been populated in the expanded row for row index {row_index} with value '{current_row[key]}'. This value will be overwritten with the value '{val}'."
                )
            current_row[key] = val

    def new_current_expanded_rows(self):
        """Begin expanding a new input row by initializing the output row(s). This should be called before expanding a new row."""
        self.current_expanded_rows: Dict[str, Dict[str, Any]] = {}
        self.current_expanded_rows[None] = {}

    def save_current_expanded_rows(self):
        """Once an input row is finished expanding, save the expanded row internally so we can begin expanding the next input row.
        The function new_current_expanded_rows should be called after this function to initialize expanding the next row.
        """
        # Sort the current rows by the row index (the row index is the key of self.current_expanded_rows)
        self.current_expanded_rows = dict(
            sorted(
                self.current_expanded_rows.items(),
                key=lambda k: -1 if k[0] is None else k[0],
            )
        )
        current_rows = list(self.current_expanded_rows.values())
        self.all_expanded_rows.extend(current_rows)

    def get_duplicate_columns(self, df: pd.DataFrame) -> Dict[str, List[str]]:
        """Get a dictionary containing lists of columns that have duplicate names. If a column
        name ends with .# (dot followed by an integer), then the base name is the column
        name without the trailing .#. If after removing the suffix it has the same base name
        as any other column then those columns are considered duplicates.

        Args:
            df (pd.DataFrame): The DataFrame to get the duplicate columns of.

        Returns:
            Dict[str, List[str]]: Dictionary where the key is the base name of a column,
                and the values are lists of column names that have that base name. An example
                is shown below:
                    {
                        "myColumn": ["myColumn", "myColumn.1", "myColumn.2"],
                        "otherColumn": ["otherColumn.1"],
                    }
        """
        duplicate_columns = {}

        # Find all duplicate columns. The key of duplicate_columns is the main column without
        # an index (eg. "myColumn"), and the values are lists of column names that are duplicates
        # of that column
        for col in df.columns:
            # Get the base name of the column name. The base name has the trailing .# removed, if
            # there is one.
            base_col = col
            if DUPLICATE_COLUMNS_SEPARATOR not in col:
                base_col = col
            else:
                prefix, suffix = col.rsplit(DUPLICATE_COLUMNS_SEPARATOR, maxsplit=1)
                if suffix.isdigit():
                    base_col = prefix

            # Add the base column name as a key, and the actual full column name to the list.
            if base_col not in duplicate_columns:
                duplicate_columns[base_col] = []
            duplicate_columns[base_col].append(col)

        # Only keep the keys where the lists have at least one column name that isn't equal
        # to the base column name (ie. the key)
        duplicate_columns = {
            k: v
            for k, v in duplicate_columns.items()
            if len(v) - (1 if k in v else 0) >= 1
        }

        return duplicate_columns

    def merge_duplicate_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Merge all columns in the DataFrame that have duplicate names. Duplicate column names
        end with a dot followed by an integer. For example, the column "myColumn.1" has the same
        name as the column "myColumn". The ".1" was added when loading the data from disk, to make
        sure the resulting DataFrame has unique column names.

        Merging the columns means taking the first non-empty value among the duplicates, and
        then dropping the duplicate columns.

        Args:
            df (pd.DataFrame): The DataFrame to merge duplicate columns. If there are duplicate
                columns then a copy is made, modified, and returned, with the original DataFrame
                left unchanged. If no duplicates are found, then the same DataFrame is returned
                unchanged.

        Returns:
            pd.DataFrame: The DataFrame with duplicate columns merged.
        """
        duplicate_columns = self.get_duplicate_columns(df)

        if duplicate_columns:

            def _get_non_null(s: pd.Series) -> Any:
                """Get the first non-empty value in the series, or None if they are all empty.
                If there are more than one non-empty values, then the first one is returned and
                a warning is logged.

                Args:
                    s (pd.Series): The series to get the first non-empty value from.

                Returns:
                    Any: The first non-empty value in s, or None if all values are empty.
                """
                non_na = s[(~pd.isna(s)) & (s != "")]
                if len(non_na) > 1:
                    logger.warning(
                        f"For row {s.name + 1}, found more than one value when merging duplicate columns {list(non_na.index)}, values are {list(non_na)}, using first value '{non_na.iloc[0]}'"
                    )
                if len(non_na) == 0:
                    return None
                return non_na.iloc[0]

            for base_column, cur_duplicates in duplicate_columns.items():
                # Once we have remove the duplicate columns and set/add the base column
                # in the DataFrame, we will move the base column to be in order so that
                # it's at the same index that the first duplicate column was at.
                first_index = min([list(df.columns).index(c) for c in cur_duplicates])

                df[base_column] = df[cur_duplicates].apply(_get_non_null, axis=1)
                if base_column in cur_duplicates:
                    cur_duplicates.remove(base_column)
                df = df.drop(cur_duplicates, axis=1)

                # Move the base column to at the index first_index
                columns = list(df.columns)
                columns.remove(base_column)
                columns.insert(first_index, base_column)
                df = df[columns]

        return df

    def get_first_group_number(self, df: pd.DataFrame) -> int:
        """Based on the column names of the specified DataFrames, find the first integer group
        number to use for generating group names of the form "{WIDE_GROUP_PREFIX}{n}".

        Any number greater than or equal to the returned value will result in a group name that
        will not interfere with already (explicitly) specified group names in the DataFrame.

        Args:
            df (pd.DataFrame): The DataFrame to get the first group number to use.

        Returns:
            int: The first group number to use when generating group names for the DataFrame.
                Using this group number, or any number greater than it, will result in group
                names that are not already used in the DataFrame.
        """
        columns = [group_of_column(c, remove_flag_prefix=True) for c in df.columns]
        columns = [int(c) for c in columns if c and c.isdigit()]
        if len(columns) == 0:
            return 0
        return max(columns) + 1

    def expand_single(self, df: pd.DataFrame) -> pd.DataFrame:
        """Expand a single input/DataFrame.

        Args:
            df (pd.DataFrame): The DataFrame to expand

        Returns:
            pd.DataFrame: The expanded DataFrame. The input DataFrame (df) is left unchanged.
        """
        self.skip_columns = []

        self.all_expanded_rows = []

        df = self.merge_duplicate_columns(df)
        first_group_number = self.get_first_group_number(df)

        # Explicit groups are those that are explicitly specified in the original data in the column names (eg. qr_qualityFlags.o123)
        self.explicit_groups = []
        # Implicit groups are those that are generated in code because the original data does not have a group in the column name (eg. qr_qualityFlags)
        self.implicit_groups = []

        # For all columns, generate the some meta data for the column that is used for expanding the columns
        column_data = []
        for column_index, col in enumerate(df.columns):
            # Get the type of the column
            column_type = self.get_column_type(col)
            if column_type is None:
                continue

            # Get or generate the column group
            column_group = group_of_column(col)
            if column_group is None:
                # Column group not available, generate a new one
                explicit_group = False
                column_group = f"{GROUP_FLAG_PREFIX}{column_index + first_group_number}"
            else:
                explicit_group = True

            # Get all flags of the column (including the group flag)
            column_flags = get_column_flags(col, ignore_prefixes=GROUP_FLAG_PREFIX)

            if explicit_group:
                self.explicit_groups.append(column_group)
            else:
                self.implicit_groups.append(column_group)

            cur_data = {
                "column": col,
                "column_index": column_index,
                "column_group": column_group,
                "explicit_group": explicit_group,
                "column_type": column_type,
                "column_flags": column_flags,
            }
            column_data.append(cur_data)

        # Iterate over all rows and all columns
        for row_idx, row in tqdm(df.iterrows(), total=len(df.index)):
            self.new_current_expanded_rows()
            # We iterate over a copy of column_data because we might be modifying column_data
            # in the for loop
            column_data_copy = column_data.copy()
            for cur_data in column_data_copy:
                col = cur_data["column"]
                column_index = cur_data["column_index"]
                column_group = cur_data["column_group"]
                column_flags = cur_data["column_flags"]
                explicit_group = cur_data["explicit_group"]
                column_type = cur_data["column_type"]
                always_use_group = explicit_group

                if column_type == ColumnType.ATTRIBUTE:
                    skip_column = not self.expand_column_type_attribute(
                        col,
                        row,
                        column_flags=column_flags,
                        column_group=column_group,
                        always_use_group=always_use_group,
                    )
                elif column_type == ColumnType.PROTOCOL_STEP_MEASURE:
                    skip_column = not self.expand_column_type_protocol_step_measure(
                        col,
                        row,
                        column_flags=column_flags,
                        column_group=column_group,
                        always_use_group=always_use_group,
                    )
                elif column_type == ColumnType.PROTOCOL_STEP_METHOD:
                    skip_column = not self.expand_column_type_protocol_step_method(
                        col,
                        row,
                        column_flags=column_flags,
                        column_group=column_group,
                        always_use_group=always_use_group,
                    )
                elif column_type == ColumnType.MEASURE:
                    skip_column = not self.expand_column_type_measure(
                        col,
                        row,
                        column_flags=column_flags,
                        column_group=column_group,
                        always_use_group=always_use_group,
                    )
                else:
                    skip_column = True

                if skip_column:
                    if row_idx > 0:
                        raise RuntimeError(
                            f"The column {col} was marked to be skipped but should only be marked when processing the first row, instead it is being marked on row {row_idx}."
                        )
                    column_data.remove(cur_data)

            # Copy over the tracking slots. We do this last to make sure all row indices
            # for the current expanded rows get populated with the tracking info.
            for col in [c for c in df.columns if is_tracking_slot(c)]:
                self.expand_column_type_tracking(col, row)

            self.save_current_expanded_rows()

        expanded_df = pd.DataFrame(self.all_expanded_rows)
        return expanded_df
