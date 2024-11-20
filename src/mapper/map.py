# %%
"""
Map data using a transformation module.

```python
from mapper import Mapper

mapper = Mapper(
    module="odm_v1_to_v2",
    module_dir=None,
    id_debug=False,
    multi_bar_progress=False
)
mapper.full_map(
    data_files={
        "measures": ["path/to/measures.csv"],
        "samples": ["path/to/samples.csv"],
        # ...
    },
    output_dir="../gen/odm_v1_to_v2",
)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path
from typing import Union, Optional, List, Dict, Any, Callable, Tuple
import os
import math
import yaml
import pandas as pd
import logging
from datetime import datetime
from multiprocessing import Pool, cpu_count
from functools import partial
import tempfile
import argparse

from linkml_map.session import Session

from linkml_runtime import SchemaView

from mapper.module_config import ModuleConfig
from utils.logger import get_logger, make_logger_bullet_list
from utils.general_utils import (
    save_data_frame,
    read_data_frame,
    order_columns,
    get_class_name_from_file_name,
    clear_dirs,
    merge_dicts_of_lists,
    choose_ignore_case_value,
)
from utils.tracking_slots import (
    TrackingSlots,
    add_tracking_columns,
    get_all_tracking_slots,
    load_schema_with_tracking_slots,
    add_tracking_slots_derivations,
)
from utils.schema_utils import all_classes_without_tree_root
from utils.clean_exit_error import CleanExitError
from filter import DataFilter
from cleaner import DataCleaner
from id_generator import IDGenerator
from utils.cli_utils import get_input_data_files
from progress import ProgressCounter, EmptyCounter

logger = get_logger(__name__)

# If True then save intermediate data to disk. This is typically used for debugging and should usually be
# False. Intermediate data are saved to the temporary directory and include the cleaned data and
# the mapped data before ID generation is performed.
SAVE_INTERMEDIATE_TO_DISK = False

# Progress bar IDs/titles
MAP_BARID = "Initial Mapping"
LOADING_BARID = "Loading Data"
SAVE_PREID_BARID = "Saving Mapped Data"
SAVE_BARID = "Saving Data"
PREPARE_BARID = "Preparing Data"

# If True then if input_max_rows is specified then we load a random sample of input_max_rows
# rows. If False then we load the first input_max_rows rows. Should usually be False. Use
# True for debugging purposes.
RANDOM_SAMPLE_DATA = False

# Change the logging level of the Transformer. For very large datasets we will get way too many WARNINGs in
# the output.
for logger_name in [
    "linkml_map.transformer.object_transformer",
    "linkml_map.transformer.transformer",
    "linkml_runtime.utils.schemaview",
]:
    trlogger = logging.getLogger(logger_name)
    trlogger.setLevel("ERROR")


def run_mapper(
    data: Dict[str, List],
    mapper_file: Union[str, Path],
    source_schema: SchemaView,
    target_schema: SchemaView,
    source_schema_file: str,
    target_schema_file: str,
    file_index: Optional[int] = None,
    unrestricted_eval: bool = False,
) -> Dict[str, List[Dict]]:
    """Run the mapper on the specified data using the specified mapper YAML file and save the
    results to disk.

    Args:
        data (Dict): The input data to map. The keys specify the table/class names and the values are the rows of
            the tables. The rows are dictionaries.
        session (Session): The linkml_map.session.Session object to use for running the mapper.
        data_output_dir (Union[str, Path]): Directory to save the output to. The outputs are CSV files
            with a name based on the mapper_file name.
        mapper_file (Union[str, Path]): The mapper config (YAML) file for the mapper to use.
        source_schema (SchemaView): The SchemaView of the source schema.
        target_schema (SchemaView): The SchemaView of the target schema.
        file_index (Optional[int]): Optional file index to add to the output file name. It's just an extra number
            so that we can differentiate between different runs of the mapper when using the same
            mapper_file. It is required if we run the mapper more than once with the same
            mapper_file, as it ensures that the filename of the output is different for each run
            (assuming we properly use unique file_index values for each run).
        unrestricted_eval (Optional[bool]): If True then run expr code in slot derivations in unrestricted mode
            (ie. allow any Python code to execute).
        filter_config_file (Optional[Union[str, Path]], optional): The filter configuration file, to filter the
            final transformed data (eg. remove rows that should be ignored due to missing data). Defaults to None.

    Returns:
        Dict[str, List[Dict]]: The mapped data, where the keys are the output class names and the
            values are the rows. The rows are dictionaries.
    """
    if source_schema is None:
        source_schema = load_schema_with_tracking_slots(source_schema_file)
    if target_schema is None and target_schema_file:
        target_schema = load_schema_with_tracking_slots(target_schema_file)

    session = Session()
    session.set_source_schema(source_schema)

    # Load the mapper spec
    with open(mapper_file, "r") as f:
        mapper_spec = yaml.safe_load(f)

    # Add all tracking slot derivations. This will copy all slots found in TrackingSlots, such as the source
    # class and source row number that the output row was derived from. These slots can be used for sorting
    # and other downstream operations such as ID generation.
    add_tracking_slots_derivations(mapper_spec, target_schema)

    # Run the mapper to get the mapped data
    # logger.debug(f"Mapping data with mapper spec {mapper_file}")
    # trans_tic = datetime.now()
    session.set_object_transformer(mapper_spec)
    session.object_transformer.unrestricted_eval = unrestricted_eval
    mapped_data = session.transform(data)
    # logger.debug(
    #     f"Mapped in {datetime.now() - trans_tic} (for mapper spec {mapper_file})"
    # )

    return file_index, mapped_data


class Mapper(object):
    def __init__(
        self,
        module: Optional[str],
        module_dir: Optional[Union[str, Path]],
        id_debug: bool = False,
        multi_bar_progress: bool = True,
    ):
        """Class to perform a full mapping, including filtering and ID generation.

        Args:
            module (Optional[str]): The built-in module for the mapping, eg. "odm_v1_to_v2" or "nwss_reporting_to_v2".
                If None then module_dir must be specified.
            module_dir (Optional[Union[str, Path]]): The directory for the mapping module. If None then module must be specified.
            id_debug (bool, optional): If True then run the ID generator in debug mode. Debug mode will result
                in the output mapped data to include various columns that were used during ID generation
                (such as the source database class name and row number used for populating a row, the original
                unmodified IDs before generation occurred, etc.), and will also not drop rows where duplicate
                primary keys are found, instead an additional column named "__drop" will be added to the output
                and set to TRUE if the row would be dropped when not in debug mode. Defaults to False.
            multi_bar_progress (bool, optional): If True then output multiple progress bars at the same time
                when appropriate. If False then only show one progress bar at a time.
        """
        self.id_debug = id_debug
        self.multi_bar_progress = multi_bar_progress

        # Tell the user which module we're using
        if module:
            logger.info(f"Running with module '{module}'")
        else:
            logger.info(f"Running with module directory {module_dir}")

        # Load the data mapping module
        self.module_config = ModuleConfig(module=module, module_dir=module_dir)

    def prepare_data(
        self,
        data_files: Dict[str, List[Union[str, Path]]],
        data_frames: Dict[str, List[pd.DataFrame]],
        schema: Union[str, SchemaView],
        max_rows: Optional[int] = 0,
    ) -> Dict[str, List[Dict]]:
        """Parse all data in a format compatible with the LinkML Mapper.

        Args:

            data_files (Dict[str, List[Union[str, Path]]]): All files to load and parse. Keys are the
                source class name and values are lists of files that belong to the class.
            data_frames (Dict[str, List[pd.DataFrame]]): A DataFrames to parse. Keys are the source class
                name and values are lists of DataFrames that belong to the class. The tracking columns
                should have already been added by calling add_tracking_columns on each DataFrame.
            schema (Union[str, SchemaView]): The schema that the data should conform to. We will only use
                DataFrames of a recognized class and cast all values to the correct type.
            max_rows (Optional[int], optional): Maximum number of rows to load from each file in data_files.
                If 0 or None then all rows are loaded. Defaults to 0.

        Returns:
            Dict[str, List[Dict]]: Dictionary of all data. Keys are the class/table names and values are
                the rows.
        """
        logger.debug("Preparing all data...")

        if isinstance(schema, str):
            schema = SchemaView(schema)

        data = {}
        cast_functions = self.get_cast_functions(schema)
        source_data = merge_dicts_of_lists([data_files, data_frames])
        # Only process data that belong to a recognized class
        all_classes = all_classes_without_tree_root(schema)
        source_data = {
            class_name: class_data
            for class_name, class_data in source_data.items()
            if class_name in all_classes
        }

        total = len([d for sdata in source_data.values() for d in sdata])
        progress = ProgressCounter({PREPARE_BARID: total})

        with progress:
            for class_name, class_data in source_data.items():
                logger.debug(f"Parsing data for class '{class_name}'...")
                for cur_data in class_data:
                    if isinstance(cur_data, (str, Path)):
                        file = str(cur_data)
                        # df = read_data_frame(file, keep_default_na=False, na_values=None)
                        df = self.load_data_with_tracking_columns(
                            {class_name: [file]}, max_rows=max_rows
                        )[class_name][0]
                    elif isinstance(cur_data, pd.DataFrame):
                        file = None
                        df = cur_data
                    else:
                        raise ValueError(
                            f"Unrecognized type of item found for class '{class_name}': type={type(cur_data)}, (data={cur_data})"
                        )

                    if df is None or len(df.index) == 0:
                        progress.update(PREPARE_BARID, 1)
                        continue

                    # Make sure all columns exist (except for TrackingSlots, which we add later)
                    class_definition = schema.induced_class(class_name)
                    all_tracking_slots = get_all_tracking_slots()
                    missing_slots = [
                        s
                        for s in class_definition.attributes
                        if s not in df.columns and s not in all_tracking_slots
                    ]
                    df[missing_slots] = ""

                    # Only keep recognized slots
                    recognized_slots = [
                        s for s in df.columns if s in class_definition.attributes
                    ]
                    df = df[recognized_slots]

                    # if file is not None:
                    #     add_tracking_columns(df, class_name, file)

                    # Reorient the data to a format recognized by the mapper (an array of rows, where
                    # each row is a dictionary of the form {column_name:value, ...})
                    cur_cast_functions = cast_functions[class_name]
                    cur_data = [
                        {c: cur_cast_functions[c](v) for c, v in r.items()}
                        for _, r in df.iterrows()
                    ]
                    if class_name not in data:
                        data[class_name] = []
                    data[class_name].extend(cur_data)

                    from_str = (
                        f"from file: {file}" if file else "from preloaded DataFrame"
                    )
                    logger.debug(
                        f"Data from class '{class_name}' has {len(cur_data)} rows ({from_str})"
                    )
                    progress.update(PREPARE_BARID, 1)

        return data

    def _cast_types(self, v: Any, cast_types: str) -> Any:
        """Try to cast a value to the types specified in cast_types. We iterate over all cast types until
        the casting works without throwing an exception. If none of the casting works then the value is returned
        unchanged.

        Args:
            v (Any): The value to cast.
            cast_types (str): A list of the cast types to try. Can have the values "float", "integer", or
            "string". Any other value will be treated as a string (eg. if the cast type is a LinkML enumeration,
            then it will be cast as a string).

        Returns:
            Any: The cast value, or the value unchanged if it could not be cast.
        """
        if pd.isna(v):
            return v
        for cast_type in cast_types:
            # The default cast function is str, this will deal with enums and other types
            cast_func = {
                "float": float,
                "integer": int,
                "string": str,
            }.get(cast_type, str)
            try:
                return cast_func(v)
            except Exception as _:
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
                rng = yaml.safe_load(slot_defn.range)
                # Add the casting function according to the range
                if isinstance(rng, list):
                    # Order of a multi-range should be float, int, string. This will ensure
                    # that we don't lose decimals by trying to cast to an int first. Anything
                    # that is not a float or int will be ordered according to the position of "*"
                    # (this includes enumeration names).
                    order = ["float", "int", "*"]
                    rng = sorted(
                        rng,
                        key=lambda x: order.index(x)
                        if x in order
                        else order.index("*"),
                    )
                    cur_cast_functions[slot_name] = partial(
                        self._cast_types, cast_types=rng
                    )
                elif rng in ["float", "double"]:
                    cur_cast_functions[slot_name] = partial(
                        self._cast_types, cast_types=["float"]
                    )
                elif rng == "integer":
                    cur_cast_functions[slot_name] = partial(
                        self._cast_types, cast_types=["integer"]
                    )
                else:
                    cur_cast_functions[slot_name] = partial(
                        self._cast_types, cast_types=["string"]
                    )
        return cast_functions

    def convert_mapped_data_to_dataframes(
        self, mapped_data: Dict[str, List], target_schema: SchemaView
    ):
        # Convert the data to a DataFrame, store in all_mapped_data, and save to disk
        all_mapped_data = {}
        for class_name, target_data in mapped_data.items():
            if target_data is None:
                continue

            # Remove any extra info from the class_name
            # eg "protocolSteps[inhibition]" becomes "protocolSteps"
            class_name = get_class_name_from_file_name(class_name, target_schema)

            df = pd.DataFrame(target_data)

            # Add any missing columns and order them according to the target schema
            if target_schema is not None:
                class_definition = target_schema.induced_class(class_name)
                all_slots = list(class_definition.attributes.keys())
                unrecognized = [s for s in df.columns if s not in all_slots]
                if len(unrecognized) > 0:
                    raise ValueError(
                        f"Found unrecognized slot(s) in mapped data for class '{class_name}': {unrecognized}"
                    )
                missing = [s for s in all_slots if s not in df.columns]
                if len(missing) > 0:
                    df[missing] = None
                df = order_columns(df, all_slots)

            # Keep a copy of the mapped data
            if class_name not in all_mapped_data:
                all_mapped_data[class_name] = []
            all_mapped_data[class_name].append(df)

        return all_mapped_data

    def make_data_splits(
        self, data: Dict[str, List], num_splits: int, min_split_size: int = 100
    ) -> List[Dict[str, List[Dict]]]:
        """Split the data into multiple smaller data splits, to make it easier to use for multiprocessing.
        Each split can be used by run_mapper. Each table is split into up to num_splits splits, depending
        on how many rows are in each table.

        Args:
            data (Dict[str, List]): The data to split. The keys are the source table names and the values
                are the rows of the data.
            num_splits (int): The number of splits to create.
            min_split_size (int, optional): If all tables when split will result in splits less
                than this many rows then no splitting is performed and instead the list [data] is returned.
                Defaults to 100.

        Returns:
            List[Dict[str, List[Dict]]]: The data splits. Each element of the array is in the same format
                as the passed in data parameter, but will possibly have missing tables (due to the table
                being fully included in earlier tables in the split) and will have possibly have fewer
                rows per table (from making the splits).
        """
        data_splits = []
        max_len = max([len(d) for d in data.values()])
        rows_per_split = math.ceil(max_len / num_splits)
        if rows_per_split < min_split_size:
            return [data]
        split_num = 0
        while True:
            # Make the data splits for each table
            split_data = {
                c: d[split_num * rows_per_split : (split_num + 1) * rows_per_split]
                for c, d in data.items()
            }
            # Remove any key where the table is empty
            split_data = {c: d for c, d in split_data.items() if len(d) > 0}
            # If all tables were empty then we're done
            if len(split_data.keys()) == 0:
                break

            data_splits.append(split_data)
            split_num += 1
        return data_splits

    def sort_mapped_data(
        self, df: pd.DataFrame, *, drop_sorting_column: bool
    ) -> pd.DataFrame:
        """Sort a mapped DataFrame using the sorting column that was injected into the DataFrame before mapping occurred, to
        maintain the original order of rows and to also ensure the order of the rows match the ordering in the mapping configuration
        file's wide map configuration.

        Args:
            df (pd.DataFrame): The DataFrame to sort, which has already undergone mapping. The original DataFrame is left
                unchanged and a sorted version is returned.
            drop_sorting_column (bool): If True then drop the sorting column that was injected into the DataFrame. The
                sorting column should only be dropped if no further sorting of the DataFrame is required.

        Returns:
            pd.DataFrame: The sorted DataFrame.
        """
        df = df.sort_values(
            [TrackingSlots.SOURCE_FILE, TrackingSlots.SOURCE_ROW], axis=0, kind="stable"
        )
        if drop_sorting_column:
            df = df.drop(get_all_tracking_slots(), axis=1)
        df = df.reset_index(drop=True)
        return df

    def clean_data(
        self,
        data_files: Dict[str, List[Union[str, Path]]],
        data_frames: Dict[str, List[pd.DataFrame]],
        output_dir: Union[str, Path],
        max_rows: Optional[int] = None,
    ) -> Tuple[Dict[str, List[str]], Dict[str, List[pd.DataFrame]]]:
        """Clean the data in the specified data files and DataFrames.

        Args:
            data_files (Dict[str, List[Union[str, Path]]]): Dictionary of input data files, where the keys are the
                class names and the values are lists of files to clean. Both data_files and data_frames are cleaned.
            data_frames (Dict[str, List[pd.DataFrame]]): Dictionary of DataFrames, where the keys are the class names
                and the values are lists of DataFrames for that class to clean. Both data_files and data_frames are
                cleaned.
            output_dir (Union[str, Path]): The directory to save the cleaned data to. If None then the data is not
                saved, but is still cleaned and returned as DataFrames.
            max_rows (Optional[int], optional): Maximum number of rows to clean from each data file or DataFrame.
                The saved data files and returned DataFrames have at most this many rows each. If 0 or None then
                all rows are cleaned. Defaults to None.

        Returns:
            Tuple[Dict[str, List[str]], Dict[str, List[pd.DataFrame]]]: Tuple of (data_files, data_frames):
                    data_files: Dictionary where the keys are the class names and the values are lists of files that
                        are cleaned.
                    data_frames: Dictionary where the keys are the class names and the values are lists of DataFrames
                        that are cleaned.
                Note that data_files["class_name"][idx] corresponds to the file where data_frames["class_name"][idx]
                is saved.
        """
        cleaner = DataCleaner(schema=self.module_config.source_schema)
        data_files, data_frames = cleaner.clean_data(
            data_files=data_files,
            data_frames=data_frames,
            output_dir=output_dir,
            max_rows=max_rows,
        )
        return data_files, data_frames

    def map_data(
        self,
        source_schema_file: Union[str, Path],
        target_schema_file: Union[str, Path],
        mapper_dir: Union[str, Path],
        data_files: Dict[str, List[Union[str, Path]]],
        data_frames: Dict[str, List[pd.DataFrame]],
        max_rows: Optional[int] = 0,
        max_processes: Optional[int] = 1,
    ) -> Dict[str, List[pd.DataFrame]]:
        """Map all the files specified in data_files using all mapper files found in the specified mapper directory.

        Args:
            source_schema_file (Union[str, Path]): The LinkML schema for the source database.
            target_schema_file (Union[str, Path]): The LinkML schema for the target database.
            mapper_dir (Union[str, Path]): The directory containing all LinkML Mapper configuration (YAML)
                files. All config files will be used for mapping all the loaded data.
            data_files (Dict[str, Dict[str, List[Union[str, Path]]]): Dictionary of source data files to map (in
                addition to the DataFrames in data_frames). The keys are the source class names and the values are
                lists of data files belonging to the class, which should be mapped.
            data_frames (Dict[str, List[pd.DataFrame]]): Dictionary of source DataFrames to map (in addition to the
                files in data_files). The keys are the source class names and the values are lists of
                DataFrames belonging to the class, which should each be mapped.
            max_rows (Optional[int], optional): Maximum number of rows to load from each file in data_files. If 0 or None then all
                rows are loaded. Defaults to 0.
            max_processes (Optional[int], optional): Maximum number of processes to use for multi-processing.
                If 1 then no multi-processing will be performed. If None or 0 then the maximum number
                (as obtained by cpu_count()) will be used. Note that for mapping small tables multi-processing
                might be slower. Defaults to 1.

        Returns:
            Dict[str, List[pd.DataFrame]]: Keys are the target class names and the values are the mapped data for
            that class.
        """
        tic = datetime.now()

        logger.debug(f"Beginning mapping at {tic}")

        map_tic = datetime.now()

        if not max_processes or max_processes <= 0:
            max_processes = cpu_count()

        source_schema = load_schema_with_tracking_slots(source_schema_file)
        if target_schema_file:
            target_schema = load_schema_with_tracking_slots(target_schema_file)
        else:
            target_schema = None

        # Prepare
        data = self.prepare_data(
            data_files=data_files,
            data_frames=data_frames,
            schema=source_schema,
            max_rows=max_rows,
        )

        if len(data) == 0:
            logger.warning(
                "No data loaded from disk. Be sure the file names match the source schema table names, that there are files in the directory, and that the files are not empty."
            )
            return {}

        logger.debug(f"Data loaded for source tables: {list(data.keys())}")

        if max_processes == 1:
            split_data = [data]
        else:
            split_data = self.make_data_splits(data, num_splits=max_processes)

        # Collect all mapper config (yaml) files
        mapper_files = [
            f
            for f in sorted(os.listdir(mapper_dir))
            if os.path.splitext(f)[1].lower() in [".yaml"]
        ]
        mapper_files = [os.path.join(mapper_dir, f) for f in mapper_files]

        # Sort by decreasing data size, to maximize overlap of multiprocessing
        # mappers = { f: yaml.safe_load(open(f, "r"))["class_derivations"] for f in mapper_files }
        # source_classes = { f: d[list(d.keys())[0]]["populated_from"] for f, d in mappers.items() }
        # source_class_sizes = { f: len(data.get(c, [])) for f, c in source_classes.items() }
        # mapper_files = sorted(mapper_files, key=lambda c: -source_class_sizes[c])

        # Create arguments to pass to run_mapper for each mapper config file.
        map_args = []
        for split_num, split in enumerate(split_data):
            cur_args = [
                {
                    "file_index": split_num + file_num * len(mapper_files),
                    "data": split,
                    # "data_output_dir": data_output_dir,
                    # "session": session,
                    "mapper_file": mapper_file,
                    "source_schema_file": source_schema_file,
                    "target_schema_file": target_schema_file,
                    "source_schema": source_schema,
                    "target_schema": target_schema,
                    "unrestricted_eval": True,
                    # "filter_config_file": filter_config_file,
                }
                for file_num, mapper_file in enumerate(mapper_files)
            ]
            map_args.extend(cur_args)

        # Call _run_mapper, either using multiple processes or one at a time
        if max_processes == 1:
            logger.debug("Running without multiprocessing")
        else:
            logger.debug(f"Running with {max_processes} processes")

        logger.info("Performing initial mapping step, this may take some time...")
        self.run_mapper_progress = ProgressCounter(
            {MAP_BARID: len(split_data) * len(mapper_files)}
        )
        with self.run_mapper_progress:
            if max_processes == 1:
                results = []
                for kwargs in map_args:
                    results.append(run_mapper(**kwargs))
                    self.run_mapper_progress.update(MAP_BARID, 1)
            else:
                pool = Pool(processes=max_processes)
                results = []
                results = [
                    pool.apply_async(
                        run_mapper,
                        (),
                        map_arg,
                        callback=lambda x: self.run_mapper_progress.update(
                            MAP_BARID, 1
                        ),
                    )
                    for map_arg in map_args
                ]
                results = [r.get() for r in results]

        # Convert mapped data to DataFrames
        all_mapped_data = {}
        results = sorted(results, key=lambda x: x[0])
        for _, cur_mapped_data in results:
            cur_mapped_dfs = self.convert_mapped_data_to_dataframes(
                cur_mapped_data, target_schema
            )
            all_mapped_data = merge_dicts_of_lists([all_mapped_data, cur_mapped_dfs])

        # Combine the DataFrames in all_mapped_data
        for class_name, all_df in all_mapped_data.items():
            df = pd.concat(all_df, ignore_index=True, axis=0)
            # Retain the original order by sorting by the TrackingSlots.
            df = self.sort_mapped_data(df, drop_sorting_column=False)
            all_mapped_data[class_name] = [df]

        logger.info(f"Finished initial mapping in {datetime.now() - map_tic}")

        return all_mapped_data

    def filter_data(
        self,
        data_frames: Dict[str, List[pd.DataFrame]],
        filter_config_file: Union[str, Path],
    ) -> Dict[str, List[pd.DataFrame]]:
        """Filter DataFrames according to a filter configuration file.

        Args:
            data_frames (Dict[str, List[pd.DataFrame]]): Dictionary of DataFrames to filter, where the
                keys are the class names and the values are lists of DataFrames belonging to the class.
                All DataFrames from the same class are merged then filtered.
            filter_config_file (Union[str, Path]): The filter configuration file to use (a CSV file)

        Returns:
            Dict[str, List[pd.DataFrame]]: The filtered DataFrames. Keys are the class names and values
                are lists of filtered DataFrames for that class.
        """
        logger.debug("Filtering all data...")
        filter_tic = datetime.now()
        data_filter = DataFilter(filter_config_file)

        # Merge data
        merged_data = {}
        for class_name, dfs in data_frames.items():
            df = pd.concat(dfs, ignore_index=True, axis=0)
            merged_data[class_name] = df

        # Filter data
        filtered_data, _ = data_filter.run_filter(data=merged_data)
        filtered_data = {k: [v] for k, v in filtered_data.items()}

        logger.debug(f"Total time for filtering: {datetime.now() - filter_tic}")

        return filtered_data

    def save_data(
        self,
        data_frames: Dict[str, List[pd.DataFrame]],
        output_dir: Union[str, Path],
        progress_barid: Optional[str] = None,
        name_format: str = "{class_name}.csv",
        exception_if_exists: bool = False,
    ) -> Dict[str, List[str]]:
        """Save the specified DataFrames to disk.

        Args:
            data_frames (Dict[str, List[pd.DataFrame]]): The data to save. The keys are the class names and the values
                are lists of DataFrames belonging to the class. For each key, the list of DataFrames are concatenated
                into a single DataFrame.
            output_dir (Union[str, Path]): The directory to save the DataFrames to.
            name_format (str, optional): The string interpolation format of the file names, accepts the variable class_name.
                Defaults to "{class_name}.csv"
            exception_if_exists (bool, optional): If True then raise an exception if a file already exists with the same
                name as a file we are trying to save. If False then overwrite the file. Defaults to False.

        Raises:
            ValueError: Only raised if exception_if_exists is True. The data could not be saved because one of the output
                files already exists. Be sure to delete the files in output_dir before callings save_data.

        Returns:
            Dict[str, List[str]]: A dictionary where the keys are class names and the values are lists
                of files saved to disk for that class.
        """
        # Save data to disk
        all_mapped_files = {}
        save_tic = datetime.now()
        if progress_barid:
            progress = ProgressCounter(
                {progress_barid: len(data_frames)}, multiple_bars=False
            )
        else:
            progress = EmptyCounter()

        with progress:
            for class_name, dfs in data_frames.items():
                df = pd.concat(dfs, ignore_index=True, axis=0)
                output_data_file = os.path.join(
                    output_dir, name_format.format(class_name=class_name)
                )
                if exception_if_exists and os.path.exists(output_data_file):
                    raise ValueError(
                        f"Output data file already exists: {output_data_file}"
                    )
                logger.debug(
                    f"Saving merged mapped data file for {class_name} ({len(dfs)} source frame(s), {len(df.index)} rows): {output_data_file}"
                )
                save_data_frame(df, output_data_file, index=False)
                if class_name not in all_mapped_files:
                    all_mapped_files[class_name] = []
                all_mapped_files[class_name].append(output_data_file)
                progress.update(progress_barid, 1)
        logger.debug(f"Total time for saving: {datetime.now() - save_tic}")

        return all_mapped_files

    def generate_ids(
        self,
        data_files: Dict[str, List[Union[str, Path]]],
        data_frames: Dict[str, List[pd.DataFrame]],
    ) -> Dict[str, List[pd.DataFrame]]:
        """Generate IDs in the data.

        Args:
            data_files (Dict[str, List[Union[str, Path]]]): The data files to load, which we will add IDs to.
                The keys are the class names and the values are lists of data files belonging to that class.
                Data from both data_files and data_frames are merged and processed.
            data_frames (Dict[str, List[pd.DataFrame]]): The data frames to add IDs to. Data from both
                data_files and data_frames are merged and processed.

        Returns:
            Dict[str, List[pd.DataFrame]]: Dictionary of DataFrames containing the data with IDs generated. The keys are
                the class names and the values are lists of DataFrames containing the generated data.
        """
        gen = IDGenerator(
            data_files=data_files,
            data_frames=data_frames,
            config_file=self.module_config.id_config,
            id_code_file=self.module_config.id_code,
            id_code_sheet=self.module_config.id_code_sheet,
            multi_bar_progress=self.multi_bar_progress,
        )
        return gen.run_generator(
            orig_columns_only=not self.id_debug, remove_duplicates=not self.id_debug
        )

    def load_data_with_tracking_columns(
        self,
        data_files: Dict[str, List[Union[str, Path]]],
        source_schema_file: Union[str, Path],
        max_rows: Optional[int] = 0,
    ) -> Dict[str, List[pd.DataFrame]]:
        """Load all data from disk (as DataFrames) and add the tracking columns.

        Args:
            data_files (Dict[str, List[Union[str, Path]]]): Dictionary of all files to load. The keys are the class
                names and the values are lists of files belonging to that class.
            source_schema_file (Union[str, Path]): The source schema that contains the classes that the data_files
                should belong to. Only files belonging to recognized classes are loaded.
            max_rows (Optional[int], optional): Maximum number of rows to load from each file. If 0 or None then all
                rows are loaded. Defaults to 0.

        Returns:
            Dict[str, List[pd.DataFrame]]: The loaded DataFrames. The keys are the class names and the values
                are lists of DataFrames belonging to that class. The order of the DataFrames within each class are the
                same as the order of the files in data_files for the same class.
        """
        if not data_files:
            raise CleanExitError("No input data found.")

        schema = SchemaView(source_schema_file)
        recognized_classes = all_classes_without_tree_root(schema)

        # Check for invalid class names
        has_unrecognized_class = False
        for class_name, files in data_files.items():
            if class_name not in recognized_classes:
                has_unrecognized_class = True
                for file in files:
                    logger.error(f"Unrecognized input table '{class_name}': {file}")
        if has_unrecognized_class:
            tables = ", ".join(sorted(recognized_classes, key=lambda x: str(x).lower()))
            msg = f"Terminating due to unrecognized table(s). Allowable tables are: {tables}"
            raise CleanExitError(msg)

        total_items = sum([len(d) for d in data_files.values()])
        progress = ProgressCounter({LOADING_BARID: total_items}, multiple_bars=False)

        warning_log = []
        with progress:
            data_frames = {}
            for class_name, files in data_files.items():
                if class_name not in recognized_classes:
                    # Unrecognized class name, so ignore the file (but tell the user)
                    for file in files:
                        logger.info(
                            f"Ignoring file from unrecognized table '{class_name}': {file}"
                        )
                        progress.update(LOADING_BARID, 1)
                    continue
                if class_name not in data_frames:
                    data_frames[class_name] = []
                for file in files:
                    try:
                        df = read_data_frame(
                            file,
                            nrows=None
                            if RANDOM_SAMPLE_DATA
                            else (max_rows if max_rows else None),
                            keep_default_na=False,
                            na_values=None,
                        )
                    except pd.errors.EmptyDataError:
                        logger.warning(
                            f"Empty file found for table '{class_name}', ignoring: {file}"
                        )
                        progress.update(LOADING_BARID, 1)
                        continue
                    except FileNotFoundError:
                        raise CleanExitError(f"Specified file does not exist: {file}")

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
                        missing_attributes_str = make_logger_bullet_list(
                            missing_attributes
                        )
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
                            choose_ignore_case_value(
                                c, all_attributes, return_same_if_missing=False
                            )
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

                    # Add tracking columns
                    add_tracking_columns(df, class_name, file)

                    data_frames[class_name].append(df)

                    logger.info(
                        f"Loaded {len(df)} rows for table '{class_name}': {file}"
                    )

                    progress.update(LOADING_BARID, 1)

        if warning_log:
            for msg in warning_log:
                logger.warning(msg)

        if len(data_frames) == 0:
            tables = ", ".join(sorted(recognized_classes))
            msg = f"No recognized tables loaded. Allowable tables are: {tables}"
            raise CleanExitError(msg)

        return data_frames

    def full_map(
        self,
        data_files: Dict[str, List[Union[str, Path]]],
        output_dir: str,
        temp_dir: Union[str, Path] = None,
        input_max_rows: int = None,
        max_processes: int = 1,
    ) -> Dict[str, List[Path]]:
        """Perform a full mapping, including filtering and ID generation.

        Args:
            data_files (Dict[str, List[Union[str, Path]]]): Dictionary specifying all source database data files
                to map. The keys are the source database class names and the values are lists of paths to the
                input data files for the class.
            output_dir (str): Directory to save all the final mapped data to.
            temp_dir (Union[str, Path], optional): Location to store all temporary files used by mapping.
                If None then a temporary directory will be created and deleted when complete. If set then
                the resulting temporary files will not be deleted. This is useful for debugging purposes.
                Defaults to None.
            input_max_rows (int, optional): Maximum number of input rows to load for mapping for each
                data file specified in data_files. Defaults to None.
            max_processes (int, optional): Maximum number of processes to run to do the mapping. For large
                datasets increasing this can increase performance. Defaults to 1.

        Returns:
            Dict[str, List[Path]]: Lists all final mapped files saved to disk. The keys are the output class
                names and the values are lists of file paths representing mapped data for the output class.
        """
        tic = datetime.now()

        output_dir = Path(output_dir)

        # Prepare temporary directory
        if not temp_dir:
            self.temp_dir_obj = tempfile.TemporaryDirectory()
            self.temp_dir = Path(self.temp_dir_obj.name)
        else:
            self.temp_dir_obj = None
            self.temp_dir = Path(temp_dir)
        logger.debug(f"Using temporary directory {self.temp_dir}")

        # Load all data
        data_frames = self.load_data_with_tracking_columns(
            data_files=data_files,
            max_rows=input_max_rows,
            source_schema_file=self.module_config.source_schema,
        )

        # Clean the data
        temp_cleaned_data_dir = self.temp_dir / "cleaned_data"
        clear_dirs([temp_cleaned_data_dir])
        data_files, data_frames = self.clean_data(
            data_files=None,
            data_frames=data_frames,
            output_dir=temp_cleaned_data_dir if SAVE_INTERMEDIATE_TO_DISK else None,
        )

        # Map the cleaned data
        data_frames = self.map_data(
            source_schema_file=self.module_config.source_schema,
            target_schema_file=self.module_config.target_schema,
            mapper_dir=self.module_config.mapper_dir,
            data_files=None,  # data_files,
            data_frames=data_frames,
            max_rows=input_max_rows,
            max_processes=max_processes,
        )

        # Filter the data
        if self.module_config.pre_id_filters:
            data_frames = self.filter_data(
                data_frames=data_frames,
                filter_config_file=self.module_config.pre_id_filters,
            )

        # Save intermediate mapped and filtered (without ID generation) data to disk
        temp_mapped_data_dir = self.temp_dir / "mapped_data"
        if SAVE_INTERMEDIATE_TO_DISK and temp_mapped_data_dir:
            clear_dirs([temp_mapped_data_dir])
            data_files = self.save_data(
                data_frames=data_frames,
                output_dir=temp_mapped_data_dir,
                progress_barid=SAVE_PREID_BARID,
                name_format="{class_name}[preid].csv",
            )

        # Generate IDs in the mapped data
        data_frames = self.generate_ids(data_files=None, data_frames=data_frames)

        # Save data to disk
        # clear_dirs([output_dir])
        data_files = self.save_data(
            data_frames, output_dir=output_dir, progress_barid=SAVE_BARID
        )
        logger.info(f"All data saved to {output_dir}")

        # Delete temporary directory
        if self.temp_dir_obj is not None:
            self.temp_dir_obj.cleanup()
            self.temp_dir_obj = None

        logger.info(f"Total runtime: {datetime.now() - tic}")

        return data_files


if __name__ == "__main__":
    if "get_ipython" in globals():
        # fmt: off
        class opts:
            # ODM v1 to v2
            # module = "odm_v1_to_v2"
            # module_dir = None
            # input_data_dir = "../../../../PHES-ODM-Data/odm_v1_data/centreau_qc/updated"
            # input_data_files = None  # ["WWMeasure", "../../../../PHES-ODM-Data/odm_v1_data/centreau_qc/updated/WWMeasure.csv"]
            # output_dir = "../../gen/odm_v1_to_v2"
            # temp_dir = "../../gen/odm_v1_to_v2/temp-100"

            # NWSS to v2
            module = "nwss_reporting_to_v2"
            module_dir = None
            # input_data_dir = "../../../../PHES-ODM-Data/nwss/private_renamed_test/"
            input_data_dir = "../../../../PHES-ODM-Data/nwss/nwss_renamed/"
            input_data_files = None # [ "nwss", "../../../../PHES-ODM-Data/nwss/private_renamed/nwss[cdc-nwss-restricted-data-set-wastewater-2024-03-19].csv" ]
            output_dir = "../../gen/nwss_reporting_to_v2-test"
            temp_dir = "../../gen/nwss_reporting_to_v2-test/temp"

            max_processes = 1
            input_max_rows = 50
            id_debug = True
        # fmt: on
    else:
        args = argparse.ArgumentParser(
            formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
        args.add_argument(
            "--module",
            type=str,
            help="The module name for the conversion. Either the 'module' or 'module_dir' command-line arguments must be provided (but not both). A module specifies the source dataset type, the target dataset type, and all required configuration for the conversion.",
            required=False,
        )
        args.add_argument(
            "--module_dir",
            type=str,
            help="The module directory for the conversion. Either the 'module' or 'module_dir' command-line arguments must be provided (but not both). A module specifies the source dataset type, the target dataset type, and all required configuration for the conversion.",
            required=False,
        )
        args.add_argument(
            "--input_data_dir",
            type=str,
            help="Directory containing all of the input data to map. The file names (without extension) correspond to the table name, with anything in square brackets ignored.",
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
            help="Directory to save all the mapped data to.",
            required=True,
        )
        args.add_argument(
            "--temp_dir",
            type=str,
            help="Directory to save all temporary files to. If specified then the temporary directory is not deleted after processing. If not specified then a system-specified temporary directory is used and deleted after processing. Primarily used for debugging.",
            required=False,
        )
        args.add_argument(
            "--input_max_rows",
            type=int,
            help="The maximum number of rows to map from each input data file. If 0 then map all rows.",
            default=0,
            required=False,
        )
        args.add_argument(
            "--max_processes",
            type=int,
            help="Maximum number of processes to run at a time for mapping the data. If non-positive then the max available processes are used.",
            default=1,
            required=False,
        )
        args.add_argument(
            "--id_debug",
            action="store_true",
            help="If set then run ID generation in debug mode, which only affects what is included in the output data files. Debug data includes some additional columns (eg. original ID values, row number column for linking, primary key index and values, etc.). Debug output will also include any duplicated primary keys, with an additional 'drop' column specifying if it is a duplicate, in which case the row would be dropped when not in debug mode.",
        )
        opts = args.parse_args()

    tic = datetime.now()

    data_files = get_input_data_files(opts.input_data_files, opts.input_data_dir)

    mapper = Mapper(
        module=opts.module,
        module_dir=opts.module_dir,
        id_debug=opts.id_debug,
        multi_bar_progress="get_ipython" not in globals(),
    )
    mapper.full_map(
        data_files=data_files,
        output_dir=opts.output_dir,
        temp_dir=opts.temp_dir,
        input_max_rows=opts.input_max_rows,
        max_processes=opts.max_processes,
    )
