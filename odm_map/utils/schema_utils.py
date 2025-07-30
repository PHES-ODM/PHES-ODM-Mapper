# %%
"""
Utility functions for LinkML schemas.
"""

from typing import Dict, List, Union, Optional
from dataclasses import asdict
import yaml
from pathlib import Path
import numpy as np

from linkml_runtime import SchemaView

from odm_map.utils.logger import make_logger_bullet_list
from odm_map.utils.general_utils import (
    choose_ignore_case_value,
)
from odm_map.utils.logger import get_logger

logger = get_logger(__name__)


def all_primary_keys(schema: SchemaView) -> Dict[str, str]:
    """Get a dictionary containing the primary key for all non-treeroot classes in the schema.

    Args:
        schema (SchemaView): The schema that we want the primary keys of.

    Returns:
        Dict[str, str]: A dictionary where the keys are the class names and the values are the
            single primary key of the class.
    """
    all_classes = all_classes_without_tree_root(schema)
    primary_keys = {}
    for cur_class in all_classes:
        class_defn = schema.induced_class(cur_class)
        class_primary_keys = []
        for attr, attr_defn in class_defn.attributes.items():
            if attr_defn.identifier:
                class_primary_keys.append(attr)

        if len(class_primary_keys) > 1:
            logger.warning(
                f"Class '{cur_class}' can only have one primary key, instead found {len(class_primary_keys)}: {class_primary_keys}"
            )
        if len(class_primary_keys) == 0:
            raise ValueError(
                f"Class '{cur_class}' must have at least one primary key, none were found."
            )
        primary_keys[cur_class] = class_primary_keys[0]

    # Sort the keys
    primary_keys = dict(sorted(primary_keys.items()))

    return primary_keys


def all_classes_without_tree_root(schema: SchemaView) -> List[str]:
    """Get a list of all classes in the schema, excluding the tree root class that contains
    all the classes.

    Args:
        schema (SchemaView): The Schema to get the classes of.

    Returns:
        List[str]: List of all classes belonging to the schema, excluding the tree root class.
    """
    classes = [str(c) for c, defn in schema.all_classes().items() if not defn.tree_root]
    return classes


def get_slot_definition(cls: str, slot: str, schema: SchemaView) -> Dict:
    """Get the full definition for the slot. This includes fields that are attributes of the class.
    If a slot is modified with a slot_usage, then we also update the returned dictionary with the
    slot usage information.

    Args:
        cls (str): The class that contains the slot.
        slot (str): The slot name to get the definition for.
        schema (SchemaView): The Schema the class and slot belong to.

    Returns:
        Dict: The dictionary with all information about the slot (eg. the name, range, pattern, etc).
            If the slot is not a member of the class then None is returned.
    """
    class_definition = schema.induced_class(cls)
    if slot in class_definition.attributes:
        return asdict(class_definition.attributes[slot])
    return None


def get_ranges_of_slot(cls: str, slot: str, schema: SchemaView) -> List[str]:
    """Get the range(s) (if any) of the slot in the specified class.

    Args:
        cls (str): The class that the slot belongs to.
        slot (str): The slot to get the range for.
        schema (SchemaView): The Schema to retrieve the slot info from.

    Returns:
        List[str]: A list of range(s) for the specified slot, if at least one range exists. If
            no range is found (eg. the class or slot are invalid) then None is returned.
    """
    defn = get_slot_definition(cls, slot, schema)

    if defn is not None:
        defn = defn.get("range", None)
        if defn is not None:
            # defn is of type linkml_runtime.linkml_model.meta.ElementName
            # We need to convert it to either type str or type List[str]
            defn = yaml.safe_load(str(defn))

    if isinstance(defn, str):
        defn = [defn]

    return defn


def validate_columns_with_schema(
    columns: List[str],
    schema: Union[SchemaView, str, Path],
    class_name: str,
    file: Union[str, Path],
    show_log: bool = True,
) -> List[str]:
    """Check for missing or unrecognized columns in the DataFrame. If missing or unrecognized
    columns are found then they are returned to the caller as a list of logging messages, so that
    the results can be reported to the user. No exception or other error occurs. It is for
    informational purposes.

    Args:
        columns (List[str]): The list of columns to validate (usually from a DataFrame).
        schema (Union[SchemaView, str, Path]): The SchemaView that defines the class
            that the DataFrame belongs to. It will provide all known columns for the class.
        class_name (str): The class (in the schema) that df belongs to.
        file (Union[str, Path]): The file that the DataFrame was loaded from. This is so
            we can tell the user which file has missing or unrecognized columns.
        show_log (bool): If True then output logger information that shows which columns
            were missing and which columns were unrecognized. If False then do not output
            the log, but instead return a list of strings representing the log.

    Returns:
        List[str]: A list of messages that say which columns in the DataFrame are missing
            or unrecognized. If there are no missing or unrecognized columns then
            this is empty ([]).
    """
    columns = list(columns)
    warning_log = []

    if isinstance(schema, (str, Path)):
        schema = SchemaView(schema)

    class_defn = schema.induced_class(class_name)

    # Check for missing required columns
    required_missing_attributes = sorted(
        [
            attr
            for attr, defn in class_defn.attributes.items()
            if attr not in columns and defn.required
        ],
        key=lambda x: str(x).lower(),
    )
    # Check for missing (but not required) columns
    not_required_missing_attributes = sorted(
        [
            attr
            for attr, defn in class_defn.attributes.items()
            if attr not in columns and not defn.required
        ],
        key=lambda x: str(x).lower(),
    )
    if required_missing_attributes or not_required_missing_attributes:
        # There are some missing attributes, tell the user
        missing_attributes = [
            f"{r} (REQUIRED)" for r in required_missing_attributes
        ] + not_required_missing_attributes
        missing_attributes_str = make_logger_bullet_list(missing_attributes)
        warning_log.append(
            f"The following columns are missing in table '{class_name}' and will be treated as blank from file {file}:\n{missing_attributes_str}"
        )

    # Check for extra unrecognized columns
    all_attributes = list(class_defn.attributes.keys())
    unrecognized_attributes = [attr for attr in columns if attr not in all_attributes]
    if unrecognized_attributes:
        # Collect any recommended renaming of attributes (based purely on capitalization. eg. If
        # sampleID is a recognized attribute but the DataFrame has an attribute named SampleID, then
        # we will recommend to the user to rename it to sampleID)
        recommended = [
            choose_ignore_case_value(c, all_attributes, return_same_if_missing=False)
            for c in unrecognized_attributes
        ]
        unrecognized_with_recommended = [
            f"{c}%s" % (f" (Recommended column name: {r})" if r else "")
            for c, r in zip(unrecognized_attributes, recommended)
        ]
        unrecognized_with_recommended_str = make_logger_bullet_list(
            sorted(
                unrecognized_with_recommended,
                key=lambda x: str(x).lower(),
            )
        )
        warning_log.append(
            f"The following unrecognized columns were found and will be ignored in table '{class_name}' from file {file}:\n{unrecognized_with_recommended_str}"
        )

    if show_log:
        for msg in warning_log:
            logger.warning(msg)

    return warning_log


