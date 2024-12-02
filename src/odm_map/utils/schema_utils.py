# %%
"""
Utility functions for LinkML schemas.
"""

import os
from typing import Dict, List, Union, Optional
from dataclasses import asdict
import yaml
import pandas as pd
from pathlib import Path
import numpy as np

from linkml_runtime import SchemaView

from odm_map.utils.logger import make_logger_bullet_list
from odm_map.utils.general_utils import (
    choose_ignore_case_value,
    EXCEL_FILE_KEY,
    EXCEL_SHEET_KEY,
)


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


def get_excel_file_classes(
    file: Union[str, Path], schema: Union[SchemaView, str, Path] = None
) -> Dict[str, List[Dict[str, str]]]:
    file = Path(file)

    if isinstance(schema, (str, Path)):
        schema = SchemaView(schema)

    # Load all sheet names from Excel file
    with pd.ExcelFile(file) as xl:
        sheet_names = list(xl.sheet_names)

    # Map the sheet names to class names
    sheet_to_class = {
        sheet_name: get_class_name_from_file_name(sheet_name, schema)
        for sheet_name in sheet_names
    }
    # Remove any sheet that maps to no class
    sheet_to_class = {s: c for s, c in sheet_to_class.items() if c is not None}

    # Create the results dictionary
    results = {}
    for sheet_name, class_name in sheet_to_class.items():
        if class_name not in results:
            results[class_name] = []
        results[class_name].append({EXCEL_FILE_KEY: file, EXCEL_SHEET_KEY: sheet_name})

    return results


def validate_columns_with_schema(
    df: pd.DataFrame,
    schema: Union[SchemaView, str, Path],
    class_name: str,
    file: Union[str, Path],
) -> List[str]:
    warning_log = []

    if isinstance(schema, (str, Path)):
        schema = SchemaView(schema)

    class_defn = schema.induced_class(class_name)

    # Check for missing required columns
    required_missing_attributes = sorted(
        [
            attr
            for attr, defn in class_defn.attributes.items()
            if attr not in df.columns and defn.required
        ],
        key=lambda x: str(x).lower(),
    )
    # Check for missing (but not required) columns
    not_required_missing_attributes = sorted(
        [
            attr
            for attr, defn in class_defn.attributes.items()
            if attr not in df.columns and not defn.required
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
    unrecognized_attributes = [
        attr for attr in df.columns if attr not in all_attributes
    ]
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
    return warning_log


def get_class_name_from_file_name(
    file_name: Union[str, Path], schema: Optional[SchemaView] = None
) -> str:
    """Get the LinkML class name based on a data file name.

    The extension is ignored, the directory is ignored, and any text after the first opening square or round
    bracket is ignored.

    Args:
        file_name (Union[str, Path]): The file name to extract the class name from. The extension is removed,
            as well as any text after the first opening square or round bracket.
        schema (Optional[SchemaView], optional): If set, then we search the basename of file_name for
            the class name. The longest class name that matches in file_name is used. We also correct
            for capitalization. If this is not set, then we use the file name as the class, without
            correcting for capitalization. In this case, it's possible that an unrecognized class name
            is returned. Defaults to None.

    Returns:
        str: The class name for the data file.
    """
    base_name = os.path.splitext(os.path.basename(file_name))[0]
    class_name = base_name.split("[")[0].split("(")[0]
    if schema is not None:
        # class_name = choose_ignore_case_value(
        #     class_name, all_classes_without_tree_root(schema)
        # )
        all_classes = all_classes_without_tree_root(schema)
        all_classes_lower = [c.lower() for c in all_classes]
        match_lower = class_name.lower()
        matches = [c for c in all_classes_lower if c in match_lower]
        if len(matches) == 0:
            return None
        matched = matches[np.argmax([len(c) for c in matches])]
        return choose_ignore_case_value(matched, all_classes)
    return class_name
