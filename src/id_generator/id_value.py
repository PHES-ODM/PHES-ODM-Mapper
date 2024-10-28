# %%
"""
Holds a custom-generated ID. Has an option to add an index to the ID, which allows to generate primary keys that are
unique, in case there are conflicting primary key values.

The index_in_progress member should be set to True if the caller is currently calculating the index for
the IDValue object. Once we are finished calculating the index it should be set to False. This is to avoid
circular dependencies on the IDs. Calculating the index of a primary key IDValue requires calculating all the other IDs
in the current row of the table. This is so that we know if the row is a duplicate of another row (in which case
we would use the index from one of the duplicate rows), or not a duplicate (in which case we add a new unique
index). While calculating the rest of the row we may require using an IDValue where the index is being calculated,
and so we cannot know what the string value of the index is yet. If this occurs, then an exception is raised.

To reduce the risk of the above problem, the index is sometimes removed/stripped when using an IDValue to calculate another
IDValue, for example, fn.makeid(datEmpty.datasets.datasetID, datEmpty.sites.siteID) will use the datasetID
and the siteID WITHOUT the index value included, so it doesn't matter if the index is being calculated
or not.

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
    def __init__(
        self, root_id: Optional[str], index: int = 0, index_in_progress: bool = False
    ):
        """Constructor for IDValue

        Args:
            root_id (Optional[str]): The ID value, without the added index. If None then this ID is considered to
                be empty (and will be replaced with a non-empty IDValue object in the future).
            index (int, optional): The index to add at the end of the ID, which is added to ensure that primary
                keys are unique and do not conflict with other primary keys. If 0 then no index is added after
                the ID. To get the full string of the ID with the index pass the IDValue object to the str() function
                (ie. str(idvalue_obj)). Defaults to 0.
            index_in_progress (bool, optional): Set to True if the caller is currently calculating the index for
                this object, False if the caller isn't calculating the index.
        """
        self._root_id: Optional[str] = root_id
        self._index: int = index
        # _str_value is the value returned by str(self)
        # _repr_value is the value returned by repr(self)
        # We calculate these values on-demand as an optimization
        self._str_value: Optional[str] = None
        self._repr_value: Optional[str] = None
        self._index_in_progress: bool = index_in_progress

    def __str__(self) -> str:
        if self._str_value is None:
            self._str_value = self.make_id_str(self._root_id, self._index)
        return self._str_value

    @classmethod
    def make_id_str(self, unindexed_value: str, index: str) -> str:
        index_str = f"{index:03d}" if index else ""
        return f"{unindexed_value}{index_str}"

    def __repr__(self) -> str:
        if self._repr_value is None:
            self._repr_value = (
                f"<{type(self).__name__}:{str(self)} object at {hex(id(self))}>"
            )
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

    @property
    def index_in_progress(self) -> bool:
        """Determine if we are currently calculating the index of this ID.

        Returns:
            bool: True if we are currently calculating the index of this ID, False otherwise.
        """
        return self._index_in_progress

    @index_in_progress.setter
    def index_in_progress(self, index_in_progress: bool):
        """Set if we are calculating the index of this ID or not.

        Args:
            index_in_progress (bool): True if we are calculating the index, False if we are not.
        """
        self._index_in_progress = index_in_progress