def remove_ignored_text_from_class_name(class_name: str) -> str:
    """Remove any text to ignore when trying to identify a class name within a string.

    This will remove all text after the first opening square or round bracket.

    Args:
        class_name (str): The class name string candidate to clean up.

    Returns:
        str: The string class_name with text we should ignore removed. After
            cleaning up the string we can search for a class name in the cleaned
            string.
    """
    return class_name.split("[")[0].split("(")[0]


def find_class(
    class_name: str, schema: Optional[SchemaView], ignore_case: bool
) -> Optional[str]:
    """Figure out which class the class_name string should belong to, making the search
    fairly flexible. We will typically search for a recognized class name in the string,
    so for example "1 - WWMeasure (2024-11-30)" would map to the class "WWMeasure".
    For a stricter search, where the whole string (after cleaning) must match a recognized class,
    see get_class().

    For cleaning, any text after the first opening square or round bracket in class_name is
    ignored.

    The matching class is the longest class name in the schema that can be found
    in the string class_name (eg. If "WWMeasure" and "Measure" are both classes in
    the schema, then the string "1 - WWMeasure" will match to "WWMeasure", even
    though "Measure" is found in the string, because "WWMeasure" is longer).

    If schema is None, then the class_name is cleaned but we return the cleaned class_name
    without searching for class name strings within the class_name (since we need schema
    to know which classes are valid classes)

    Args:
        class_name (str): The string to search for the class name. Any text after the
            first opening square or round bracket in class_name is ignored.
        schema (Optional[SchemaView], optional): The schema containing all the recognized
            classes. Can be None.
        ignore_case (bool): If True then make the search case-insensitive, otherwise
            make it case-sensitive.

    Returns:
        Optional[str]: The class that the string should represent, or None if no
            class was found.
    """
    class_name = remove_ignored_text_from_class_name(class_name)

    if schema is None:
        return class_name

    all_classes = all_classes_without_tree_root(schema)

    all_classes_lower = [c.lower() for c in all_classes] if ignore_case else all_classes
    match_lower = class_name.lower() if ignore_case else class_name

    # Find all matches
    matches = [c for c in all_classes_lower if c in match_lower]
    if len(matches) == 0:
        return None
    # Match found, so get the longeset matching class name
    matched = matches[np.argmax([len(c) for c in matches])]

    # Correct capitalization of class
    return choose_ignore_case_value(matched, all_classes)


def get_class(
    class_name: str, schema: Optional[SchemaView], ignore_case: bool
) -> Optional[str]:
    """Get the recognized class name based on the string class_name (optionally case-
    sensitive or case-insensitive), or None if the class name does not exist.

    Any text after the first opening square or round bracket in class_name is
    ignored.

    If schema is None, then we simply return the cleaned text as a class name,
    since we need schema to know which class names are valid.

    Args:
        class_name (str): The string to get the class name for. Any text after the
            first opening square or round bracket in class_name is ignored.
        schema (Optional[SchemaView], optional): The schema that contains all the
            recognized classes. If None then we simply return the cleaned class_name
            (since we need schema to know which class names are valid)
        ignore_case (bool): If True then make class_name case-insensitive, but return
            the class name with the correct capitaliztion. If False then only
            return the recognized class if class_name already has the correct
            capitalization.

    Returns:
        Optional[str]: The recognized class name, or None if class_name is not
            a recognized class name in the schema. If schema is None, then we
            clean class_name (remove text after the first opening round or
            square bracket) and return the value without checking if it is
            a valid class name.
    """
    class_name = remove_ignored_text_from_class_name(class_name)

    if schema is None:
        return class_name

    all_classes = all_classes_without_tree_root(schema)

    if ignore_case:
        # Case-insensitive
        return choose_ignore_case_value(
            class_name, all_classes, return_same_if_missing=False
        )
    else:
        # Case-sensitive, so only return exact match
        if class_name in all_classes:
            return class_name
        return None
