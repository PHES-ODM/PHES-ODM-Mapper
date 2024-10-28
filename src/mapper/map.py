"""
Map data using a transformation module.

```python
from mapper import full_map

full_map(
    module="odm_v1_to_v2",
    module_dir=None,
    data_files={
        "measures": ["path/to/measures.csv"],
        "samples": ["path/to/samples.csv"],
        # ...
    },
    output_dir="../gen/odm_v1_to_v2",
    )
"""

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

from linkml_map.session import Session

from linkml_runtime import SchemaView
from linkml_runtime.linkml_model import SlotDefinition

from mapper.module_config import ModuleConfig
from utils.general_utils import (
    save_data_frame,
    read_data_frame,
    get_logger,
    order_columns,
    get_class_name_from_file_name,
    clear_dirs,
)
from utils.tracking_slots import TrackingSlots, TrackingSlotsTypes
from filter import DataFilter
from cleaner import DataCleaner
from id_generator import IDGenerator

logger = get_logger(__name__)

# During mapping several DataFrames are created, and there may be multiple DataFrames for a single class.
# If SAVE_UNMERGED_DATA is True (and a data_output_dir is specified) then we save these DataFrames to disk as separate files.
# If SAVE_UNMERGED_DATA is False then we do not save this data to disk.
# In all cases (if a data_output_dir is specified), once all mapping is complete, we merge these DataFrames into single DataFrames
# for each class, and then save them to disk. Typically, we do not need the unmerged data as it gets saved at the end as the merged data.
# This is mainly for debugging purposes, and should typically be set to False if not debugging.
SAVE_UNMERGED_DATA = False


# Change the logging level of the Transformer. For very large datasets we will get way too many WARNINGs in
# the output.
for logger_name in [
    "linkml_map.transformer.object_transformer",
    "linkml_map.transformer.transformer",
]:
    trlogger = logging.getLogger(logger_name)
    trlogger.setLevel("ERROR")


def load_data(
    data_files: Dict[str, Union[str, Path]],
    schema: Union[str, SchemaView],
) -> Dict[str, List[Dict]]:
    """Load all data files (CSV, TSV, and TXT files) from disk in a format compatible with the
    LinkML Mapper.

    Args:
        data_files (Dict[str, Union[str, Path]]): All data files to load. Keys are the source class
            name and values are lists of files to load that belong to the class.
        schema (Union[str, SchemaView]): The schema that the data should conform to. We will only load
            files of a recognized class and cast all values to the correct type.

    Returns:
        Dict[str, List[Dict]]: Dictionary of all data. Keys are the class/table names and values are
            the rows. The class that each loaded file belongs to is determined by the file name, which
            should be in the format "class_name[extra_stuff].ext" where "extra_stuff" can be any
            additional text that is ignored.
    """
    # Read all the data from disk.
    logger.info("Reading all data from disk...")

    if isinstance(schema, str):
        schema = SchemaView(schema)

    data = {}
    cast_functions = get_cast_functions(schema)
    for class_name, files in data_files.items():
        # Skip if the file name is not a recognized class
        if class_name not in schema.all_classes():
            continue
        for file in files:
            logger.info(f"Reading data file {file}...")
            df = read_data_frame(file, keep_default_na=False, na_values=None)
            if df is None or len(df.index) == 0:
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

            # Add the tracking columns (eg. source class and source row), which are used for sorting
            # and other downstream operations such as ID generation.
            # First make sure the tracking columns don't already exist (this would be due to a name
            # conflict, where the source data already has columns with the same name as a tracking
            # column)
            existing_tracking_slots = set(df.columns).intersection(all_tracking_slots)
            if len(existing_tracking_slots) > 0:
                raise ValueError(
                    f"Loaded data already has one or more columns with the same name as a tracking column: {existing_tracking_slots}"
                )
            df[TrackingSlots.SOURCE_ROW] = df.index
            df[TrackingSlots.SOURCE_CLASS] = class_name
            df[TrackingSlots.SOURCE_FILE] = file
            # We zero-pad the source row number in the SOURCE_FILE_AND_ROW string. This is to ensure if we sort
            # by SOURCE_FILE_AND_ROW the row number will be in the proper order
            # eg. Sorting the strings "2" and "10" will result in the incorrect order ["10", "2"], but sorting the strings
            # "02" and "10" will result in the correct order ["02", "10"].
            max_row_digits = len(str(df[TrackingSlots.SOURCE_ROW].max()))
            df[TrackingSlots.SOURCE_FILE_AND_ROW] = df.apply(
                lambda x: f"{x[TrackingSlots.SOURCE_FILE]}/{x[TrackingSlots.SOURCE_ROW]:0{max_row_digits}d}",
                axis=1,
            )

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
            logger.info(f"Data file has {len(cur_data)} rows: {file}")

    return data


