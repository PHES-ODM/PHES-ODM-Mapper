"""
Manage data for a class, including creating lookup tables for faster access to rows within the table (for certain slots).

## Usage

```python
# Create data for class 'measures', load data from 'measures.csv', create lookup tables for faster access
# for slots in lookup_slots, initialize for generating IDs for slots in generated_slots, and set the primary
# key for the data to "measureRepID".
data = GeneratorData(
    class_name="measures",
    input_data=["measures.csv"],
    primary_key="measureRepID",
    generated_slots=["measureRepID", "siteID", "organizationID"],
)
data.init_lookup_table(["measureRepID", "(__source_file_and_row__)"])

# ... process the data, generate IDs, etc ...

data_frames, *_ = data.finalize_data(keep_extra_and_tracking_columns=False, keep_debug_columns=False, remove_duplicates=True)
```
"""

import os
import pandas as pd
import numpy as np
from typing import Union, List, Any, Optional, Tuple, Dict
from collections.abc import Iterable
from pathlib import Path

from odm_map.id_generator.row_index_lookup import RowIndexLookup
from odm_map.id_generator.id_value import IDValue
from odm_map.id_generator.id_na import EMPTY_OBJ, isna

from odm_map.utils.logger import get_logger
from odm_map.utils.extra_and_tracking_slots import (
    is_extra_or_tracking_slot,
    is_tracking_slot,
    is_extra_slot,
)
from odm_map.utils.general_utils import (
    read_data_frame,
    save_data_frame,
)

logger = get_logger(__name__)

# In debug mode, instead of dropping rows with duplicate primary IDs (except for the first duplicate),
# we retain all rows and add a column named DROP_COLUMN which is True if the row would have been dropped
# if not in debug mode.
DROP_COLUMN = "____drop"

# Column to store the row hashes in. Row hashes are created by make_row_hash, and allows faster lookup
# of matching rows.
HASH_COLUMN = "____hash"

# We save the original ID values in the loaded DataFrames to new columns with the same column
# name as the original preceded by INITIAL_ID_PREFIX (ie. f"{INITIAL_ID_PREFIX}{column_name}")
INITIAL_ID_PREFIX = "__"

UNINDEXED_PK_SLOT = f"{INITIAL_ID_PREFIX * 2}pk_unindexed"
PK_INDEX_SLOT = f"{INITIAL_ID_PREFIX * 2}pk_index"

USE_PRIMARY_KEY_LIST = True

# If True, then for determining if two rows are identical matches, include the columns that contain
# the initial ID values (ie. if an ID needs to be generated, the initial value is what is loaded
# from disk for that ID before it gets generated). This may be helpful in cases where two initial
# IDs are different but after parsing becomes the same. For example "Public Health Ontario (PHO)"
# and "Public Health Ontario (PHO)!" will both become "public_Health_Ontario_PHO", but we may
# want them to be treated as different, in which case including the original values as match columns
# will ensure the two rows are treated as being different.
INCLUDE_INITIAL_VALUE_SLOTS_IN_MATCH_COLUMNS = True


