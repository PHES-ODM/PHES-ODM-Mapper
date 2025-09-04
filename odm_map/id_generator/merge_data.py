"""
The class MergeData merges multiple files belonging to the same dataset together.

During merging the primary keys are updated (by adding indices) to make sure there
are no conflicts in primary key names. Foreign keys are also updated to account
for the changes in primary keys.

For each table, the first file of that table remains unchanged (ie. no changes in
primary or foreign keys), however, any table merged onto the end of the initial
table might be changed (ie. changes in primary/foreign keys to avoid conflicts).

## Usage

```python
from odm_map.id_generator.merge_data import MergeData

merge = MergeData(
    inputs=[
        "data/dir1",
        "data/dir2",
        "data/dir3"],
    schema="schemas/odm_v3.yaml"
)
data_frames = merge.merge("output/dir/", debug=False)
```
"""

from typing import Union, List, Tuple, Optional, Dict
from pathlib import Path
import pandas as pd

from linkml_runtime import SchemaView

from odm_map.utils.logger import get_logger
from odm_map.utils.general_utils import merge_dicts_of_lists
from odm_map.utils.cli_utils import get_input_data_files_from_dir
from odm_map.utils.extra_and_tracking_slots import (
    load_data_with_source_tracking_columns,
)
from odm_map.id_generator.generator import IDGenerator

logger = get_logger(__name__)


class CodeColumns:
    CLASS = "class"
    SLOT = "slot"
    CODE0 = "code0"