def _cast_types(v: Any, cast_types: str) -> Any:
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


def get_cast_functions(schema: SchemaView) -> Dict[str, Dict[str, Callable]]:
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
    for class_name in schema.all_classes():
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
            slot_defn = schema.induced_slot(slot_name=slot_name, class_name=class_name)
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
                    key=lambda x: order.index(x) if x in order else order.index("*"),
                )
                cur_cast_functions[slot_name] = partial(_cast_types, cast_types=rng)
            elif rng in ["float", "double"]:
                cur_cast_functions[slot_name] = partial(
                    _cast_types, cast_types=["float"]
                )
            elif rng == "integer":
                cur_cast_functions[slot_name] = partial(
                    _cast_types, cast_types=["integer"]
                )
            else:
                cur_cast_functions[slot_name] = partial(
                    _cast_types, cast_types=["string"]
                )
    return cast_functions


def add_tracking_slots_derivations(spec: Dict, target_schema: SchemaView):
    """Add slot derivations for all class derivations in the mapper spec to copy over the tracking columns
    (from TrackingSlots) to the output. The tracking slots include the source class and source row number
    that mapped data was mapped from. It helps with sorting the output and other down-stream operations
    (eg. might be used when generating IDs that depend on which source class the row originated from)

    Args:
        spec (Dict): The mapper spec to add a row number slot derivation to all classes.
        target_schema (SchemaView): The LinkML schema for the target database that the spec maps onto.
    """
    tree_root = [
        c for c in target_schema.all_classes() if target_schema.get_class(c).tree_root
    ][0]

    all_tracking_slots = get_all_tracking_slots()
    for class_name, class_derivation in spec["class_derivations"].items():
        if class_name == tree_root:
            continue

        for col in all_tracking_slots:
            class_derivation["slot_derivations"][col] = {
                "name": col,
                "populated_from": col,
            }


def add_tracking_slots_to_schema(schema: SchemaView):
    """Add all tracking slots to all classes in the schema.

    Tracking slots include the source row number and class name of a row. These get copied over
    to the mapped data so we know which class and row and output row was derived from. It can
    be used for sorting and other downstream operations, such as for ID generation.

    Args:
        schema (SchemaView): The schema to add the tracking slots to (for all classes).
    """
    all_tracking_slots = get_all_tracking_slots()
    for slot_definition in schema.schema.classes.values():
        slot_definition.slots.extend(all_tracking_slots)

    for slot in all_tracking_slots:
        rng = TrackingSlotsTypes.get(slot, "string")
        schema.schema.slots[slot] = SlotDefinition(
            name=slot, from_schema=schema.schema.id, range=rng
        )


def get_all_tracking_slots() -> List[str]:
    """Get all the tracking slots, which are all the columns specified in TrackingSlots.

    Tracking slots include the source row number and class name of a row. These get copied over
    to the mapped data so we know which class and row and output row was derived from. It can
    be used for sorting and other downstream operations, such as for ID generation.

    Returns:
        List[str]: List of all tracking slots.
    """
    return [
        getattr(TrackingSlots, v) for v in vars(TrackingSlots) if not v.startswith("__")
    ]