class GeneratorData:
    def __init__(
        self,
        class_name: str,
        input_data: List[Union[str, Path, Dict, pd.DataFrame]],
        primary_key: str,
        generated_slots: Optional[List[str]] = None,
    ):
        self.class_name = class_name
        self.primary_key = primary_key
        self.generated_slots = generated_slots if generated_slots else []
        self.largest_pk_indices = {}

        all_dfs = []
        # Load all data in input_data, store in all_dfs so we can concatenate them
        for cur_data in input_data:
            file = None
            if isinstance(cur_data, (str, Path, Dict)):
                # Load DataFrame from file
                file = cur_data
                logger.debug(f"Loading data from {str(file)}")
                df = read_data_frame(file, keep_default_na=False, na_values=None)
            elif isinstance(cur_data, pd.DataFrame):
                # Data is already in DataFrame format
                file = None
                df = cur_data
            else:
                raise TypeError(
                    f"Unrecognized type for input to GeneratorData: type={type(cur_data)}"
                )

            missing_generated_slots = [
                s for s in self.generated_slots if s not in df.columns
            ]
            if missing_generated_slots:
                df[missing_generated_slots] = None

            # Make sure the columns in df match what we have loaded previously
            if len(all_dfs) > 0:
                first_df = all_dfs[0]
                missing_cur_columns = [
                    c for c in first_df.columns if c not in df.columns
                ]
                if len(missing_cur_columns) > 0:
                    raise ValueError(
                        f"DataFrame for file '{file}' has missing columns: {missing_cur_columns}"
                    )
                missing_full_columns = [
                    c for c in df.columns if c not in first_df.columns
                ]
                if len(missing_full_columns) > 0:
                    raise ValueError(
                        f"DataFrame for file '{file}' has extra columns: {missing_full_columns}"
                    )

            all_dfs.append(df)

        # Concatenate all loaded DataFrames into a single DataFrame
        self.orig_df = pd.concat(all_dfs, ignore_index=True, axis=0)

        # Create a list of all original columns found in the dataset (excluding the tracking columns)
        columns = list(df.columns)
        columns = [c for c in columns if not is_extra_or_tracking_slot(c)]
        self.orig_columns = columns

        self.prepare_ids()

        # Add extra slots
        self.orig_df[UNINDEXED_PK_SLOT] = None
        self.orig_df[PK_INDEX_SLOT] = None
        self.orig_df[HASH_COLUMN] = None

        self.columns = list(self.orig_df.columns)

        if USE_PRIMARY_KEY_LIST:
            self.used_primary_keys = {}

        # Create list of columns used for identifying identical rows. Excludes the primary key column
        # but includes the column at UNINDEXED_PK_SLOT (ie the unindexed primary key).
        self.match_columns = [
            self.get_column_index(c) for c in self.orig_columns if c != self.primary_key
        ]
        if INCLUDE_INITIAL_VALUE_SLOTS_IN_MATCH_COLUMNS:
            self.match_columns.extend(
                [self.get_column_index(c) for c in self.initial_value_columns]
            )
        self.match_columns.append(self.get_column_index(UNINDEXED_PK_SLOT))

        # Convert the DataFrame to a Numpy array
        self.data = self.orig_df.to_numpy()
        # Set all NA values to EMPTY_OBJ
        self.data[pd.isna(self.data)] = EMPTY_OBJ

    def __len__(self):
        return len(self.data)

    def make_initial_slot_names_if_generated_slots(
        self, slots: Union[str, List[str]]
    ) -> List[str]:
        """If any of the specified slots is for a slot that is generated adjust the slot name so
        that it refers to the slot containing the ORIGINAL value for the slot as it was loaded from
        disk. For example, if sampleID is a generated slot, then we will typically replace it
        with __sampleID, where the original values are stored.

        Args:
            slots (Union[str, List[str]]): Either a single slot (str) or a list of slots.

        Returns:
            List[str]: The slots parameter (converted to a list if required) with all slots
                that are generated replaced with the slot to reference the original values
                as loaded form disk for that slot.
        """
        if isinstance(slots, str):
            slots = [slots]
        else:
            slots = slots.copy()
        for idx, s in enumerate(slots):
            if s in self.generated_slots:
                slots[idx] = f"{INITIAL_ID_PREFIX}{s}"
        return slots

    def prepare_ids(self):
        """Do some preparation of the ID columns in the loaded DataFrame.

        We will copy the IDs to new columns where the names are preceded by INITIAL_ID_PREFIX. The values
        in the new columns will remain unchanged, but the values in the old columns will be set to None and
        their IDs generated once make_all_ids is called.

        Args:
        """
        self.current_class = None
        self.current_row_index = None
        self.initial_value_columns = []

        logger.debug(f"Preparing IDs for class '{self.class_name}'")
        # Copy all ID columns to new columns preceded by INITIAL_ID_PREFIX (eg. __), and clear the
        # original column. Once make_all_ids is called, if the original column has a None value
        # then that means we need to calculate the ID for that column (while the double-underscore
        # column remains unchanged).
        slots = [s for s in self.generated_slots if s in self.orig_df.columns]
        if len(slots) > 0:
            orig_values_slots = [f"{INITIAL_ID_PREFIX}{s}" for s in slots]
            self.orig_df[orig_values_slots] = self.orig_df[slots]
            self.orig_df[slots] = None  # IDValue(None)
            self.initial_value_columns.extend(orig_values_slots)

    def init_lookup_table(self, lookup_slots: List[str]):
        """Initialize the lookup tables and populate them.

        Args:
            lookup_slots (List[str]): All slots with our class that should have a lookup table.
        """
        if lookup_slots is None:
            lookup_slots = []

        # We always include UNINDEXED_PK_SLOT and self.primary_key, they are both used frequently
        # by generate_primary_key_index so we include them for performance reasons.
        if not USE_PRIMARY_KEY_LIST and self.primary_key not in lookup_slots:
            lookup_slots = lookup_slots + [self.primary_key]
        if HASH_COLUMN not in lookup_slots:
            lookup_slots = lookup_slots + [HASH_COLUMN]
        self.lookup = RowIndexLookup(lookup_slots)

        # Populate all slots in the lookup table
        for idx in range(len(self.data)):
            for slot in self.lookup.all_lookup_slots():
                if not self.has_column(slot):
                    continue
                row = self.data[idx, :]
                val = row[self.get_column_index(slot)]
                self.lookup.add_index(slot, val, idx)

    def get_row_at_index(self, idx: int) -> np.ndarray:
        """Get the row at the specified 0-based index.

        Args:
            idx (int): The index of the row to retrieve.

        Returns:
            np.ndarray: The row at index idx.
        """
        return self.data[idx, :]

    def has_column(self, col: str) -> bool:
        """Test to see if the data has the specified column


        Args:
            col (str): The column name to test.

        Returns:
            bool: True if the column exists, False otherwise
        """
        return col in self.columns

    def get_column_index(self, col: Union[str, List[str]]) -> Union[int, List[int]]:
        """Get the index/indices of the specified column name(s).

        The index is the 0-based column number for the 2D Numpy array for the data.

        Args:
            col (Union[str, List[str]]): The column name(s) to get the index for.

        Returns:
            Union[int, List[int]]: The index or indices.
        """

        def _get_index(c: str) -> int:
            return self.columns.index(c)

        # col is a single column name (string), return a single index
        if isinstance(col, str):
            return _get_index(col)

        # col is a list of column names, return a list of indices
        indices = []
        for c in col:
            indices.append(_get_index(c))
        return indices

    def get_data_value(self, slot: str, row_index: int) -> Any:
        """Get the value in the data at the specified class, slot, and row index.

        Args:
            class_name (str): The name of the class.
            slot (str): The slot.
            row_index (int): The row index.

        Returns:
            Any: The value at the row/slot/class.
        """
        return self.data[row_index, self.get_column_index(slot)]

    def get_value_from_row(self, row: np.ndarray, slot: str) -> Any:
        return row[self.get_column_index(slot)]

    def set_data_value(self, slot: str, row_index: int, v: Any) -> Any:
        """Set the value in the data for the specified slot and row index.

        Args:
            slot (str): The slot.
            row_index (int): The row index.
            v (Any): The value to set at the slot and row.

        Returns:
            Any: The value that was set, which might be different than v.
        """
        if slot in self.generated_slots and not isinstance(v, IDValue):
            v = IDValue(v)

        if self.lookup.is_lookup_slot(slot):
            prev_value = self.get_data_value(slot, row_index)
            self.lookup.change_value_at_index(slot, row_index, prev_value, v)

        self.data[row_index, self.get_column_index(slot)] = v

        # If we're setting a primary key value, then update the largest index used by
        # the primary key
        if slot == self.primary_key and isinstance(v, IDValue) and v.index is not None:
            prev_value = self.largest_pk_indices.get(v.unindexed_value, -1)
            self.largest_pk_indices[v.unindexed_value] = max(v.index, prev_value)

        return v

    def get_rows_equal(
        self,
        slots: Union[str, List[str]],
        match_value: Any,
        max_rows: Optional[int] = None,
        ignore_indices: Optional[List[int]] = None,
        return_indices: Optional[bool] = False,
    ) -> Union[np.ndarray, Tuple[np.ndarray, np.ndarray]]:
        """Get the rows where slots are equal to match_value.

        slots can be either a single slot or a list of slots. For a single slot, if the slot value equals
        match_value or any of the values in match_value (ie. a list of values) then a match occurs.

        For multiple slots, then match_value must either be a list of values, or a list of lists. If a list of
        values (where the values are not lists), then if all elements between the slots and match_values match
        (ie. slots[idx] == match_value[idx] for all idx), then a match occurs. If match_values is a list of lists,
        then if any sublist matches the slots then a match occurs.

        Args:
            slots (Union[str, List[str]]): The slot(s) to use for matching.
            match_value (Any): The value(s) to match.
            max_rows (Optional[int], Optional): The maximum number of rows to retrieve. Only the first max_rows matching rows
                are returned. If None then all matched rows are returned. Defaults to None.
            ignore_indices (Optional[List[int]], Optional): A list of indices to ignore. The rows at these indices
                will not be returned. If None then all rows are considered.
            return_indices (Optional[bool], Optional): If True then return the indices of the rows, along with the rows. The return
                value will be the tuple (rows, indices), where indices is a 1-D array of the integer indices of the rows.
                If False then only the rows are returned.

        Returns:
            Union[np.ndarray, Tuple[np.ndarray, np.ndarray]]: If return_indices is False then returns an 2D Numpy array that is
                the selected rows that match. If return_indices is True then returns a tuple consisting of the (rows, indices),
                where indices is a 1D Numpy array specifying the indices of the returned matching rows in the full dataset
                for the class. If no matches are found the either None or the tuple (None, None) are returned,
                depending on the value of return_indices.
        """

        def _ret_value(rows, indices):
            # Create the return value. If return_indices is True we return a tuple (rows, indices), if False we simply return rows
            if return_indices:
                return rows, indices
            return rows

        def _ismatch(v1: Any, v2: Any) -> bool:
            # Test if v1 is equal to v2. We treat all NaNs and "" as equal.
            v1_na = isna(v1) or v1 == ""
            v2_na = isna(v2) or v2 == ""
            return v1 == v2 or (v1_na and v2_na)

        def _row_matches(row: np.ndarray, match_value: Any) -> bool:
            # A row matches if any value in match_value matches
            for cur_match_value in match_value:
                # Make cur_match_value be of the form [a, b, c, ..., n], where n should
                # be equal to the number of slots being matched. If it is not equal to
                # the number of slots then the match for the current value fails.
                if not isinstance(cur_match_value, (list, tuple, np.ndarray)):
                    cur_match_value = [cur_match_value]
                match = True
                if len(cur_match_value) != len(row):
                    match = False
                    break
                # Compare all values in cur_match_value to all values in row. Each value must match
                for m, row_v in zip(cur_match_value, row):
                    if not _ismatch(m, row_v):
                        # No match, so break then continue to the next match_value
                        match = False
                        break
                if match:
                    return True
            return False

        # Get the variables ready
        if isinstance(slots, str):
            # We are matching a single slot. Make slots an array and
            # also make sure match_value is an array.
            slots = [slots]
            if not isinstance(match_value, (list, tuple, np.ndarray)):
                match_value = [match_value]

        # For finding rows using a slot that has a fast lookup table, use the lookup table
        if len(slots) == 1 and self.lookup.is_lookup_slot(slots[0]):
            slot = slots[0]
            all_indices = []

            # Find all row indices where the value in the slot matches any of the values
            # in match_value
            for cur_match_value in match_value:
                if not isinstance(cur_match_value, (list, tuple, np.ndarray)):
                    cur_match_value = [cur_match_value]
                for sub_match_value in cur_match_value:
                    if self.lookup.slot_has_value(slot, sub_match_value):
                        indices = self.lookup.get_indices(slot, sub_match_value)
                        if ignore_indices is not None:
                            indices = [i for i in indices if i not in ignore_indices]
                        all_indices.append(indices)

            # Combine all matched indices
            indices = [i for sub in all_indices for i in sub]
            # If multiple values in match_value were matched, then we had multiple set
            # of indices that were merged, so we need to sort them. If only one value
            # matched, then they are already in order, so no sorting is required.
            if len(all_indices) > 1:
                indices = list(set(indices)).sort()
            if max_rows:
                indices = indices[:max_rows]

            if len(indices) == 0:
                return _ret_value(None, None)
            return _ret_value(self.data[indices], indices)
        else:
            # Get all matching indices
            matched_indices = []
            slots_idx = self.get_column_index(slots)
            for idx, row in enumerate(self.data[:, slots_idx]):
                if ignore_indices is not None and idx in ignore_indices:
                    continue
                if _row_matches(row, match_value):
                    matched_indices.append(idx)
                    if max_rows and len(matched_indices) >= max_rows:
                        break

            if len(matched_indices) == 0:
                return _ret_value(None, None)

            return _ret_value(self.data[matched_indices], np.array(matched_indices))

    def get_rows_at_index(self, index: Union[int, List[int]]) -> np.ndarray:
        """Get the row(s) at the specified indices.

        Args:
            class_name (str): The class to get the rows from.
            index (Union[int, List[int]]): A single index or list of indices to retrieve the
                rows of.

        Returns:
            np.ndarray: The retrieved rows (2D Numpy array).
        """
        if not isinstance(index, Iterable):
            index = [index]
        return self.data[index]

    def make_row_hash(self, row: np.ndarray) -> int:
        """Make a hash of the row.

        Args:
            row (np.ndarray): The row data to hash.

        Returns:
            int: The hash value.
        """
        if row.ndim == 2:
            row = row[0]
        val = "//".join([str(c) for c in row])
        hash_value = hash(val)
        return hash_value

    def generate_primary_key_index(self, row_index: int) -> Any:
        """For the (unindexed) primary key value currently found at the row index,
        either group it with other rows generated so far that are identical to the row at row_index
        (by using the same primary key index as found in the duplicate rows), or if there are no other
        identical rows so far add an optional index to make sure the primary key is unique.

        An unindexed primary key value is the original calculated ID, without any modification. These
        values are stored in the UNINDEXED_PK_SLOT of the class's Numpy data. In order to create a unique
        primary key from this unindexed value, we add an index to it (eg. a trailing number).
        This index number is stored in PK_INDEX_SLOT. The actual primary key becomes a combination
        of the unindexed pk value and the pk index (eg. "mySample" + "001" = "mySample001").

        If the pk index is 0 then the indexed pk value will be the same as the unindexed pk value
        (eg. "mySample", without a trailing number).

        When calling this function, the value currently found in the row's primary key column is
        assumed to be the unindexed value. Both the values at PK_INDEX_SLOT and UNINDEXED_PK_SLOT
        are ignored. Once this function is complete, all three of these columns will be set with
        the new values.

        Args:
            row_index (int): The 0-based row number in the class to group the primary key for.

        Returns:
            Any: The value of the primary key at row row_index, after any grouping is performed.
        """

        def _set_current_row_values(unindexed_pk: str, pk_index: int):
            """Set the ID values for the current row (the indexed pk value in self.primary_key, the
            unindexed pk value in UNINDEXED_PK_SLOT, and the index in PK_INDEX_SLOT).
            """
            self.set_data_value(PK_INDEX_SLOT, row_index, pk_index)
            self.set_data_value(UNINDEXED_PK_SLOT, row_index, unindexed_pk)
            id_value = IDValue(unindexed_pk, pk_index, index_in_progress=False)
            self.set_data_value(
                self.primary_key,
                row_index,
                id_value,
            )

            new_row = self.get_row_at_index(row_index)[self.match_columns]
            hash_value = self.make_row_hash(new_row)
            self.set_data_value(HASH_COLUMN, row_index, hash_value)

            if USE_PRIMARY_KEY_LIST:
                self.used_primary_keys[str(id_value)] = True

        # The unindex PK value is currently at self.primary_key. Copy the value over to the UNINDEXED_PK_SLOT
        # then clear self.primary_key (since we will recalculate it)
        unindexed_pk_value = self.get_data_value(self.primary_key, row_index)
        # When the unindexed value for the primary key is an empty string ("", but not None) then this row will always
        # have an index of 0. These are rows that should get removed downstream of the mapper (by running a filter).
        if (isinstance(unindexed_pk_value, str) and unindexed_pk_value == "") or (
            isinstance(unindexed_pk_value, IDValue)
            and unindexed_pk_value.unindexed_value == ""
        ):
            _set_current_row_values("", 0)
            return self.get_data_value(self.primary_key, row_index)
        self.set_data_value(self.primary_key, row_index, None)
        self.set_data_value(PK_INDEX_SLOT, row_index, None)
        self.set_data_value(UNINDEXED_PK_SLOT, row_index, unindexed_pk_value)

        # Get the current row (at row_index)
        current_row = self.get_rows_at_index(row_index)

        # Collect all rows that are identical to the current row
        current_row_match = current_row[:, self.match_columns]
        current_hash = self.make_row_hash(current_row_match)
        match_indices = self.lookup.get_indices(HASH_COLUMN, current_hash)

        # Go through all rows that have the same hash, and find an identical match. We need to do the
        # identical match test because of the way that a hash is made, by concatenating the cells of a
        # row as strings. It's possible that non-identical rows will have the same string. For example,
        # the following two rows will have the same hash/string (if we concatenate the strings with no
        # separator):
        #    animal1     animal2
        #    Hamster!    Frog
        #    Hamster     !Frog
        # Note too that it's likely we will find a match immediately, since instances like the above example
        # are rare.
        # We go in reverse order of match_indices, because it's more likely that rows close to eachother
        # will be similar (and we generally generate rows from top to bottom), so we might find a match
        # sooner in reverse order.
        identical_row_idx = None
        for i in match_indices[::-1]:
            if i == row_index:
                continue

            cur_row = self.data[i, self.match_columns]
            if np.equal(cur_row, current_row_match).all(axis=1):
                identical_row_idx = i
                break

        if identical_row_idx is not None:
            # There are identical rows, so use the PK index found in the first identical row
            # pk_index = identical_rows[0, self.get_column_index(PK_INDEX_SLOT)]
            pk_index = self.data[
                identical_row_idx, self.get_column_index(PK_INDEX_SLOT)
            ]
            _set_current_row_values(unindexed_pk_value, pk_index)
        else:
            # There are no identical rows, so get a PK index that results in a unique indexed PK
            # pk_index = 0
            pk_index = self.largest_pk_indices.get(unindexed_pk_value, 0)

            while True:
                indexed_pk_value = IDValue.make_id_str(unindexed_pk_value, pk_index)
                # If indexed_pk_value is unique in column self.primary_key then use it.
                # Note that we have previously set the value in column self.primary_key for the current row to None
                if USE_PRIMARY_KEY_LIST:
                    if indexed_pk_value not in self.used_primary_keys:
                        break
                else:
                    indices = self.lookup.get_indices(
                        self.primary_key, indexed_pk_value
                    )
                    if len(indices) == 0:
                        break
                pk_index += 1
            _set_current_row_values(unindexed_pk_value, pk_index)

        return self.get_data_value(self.primary_key, row_index)

    def finalize_data(
        self,
        keep_extra_columns: bool,
        keep_tracking_columns: bool,
        keep_debug_columns: bool,
        remove_duplicates: bool,
    ) -> Tuple[Dict[str, List[pd.DataFrame]], int, int, int]:
        """Finalize the data by converting it to a DataFrame and dropping duplicates based on the
        primary key.

        Args:
            keep_extra_columns (bool): If True, then keep the extra columns in the final DataFrame. These
                are columns that start with the string extra_and_tracking_slots.EXTRA_SLOT_PREFIX and end with the
                string extra_and_tracking_slots.EXTRA_SLOT_SUFFIX. If False then they are removed.
            keep_tracking_columns (bool): If True, then keep the tracking columns in the final DataFrame.
                These are columns that specify from which row and file/table each of the output rows was populated
                from. Tracking columns start with the string extra_and_tracking_slots.TRACKING_SLOT_PREFIX and end
                with the string extra_and_tracking_slots.TRACKING_SLOT_SUFFIX. If False then these columns are
                dropped.
            keep_debug_columns (bool): If True then keep additional columns for debugging. These are
                temporary columns that are used for running, such as columns containing the old IDs
                before generation was run, the hash column, etc.
            remove_duplicates (bool): If True then remove duplicates based on the primary keys of each
                class. In production this is typically True. If False then duplicates are retained,
                but an extra __drop column is added where the value is True if that row would
                have been dropped if remove_duplicates was True.

        Returns:
            Tuple[Dict[str, List[pd.DataFrame]], int, int, int]:
                Dict[str, List[pd.DataFrame]]: All DataFrames, where the keys are the target class names and the values
                    are lists of DataFrames for the class.
                int: Number of total rows, before dropping duplicates
                int: Number of total rows, after dropping duplicates
                int: Number of dropped duplicates
        """
        self.data[self.data == EMPTY_OBJ] = None
        self.df = pd.DataFrame(self.data, columns=self.columns)

        # Keep only requested columns, based on keep_extra_and_tracking_columns and keep_debug_columns
        keep_columns = self.orig_columns.copy()
        # Put the extra slots first, followed by the tracking slots
        if keep_extra_columns:
            keep_columns.extend([c for c in self.df.columns if is_extra_slot(c)])
        if keep_tracking_columns:
            keep_columns.extend([c for c in self.df.columns if is_tracking_slot(c)])
        if keep_debug_columns:
            keep_columns.extend(
                [
                    c
                    for c in self.df.columns
                    if c not in self.orig_columns and not is_extra_or_tracking_slot(c)
                ]
            )

        self.df = self.df[keep_columns]

        total_rows = len(self.df)
        total_dropped_rows = 0

        # Drop rows where primary key is a duplicate
        if self.primary_key:
            orig_len = len(self.df)

            if remove_duplicates:
                # Drop rows where self.primary_key is a duplicate
                self.df = self.df.drop_duplicates(self.primary_key, keep="first")
                new_len = len(self.df)
            else:
                # Add "drop" column for testing
                columns = list(self.df.columns)
                dupes_filt = self.df.duplicated(self.primary_key, keep="first")
                if dupes_filt.any():
                    self.df.loc[dupes_filt, DROP_COLUMN] = True
                else:
                    if DROP_COLUMN not in self.df.columns:
                        self.df[DROP_COLUMN] = None
                # Put the DROP_COLUMN first
                self.df = self.df[[DROP_COLUMN] + columns]
                new_len = orig_len - self.df[DROP_COLUMN].sum()

            total_dropped_rows = total_rows - new_len

            logger.debug(
                f"Dropped duplicate primary keys for class '{self.class_name}': {orig_len} -> {new_len} (-{total_dropped_rows})"
            )

        self.total_rows = total_rows
        self.total_rows_minus_dropped_rows = total_rows - total_dropped_rows
        self.total_dropped_rows = total_dropped_rows

        return (
            {self.class_name: [self.df]},
            self.total_rows,
            self.total_rows_minus_dropped_rows,
            self.total_dropped_rows,
        )

    def save_data(
        self,
        output_dir: str,
    ) -> Tuple[Dict[str, List[Path]], Dict[str, List[pd.DataFrame]]]:
        """Save the data to disk.

        Args:
            output_dir (str): Directory to save DataFrame to.

        Returns:
            Tuple[Dict[str, List[Path]], Dict[str, List[pd.DataFrame]]]: A tuple of two dictionaries corresponding
                to (saved_files, data_frames):
                    saved_files: All saved files, where the keys are the target class names and the values
                        are lists of output files for the class.
                    data_frames: All saved DataFrames, where the keys are the target class names
                        and the values are lists of DataFrames for the class.
                Note that saved_files["class_name"][idx] corresponds to the file that data_frames["class_name"][idx]
                was saved to.
        """
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        output_file = os.path.join(output_dir, f"{self.class_name}.csv")

        save_data_frame(self.df, output_file, index=False)

        return {self.class_name: [Path(output_file)]}, {self.class_name: [self.df]}