class MergeData:
    def __init__(self, inputs: Union[str, Path], schema: Union[str, Path, SchemaView]):
        """Constructor for MergeData.

        Args:
            inputs (Union[str, Path]): List of directories to merge. The files should be data files
                (eg. CSV, TSV files) where the file names contain class names found in the schema.
                The data for each class will be merged together for each class.
            schema (Union[str, Path, SchemaView]): Path or SchemaView for the LinkML schema.
        """
        if isinstance(schema, (str, Path)):
            schema = SchemaView(schema)
        self.schema = schema

        self.retrieve_all_foreign_keys()
        self.retrieve_all_primary_keys()

        # Load all inputs
        self.datasets = []
        for cur_input in inputs:
            files = get_input_data_files_from_dir(cur_input, self.schema)
            dfs = load_data_with_source_tracking_columns(files, self.schema)
            self.datasets.append(dfs)

    def merge(
        self,
        output_dir: Optional[Union[str, Path]] = None,
        multi_bar_progress: bool = True,
        debug: bool = False,
    ) -> Dict[str, List[pd.DataFrame]]:
        """Merge all data and optionally save to disk.

        Args:
            output_dir (Optional[Union[str, Path]], optional): Directory to save the merged
                data to. If None then the data is returned but not saved to disk. Defaults
                to None.
            multi_bar_progress (bool, optional): If True then show multiple progress bars
                at the same time showing the progress of the ID generation. There is one
                progress bar per class that we are generating IDs for. If False then only
                show one progress bar at a time. We would normally use True, but for cases
                where showing multiple bars at once does not display well (eg. in a Jupyter
                notebook), then False should be specified. Defaults to True.
            debug (bool, optional): If True then run the ID generator in debug mode. In debug
                mode the output will contain additional columns for debugging info. Rows
                with duplicate primary keys will also be retained, but a new __drop column
                will be added that is True if the row should be dropped. Defaults to False.
        """
        self.generate_assets()

        id_code_df = pd.concat(
            [self.fk_id_code_df, self.pk_id_code_df], axis=0, ignore_index=True
        )
        id_code_files = [{"id_code_df": id_code_df}]

        gen = IDGenerator(
            data_files=None,
            data_frames=self.all_dfs,
            schema=self.schema,
            config_file=self.named_linkages,
            id_code_files=id_code_files,
            multi_bar_progress=multi_bar_progress,
        )
        data_frames = gen.run_generator(
            keep_extra_columns=debug,
            keep_tracking_columns=debug,
            keep_debug_columns=debug,
            remove_duplicates=not debug,
        )
        if output_dir is not None:
            gen.save_all(output_dir)

        return data_frames

    def generate_assets(self):
        """Generate all assets (in memory) as preprocess all input datasets. This is to prepare
        for the actual merging.
        """
        self.make_pk_id_code()
        self.make_fk_id_code()
        self.make_named_linkages()
        self.make_linkage_slots()
        self.combine_datasets()

    def get_foreign_keys_for_class(self, class_name: str) -> List[str]:
        """Get all slots in the class class_name that are foreign keys into other classes.

        Args:
            class_name (str): The name of the class to get the foreign keys for.

        Returns:
            List[str]: List of slot names that are foreign keys.
        """
        return [s for c, s in self.foreign_keys if str(class_name) == c]

    def get_linkage_path_name(
        self, source_class: str, source_slot: str, target_class: str, target_slot: str
    ) -> str:
        """Get the name of the linkage path that provides linking from the source slot
        to the target slot, to retrieve a primary key (at the target slot) that should
        be used as a foreign key (at the source slot).

        Args:
            source_class (str): The source class that the source slot belongs to.
            source_slot (str): The source slot that the linkage is for. This is a
                foreign key.
            target_class (str): The target class that the target slot belongs to.
            target_slot (str): The target slot that the linkage is for. This is a
                primary key.

        Returns:
            str: The string name to use for the named linkage.
        """
        return f"{source_class}_{source_slot}_{target_class}_{target_slot}"

    def get_linkage_slot_name(
        self, source_class: str, source_slot: str, target_class: str, target_slot: str
    ) -> str:
        """Get the slot name to use for linking from the source slot to the target slot.
        This slot is used for linking, by matching values in the source class and the
        target class. It is the slot used in the linkage path that is given the name
        provided by the function get_linkage_path_name, where the parameters are
        the same as for this function.

        Args:
            source_class (str): The class that the source slot in the linkage belongs to.
            source_slot (str): The source slot that the linkage is for. This is a foreign
                key that gets linked to the target slot (the primary key), by matching
                values found in the returned slot name.
            target_class (str): The class that the target slot in the linkage belongs to.
            target_slot (str): The target slot that the linkage is for. This is a primary
                key that gets populated in the source_slot (the foreign key), by matching
                values found in the returned slot name.

        Returns:
            str: The slot name that is used to link from the source slot (a foreign key)
                to the target slot (a primary key). This slot gets added to the source_class
                and target_class, to provide the slots used for linking.
        """
        linkage_path_name = self.get_linkage_path_name(
            source_class, source_slot, target_class, target_slot
        )
        return f"_extra_{linkage_path_name}_tag"

    def make_pk_id_code(self):
        """Generate the custom ID code that specified how all primary keys get generated.

        The resulting code gets saved in memory in self.pk_id_code_df and can be used by
        the IDGenerator.
        """
        df = pd.DataFrame(
            {
                CodeColumns.CLASS: [],
                CodeColumns.SLOT: [],
                CodeColumns.CODE0: [],
            }
        )

        # Add custom code for all primary keys
        for class_name, slot_name in self.primary_keys:
            # Is a primary key, add the custom code
            code = f"dat.{class_name}.__{slot_name}"
            row = pd.DataFrame(
                {
                    CodeColumns.CLASS: [class_name],
                    CodeColumns.SLOT: [slot_name],
                    CodeColumns.CODE0: [code],
                }
            )
            df = pd.concat([df, row], axis=0, ignore_index=True)

        self.pk_id_code_df = df

    def make_fk_id_code(self):
        """Generate the custom ID code that specified how all foreign keys get generated.

        The resulting code gets saved in memory in self.fk_id_code_df and can be used by
        the IDGenerator.
        """
        df = pd.DataFrame(
            {
                CodeColumns.CLASS: [],
                CodeColumns.SLOT: [],
                CodeColumns.CODE0: [],
            }
        )

        # Add custom code for all foreign keys
        for class_name, slot_name in self.foreign_keys:
            # Add the custom code for the slot
            target_class_name, target_slot_name = self.get_fk_target(
                class_name, slot_name
            )
            linkage_path_name = self.get_linkage_path_name(
                class_name, slot_name, target_class_name, target_slot_name
            )
            code = f'dat.{target_class_name}.get_first_linked_value("{target_slot_name}", linkage_path="{linkage_path_name}")'
            row = pd.DataFrame(
                {
                    CodeColumns.CLASS: [class_name],
                    CodeColumns.SLOT: [slot_name],
                    CodeColumns.CODE0: [code],
                }
            )
            df = pd.concat([df, row], axis=0, ignore_index=True)

        self.fk_id_code_df = df

    def get_fk_target(self, class_name: str, slot_name: str) -> Tuple[str, str]:
        """Get the target class and slot that the specified slot points to. The specified
        slot is a foreign key, and the returned class/slot is a primary key.

        Args:
            class_name (str): The class name for the foreign key.
            slot_name (str): The slot name for the foreign key.

        Returns:
            Tuple[str, str]: A tuple of (class, slot) where "class" is the class name
                that slot_name points to and "slot" is the slot name that slot_name
                points to. The returned class/slot combination is a primary key that is
                a target of the specified foreign key.
        """
        slot_defn = self.schema.induced_slot(slot_name, class_name)
        target_class_name = str(slot_defn.range)
        target_class_defn = self.schema.induced_class(target_class_name)
        target_identifiers = [
            str(k) for k, v in target_class_defn.attributes.items() if v.identifier
        ]
        return target_class_name, target_identifiers[0]

    def make_named_linkages(self):
        """Make a dictionary (ie. a configuration) of all named linkages that is used by
        the ID generator to link foreign keys to primary keys.
        """
        named_linkages = {}
        # Add a named linkage for all foreign keys, from the source slot to the target slot
        for class_name, slot_name in self.foreign_keys:
            target_class_name, target_slot_name = self.get_fk_target(
                class_name, slot_name
            )
            linkage_path_name = self.get_linkage_path_name(
                class_name, slot_name, target_class_name, target_slot_name
            )
            linkage_slot_name = self.get_linkage_slot_name(
                class_name, slot_name, target_class_name, target_slot_name
            )
            # Add the named linkage path. The source and target slots in the linkage are both
            # named linkage_slot_name.
            cur_path = {
                linkage_path_name: {
                    class_name: {
                        target_class_name: {
                            "source_slot": [linkage_slot_name],
                            "target_slot": [linkage_slot_name],
                        }
                    }
                }
            }
            named_linkages.update(cur_path)

        self.named_linkages = {"named_class_linkages": named_linkages}

    def retrieve_all_foreign_keys(self):
        """Retrieve all (class, slot) tuples for all foreign keys in the schema and
        save the results internally to self.foreign_keys for future use.
        """
        foreign_keys = []
        for class_name in self.schema.all_classes().keys():
            class_defn = self.schema.induced_class(class_name)
            for attr_name, attr_defn in class_defn.attributes.items():
                rng = attr_defn.range
                if rng in self.schema.all_classes():
                    foreign_keys.append((str(class_name), str(attr_name)))
        self.foreign_keys: List[Tuple[str, str]] = foreign_keys

    def retrieve_all_primary_keys(self):
        """Retrieve all (class, slot) tuples for all primary keys in the schema and
        save the results internally to self.primary_keys for future use.
        """
        primary_keys = []
        for class_name in self.schema.all_classes().keys():
            class_defn = self.schema.induced_class(class_name)
            for attr_name, attr_defn in class_defn.attributes.items():
                if attr_defn.identifier:
                    primary_keys.append((str(class_name), str(attr_name)))
        self.primary_keys: List[Tuple[str, str]] = primary_keys

    def make_linkage_slots(self):
        """Add all linkage slots (which are named according to the function get_linkage_slot_name)
        to all loaded datasets. The values in the linkage slots in each DataFrame are set so that
        we can link foreign keys in one table to primary keys in other tables.
        """
        # for dataset_idx, dataset in enumerate(self.datasets[1:]):
        for dataset_idx, dataset in enumerate(self.datasets):
            for class_name, dfs in dataset.items():
                if len(dfs) != 1:
                    raise ValueError(
                        f"Class '{class_name}' must have only one DataFrame, but {len(dfs)} were found."
                    )
                # Get the source DataFrame (belonging to the class of the foreign key)
                df = dfs[0]

                # Loop through all foreign keys
                for slot_name in self.get_foreign_keys_for_class(class_name):
                    target_class_name, target_slot_name = self.get_fk_target(
                        class_name, slot_name
                    )
                    if target_class_name not in dataset:
                        logger.warning(
                            f"Target class '{target_class_name}' for foreign key '{class_name}.{slot_name}' does not have a DataFrame in the dataset."
                        )
                        continue

                    # Get the target DataFrame (belonging to the class of the primary key)
                    target_df = dataset[target_class_name][0]
                    linkage_slot_name = self.get_linkage_slot_name(
                        class_name, slot_name, target_class_name, target_slot_name
                    )
                    if linkage_slot_name not in target_df.columns:
                        target_df[linkage_slot_name] = None

                    if linkage_slot_name not in df.columns:
                        df[linkage_slot_name] = "<nolink>"

                    # Find the primary key (in target_df[target_slot_name]) that matches
                    # the foreign key (in df[slot_name]).
                    # In the matching rows, make the values in the column linkage_slot_name equal
                    for idx, val in enumerate(df[slot_name]):
                        if val is None or val == "":
                            continue
                        target_idx = target_df[
                            target_df[target_slot_name] == val
                        ].index[0]
                        match_value = f"set{dataset_idx}_{idx}"
                        target_value = target_df.loc[target_idx, linkage_slot_name]
                        if target_value:
                            # A match value already exists, so use it instead
                            df.loc[idx, linkage_slot_name] = target_value
                        else:
                            target_df.loc[target_idx, linkage_slot_name] = match_value
                            df.loc[idx, linkage_slot_name] = match_value

    def combine_datasets(self):
        """Combine the loaded and processed datasets, so that we have a single DataFrame per class.
        This should be done immediately before calling the merge function.
        """
        all_dfs = merge_dicts_of_lists(self.datasets)

        # For each class, combine all the DataFrames for that class into a single DataFrame.
        for class_name, dfs in all_dfs.items():
            all_dfs[class_name] = [pd.concat(dfs, axis=0, ignore_index=True)]

        self.all_dfs = all_dfs
