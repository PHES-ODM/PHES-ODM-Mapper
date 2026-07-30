"""
A lookup table, mapping values (for a given slot) to row indices, so we can quickly get the
indices for the values.

A single lookup table represents the data for a single 2D table. Only the slots
specified in the constructor will have lookup tables.

Note that all NA values that return True by isna (eg. float("NaN") and None) are treated
the same.

## Usage

```python
# Make slot1 and slot2, and do initial population of data
lookup = RowIndexLookup(["slot1", "slot2"])
lookup.add_index("slot1", "valA", 0)
lookup.add_index("slot1", "valA", 1)
lookup.add_index("slot1", "valA", 2)
lookup.add_index("slot1", "valB", 3)
lookup.add_index("slot1", "valB", 4)
lookup.add_index("slot2", "valC", 0)

# Prints True
print(lookup.is_lookup_slot("slot1"))
# Prints False
print(lookup.is_lookup_slot("otherSlot"))
# Prints ['slot1', 'slot2']
print(lookup.all_lookup_slots())

# Prints [0, 1, 2]
print(lookup.get_indices("slot1", "valA"))

# Prints [3, 4]
print(lookup.get_indices("slot1", "valB"))

# Change the value in slot1 at row 1 from "valA" to "valB"
lookup.change_value_at_index("slot1", 1, "valA", "valB")

# Prints [0, 2]
print(lookup.get_indices("slot1", "valA"))
# Prints [1, 3, 4]
print(lookup.get_indices("slot1", "valB"))
```
"""

from bisect import insort
from typing import Any

from sortedcontainers import SortedList

from odm_map.id_generator.id_na import isna
from odm_map.id_generator.id_value import IDValue

# If True, then use SortedList for the list of indices. If False then use a regular Python list (and
# keep the list sorted by using bisect.insort to insert new values). They both give the same results,
# but one might be faster than the other.
USE_SORTED_LIST = True


class RowIndexLookup:
    def __init__(self, lookup_slot: list[Any]):
        """Constructor for RowIndexLookup.

        Args:
            lookup_slot (list[Any]): List of slots that should have a lookup table.
        """
        lookup_slot = list(dict.fromkeys([self._get_value_key(s) for s in lookup_slot]))
        self.data = {s: {} for s in lookup_slot}

    def __repr__(self):
        return repr(self.data)

    def __str__(self):
        return str(self.data)

    def _get_value_key(self, value: Any) -> Any:
        """Get the key in a lookup table corresponding to the value. This will map all NA
        values to None, and return other values unchanged casted to a string. (NA values are
        all treated the same in a looup table).

        Args:
            value (Any): The value to convert to a key.

        Returns:
            Any: The key corresponding to the value.
        """
        if isna(value) or (isinstance(value, IDValue) and value.is_empty()):
            return None
        return str(value)

    def add_index(self, slot: str, value: Any, idx: int):
        """Add a row index that the value should map to.

        Args:
            slot (str): The slot to add the index to.
            value (Any): The value that gets mapped to the index.
            idx (int): The row index to add, for the value.
        """
        key = self._get_value_key(value)
        if slot not in self.data:
            self.data[slot] = {}
        if key not in self.data[slot]:
            self.data[slot][key] = SortedList() if USE_SORTED_LIST else []
        if USE_SORTED_LIST:
            self.data[slot][key].add(idx)
        else:
            insort(self.data[slot][key], idx)

    def is_lookup_slot(self, slot: str) -> bool:
        """Determine if the specified slot has a lookup table.

        Args:
            slot (str): The slot to check.

        Returns:
            bool: True if slot has a lookup table, False otherwise.
        """
        return slot in self.data

    def slot_has_value(self, slot: str, value: Any) -> bool:
        """Determine if the slot has a lookup table and if the value (that maps
        to row indices) is found as a key in the lookup table.

        Args:
            slot (str): The slot to check.
            value (Any): The value to check.

        Returns:
            bool: True if the value is found in the lookup table for the slot (and hence
                can be mapped to row indices). False otherwise.
        """
        value = self._get_value_key(value)
        return slot in self.data and value in self.data[slot]

    def change_value_at_index(
        self, slot: str, idx: int, prev_value: Any, new_value: Any
    ):
        """Remove the specified index for a value (prev_value) and move the index
        to a new value (new_value), for a given slot. This should be called
        whenever a value in the original data table that the lookup is for changes
        from prev_value to new_value.

        Args:
            slot (str): The slot that the values and index are for.
            idx (int): The index to move to a new value.
            prev_value (Any): The value that points to the index, that is changing.
            new_value (Any): The new value that is being set at the index (in the
                specified slot). Once complete, the lookup table will include the row
                index when new_value is looked up.
        """
        prev_value = self._get_value_key(prev_value)
        new_value = self._get_value_key(new_value)
        if prev_value != new_value or (isna(prev_value) != isna(new_value)):
            if prev_value in self.data[slot]:
                self.data[slot][prev_value].remove(idx)
                if len(self.data[slot][prev_value]) == 0:
                    del self.data[slot][prev_value]
            if new_value not in self.data[slot]:
                self.data[slot][new_value] = SortedList() if USE_SORTED_LIST else []
            if USE_SORTED_LIST:
                self.data[slot][new_value].add(idx)
            else:
                insort(self.data[slot][new_value], idx)

    def all_lookup_slots(self) -> list[Any]:
        """Get a list of all lookup slots.

        Returns:
            list[Any]: List of lookup slots.
        """
        return list(self.data.keys())

    def get_indices(self, slot: str, value: Any) -> list[int]:
        """Get all row indices that have the specified value in the specified slot.

        Args:
            slot (str): The slot.
            value (Any): The value to get the indices for (in the slot).

        Returns:
            list[int]: List of row indices where the slot is equal to value.
                If the value does not exist, then an empty list [] is returned.
        """
        value = self._get_value_key(value)
        return self.data[slot].get(value, [])
