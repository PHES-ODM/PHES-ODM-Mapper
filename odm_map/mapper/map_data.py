from typing import Any, Dict, List, Tuple, Optional, Union, Callable
import os
from pathlib import Path
import yaml
from functools import partial
import pandas as pd
import math
from datetime import datetime
from multiprocessing import Pool, cpu_count

from linkml_runtime import SchemaView
from linkml_map.session import Session

from odm_map.utils.logger import get_logger
from odm_map.utils.schema_utils import (
    all_classes_without_tree_root,
    find_class,
)
from odm_map.progress import ProgressCounter
from odm_map.utils.tracking_slots import (
    load_schema_with_tracking_slots,
    get_all_tracking_slots,
    add_tracking_slots_derivations,
    load_data_with_tracking_columns,
    drop_tracking_slots,
    TrackingSlots,
)
from odm_map.utils.general_utils import (
    merge_dicts_of_lists,
    order_columns,
    save_data_frame,
)

logger = get_logger(__name__)


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


class DataMapper(object):
    def __init__(self): ...

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

    def sort_mapped_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Sort a mapped DataFrame using the tracking columns that were injected into the DataFrame before mapping occurred, to
        maintain the original order of rows and to also ensure the order of the rows match the ordering in the mapping configuration
        file's wide map configuration.

        Args:
            df (pd.DataFrame): The DataFrame to sort, which has already undergone mapping. The original DataFrame is left
                unchanged and a sorted version is returned.

        Returns:
            pd.DataFrame: The sorted DataFrame.
        """
        df = df.sort_values(
            [
                TrackingSlots.SOURCE_CLASS,
                TrackingSlots.SOURCE_FILE,
                TrackingSlots.SOURCE_ROW,
            ],
            axis=0,
            kind="stable",
        )
        df = df.reset_index(drop=True)
        return df

    def prepare_data(
        self,
        data_frames: Dict[str, List[pd.DataFrame]],
        schema: Union[str, SchemaView],
        prepare_barid: str = "Preparing IDs",
    ) -> Dict[str, List[Dict]]:
        """Parse all data in a format compatible with the LinkML Mapper.

        Args:
            data_frames (Dict[str, List[pd.DataFrame]]): A DataFrames to parse. Keys are the source class
                name and values are lists of DataFrames that belong to the class. The tracking columns
                should have already been added by calling add_tracking_columns on each DataFrame.
            schema (Union[str, SchemaView]): The schema that the data should conform to. We will only use
                DataFrames of a recognized class and cast all values to the correct type.

        Returns:
            Dict[str, List[Dict]]: Dictionary of all data. Keys are the class/table names and values are
                the rows.
        """
        logger.debug("Preparing all data...")

        if isinstance(schema, str):
            schema = SchemaView(schema)

        data = {}
        cast_functions = self.get_cast_functions(schema)
        # Only process data that belong to a recognized class
        all_classes = all_classes_without_tree_root(schema)
        data_frames = {
            class_name: class_data
            for class_name, class_data in data_frames.items()
            if class_name in all_classes
        }

        total = len([d for sdata in data_frames.values() for d in sdata])
        progress = ProgressCounter({prepare_barid: total})

        with progress:
            for class_name, class_data in data_frames.items():
                logger.debug(f"Parsing data for class '{class_name}'...")
                for df in class_data:
                    if df is None or len(df.index) == 0:
                        progress.update(prepare_barid, 1)
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

                    logger.debug(
                        f"Data from class '{class_name}' has {len(cur_data)} rows"
                    )
                    progress.update(prepare_barid, 1)

        return data

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

    def convert_mapped_data_to_dataframes(
        self, mapped_data: Dict[str, List[Dict]], target_schema: Optional[SchemaView]
    ) -> Dict[str, List[pd.DataFrame]]:
        """Convert the specified data that has already been mapped to DataFrames.

        Args:
            mapped_data (Dict[str, List[Dict]]): The data to convert to DataFrames. The
                keys are class names and the values are lists of rows for that class.
                A row is a dictionary where the keys are the column names and the values
                are the value of that column.
            target_schema (Optional[SchemaView]): The schema that the data conforms to.
                This is used to get the correct class names and to add any missing
                columns in the data. If None then we cannot guarantee if a class name
                is correct (but we do clean the class name by removing everything after the
                first opening square or round bracket), and we cannot add missing columns.

        Returns:
            Dict[str, List[pd.DataFrame]]: Dictionary of all DataFrames. The keys are the
                class names and the values are lists of DataFrames belonging to the class.
        """
        # Convert the data to a DataFrame, store in all_mapped_data, and save to disk
        all_mapped_data = {}
        for class_name, target_data in mapped_data.items():
            if target_data is None:
                continue

            # Remove any extra info from the class_name
            # eg "protocolSteps[inhibition]" becomes "protocolSteps"
            orig_class_name = class_name
            class_name = find_class(class_name, target_schema, ignore_case=True)
            if class_name is None:
                logger.error(
                    f"Found mapped class name '{orig_class_name}' that does not exist in target schema, discarding data."
                )
                continue

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

    def run(
        self,
        data_files: Dict[str, List[Union[str, Path, Dict]]],
        data_frames: Dict[str, List[pd.DataFrame]],
        output_dir: Union[str, Path],
        source_schema_file: Union[str, Path],
        target_schema_file: Optional[Union[str, Path]],
        mappers_dir: Union[str, Path],
        max_rows: Optional[int] = 0,
        max_processes: Optional[int] = 1,
        prepare_barid: str = "Preparing Data",
        map_barid: str = "Mapping",
        convert_barid: str = "Processing Data",
        keep_tracking_columns: bool = False,
    ) -> Tuple[Dict[str, pd.DataFrame], Dict[str, List[Path]]]:
        """Map all the data specified in data_frames using all mapper files found in the specified mapper directory.

        Args:
            data_files (Dict[str, List[Union[str, Path, Dict]]]): Dictionary of source data files to map. The keys
                are the source class names and the values are lists of file paths belonging to the class, which
                should each be mapped.
            data_frames (Dict[str, List[pd.DataFrame]]): Dictionary of source DataFrames to map. The keys are the
                source class names and the values are lists of DataFrames belonging to the class, which should each
                be mapped.
            output_dir (Union[str, Path]): Directory to save all final mapped data to. If empty then the data
                is not saved to disk.
            source_schema_file (Union[str, Path]): The LinkML schema for the source database.
            target_schema_file (Optional[Union[str, Path]], optional): The LinkML schema for the target database.
                Can be None.
            mappers_dir (Union[str, Path]): The directory containing all LinkML Mapper configuration (YAML)
                files. All config files will be used for mapping all the loaded data.
            max_rows (Optional[int], optional): Maximum number of rows to load from the files in data_files.
                If 0 or None then all rows are loaded. Defaults to 0.
            max_processes (Optional[int], optional): Maximum number of processes to use for multi-processing.
                If 1 then no multi-processing will be performed. If None or 0 then the maximum number
                (as obtained by cpu_count()) will be used. Note that for mapping small tables multi-processing
                might be slower. Defaults to 1.
            prepare_barid (str, optional): The ID/title to give to the progress bar for preparing the data,
                before the initial mapping. Defaults to "Preparing Data",
            map_barid (str, optional) The ID/title to give the the progress bar for the mapping step.
                Defaults to "Mapping"
            convert_barid (str, optional): The ID/title to give to the progress bar for converting the mapped data
                to DataFrames. Defaults to "Processing Data".
            keep_tracking_columns (bool):  If True then keep all tracking slots in the output. These are slots
                that identify which file and row in the source data an output row was populated from. If False
                then the tracking slots are dropped.

        Returns:
            Tuple[Dict[str, pd.DataFrame], Dict[str, Path]]: Tuple in the form (data_frames, output_files).
                data_frames (Dict[str, pd.DataFrame]): The mapped data, where they keys are the classes and the values are the
                    final mapped DataFrames.
                output_files (Dict[str, List[Path]]): If output_dir was specified, then a dictionary where
                    the keys are the class names saved and the values are lists of output fitered files saved for the class.
                    If output_dir was not specified then an empty dictionary is returned.
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

        if not data_frames:
            data_frames = {}

        # Load files from disk
        if data_files:
            loaded_data = load_data_with_tracking_columns(
                data_files=data_files,
                schema=source_schema,
                add_all_tracking_columns=True,
                max_rows=max_rows,
            )
            data_frames = merge_dicts_of_lists([data_frames, loaded_data])

        # Prepare all data in correct format
        data = self.prepare_data(
            data_frames=data_frames,
            schema=source_schema,
            prepare_barid=prepare_barid,
        )

        if len(data) == 0:
            if data_files:
                logger.warning(
                    "No data loaded from disk for mapping. Be sure the file names match the source table names, Excel files have sheet names matching table names, that there are files in the directory, and that the files are not empty."
                )
            else:
                logger.warning(
                    "No data found for mapping. Be sure the input data belong to recognized tables"
                )
            return {}, {}

        logger.debug(f"Data loaded for source tables: {list(data.keys())}")

        if max_processes == 1:
            split_data = [data]
        else:
            split_data = self.make_data_splits(data, num_splits=max_processes)

        # Collect all mapper config (yaml) files
        mapper_files = [
            f
            for f in sorted(os.listdir(mappers_dir))
            if os.path.splitext(f)[1].lower() in [".yaml"]
        ]
        mapper_files = [os.path.join(mappers_dir, f) for f in mapper_files]

        # Sort by decreasing data size, to maximize overlap of multiprocessing
        # mappers = { f: yaml.safe_load(open(f, "r"))["class_derivations"] for f in mapper_files }
        # source_classes = { f: d[list(d.keys())[0]]["populated_from"] for f, d in mappers.items() }
        # source_class_sizes = { f: len(data.get(c, [])) for f, c in source_classes.items() }
        # mapper_files = sorted(mapper_files, key=lambda c: -source_class_sizes[c])

        # Create arguments to pass to run_mapper for each data split and each mapper config file.
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
        run_mapper_progress = ProgressCounter(
            {map_barid: len(split_data) * len(mapper_files)}
        )
        with run_mapper_progress:
            if max_processes == 1:
                results = []
                for kwargs in map_args:
                    results.append(run_mapper(**kwargs))
                    run_mapper_progress.update(map_barid, 1)
            else:
                pool = Pool(processes=max_processes)
                results = []
                results = [
                    pool.apply_async(
                        run_mapper,
                        (),
                        map_arg,
                        callback=lambda _: run_mapper_progress.update(map_barid, 1),
                    )
                    for map_arg in map_args
                ]
                results = [r.get() for r in results]

        # Convert mapped data to DataFrames
        all_mapped_data = {}
        results = sorted(results, key=lambda x: x[0])
        convert_progress = ProgressCounter({convert_barid: len(results)})
        with convert_progress:
            for _, cur_mapped_data in results:
                cur_mapped_dfs = self.convert_mapped_data_to_dataframes(
                    cur_mapped_data, target_schema
                )
                all_mapped_data = merge_dicts_of_lists(
                    [all_mapped_data, cur_mapped_dfs]
                )
                convert_progress.update(convert_barid, 1)

        # Combine the DataFrames in all_mapped_data and drop tracking columns if required
        logger.info("Combining all mapped data...")
        for class_name, all_df in all_mapped_data.items():
            df = pd.concat(all_df, ignore_index=True, axis=0)
            # Retain the original order by sorting by the TrackingSlots.
            df = self.sort_mapped_data(df)
            if not keep_tracking_columns:
                df = drop_tracking_slots(df)
            all_mapped_data[class_name] = [df]

        # Save data to disk
        output_files = {}
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            for class_name, all_df in all_mapped_data.items():
                df = pd.concat(all_df, ignore_index=True, axis=0)
                output_file = os.path.join(output_dir, f"{class_name}.csv")
                save_data_frame(df, output_file, index=False)
                if class_name not in output_files:
                    output_files[class_name] = []
                output_files[class_name].append(Path(output_file))

        logger.info(f"Finished initial mapping in {datetime.now() - map_tic}")

        return all_mapped_data, output_files
