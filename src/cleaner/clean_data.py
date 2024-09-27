# %%
"""
Utility functions for cleaning data.

fix_data_with_schema will make sure column names have the correct capitalization (ie. they match the slots in the schema).
It will also go through all columns that are enumerations and correct the capitalization of all values in the column.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path
import pandas as pd
import os
import argparse
from typing import Tuple, List, Union, Optional, Dict

from linkml_runtime import SchemaView

from utils.general_utils import (
    read_data_frame,
    save_data_frame,
    get_logger,
    choose_ignore_case_value,
    clear_dirs,
    get_unique_output_file,
)
from utils.cli_utils import get_input_data_files
from utils.schema_utils import get_ranges_of_slot

# If True and max_rows is specified in clean_data_file, then when loading the input dataset, load the
# full dataset then take a random sample from it. Note that the random state (seed) is kept constant
# when selecting a random sample, so the same rows will be loaded for the same values of max_rows.
# If False then load the first max_rows samples (which is faster).
RANDOM_SAMPLE_DATA = False

logger = get_logger(__name__)


def fix_data_with_schema(
    df: pd.DataFrame, class_name: str, schema: SchemaView
) -> pd.DataFrame:
    """Using the specified schema, do some basic cleanup of the DataFrame so that it better matches
    the requirements of the schema. We will make sure the column names and enumeration values have the
    correct capitalization, and drop any columns that are not recognized by the schema.

    Args:
        df (pd.DataFrame): The DataFrame to clean up. The original is left unchanged (a copy is returned).
        class_name (str): The class name of the table.
        schema (SchemaView): The LinkML schema to use for making any corrections to the data.

    Returns:
        pd.DataFrame: A copy of the DataFrame, with the basic cleanup performed.
    """
    if class_name not in schema.all_classes():
        logger.info(
            f"Not fixing data for class {class_name} since class is not recognized"
        )
        return df

    logger.info(f"Fixing data for class {class_name}")
    df = df.copy()

    class_definition = schema.induced_class(class_name)

    # Fix up column names (Use correct capitalization)
    df.columns = [
        choose_ignore_case_value(col, list(class_definition.attributes.keys()))
        for col in df.columns
    ]

    # Fix enumerations (Use correct capitalization), and only keep recognized slots
    keep_columns = []
    for slot_name in df.columns:
        if slot_name not in class_definition.attributes:
            continue
        keep_columns.append(slot_name)
        slot_ranges = get_ranges_of_slot(class_name, slot_name, schema)

        if slot_ranges:
            for slot_range in slot_ranges:
                # Get enumeration for the slot range, if there is one, and fix up the capitalization of all slot values.
                enum = schema.all_enums().get(str(slot_range), None)
                if enum is not None:
                    permissible_values = list(enum.permissible_values.keys())
                    lowercase_permissible_values = [
                        v.lower() for v in permissible_values
                    ]
                    df[slot_name] = df[slot_name].apply(
                        lambda x: choose_ignore_case_value(
                            x,
                            permissible_values,
                            lowercase_permissible_values,
                            return_same_if_missing=True,
                        )
                    )

    return df[keep_columns]


def fix_data_no_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Do some general fixes to the DataFrame. This includes converting dates and datetimes to proper format
    (as recognized by LinkML), and converting booleans to "true"/"false" strings. These are all fixes
    that are independent of any LinkML schema.

    Args:
        df (pd.DataFrame): The DataFrame to fix.

    Returns:
        pd.DataFrame: The fixed DataFrame. The original is left unchanged, this is a copy.
    """
    # df = df.copy()
    # for col in df.columns:
    #     if df[col].dtype != object:
    #         continue
    #     try:
    #         # First try to parse a date without time, then convert back to a string
    #         # recognizable by linkml as a date
    #         df[col] = pd.to_datetime(df[col], format="%Y-%m-%d").dt.strftime("%Y-%m-%d")
    #     except Exception:
    #         try:
    #             # Try to prase a date with time in ISO8601 format, then convert back to a string
    #             # recognizable by linkml as a datetime
    #             df[col] = pd.to_datetime(df[col], format="ISO8601", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    #         except Exception:
    #             ...
    #     # @TODO: We don't need this! Only ODM v2 uses lowercase "true"/"false" strings, but we should
    #     # not have specialized code to fix this.
    #     # Convert bools (True/False) to strings ('true'/'false')
    #     for col in df.columns:
    #         if df[col].dtype == bool:
    #             df[col] = df[col].astype(str)
    #             df.loc[df[col] == "True", col] = "true"
    #             df.loc[df[col] == "False", col] = "false"

    return df