def run_mapper(
    data: Dict[str, List],
    session: Session,
    data_output_dir: Union[str, Path],
    mapper_file: Union[str, Path],
    source_schema: SchemaView,
    target_schema: SchemaView,
    file_index: Optional[int] = None,
    unrestricted_eval: bool = False,
    filter_config_file: Optional[Union[str, Path]] = None,
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
    # Load the mapper spec
    with open(mapper_file, "r") as f:
        mapper_spec = yaml.safe_load(f)

    # Add all tracking slot derivations. This will copy all slots found in TrackingSlots, such as the source
    # class and source row number that the output row was derived from. These slots can be used for sorting
    # and other downstream operations such as ID generation.
    add_tracking_slots_derivations(mapper_spec, target_schema)

    # Run the mapper to get the mapped data
    logger.info(f"Mapping data with mapper spec {mapper_file}")
    trans_tic = datetime.now()
    session.set_object_transformer(mapper_spec)
    session.object_transformer.unrestricted_eval = unrestricted_eval
    mapped_data = session.transform(data)
    logger.info(
        f"Mapped in {datetime.now() - trans_tic} (for mapper spec {mapper_file})"
    )

    # Convert the data to a DataFrame, store in all_mapped_data, and save to disk
    all_mapped_data = {}
    for target_type, target_data in mapped_data.items():
        if target_data is None:
            continue

        # Remove any extra info from the target_type
        # eg "protocolSteps[inhibition]" becomes "protocolSteps"
        target_type = get_class_name_from_file_name(target_type, target_schema)

        df = pd.DataFrame(target_data)

        # Add any missing columns and order them according to the target schema
        if target_schema is not None:
            class_definition = target_schema.induced_class(target_type)
            all_slots = list(class_definition.attributes.keys())
            unrecognized = [s for s in df.columns if s not in all_slots]
            if len(unrecognized) > 0:
                raise ValueError(
                    f"Found unrecognized slot(s) in mapped data for class '{target_type}': {unrecognized}"
                )
            missing = [s for s in all_slots if s not in df.columns]
            if len(missing) > 0:
                df[missing] = None
            df = order_columns(df, all_slots)

        # Keep a copy of the mapped data
        if target_type not in all_mapped_data:
            all_mapped_data[target_type] = []
        all_mapped_data[target_type].append(df)

        # Save the unmerged mapped data to disk (typically just for debugging purposes, we save
        # the whole filtered and sorted data later on)
        if SAVE_UNMERGED_DATA and len(df.index) > 0 and data_output_dir is not None:
            file_index_tag = f"-{file_index:010d}" if file_index is not None else ""
            output_data_file = os.path.join(
                data_output_dir,
                f"%s-{target_type}{file_index_tag}.csv"
                % os.path.splitext(os.path.basename(mapper_file))[0],
            )
            logger.info(
                f"Saving mapped data file for {target_type} ({len(df.index)} rows): {output_data_file}"
            )
            # all_tracking_slots = get_all_tracking_slots()
            # keep_columns = [c for c in df.columns if c not in all_tracking_slots]
            keep_columns = df.columns
            save_data_frame(df[keep_columns], output_data_file, index=False)

    return file_index, all_mapped_data


def _run_mapper_with_kwargs(kwargs: Dict) -> Dict[str, List[Dict]]:
    """Call run_mapper with the specified kwargs as named parameters.

    Args:
        kwargs (Dict): Dictionary of key-values to pass to run_mapper.

    Returns:
        Dict[str, List[Dict]]: The result of running run_mapper.
    """
    return run_mapper(**kwargs)


def make_data_splits(
    data: Dict[str, List], num_splits: int, min_split_size: int = 100
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


def sort_mapped_data(df: pd.DataFrame, *, drop_sorting_column: bool) -> pd.DataFrame:
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


def map_and_filter(
    source_schema_file: Union[str, Path],
    target_schema_file: Union[str, Path],
    mapper_dir: Union[str, Path],
    data_files: Dict[str, Union[str, Path]],
    data_output_dir: Optional[Union[str, Path]] = None,
    filter_config_file: Optional[Union[str, Path]] = None,
    max_processes: Optional[int] = 1,
) -> Tuple[Dict[str, pd.DataFrame], Dict[str, List[Path]]]:
    """Map all the files specified in data_files using all mapper files found in the specified mapper directory,
    and optionally filter the results.

    This funciton will not generate IDs. To do the full mapping plus ID generation call full_map instead.

    The results will be saved to data_output_dir if specified. The file names will be the name of the output
    class.

    The results are returned and optionally saved to disk.

    Args:
        source_schema_file (Union[str, Path]): The LinkML schema for the source database.
        target_schema_file (Union[str, Path]): The LinkML schema for the target database.
        mapper_dir (Union[str, Path]): The directory containing all LinkML Mapper configuration (YAML)
            files. All config files will be used for mapping all the loaded data.
        data_files (Dict[str, Union[str, Path]]): Dictionary of all source data files to map. The keys
            are the source class names and the values are lists of data files belonging to the class,
            which should be mapped.
        data_output_dir (Optional[Union[str, Path]], optional): Directory to save the mapped output to. If None
            then the mapped data are not saved to disk, but are still returned. Defaults to None.
        filter_config_file (Optional[Union[str, Path]], optional): The filter configuration file, to filter the
            final transformed data (eg. remove rows that should be ignored due to missing data). Defaults to None.
        max_processes (Optional[int], optional): Maximum number of processes to use for multi-processing.
            If 1 then no multi-processing will be performed. If None or 0 then the maximum number
            (as obtained by cpu_count()) will be used. Note that for mapping small tables multi-processing
            might be slower. Defaults to 1.

    Returns:
        Tuple[Dict[str, pd.DataFrame], Dict[str, List[Path]]]: The mapped data as a tuple
            (all_mapped_data, all_mapped_files).
            all_mapped_data (Dict[str, pd.DataFrame]): Keys are the target class names and the values are the mapped
                data (a single DataFrame) for that class.
            all_mapped_files (Dict[str, List[Path]]): Keys are the target class names and values are a list of
                the output data files of the mapped data for the class.
    """
    tic = datetime.now()

    logger.info(f"Beginning mapping at {tic}")

    map_tic = datetime.now()

    if not max_processes or max_processes <= 0:
        max_processes = cpu_count()

    source_schema = SchemaView(source_schema_file)
    target_schema = SchemaView(target_schema_file) if target_schema_file else None

    # Add all tracking slots to the source schema. These include the source class and source row number.
    # Later on, after loading the mapper spec, we add a slot derivation for all classes to copy the tracking slots to
    # the output (see add_tracking_slots_derivations)
    add_tracking_slots_to_schema(source_schema)
    if target_schema:
        add_tracking_slots_to_schema(target_schema)

    # Read all the data from disk.
    data = load_data(data_files, source_schema)

    if len(data) == 0:
        logger.warning(
            "No data loaded from disk. Be sure the file names match the source schema table names, that there are files in the directory, and that the files are not empty."
        )
        return {}, {}

    logger.info(f"Data loaded for source tables: {list(data.keys())}")

    if max_processes == 1:
        split_data = [data]
    else:
        split_data = make_data_splits(data, num_splits=max_processes)

    # Set up the LinkML Mapper Session
    logger.info("Creating Session for mapping")
    t = datetime.now()
    session = Session()
    session.set_source_schema(source_schema)
    logger.info(f"Finished creating Session for mapping in {datetime.now() - t}")

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

    # Create arguments to pass to _run_mapper for each mapper config file.
    map_args = []
    for split_num, split in enumerate(split_data):
        cur_args = [
            {
                "file_index": split_num + file_num * len(mapper_files),
                "data": split,
                "data_output_dir": data_output_dir,
                "session": session,
                "mapper_file": mapper_file,
                "source_schema": source_schema,
                "target_schema": target_schema,
                "unrestricted_eval": True,
                "filter_config_file": filter_config_file,
            }
            for file_num, mapper_file in enumerate(mapper_files)
        ]
        map_args.extend(cur_args)

    # Call _run_mapper, either using multiple processes or one at a time
    if max_processes == 1:
        logging.info("Running without multiprocessing")
        results = []
        for args in map_args:
            results.append(_run_mapper_with_kwargs(args))
    else:
        logging.info(f"Running with {max_processes} processes")
        pool = Pool(max_processes)
        results = pool.map(_run_mapper_with_kwargs, map_args)

    # Collect all the results in a single Dictionary. The keys are the target class and the
    # values are Lists of the resulting DataFrames.
    all_mapped_data = {}
    results = sorted(results, key=lambda x: x[0])
    for _, cur_mapped_data in results:
        for cls, mapped_data in cur_mapped_data.items():
            if cls not in all_mapped_data:
                all_mapped_data[cls] = []
            all_mapped_data[cls].extend(mapped_data)

    # Combine the DataFrames in all_mapped_data
    for target_type, all_df in all_mapped_data.items():
        df = pd.concat(all_df, axis=0)
        # Retain the original order by sorting by the TrackingSlots.
        df = sort_mapped_data(df, drop_sorting_column=False)
        all_mapped_data[target_type] = df

    logger.info(f"Total time for mapping: {datetime.now() - map_tic}")

    # Filter all the DataFrames
    if filter_config_file:
        filter_tic = datetime.now()
        data_filter = DataFilter(filter_config_file)
        filtered_mapped_data = {}
        for target_type, df in all_mapped_data.items():
            data = {target_type: df}
            data, _ = data_filter.run_filter(data=data)
            for target_class, target_df in data.items():
                if target_class not in filtered_mapped_data:
                    filtered_mapped_data[target_class] = []
                filtered_mapped_data[target_class].append(target_df)
        # Combine the DataFrames in filtered_mapped_data
        for target_class, all_df in filtered_mapped_data.items():
            df = pd.concat(all_df, axis=0).reset_index(drop=True)
            filtered_mapped_data[target_class] = df
        all_mapped_data = filtered_mapped_data
        logger.info(f"Total time for filtering: {datetime.now() - filter_tic}")

    # Save data to disk
    all_mapped_files = {}
    if data_output_dir is not None:
        save_tic = datetime.now()
        for class_name, df in all_mapped_data.items():
            output_data_file = os.path.join(data_output_dir, f"{class_name}[preid].csv")
            if os.path.exists(output_data_file):
                raise ValueError(f"Output data file already exists: {output_data_file}")
            logger.info(
                f"Saving merged mapped data file for {class_name} ({len(all_df)} source frame(s), {len(df.index)} rows): {output_data_file}"
            )
            save_data_frame(df, output_data_file, index=False)
            if class_name not in all_mapped_files:
                all_mapped_files[class_name] = []
            all_mapped_files[class_name].append(output_data_file)
        logger.info(f"Total time for saving: {datetime.now() - save_tic}")

    return all_mapped_data, all_mapped_files


def full_map(
    module: str,
    module_dir: str,
    data_files: Dict[str, List[Union[str, Path]]],
    output_dir: str,
    temp_dir: Union[str, Path] = None,
    input_max_rows: int = None,
    max_processes: int = 1,
    id_debug: bool = False,
) -> Dict[str, List[Path]]:
    """Perform a full mapping, including filtering and ID generation.

    Args:
        module (str): The built-in module for the mapping, eg. "odm_v1_to_v2" or "nwss_reporting_to_v2".
            If None then module_dir must be specified.
        module_dir (str): The directory for the mapping module. If None then module must be specified.
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
        id_debug (bool, optional): If True then run the ID generator in debug mode. Debug mode will result
            in the output mapped data to include various columns that were used during ID generation
            (such as the source database class name and row number used for populating a row, the original
            unmodified IDs before generation occurred, etc.), and will also not drop rows where duplicate
            primary keys are found, instead an additional column named "__drop" will be added to the output
            and set to TRUE if the row would be dropped when not in debug mode. Defaults to False.

    Returns:
        Dict[str, List[Path]]: Lists all final mapped files saved to disk. The keys are the output class
            names and the values are lists of file paths representing mapped data for the output class.
    """
    tic = datetime.now()

    output_dir = Path(output_dir)

    # Prepare temporary directory
    if not temp_dir:
        temp_dir_obj = tempfile.TemporaryDirectory()
        temp_dir = Path(temp_dir_obj.name)
    else:
        temp_dir_obj = None
        temp_dir = Path(temp_dir)
    logger.info(f"Using temporary directory {temp_dir}")

    # Load the data mapping module
    module_dir = (
        Path(os.path.dirname(__file__)) / ".." / ".." / "data" / "modules" / module
        if module
        else module_dir
    )
    module_config = ModuleConfig(module_dir)

    # Clean the data
    mapped_data_dir = temp_dir / "mapped_data"
    cleaned_data_dir = temp_dir / "cleaned_data"
    clear_dirs([cleaned_data_dir, mapped_data_dir])
    cleaner = DataCleaner(schema=module_config.source_schema)
    data_files = cleaner.clean_data_files(
        data_files,
        output_dir=cleaned_data_dir,
        max_rows=input_max_rows,
    )

    # Map the cleaned data
    _, data_files = map_and_filter(
        source_schema_file=module_config.source_schema,
        target_schema_file=module_config.target_schema,
        mapper_dir=module_config.mapper_dir,
        data_files=data_files,
        data_output_dir=mapped_data_dir,
        filter_config_file=module_config.filters,
        max_processes=max_processes,
    )

    # Generate IDs in the mapped data
    id_output_dir = output_dir
    clear_dirs([id_output_dir])
    gen = IDGenerator(
        data_files=data_files,
        config_file=module_config.id_config,
        id_code_file=module_config.id_code,
        id_code_sheet=None,
    )
    gen.make_all_ids()
    data_files = gen.save_all(
        output_dir=id_output_dir,
        orig_columns_only=not id_debug,
        drop_duplicates=not id_debug,
    )

    # Delete temporary directory
    if temp_dir_obj is not None:
        temp_dir_obj.cleanup()

    logger.info(f"Total runtime: {datetime.now() - tic}")

    return data_files
