# %%
"""
Class for cleaning data.

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
from utils.tracking_slots import get_all_tracking_slots
from utils.cli_utils import get_input_data_files
from utils.schema_utils import get_ranges_of_slot

# If True and max_rows is specified in clean_data_file, then when loading the input dataset, load the
# full dataset then take a random sample from it. Note that the random state (seed) is kept constant
# when selecting a random sample, so the same rows will be loaded for the same values of max_rows.
# If False then load the first max_rows samples (which is faster).
RANDOM_SAMPLE_DATA = False

logger = get_logger(__name__)


class DataCleaner(object):
    def __init__(
        self,
        schema: Optional[Union[str, Path, SchemaView]] = None,
    ):
        if isinstance(schema, (str, Path)):
            self.schema = SchemaView(schema)

    def fix_data_with_schema(self, df: pd.DataFrame, class_name: str) -> pd.DataFrame:
        """Using the schema, do some basic cleanup of the DataFrame so that it better matches
        the requirements of the schema. We will make sure the column names and enumeration values have the
        correct capitalization, and drop any columns that are not recognized by the schema.

        Args:
            df (pd.DataFrame): The DataFrame to clean up. The original is left unchanged (a copy is returned).
            class_name (str): The class name of the table.

        Returns:
            pd.DataFrame: A copy of the DataFrame, with the basic cleanup performed.
        """
        if class_name not in self.schema.all_classes():
            logger.info(
                f"Not cleaning data for class {class_name} since class is not recognized"
            )
            return df

        logger.info(f"Cleaning data for class {class_name}")
        df = df.copy()

        class_definition = self.schema.induced_class(class_name)

        # Fix up column names (Use correct capitalization)
        df.columns = [
            choose_ignore_case_value(col, list(class_definition.attributes.keys()))
            for col in df.columns
        ]

        # changes_history stores a count of the changes made to enumeration values to correct for capitalization.
        # The keys are the slot name, and the values are a sub dictionary. The keys of the sub dictionary
        # are the change string (in the form "origEnumValue -> fixedEnumValue") and the values are the
        # counts of how many times that change was made.
        changes_history = {}

        # Fix enumerations (Use correct capitalization), and only keep recognized slots
        keep_columns = []
        all_tracking_slots = get_all_tracking_slots()
        for slot_name in df.columns:
            if slot_name in all_tracking_slots:
                keep_columns.append(slot_name)
                continue
            if slot_name not in class_definition.attributes:
                continue
            keep_columns.append(slot_name)
            slot_ranges = get_ranges_of_slot(class_name, slot_name, self.schema)

            if slot_ranges:
                for slot_range in slot_ranges:
                    # Get enumeration for the slot range, if there is one, and fix up the capitalization of all slot values.
                    enum = self.schema.all_enums().get(str(slot_range), None)
                    if enum is not None:
                        permissible_values = list(enum.permissible_values.keys())
                        lowercase_permissible_values = [
                            v.lower() for v in permissible_values
                        ]
                        df_orig = df[slot_name].copy()
                        df[slot_name] = df[slot_name].apply(
                            lambda x: choose_ignore_case_value(
                                x,
                                permissible_values,
                                lowercase_permissible_values,
                                return_same_if_missing=True,
                            )
                        )

                        # Keep a history of which enum values were changed
                        changes_filt = (df_orig != df[slot_name]) & (
                            ~pd.isna(df_orig) | ~pd.isna(df[slot_name])
                        )
                        if changes_filt.any():
                            # changes_str is "origEnumValue -> fixedEnumValue"
                            changes_str = (
                                df_orig[changes_filt]
                                + " -> "
                                + df[slot_name][changes_filt]
                            )
                            if slot_name not in changes_history:
                                changes_history[slot_name] = {}
                            slot_changes_history = changes_history[slot_name]
                            # Loop through all changes_str values, and increase the count for each
                            for change_key in changes_str:
                                if change_key not in slot_changes_history:
                                    slot_changes_history[change_key] = 0
                                slot_changes_history[change_key] += 1

        # Report the capitalization changes to the user
        for slot_name, slot_history in changes_history.items():
            for change_str, count in slot_history.items():
                slot_history[change_str] = f"{count} time{'s' if count != 1 else ''}"
            slot_history = [f"'{k}' {c}" for k, c in slot_history.items()]
            changes_str = "; ".join(slot_history)
            if changes_str:
                logger.info(
                    f"The following enumeration values were automatically corrected for capitalization in slot '{slot_name}' of class '{class_name}': {changes_str}"
                )

        return df[keep_columns]

    def fix_data_no_schema(self, df: pd.DataFrame) -> pd.DataFrame:
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

    def clean_single_data(
        self,
        data_file: Optional[Union[str, Path]],
        data_frame: Optional[pd.DataFrame],
        output_file: Optional[Union[str, Path]],
        class_name: str,
        max_rows: Optional[int] = 0,
    ) -> Tuple[str, pd.DataFrame]:
        """Clean either a single data file or a single DataFrame.

        Args:
            data_file (Optional[Union[str, Path]]): The file to clean. If specified then data_frame must be None.
            data_frame (Optional[pd.DataFrame]): The DataFrame to clean. If specified then data_file must be None.
            output_file (Optional[Union[str, Path]]): The file to save the cleaned data to. This should
                be different than the input_file to avoid overwriting the original. If None then the cleaned
                data is not saved to disk, but the cleaned DataFrame is still returned.
            class_name (str): The class name that the data_file or data_frame is for. This should be a class name found in
                the schema.
            max_rows (Optional[int]): Maximum number of rows to clean from the file or DataFrame. The returned DataFrame
                and save data will have at most this many rows. If 0 or None then clean all rows. Defaults to 0.

        Returns:
            Tuple[str, pd.DataFrame]: A tuple of (new file name, data frame). The DataFrame
                is the contents of the file with any required processing performed (eg.
                putting dates and datetimes into the correct string format)
        """
        if (
            output_file is not None
            and data_file is not None
            and output_file == data_file
        ):
            raise ValueError(
                f"The input file and output file must be different: {data_file=}, {output_file=}"
            )

        if output_file is not None and os.path.dirname(output_file):
            os.makedirs(os.path.dirname(output_file), exist_ok=True)

        if data_file is not None:
            logger.info(f"Cleaning data from {data_file}")

            # Read the DataFrame from disk
            df = read_data_frame(
                data_file,
                nrows=None if RANDOM_SAMPLE_DATA else (max_rows if max_rows else None),
                keep_default_na=False,
                na_values=None,  # [""],
            )
        else:
            df = data_frame

        if RANDOM_SAMPLE_DATA and max_rows and len(df) > max_rows:
            df = df.sample(max_rows, random_state=0).reset_index(drop=True)

        # Fix the data
        df = self.fix_data_no_schema(df)
        if self.schema:
            df = self.fix_data_with_schema(df, class_name)

        # Save to disk
        if output_file is not None:
            logger.info(f"Saving fixed data to {output_file}")
            save_data_frame(df, output_file, index=False)

        return output_file, df

    def clean_data(
        self,
        data_files: Dict[str, List[Union[str, Path]]],
        data_frames: Dict[str, List[pd.DataFrame]],
        output_dir: Union[str, Path],
        max_rows: int = 0,
    ) -> Tuple[Dict[str, List[str]], Dict[str, List[pd.DataFrame]]]:
        """Clean all data files and DataFrames and optionally save the cleaned data to the specified output
        directory, ensuring that all output files names are unique and no existing file in output_dir is modified.

        Cleaning involve making sure columns are capitalized correctly, and making sure enumerations are capitalized
        correctly, and possibly other operations.

        Args:
            data_files (List[Union[str, Path]]]): Dictionary of all data files to clean. The keys are
                the class names and the values are lists of file paths belonging to that class. Both data_files
                and data_frames are cleaned.
            data_frames (Dict[str, List[pd.DataFrame]]): Dictionary of all DataFrames to clean. The keys are
                the class names and the values are lists of DataFrames belonging to that class. Both data_files
                and data_frames are cleaned.
            output_dir (Union[str, Path]): Output directory to save the cleaned data files to. To avoid overwriting
                files in data_files that have the same name, we ensure that all output files have unique file names.
                The returned dictionary will contain the updated file name, if a file name is changed.
                If output_dir is None then the cleaned data is not saved to disk, and the cleaned DataFrames
                are returned.
            max_rows (int): Maximum number of rows to load and clean for each file. If 0 then clean all rows.
                Defaults to 0.

        Returns:
            Tuple[Dict[str, List[str]], Dict[str, List[pd.DataFrame]]]: A tuple of [cleaned_data_files, cleaned_data_frames]:
                cleaned_data_files: Dictionary of all outputed cleaned data files. The keys are the class name
                    the file belongs to and the values are lists of files. If output_dir is None then data_files will be
                    None (ie. no data saved to disk), instead see data_frames.
                cleaned_data_frames: Dictionary of all cleaned DataFrames. The keys are the class names and the
                    values are lists of cleaned DataFrames.
        """
        if output_dir:
            clear_dirs([output_dir])

        output_data_files = {}
        output_data_frames = {}

        for all_data in [data_files, data_frames]:
            if not all_data:
                continue
            for class_name, sub_data in all_data.items():
                if class_name not in output_data_files:
                    output_data_files[class_name] = []
                if class_name not in output_data_frames:
                    output_data_frames[class_name] = []
                for data in sub_data:
                    data_file = data if isinstance(data, (str, Path)) else None
                    data_frame = data if isinstance(data, pd.DataFrame) else None
                    assert (data_file is None) != (data_frame is None)

                    if output_dir is not None:
                        if data_file:
                            output_file = os.path.join(
                                output_dir, os.path.basename(data_file)
                            )
                        else:
                            output_file = os.path.join(output_dir, f"{class_name}.csv")
                        # Make sure the output file doesn't already exist
                        output_file = get_unique_output_file(output_file)
                    else:
                        output_file = None

                    output_file, output_data_frame = self.clean_single_data(
                        data_file=data_file,
                        data_frame=data_frame,
                        output_file=output_file,
                        class_name=class_name,
                        max_rows=max_rows,
                    )
                    output_data_files[class_name].append(
                        Path(output_file) if output_file else None
                    )
                    output_data_frames[class_name].append(output_data_frame)

        return output_data_files, output_data_frames


if __name__ == "__main__":
    if "get_ipython" in globals():
        # fmt: off
        class opts:
            # input_data_dir = "../../../../PHES-ODM-Data/odm_v1_data/centreau_qc/updated"
            # input_data_files = None
            # output_dir = "../../gen/odm_v1_to_v2-test/cleaned_data"
            # max_rows = 100
            # schema = "../../data/modules/odm_v1_to_v2/schemas/odm_v1.yaml"

            input_data_dir = "../../../../PHES-ODM-Data/nwss/nwss_renamed/"
            input_data_files = None
            output_dir = "../../gen/nwss_reporting_to_v2-test/cleaned_data"
            max_rows = 100
            schema = "../../data/modules/nwss_reporting_to_v2/schemas/nwss_reporting.yaml"
        # fmt: on
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

    data_files = get_input_data_files(opts.input_data_files, opts.input_data_dir)
    cleaner = DataCleaner(schema=opts.schema)
    data_files, data_frames = cleaner.clean_data(
        data_files=data_files,
        data_frames=None,
        output_dir=opts.output_dir,
        max_rows=opts.max_rows,
    )

    logger.info("Finished!")