def clean_data_file(
    input_file: Union[str, Path],
    output_file: Optional[Union[str, Path]],
    class_name: str,
    schema: Optional[Union[str, Path, SchemaView]] = None,
    max_rows: Optional[int] = 0,
) -> Tuple[str, pd.DataFrame]:
    """Clean the specified file and save to the specified output directory. The file should be a tsv, csv, or txt
    file (txt files are treated as tab-separated).

    Args:
        input_file (Union[str, Path]): The file to clean.
        output_file (Optional[Union[str, Path]]): The file to save the cleaned data file to. This should
            be different than the input_file to avoid overwriting the original.
        class_name (str): The class name that the input_file is for. This should be a class name found in
            the schema.
        max_rows (Optional[int]): Maximum nuimber of rows to load and clean from the file. If 0 then clean
            all rows. Defaults to 0.
        schema (Optional[Union[str, Path, SchemaView]]): If specified the path to a schema file. We will
            do some minor cleanup of the data to conform better to the schema (eg. fixing capitalization of
            columns and enumerations). If None then no cleanup is performed. Defaults to None.

    Returns:
        Tuple[str, pd.DataFrame]: A tuple of (new file name, data frame). The DataFrame
            is the contents of the file with any required processing performed (eg.
            putting dates and datetimes into the correct string format)
    """
    if output_file == input_file:
        raise ValueError(
            f"The input_file and output_file must be different: {input_file=}, {output_file=}"
        )

    if isinstance(schema, (str, Path)):
        schema = SchemaView(schema)

    if os.path.dirname(output_file):
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

    logger.info(f"Fixing data from {input_file}")

    # Read the DataFrame from disk
    df = read_data_frame(
        input_file,
        nrows=None if RANDOM_SAMPLE_DATA else (max_rows if max_rows else None),
        keep_default_na=False,
        na_values=[""],
    )

    if RANDOM_SAMPLE_DATA and max_rows and len(df) > max_rows:
        df = df.sample(max_rows, random_state=0).reset_index(drop=True)

    # Fix the data
    df = fix_data_no_schema(df)
    if schema:
        df = fix_data_with_schema(df, class_name, schema=schema)

    # Save to disk
    logger.info(f"Saving fixed data to {output_file}")
    save_data_frame(df, output_file, index=False)

    return output_file, df


def clean_data_files(
    data_files: Dict[str, Union[str, Path]],
    output_dir: Union[str, Path],
    schema: Optional[Union[str, Path, SchemaView]] = None,
    max_rows: int = 0,
) -> Dict[str, List[str]]:
    """Clean all TSV, TXT, and CSV data files specified data_files dictionary and save the cleaned data
    to the specified output directory, ensuring that all output files names are unique and no existing
    file in output_dir is modified.

    Cleaning involves
    changing the format of dates, making sure columns are capitalized correctly, and making sure enumerations are capitalized correctly.

    Args:
        data_files (Dict[str, Union[str, Path]]): Dictionary of all TSV/TXT/CSV files to clean. The keys are
            the class name for the data file and the values are lists of file paths.
        output_dir (Union[str, Path]): Output directory to save the cleaned data files to. To avoid overwriting
            files in data_files that have the same name, we ensure that all output files have unique file names.
            The returned dictionary will contain the updated file name, if a file name is changed.
        max_rows (int): Maximum number of rows to load and clean for each file. If 0 then clean all rows.
            Defaults to 0.
        schema (Optional[Union[str, Path, SchemaView]]): If specified the path to a schema file. We
            will do some minor cleanup of the data to conform better to the schema (eg. fixing
            capitalization of columns and enumerations). If None then no cleanup is performed.
            Defaults to None.

    Returns:
        Dict[str, List[str]]: Dictionary of all outputed cleaned data files. The keys are the class name
            the file belongs to and the values are lists of files. This is the same as the parameter
            data_files, but with the lists of files being a list of the cleaned files.
    """
    output_data_files = {}

    for class_name, input_files in data_files.items():
        output_data_files[class_name] = []
        for input_file in input_files:
            output_file = os.path.join(output_dir, os.path.basename(input_file))

            # Make sure the output file doesn't already exist
            output_file = get_unique_output_file(output_file)

            output_file, _ = clean_data_file(
                input_file,
                output_file,
                class_name=class_name,
                schema=schema,
                max_rows=max_rows,
            )
            output_data_files[class_name].append(Path(output_file))

    return output_data_files


if __name__ == "__main__":
    if "get_ipython" in globals():

        class opts:
            input_data_dir = "../../../../PHES-ODM-Data/odm_v1_data/centreau_qc/updated"
            input_data_files = None
            output_dir = "../../gen/odm_v1_to_v2/cleaned_data"
            max_rows = 1000
            schema = "../../data/modules/odm_v1_to_v2/schemas/odm_v1.yaml"
            # schema = "../../data/nwss_reporting/linkml/nwss_reporting.yaml"
    else:
        args = argparse.ArgumentParser(
            formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
        args.add_argument(
            "--input_data_dir",
            type=str,
            help="Clean all csv, txt, and tsv files in this directory. txt files are treated as tab-separated",
            required=False,
        )
        args.add_argument(
            "--input_data_files",
            nargs="+",
            type=str,
            help="List of all input files and the source class for each file. Format is 'class_name file.csv [class_name2 file2.csv ...]'",
            required=False,
        )
        args.add_argument(
            "--output_dir",
            type=str,
            help="Save results to this directory",
            required=True,
        )
        args.add_argument(
            "--max_rows",
            type=int,
            help="Maximum number of rows to load and clean. If 0 then clean all rows. Default is 0.",
            default=0,
            required=False,
        )
        args.add_argument(
            "--schema",
            type=str,
            help="Schema file that the data conforms to. We will do some basic cleanup to the data based on this schema (eg. correcting capitalization of classes and enums). We assume the file name of the file being cleaned is the class name for the data. If no schema provided then only basic cleanup is performed",
            required=False,
        )
        opts = args.parse_args()

    clear_dirs([opts.output_dir])

    data_files = get_input_data_files(opts.input_data_files, opts.input_data_dir)
    d = clean_data_files(
        data_files,
        output_dir=opts.output_dir,
        max_rows=opts.max_rows,
        schema=opts.schema,
    )
    print(d)

    logger.info("Finished!")
