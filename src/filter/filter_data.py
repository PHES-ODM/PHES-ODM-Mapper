# %%
"""
Filter DataFrames (or data on disk) using configuration files.

## Usage

```python
# Filter .csv, .tsv, and .txt (tab-separated) files and save
# to "data/output".
data_files = {
    "measures": ["path/to/measures.csv"],
    "samples": ["path/to/samples.csv"],
}
filter = DataFilter("filter_config_file.csv")
filtered_data, filtered_files = filter.run_filter(data_files=data_files,
                                                  output_data_dir="data/output")

# Filter DataFrames (don't save to disk).
data = {
    "measures" : measures_df,
    "qualityReports" : qualityReports_df,
}
filtered_data, _ = filter.run_filter(data=data)
```
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from typing import Union, Dict, List, Tuple
import yaml
import pandas as pd
import argparse
from pathlib import Path
import os
from datetime import datetime

from utils.general_utils import (
    read_data_frame,
    save_data_frame,
    parse_df_values,
    get_logger,
)
from utils.cli_utils import get_input_data_files
from filter.filter_funcs import call_filter_func

logger = get_logger(__name__)


class FilterConfigColumns:
    INPUT_FILTER = "inputFilter"
    OUTPUT_FILTER = "outputFilter"
    CLASS = "class"
    SLOT = "slot"
    OPERATION = "operation"
    VALUE = "value"


class DataFilter(object):
    def __init__(self, filter_config_file: Union[str, Path]):
        self.config_df = read_data_frame(filter_config_file, keep_default_na=False)
        self.config_df = self.config_df.astype(str)

        # Drop empty rows
        self.config_df = self.config_df[
            self.config_df.apply(lambda x: (x != "").any(), axis=1)
        ]
        # Load values as YAML
        self.config_df[FilterConfigColumns.VALUE] = self.config_df[
            FilterConfigColumns.VALUE
        ].map(yaml.safe_load)

    def load_data(
        self, data_files: Dict[str, Union[Path, str]]
    ) -> Dict[str, pd.DataFrame]:
        """Load all data specified in data_files.

        Args:
            data_files (Dict[str, Union[Path, str]]): All data files to load. The keys are the class names
                and the values are list of data files to load belonging to the class.

        Returns:
            Dict[str, pd.DataFrame]: Dictionary where the keys are the class names and the values are
                the loaded DataFrames.
        """
        data = {}
        for class_name, files in data_files.items():
            for file in files:
                logger.info(f"Loading data from {file} (class='{class_name}')")

                # Load the data and append to any existing data for the class
                df = read_data_frame(file, keep_default_na=False, na_values=[""])
                if class_name not in data:
                    data[class_name] = df
                else:
                    data[class_name] = pd.concat(
                        [data[class_name], df], ignore_index=True
                    )

        for df in data.values():
            parse_df_values(df, inline=True)

        return data

    def save_data(
        self, data: Dict[str, pd.DataFrame], output_data_dir: Union[Path, str]
    ) -> Dict[str, List[Path]]:
        """Save all the data as CSV files to the output directory.

        Args:
            data (Dict[str, pd.DataFrame]): Data to save. The keys are the class names (which become the
                file names) and the values are the DataFrames to save.
            output_data_dir (Union[Path, str]): The directory to save all data to, as CSV files.

        Returns:
            Dict[str, List[Path]]: Dictionary of all files saved to disk. The keys are the class names
                that the files belong to, and the values are list of files belonging to the class.
        """
        output_files = {}
        output_data_dir = Path(output_data_dir)
        if not output_data_dir.exists():
            output_data_dir.mkdir()
        for cur_class, cur_data in data.items():
            output_file = output_data_dir / f"{cur_class}.csv"
            logger.info(f"Saving data to {output_file}")
            save_data_frame(cur_data, output_file, index=False)

            if cur_class not in output_files:
                output_files[cur_class] = []
            output_files[cur_class].append(output_file)
        return output_files

    def run_filter(
        self,
        *,
        data: Dict[str, pd.DataFrame] = None,
        data_files: Dict[str, List[Union[str, Path]]] = None,
        output_data_dir: Union[Path, str] = None,
    ) -> Tuple[Dict[str, pd.DataFrame], Dict[str, List[Path]]]:
        """Run the filters specified in the configuration file on all the data, and optionally save the data to disk.

        Args:
            data (Dict[str, pd.DataFrame], optional): The data to filter. The keys are the class names and the values are the
                DataFrames to filter. This dictionary is left unchanged, the returned dictionary is the filtered data.
                If None then data_dir must be specified. Defaults to None.
            data_files (Dict[str, List[Union[str, Path]]], optional): If data is None, then load all data specified by data_files. The keys
                are the data file class names and the values are a list of files to filter belonging to the class. Defaults to None.
            output_data_dir (Union[Path, str], optional): If specified then the directory to save all data after filtering has been
                performed. Defaults to None.

        Returns:
            Tuple[Dict[str, pd.DataFrame], Dict[str, Path]]: Tuple in the form (data, output_files).
                data (Dict[str, pd.DataFrame]): The filtered data, where they keys are the classes and the values are the
                    filtered DataFrames.
                output_files (Dict[str, List[Path]]): If output_data_dir was specified, then a dictionary where
                    the keys are the class names saved and the values are lists of output fitered files saved for the class.
                    If output_data_dir was not specified then an empty dictionary is returned.
        """
        tic = datetime.now()

        # If no data is provided, then load the data from data_dir
        if data is None:
            data = self.load_data(data_files)
        else:
            # Make a shallow copy of the dictionary, since we might be changing it. We return the copy.
            data = data.copy()

        filters = {}
        # Go through each row and perform the filtering
        for _, config_row in self.config_df.iterrows():
            input_filter = str(config_row[FilterConfigColumns.INPUT_FILTER])
            output_filter = str(config_row[FilterConfigColumns.OUTPUT_FILTER])
            cls = config_row[FilterConfigColumns.CLASS]
            slot = config_row[FilterConfigColumns.SLOT]
            op = config_row[FilterConfigColumns.OPERATION]
            value = config_row[FilterConfigColumns.VALUE]

            if cls and cls not in data:
                # logger.info(f"Not running filter on class '{cls}', data for class does not exist")
                continue

            logger.info(
                f"Running input filter '{input_filter}', output filter '{output_filter}' with operation '{op}' on class '{cls}', slot '{slot}', and value '{value}'"
            )

            # Perform the filtering operation
            call_filter_func(
                op,
                input_name=input_filter,
                output_name=output_filter,
                filters=filters,
                data=data,
                cls=cls,
                slot=slot,
                value=value,
            )

        output_files = {}
        if output_data_dir:
            output_files = self.save_data(data, output_data_dir)

        logger.info(f"Filtered in {datetime.now() - tic}")
        return data, output_files


if __name__ == "__main__":
    if "get_ipython" in globals():
        # fmt: off
        class opts:
            input_data_dir = "../../gen/nwss_reporting_to_v2/temp/mapped_data"
            input_data_files = None
            filter_config_file = "../../data/modules/nwss_reporting_to_v2/filters/nwss_reporting_to_v2_filters.csv"
            output_data_dir = "../../gen/nwss_reporting_to_v2/filtered_mapped_data"
        # fmt: on
    else:
        args = argparse.ArgumentParser(
            formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
        args.add_argument(
            "--input_data_dir",
            type=str,
            help="Directory containing all of the input data to filter. The file names (without extension) correspond to the table name, with anything after the first square or round bracket ignored.",
            required=False,
        )
        args.add_argument(
            "--input_data_files",
            nargs="+",
            type=str,
            help="List of all input files to filter, and the source class for each file. Format is 'class_name file.csv [class_name2 file2.csv ...]'",
            required=False,
        )
        args.add_argument(
            "--filter_config_file",
            type=str,
            help="Location of the CSV or TSV filtering configuration file.",
            required=True,
        )
        args.add_argument(
            "--output_data_dir",
            type=str,
            help="Location to save the filtered data to.",
            required=True,
        )
        opts = args.parse_args()

    data_files = get_input_data_files(opts.input_data_files, opts.input_data_dir)

    filterer = DataFilter(opts.filter_config_file)
    filterer.run_filter(
        data_files=data_files,
        output_data_dir=opts.output_data_dir,
    )
