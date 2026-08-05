"""
For multivalued enum slots keep only the enumeration values that have the deepest enum value in
the hierarchy for the enumeration as specified in a LinkML schema. That is, if the slot has multiple
values, then remove any of the values that is a parent (via the is_a attribute in the LinkML schema)
of any of the other values.

# Usage

```python
from odm_map.enum_hierarchy.enum_hierarchy_selector import EnumHierarchySelector

# The following will apply the selector to all slots in the DataFrames that are multivalued and
# that have at least one enumeration in its range, according to the LinkML schema.
selector = EnumHierarchySelector("pha4ge.yaml")
selector.select(data_files=data_files, output_dir="/output/dir", output_fmt="{class_name}-sel.csv")
```
"""

import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml
from linkml_runtime import SchemaView
from linkml_runtime.linkml_model import SlotDefinition

from odm_map.utils.general_utils import (
    load_data_frames_for_classes,
    make_multivalued,
    save_data_frame,
)
from odm_map.utils.logger import get_logger
from odm_map.utils.schema_utils import get_ranges_of_slot_defn

logger = get_logger(__name__)


class ConfigKeys:
    CLASSES = "classes"
    SLOTS = "slots"


class EnumHierarchySelector:
    def __init__(
        self, schema: str | Path | SchemaView, config: str | Path | None = None
    ):
        if isinstance(schema, SchemaView):
            self.schema = schema
        else:
            self.schema = SchemaView(schema)

        if config:
            with open(config, "r") as f:
                self.config = yaml.safe_load(f)
        else:
            self.config = None

    def select(
        self,
        data_files: dict[str, list[str | Path]] | None = None,
        data_frames: dict[str, list[pd.DataFrame]] | None = None,
        output_dir: str | Path | None = None,
        output_fmt: str | None = "{class_name}.csv",
        max_rows: int | None = None,
    ) -> dict[str, list[pd.DataFrame]]:
        """From the specified data files and frames, select all the deepest enumeration values from
        the DataFrames for all slots that are multivalued and that have enumeration ranges.

        Results can optionally be saved to disk.

        Args:
            data_files (dict[str, list[str | Path]] | None, optional): A dictionary of files and/or
                directories to load the data from, in addition to the data in data_frames. The keys
                are the class names and the values are all data files/directories to load for that
                class name. Defaults to None.
            data_frames (dict[str, list[pd.DataFrame]] | None, optional): A dictionary of DataFrames
                to apply the selector to. They keys are the class names and the values are
                lists of DataFrames belonging to that class. This dictionary and the DataFrames
                might be modified in-place. Defaults to None.
            output_dir (str | Path | None, optional): If not empty then the directory to save
                the resulting data to. Defaults to None.
            output_fmt (str | None, optional): If output_dir is specified then the file name
                to save to the output dir, with the string interpolation tag {class_name} available.
                eg. if "{class_name}-sel.csv", then the file name for the "measures" class will be
                "measures-sel.csv". Defaults to "{class_name}.csv".
            max_rows (int | None, optional): Maximum number of rows to load from the files in
                data_files. Defaults to None.

        Returns:
            dict[str, list[pd.DataFrame]]: The DataFrames after selection is performed. The keys
                are the class names and the values are lists of DataFrames belonging to that class,
                after selection is performed. Some of the DataFrames might be the same as the
                ones originally passed in with the data_frames parameter, and the returned
                dictionary might be the same as data_frames.
        """
        # Load all the data into data_frames
        if data_frames is None:
            data_frames = {}
        load_data_frames_for_classes(data_files, data_frames, max_rows=max_rows)

        tic = datetime.now().astimezone()
        for class_name, dfs in data_frames.items():
            logger.info(f"Selecting from enum hierarchy for class {class_name}")
            class_defn = self.schema.induced_class(class_name)

            slots = []
            if self.config is None:
                # Collect all the slots to process. These are multivalued slots that have at least one enumeration
                # in its range
                for slot_defn in class_defn.attributes.values():
                    if not slot_defn.multivalued:
                        continue

                    # Get the range of the slot
                    ranges = get_ranges_of_slot_defn(slot_defn)

                    for rng in ranges:
                        if rng in self.schema.all_enums():
                            slots.append(slot_defn)
                            break
            else:
                # The slots to process for the current class is specified in the config file.
                class_config = self.config.get(ConfigKeys.CLASSES, {}).get(
                    class_name, None
                )
                if class_config:
                    slots_config = class_config.get(ConfigKeys.SLOTS, [])
                    for cur_slot in slots_config:
                        slot_defn = class_defn.attributes[cur_slot]
                        slots.append(slot_defn)

            if not slots:
                continue

            # Go through the DataFrames and process all the slots
            logger.info(
                f"Selecting from slots in class '{class_name}': {', '.join([s.name for s in slots])}"
            )
            for df in dfs:
                for slot_defn in slots:
                    self.select_from_df(df, class_name, slot_defn)

        logger.info(
            f"Finished all enum hierarchy selection: {datetime.now().astimezone() - tic}"
        )

        if output_dir and output_fmt:
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            for class_name, dfs in data_frames.items():
                df = pd.concat(dfs, axis=0)
                output_file = os.path.join(
                    output_dir, output_fmt.format(class_name=class_name)
                )
                logger.info(
                    f"Saving after selecting enum hierarchy for class {class_name} to {output_file}"
                )
                save_data_frame(df, output_file)

        return data_frames

    def select_from_df(
        self, df: pd.DataFrame, class_name: str, slot_defn: SlotDefinition
    ):
        """Select the deepest enumeration value(s) from the DataFrame that belongs to class
        class_name for the single slot defined by slot_defn.

        Args:
            df (pd.DataFrame): The DataFrame to select from. This is modified in-place.
            class_name (str): The class name that the DataFrame belongs to.
            slot_defn (SlotDefinition): The slot definition for the slot to select from.
        """
        ranges = get_ranges_of_slot_defn(slot_defn)
        # Cache ancestor lookups: same enum value appearing in many rows is only resolved once.
        ancestor_cache: dict = {}
        for row_idx, cell in df[slot_defn.name].items():
            # Get the values for the current row in the slot (orig_vals), we will replace them with new_vals
            orig_vals = make_multivalued(cell)
            new_vals = orig_vals.copy()
            # Iterate over all the values in the current row for the slot, remove any of the values that appear as
            # an ancestor of any of the other values
            for val in orig_vals:
                for rng in ranges:
                    # Remove all values in new_vals that is an ancestor for the current val. Note that
                    # permissible_value_ancestors will return val as well, which is why we need to not
                    # include val in ancestors
                    cache_key = (val, rng)
                    if cache_key not in ancestor_cache:
                        try:
                            ancestors = self.schema.permissible_value_ancestors(val, rng)
                        except:
                            ancestors = []
                        ancestor_cache[cache_key] = [
                            str(a)
                            for a in ancestors
                            if str(a) != val
                        ]
                    ancestors = ancestor_cache[cache_key]
                    new_vals = [v for v in new_vals if v not in ancestors]
            if new_vals != orig_vals:
                logger.info(
                    f"Selected deepest enum values from {class_name}.{slot_defn.name}:{row_idx}: Original={orig_vals} New={new_vals}"
                )
                # @TODO: Is this the best way to convert to a multi-valued string? LinkML treats multivalued values
                # as comma-separated strings, without outer square brackets, and without applying any escaping of
                # commas within the values.
                df.loc[row_idx, slot_defn.name] = ",".join(new_vals)
