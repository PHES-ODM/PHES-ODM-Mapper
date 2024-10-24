# %%
"""
Holds a custom-generated ID. Has an option to add an index to the ID, which allows to generate primary keys that are
unique, in case there are conflicting primary key values.

# Usage

```python
id_value = IDValue("myID", 3)
# Prints "myID003"
print(id_value)
# Prints "True"
print(id_value == "myID003")
# Prints "False
print(id_value == "myID001")

id_value = IDValue("myID")
# Prints "myID"
print(id_value)
```
"""

from typing import Optional


class IDValue(object):
    def __init__(self, root_id: Optional[str], index: int = 0):
        """Constructor for IDValue

        Args:
            root_id (Optional[str]): The ID value, without the added index. If None then this ID is considered to
                be empty (and will be replaced with a non-empty IDValue object in the future).
            index (int, optional): The index to add at the end of the ID, which is added to ensure that primary
                keys are unique and do not conflict with other primary keys. If 0 then no index is added after
                the ID. To get the full string of the ID with the index pass the IDValue object to the str() function
                (ie. str(idvalue_obj)). Defaults to 0.
        """
        self._root_id: Optional[str] = root_id
        self._index: int = index
        # _str_value is the value returned by str(self)
        # _repr_value is the value returned by repr(self)
        # We calculate these values on-demand as an optimization
        self._str_value: Optional[str] = None
        self._repr_value: Optional[str] = None

    def __str__(self) -> str:
        if self._str_value is None:
            index_str = f"{self._index:03d}" if self._index else ""
            self._str_value = f"{self._root_id}{index_str}"
        return self._str_value

    def __repr__(self) -> str:
        if self._repr_value is None:
            self._repr_value = f"<IDValue:{str(self)}>"
        return self._repr_value

    def __eq__(self, value: object) -> bool:
        return str(self) == value

    def __ne__(self, value: object) -> bool:
        return str(self) != value

    def __len__(self) -> int:
        return len(str(self))

    def __hash__(self) -> int:
        return hash(str(self))

    def __bool__(self) -> bool:
        return not self.is_empty()

    def is_empty(self) -> bool:
        return self._root_id is None

    @property
    def unindexed_value(self) -> Optional[str]:
        """Get the unindexed ID value (ie. the value passed as root_id to the constructor)

        Returns:
            Optional[str]: The unindexed ID value, or None if the ID object is empty.
        """
        return self._root_id

    @property
    def index(self) -> int:
        """Get the index of the ID (ie. the value passed as index to the constructor).

        Returns:
            int: The integer index of the ID.
        """
        return self._index
