"""
Provide a global object (EMPTY_OBJ) that can be used in a Numpy array (or Pandas DataFrame) to represent a NA value (eg. float("NaN"), None, etc).
Typically, we would replace all NA values in a Numpy array with EMPTY_OBJ, which would then make comparisons
easier. For example:

None == float("NaN") is False

But if we replace all NAs with EMPTY_OBJ, we would get:

EMPTY_OBJ == EMPTY_OBJ is True
"""

from typing import Any

import pandas as pd


class EmptyObject:
    def __init__(self):
        pass

    def __str__(self) -> str:
        return ""

    def __repr__(self) -> str:
        return f"<{type(self).__name__} object at {hex(id(self))}>"


EMPTY_OBJ = EmptyObject()


def isna(v: Any) -> bool:
    """Test if a value is a NA value. This performs both a test to see if v is NA by calling pd.isna(v) and also
    a test if v is EMPTY_OBJ.

    Args:
        v (Any): The value to test.

    Returns:
        bool: True if v is an NA value, False otherwise.
    """
    if isinstance(v, list):
        return len([i for i in v if not isna(i)]) == 0
    return pd.isna(v) or v is EMPTY_OBJ
