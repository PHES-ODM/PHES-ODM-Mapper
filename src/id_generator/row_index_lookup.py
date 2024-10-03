# %%
"""
A lookup table, where values within slots get mapped to a list of row indices, where
the indices are all rows where the value in the slot are equal to the requested value.
A single lookup table represents the data for a single 2D table. Only the slots
specified in the constructor will have lookup tables.

Note that all NA values that return True by pd.isna (eg. float("NaN") and None) are treated
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
print(lookup.all_slots())

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

from typing import Any, List
import pandas as pd
import bisect


class RowIndexLookup:
    def __init__(self, initial_slots: List[Any] = {}):
        initial_slots = list(
            dict.fromkeys([self._get_value_key(s) for s in initial_slots])
        )
        self.data = {s: {} for s in initial_slots}

    def _get_value_key(self, key):
        if pd.isna(key):
            return None
        return key

    def add_index(self, slot: str, value: Any, idx: int):
        key = self._get_value_key(value)
        if slot not in self.data:
            self.data[slot] = {}
        if key not in self.data[slot]:
            self.data[slot][key] = []
        bisect.insort(self.data[slot][key], idx)

    def is_lookup_slot(self, slot: str):
        return slot in self.data

    def slot_has_value(self, slot: str, value: Any) -> bool:
        value = self._get_value_key(value)
        return slot in self.data and value in self.data[slot]

    def change_value_at_index(
        self, slot: str, idx: int, prev_value: Any, new_value: Any
    ):
        prev_value = self._get_value_key(prev_value)
        new_value = self._get_value_key(new_value)
        if prev_value != new_value or (pd.isna(prev_value) != pd.isna(new_value)):
            self.data[slot][prev_value].remove(idx)
            if len(self.data[slot][prev_value]) == 0:
                del self.data[slot][prev_value]
            if new_value not in self.data[slot]:
                self.data[slot][new_value] = []
            bisect.insort(self.data[slot][new_value], idx)

    def all_slots(self) -> List[Any]:
        return list(self.data.keys())

    def get_indices(self, slot: str, value: Any) -> List[int]:
        value = self._get_value_key(value)
        return self.data[slot][value]

    def __repr__(self):
        return repr(self.data)

    def __str__(self):
        return str(self.data)
