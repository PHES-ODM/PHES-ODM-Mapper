"""
The SchemaCaster tries to cast values (either in a DataFrame or individual values) according to the type of the
class and slot that the value belongs to, according to a LinkML schema.

# Usage

```python
schema_caster = SchemaCaster("path/to/schema.yaml")

# The following will cast all values in all columns of df, according to the types of the columns
new_df = schema_caster.cast_df(df, "sites", inline=False)

# The following will return the float 12.3 (if geoLat is a float)
new_v = schema_caster.cast_value("12.3", "sites", "geoLat")
```
"""

from typing import Union, Any, Dict, Callable
from pathlib import Path
import pandas as pd
import yaml
from functools import partial

from linkml_runtime import SchemaView

from odm_map.utils.general_utils import make_multivalued
from odm_map.utils.schema_utils import all_classes_without_tree_root


class SchemaCaster:
    def __init__(self, schema: Union[str, Path, SchemaView]):
        if isinstance(schema, (Path, str)):
            schema = SchemaView(schema)
        self.schema = schema

        self.cast_functions = self.get_cast_functions(self.schema)

    def _cast_types(self, v: Any, multivalued: bool, cast_types: str) -> Any:
        """Try to cast a value to the types specified in cast_types. We iterate over all cast types until
        the casting works without throwing an exception. If none of the casting works then the value is returned
        unchanged.

        Args:
            v (Any): The value to cast.
            multivalued (bool): If True then cast as multivalued. Ie. We create an array.
            cast_types (str): A list of the cast types to try. Can have the values "float", "integer", or
            "string". Any other value will be treated as a string (eg. if the cast type is a LinkML enumeration,
            then it will be cast as a string).

        Returns:
            Any: The cast value, or the value unchanged if it could not be cast.
        """
        if not isinstance(v, (list, tuple)) and pd.isna(v):
            return v

        if multivalued:
            v = make_multivalued(v)

        for cast_type in cast_types:
            # The default cast function is str, this will deal with enums and other types
            cast_func = {
                "float": float,
                "integer": int,
                "string": str,
            }.get(cast_type, str)
            try:
                if multivalued and isinstance(v, list):
                    # @TODO: Should we keep uncastable elements?
                    return [cast_func(i) for i in v]
                return cast_func(v)
            except Exception:
                pass
        return v

    def get_cast_functions(self, schema: SchemaView) -> Dict[str, Dict[str, Callable]]:
        """Get a dictionary specifying how all slots/attributes in all classes of the schema should
        be cast, according to the range of the slot.

        The keys of the returned dictionary are all the class names in the schema, and the values are
        sub-dictionaries specifying how values in the slots of the class should be cast.
        The sub-dictionaries have keys that are slot names (or attribute names) in the class,
        and the values are functions that take a single parameter to cast a value. For example,
        the function might be float, int, or str.

        Args:
            schema (SchemaView): The schema to get the casting functions for.

        Returns:
            Dict[str, Dict[str, Callable]]: Dictionary of all casting functions. Keys are the schema
                class names, values are dictionaries where keys are the slot names and values are
                the casting functions (that take a single parameter to cast).
        """
        cast_functions = {}
        # Loop through all classes in the schema
        for class_name in all_classes_without_tree_root(schema):
            class_defn = schema.induced_class(class_name)

            # Add the sub-dictionary for the current class name
            cast_functions[class_name] = {}

            # Loop through all attributes in the current class and add the casting functions
            # to cur_cast_functions. Note that induced classes have converted all slots to
            # attributes.
            cur_cast_functions = cast_functions[class_name]
            for slot_name in class_defn.attributes:
                # Get the range of the slot. It is a string (even if it's a list of ranges),
                # so we must convert it to a list using yaml. If it is not a list then
                # yaml will just keep it as a string.
                slot_defn = schema.induced_slot(
                    slot_name=slot_name, class_name=class_name
                )
                multivalued = slot_defn.multivalued

                rng = yaml.safe_load(str(slot_defn.range))
                # Add the casting function according to the range
                if isinstance(rng, list):
                    # Order of a multi-range should be float, int, string. This will ensure
                    # that we don't lose decimals by trying to cast to an int first. Anything
                    # that is not a float or int will be ordered according to the position of "*"
                    # (this includes enumeration names).
                    order = ["float", "int", "*"]
                    rng = sorted(
                        rng,
                        key=lambda x: (
                            order.index(x) if x in order else order.index("*")
                        ),
                    )
                    cur_cast_functions[slot_name] = partial(
                        self._cast_types, multivalued=multivalued, cast_types=rng
                    )
                elif rng in ["float", "double"]:
                    cur_cast_functions[slot_name] = partial(
                        self._cast_types, multivalued=multivalued, cast_types=["float"]
                    )
                elif rng == "integer":
                    cur_cast_functions[slot_name] = partial(
                        self._cast_types,
                        multivalued=multivalued,
                        cast_types=["integer"],
                    )
                else:
                    cur_cast_functions[slot_name] = partial(
                        self._cast_types, multivalued=multivalued, cast_types=["string"]
                    )
        return cast_functions

    def cast_df(
        self, df: pd.DataFrame, class_name: str, inline: bool = True
    ) -> pd.DataFrame:
        """Cast the values in the DataFrame according to the LinkML schema, using the specified
        class.

        Values that cannot be cast are left unchanged.

        Args:
            df (pd.DataFrame): The DataFrame to cast the values of.
            class_name (str): The class name that the DataFrame belongs to. This should be a
                class name found in the LinkML schema specified in the constructor.
            inline (bool, optional): If True then modify the DataFrame inplace (and return the
                modified DataFrame). If False the keep the original DataFrame unchanged and cast
                a copy of it (and return the copy). Defaults to True.

        Returns:
            pd.DataFrame: The casted DataFrame. If inline is True then the same value passed
                in as df is returned. If inline is False then a copy of df (with values
                casted) is returned, and the passed in DataFrame is left unchanged.
        """
        if not inline:
            df = df.copy()
        cur_cast_functions = self.cast_functions[class_name]
        for col, cast_func in cur_cast_functions.items():
            if col in df.columns:
                df[col] = df[col].apply(lambda v: cast_func(v))
        return df

    def cast_value(self, v: Any, class_name: str, slot_name: str) -> Any:
        """Cast the specified value, that belongs to the specified class and slot.

        Values that cannot be cast are left unchanged.

        Args:
            v (Any): The value to cast.
            class_name (str): The class in the LinkML schema that the value belongs to.
            slot_name (str): The slot within the class, in the LinkML schema, that the
                value belongs to.

        Returns:
            Any: The casted value. If the value can't be cast then the value is returned
                unchanged.
        """
        cur_cast_function = self.cast_functions[class_name][slot_name]
        return cur_cast_function(v)
