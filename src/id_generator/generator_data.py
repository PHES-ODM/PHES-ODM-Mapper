"""
Manage data for a class, including creating lookup tables for faster access to rows within the table (for certain slots).

## Usage

```python
# Create data for class 'measures', load data from 'measures.csv', create lookup tables for faster access
# for slots in lookup_slots, initialize for generating IDs for slots in generated_slots, and set the primary
# key for the data to "measureRepID".
data = GeneratorData(
    class_name="measures",
    data_files=["measures.csv"],
    lookup_slots=["measureRepID", "(__source_file_and_row__)"],
    generated_slots=["measureRepID", "siteID", "organizationID"],
    primary_key="measureRepID",
)
```
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import numpy as np
from typing import Union, List, Any, Optional, Tuple, Dict
from collections.abc import Iterable
from pathlib import Path

from id_generator.row_index_lookup import RowIndexLookup
from utils.tracking_slots import TrackingSlots

from utils.general_utils import (
    read_data_frame,
    save_data_frame,
    get_logger,
)

logger = get_logger(__name__)

# In debug mode, instead of dropping rows with duplicate primary IDs (except for the first duplicate),
# we retain all rows and add a column named DROP_COLUMN which is True if the row would have been dropped
# if not in debug mode.
DROP_COLUMN = "__drop"

# We save the original ID values in the loaded DataFrames to new columns with the same column
# name as the original preceded by ORIG_ID_PREFIX (ie. f"{ORIG_ID_PREFIX}{column_name}")
ORIG_ID_PREFIX = "__"

UNINDEXED_PK_SLOT = f"{ORIG_ID_PREFIX*2}pk_unindexed"
PK_INDEX_SLOT = f"{ORIG_ID_PREFIX*2}pk_index"


class GeneratorData:
    def __init__(
        self,
        class_name: str,
        data_files: List[Union[str, Path]],
        primary_key: str,
        lookup_slots: Optional[List[str]] = None,
        generated_slots: Optional[List[str]] = None,
    ):
        self.class_name = class_name
        self.primary_key = primary_key
        self.generated_slots = generated_slots if generated_slots else []

        for file in data_files:
            logger.info(f"Loading data from {str(file)}")
            df = read_data_frame(file)

            self.orig_df = df

            # Create a list of all original columns found in the dataset
            columns = list(df.columns)
            for s in self.get_all_tracking_slots():
                if s not in columns:
                    raise ValueError(
                        f"Tracking column '{s}' must exist in the data at {str(file)}"
                    )
                columns.remove(s)
            self.orig_columns = columns

        self.prepare_ids()

        # Add the primary key slot
        self.orig_df[UNINDEXED_PK_SLOT] = None
        self.orig_df[PK_INDEX_SLOT] = None
        self.columns = list(self.orig_df.columns)

        # Convert the DataFrame to a Numpy array
        self.data = self.orig_df.to_numpy()

        if lookup_slots:
            self.init_lookup_table(lookup_slots)
        

    def __len__(self):
        return len(self.data)

    def make_orig_slot_names_if_generated_slots(self, slots: Union[str, List[str]]) -> List[str]:
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
                slots[idx] = f"{ORIG_ID_PREFIX}{s}"
        return slots

    def prepare_ids(self):
        """Do some preparation of the ID columns in the loaded DataFrame.

        We will copy the IDs to new columns where the names are preceded by ORIG_ID_PREFIX. The values
        in the new columns will remain unchanged, but the values in the old columns will be set to None and
        their IDs generated once make_all_ids is called.

        Args:
        """
        self.current_class = None
        self.current_row_index = None

        logger.info(f"Preparing IDs for class '{self.class_name}'")
        # Copy all ID columns to new columns preceded by ORIG_ID_PREFIX (eg. __), and clear the
        # original column. Once make_all_ids is called, if the original column has a None value
        # then that means we need to calculate the ID for that column (while the double-underscore
        # column remains unchanged).
        slots = [s for s in self.generated_slots if s in self.orig_df.columns]
        if len(slots) > 0:
            orig_values_slots = [f"{ORIG_ID_PREFIX}{s}" for s in slots]
            self.orig_df[orig_values_slots] = self.orig_df[slots]
            self.orig_df[slots] = None

    def init_lookup_table(self, lookup_slots: List[str]):
        """Initialize the lookup tables and populate them.

        Args:
            lookup_slots (List[str]): All slots with our class that should have a lookup table.
        """
        # We always include UNINDEXED_PK_SLOT
        if UNINDEXED_PK_SLOT not in lookup_slots:
            lookup_slots = lookup_slots + [UNINDEXED_PK_SLOT]
        self.lookup = RowIndexLookup(lookup_slots)

        # Populate all slots in the lookup table
        for idx in range(len(self.data)):
            for slot in self.lookup.all_lookup_slots():
                row = self.data[idx, :]
                val = row[self.get_column_index(slot)]
                self.lookup.add_index(slot, val, idx)

    def get_all_tracking_slots(self) -> List[str]:
        """Get all the tracking slots, which are all the columns specified in TrackingSlots.

        Tracking slots include the source row number and class name of a row. These get copied over
        to the mapped data so we know which class and row and output row was derived from. It can
        be used for sorting and other downstream operations, such as for ID generation.

        Returns:
            List[str]: List of all tracking slots.
        """
        return [
            getattr(TrackingSlots, v)
            for v in vars(TrackingSlots)
            if not v.startswith("__")
        ]

    def get_row_at_index(self, idx):
        return self.data[idx, :]

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

    def set_data_value(self, slot: str, row_index: int, v: Any):
        """Set the value in the data for the specified slot and row index.

        Args:
            slot (str): The slot.
            row_index (int): The row index.
            v (Any): The value to set at the slot and row.
        """
        if self.lookup.is_lookup_slot(slot):
            prev_value = self.get_data_value(slot, row_index)
            self.lookup.change_value_at_index(slot, row_index, prev_value, v)

        self.data[row_index, self.get_column_index(slot)] = v

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
            v1_na = pd.isna(v1) or v1 == ""
            v2_na = pd.isna(v2) or v2 == ""
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

    def group_primary_key(self, row_index: int) -> Any:
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

        def _make_indexed_pk(unindexed_pk: str, pk_index: int) -> str:
            """Make an indexed primary key value, based on the unindexed primary key value and
            a numerical index."""
            if pk_index:
                return f"{unindexed_pk}{pk_index:03d}"
            else:
                return unindexed_pk

        def _set_current_row_values(unindexed_pk: str, pk_index: int):
            """Set the ID values for the current row (the indexed pk value in self.primary_key, the
            unindexed pk value in UNINDEXED_PK_SLOT, and the index in PK_INDEX_SLOT).
            """
            self.set_data_value(PK_INDEX_SLOT, row_index, pk_index)
            self.set_data_value(UNINDEXED_PK_SLOT, row_index, unindexed_pk)
            indexed_pk_value = _make_indexed_pk(unindexed_pk, pk_index)
            self.set_data_value(self.primary_key, row_index, indexed_pk_value)

        # The unindex PK value is currently at self.primary_key. Copy the value over to the UNINDEXED_PK_SLOT
        # then clear self.primary_key (since we will recalculate it)
        unindexed_pk_value = self.get_data_value(self.primary_key, row_index)
        self.set_data_value(self.primary_key, row_index, None)
        self.set_data_value(PK_INDEX_SLOT, row_index, None)
        self.set_data_value(UNINDEXED_PK_SLOT, row_index, unindexed_pk_value)

        # Get the current row (at row_index)
        current_row = self.get_rows_at_index(row_index)

        # Get all rows that have the same unindexed primary key value
        rows, _ = self.get_rows_equal(
            UNINDEXED_PK_SLOT,
            unindexed_pk_value,
            ignore_indices=[row_index],
            return_indices=True,
        )

        if rows is None:
            rows = []

        if len(rows) > 0:
            # Get the rows that are identical to current_row
            # The columns we use for matching are all of the original columns in the loaded DataFrame, without the primary key column
            # but with the column at UNINDEXED_PK_SLOT.
            columns = [
                self.get_column_index(c)
                for c in self.orig_columns
                if c != self.primary_key
            ]
            columns.append(self.get_column_index(UNINDEXED_PK_SLOT))

            # Replace NANs so that they can be equated to each other (normally, float("nan") == float("nan") is False, but we
            # want it to be true by replacing the nan values with a single comparable value)
            nanobj = object()
            rows_nan = rows[:, columns].copy()
            current_row_nan = current_row[:, columns].copy()
            rows_nan[np.where(pd.isna(rows_nan))] = nanobj
            current_row_nan[np.where(pd.isna(current_row_nan))] = nanobj

            # Collect all rows that are identical to the current row
            identical_rows_filt = np.equal(rows_nan, current_row_nan).all(axis=1)
            identical_rows = rows[identical_rows_filt, :]
        else:
            # There are no identical rows
            identical_rows = []

        if len(identical_rows) > 0:
            # There are identical rows, so use the PK index found in the first identical row
            pk_index = identical_rows[0, self.get_column_index(PK_INDEX_SLOT)]
            _set_current_row_values(unindexed_pk_value, pk_index)
        else:
            # There are no identical rows, so get a PK index that results in a unique indexed PK
            pk_index = 0
            if len(rows) > 0:
                index_values = rows[:, self.get_column_index(PK_INDEX_SLOT)]
                index_values = index_values[~pd.isna(index_values)]
                if len(index_values) > 0:
                    pk_index = index_values.max() + 1
            while True:
                indexed_pk_value = _make_indexed_pk(unindexed_pk_value, pk_index)
                # If indexed_pk_value is unique in column self.primary_key then use it.
                # Note that we have previously set the value in column self.primary_key for the current row to None
                if (
                    indexed_pk_value
                    not in self.data[:, self.get_column_index(self.primary_key)]
                ):
                    break
                pk_index += 1
            _set_current_row_values(unindexed_pk_value, pk_index)

        return self.get_data_value(self.primary_key, row_index)

    def save_data(
        self,
        output_dir: str,
        orig_columns_only: bool = True,
        drop_duplicates: bool = True,
    ) -> Dict[str, List[Path]]:
        """Save the data to disk.

        Args:
            output_dir (str): Directory to save DataFrame to.
            orig_columns_only (bool, optional): If True then only save the original columns that were part
                of the source database and table as initially loaded from disk. If False then all columns are saved,
                including any columns temporarily created for mapping operations and debugging columns.
                Defaults to True.
            drop_duplicates (bool, optional): If True then drop all rows where the primary key is a duplicate
                (except for the first duplicate). If False then all rows are retained, instead a column named
                DROP_COLUMN is added and set to True if the row would have been dropped. Note that
                the DROP_COLUMN column will only be retained if orig_columns_only is False. Defaults to True.

        Returns:
            Dict[str, List[Path]]: All saved files, where the keys are the target class names and the values
                are lists of output files for the class.
        """
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        output_file = os.path.join(output_dir, f"{self.class_name}.csv")
        data = pd.DataFrame(self.data, columns=self.columns)

        # Drop rows where primary key is a duplicate
        if self.primary_key:
            orig_len = len(data)

            if drop_duplicates:
                # Drop rows where self.primary_key is a duplicate
                data = data.drop_duplicates(self.primary_key, keep="first")
                new_len = len(data)
            else:
                # Add "drop" column for testing
                columns = list(data.columns)
                dupes_filt = data.duplicated(self.primary_key, keep="first")
                data.loc[dupes_filt, DROP_COLUMN] = True
                data = data[[DROP_COLUMN] + columns]
                new_len = orig_len - data[DROP_COLUMN].sum()

            logger.info(
                f"Dropped duplicate primary keys for class '{self.class_name}': {orig_len} -> {new_len} ({new_len-orig_len})"
            )

        if orig_columns_only:
            # Remove additional columns that were added temporarily for execution purposes
            data = data[self.orig_columns]

        save_data_frame(data, output_file, index=False)

        output_data_files = {self.class_name: [Path(output_file)]}
        return output_data_files
