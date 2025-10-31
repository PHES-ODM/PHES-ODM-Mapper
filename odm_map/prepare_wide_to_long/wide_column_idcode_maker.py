from typing import Union, Optional, Dict, Tuple, List, Generator
from pathlib import Path
import yaml
import pandas as pd
import os

from linkml_runtime import SchemaView

from odm_map.utils.logger import get_logger
from odm_map.utils.general_utils import read_data_frame, save_data_frame
from odm_map.prepare_wide_to_long.wide_column_utils import (
    ConfigKeys,
    WideColumnValues,
    column_and_group_of_column,
    get_extra_slot_for_flag_prefix,
    GROUP_FLAG_PREFIX,
)
from odm_map.utils.extra_and_tracking_slots import (
    is_tracking_slot,
    TrackingSlots,
)
from odm_map.utils.schema_utils import (
    get_ranges_of_slot_defn,
    all_classes_without_tree_root,
    get_primary_key,
)

logger = get_logger(__name__)


# All columns that should be in the ID code generation config file
class IDCodeColumns:
    CLASS = "class"
    SLOT = "slot"
    # The code columns are in the format f"{CODE_PREFIX}{CODE_SUFFIX}".format(idx), eg "code000", "code001", etc
    CODE_PREFIX = "code"
    CODE_SUFFIX = "{:03d}"


class MetaConfigKeys:
    EXPLICIT_GROUPS_KEY = "explicit_groups"
    IMPLICIT_GROUPS_KEY = "implicit_groups"


ID_CODE_FILE = "id_code.csv"
ID_CODE_CONFIG_FILE = "id_code_config.yaml"


class WideColumnIDCodeMaker:
    def __init__(
        self,
        config: Union[str, Path, Dict],
        expanded_meta: Union[str, Path, Dict],
        source_class_name: str,
        target_schema: Union[str, Path, SchemaView],
    ):
        self.source_class_name = source_class_name

        if isinstance(target_schema, (str, Path)):
            target_schema = SchemaView(target_schema)
        self.target_schema: SchemaView = target_schema

        if isinstance(config, dict):
            self.config = config
        else:
            with open(config, "r") as f:
                self.config = yaml.safe_load(f)

        if isinstance(expanded_meta, dict):
            self.meta_config = expanded_meta
        else:
            with open(expanded_meta, "r") as f:
                self.meta_config = yaml.safe_load(f)

    def iter_columns(
        self, df: pd.DataFrame
    ) -> Generator[Tuple[str, str, str, str], None, None]:
        for col in df.columns:
            if is_tracking_slot(col):
                continue

            # Get the current class (class_name), slot (slot_name), and group (group_name)
            col_no_group, group_name = column_and_group_of_column(col)
            parts = col_no_group.split(WideColumnValues.COLUMN_PART_SEPARATOR)
            if len(parts) != 2:
                logger.warning(
                    f"Expected column to have two parts, but {len(parts)} found instead: {col}"
                )
                continue
            class_short_name, slot_name = parts
            class_name = self.get_table_long_name(class_short_name)

            yield class_name, class_short_name, slot_name, group_name

    def make(
        self,
        data_file: Union[str, Path],
        data_frame: pd.DataFrame,
        output_dir: Union[str, Path] = None,
    ) -> Tuple[pd.DataFrame, Optional[str], Dict, Optional[str]]:
        if data_file:
            data_frame = read_data_frame(
                data_file, keep_default_na=False, na_values=None, nrows=0
            )
        self.df: pd.DataFrame = data_frame
        self.class_groups: Dict[str, Dict[str, List[str]]] = {}

        for class_name, class_short_name, slot_name, group_name in self.iter_columns(
            self.df
        ):
            if class_name not in self.class_groups:
                self.class_groups[class_name] = {
                    MetaConfigKeys.EXPLICIT_GROUPS_KEY: [],
                    MetaConfigKeys.IMPLICIT_GROUPS_KEY: [],
                }

            # Add the group_name to the explicit or implicit groups for the class
            if group_name in self.meta_config.get(
                MetaConfigKeys.EXPLICIT_GROUPS_KEY, []
            ):
                self.class_groups[class_name][
                    MetaConfigKeys.EXPLICIT_GROUPS_KEY
                ].append(group_name)
            if group_name in self.meta_config.get(
                MetaConfigKeys.IMPLICIT_GROUPS_KEY, []
            ):
                self.class_groups[class_name][
                    MetaConfigKeys.IMPLICIT_GROUPS_KEY
                ].append(group_name)

        # Remove duplicates from explicit and implicit groups
        for class_info in self.class_groups.values():
            class_info[MetaConfigKeys.EXPLICIT_GROUPS_KEY] = list(
                dict.fromkeys(class_info[MetaConfigKeys.EXPLICIT_GROUPS_KEY])
            )
            class_info[MetaConfigKeys.IMPLICIT_GROUPS_KEY] = list(
                dict.fromkeys(class_info[MetaConfigKeys.IMPLICIT_GROUPS_KEY])
            )

        # Go through all classes, create both the ID generation code and the linkage rules between classes

        # Go through all classes, create the ID code and the linkage rules for all slots that are foreign keys.
        id_code_df = pd.DataFrame()
        class_linkages = {}
        all_classes = sorted(all_classes_without_tree_root(self.target_schema))
        for class_name in all_classes:
            class_defn = self.target_schema.induced_class(class_name)
            for slot_defn in class_defn.attributes.values():
                ranges = get_ranges_of_slot_defn(slot_defn)

                # Get all ranges that point to another class
                ranges = [r for r in ranges if r in all_classes and r != class_name]

                for target_class in ranges:
                    # We want to link from the slot to the primary key of the target_class
                    # The ID code will be dat.target_class.primary_key.
                    # Get the primary key
                    target_primary_key = get_primary_key(
                        target_class, self.target_schema
                    )

                    # Create the ID code
                    code_column_name = f"{IDCodeColumns.CODE_PREFIX}{IDCodeColumns.CODE_SUFFIX}".format(
                        0
                    )
                    code = f"dat.{target_class}.{target_primary_key}"
                    cur_id_code = pd.DataFrame(
                        {
                            IDCodeColumns.CLASS: class_name,
                            IDCodeColumns.SLOT: slot_defn.name,
                            code_column_name: code,
                        },
                        index=[0],
                    )
                    id_code_df = pd.concat([id_code_df, cur_id_code], ignore_index=True)

                    # Create the linkage rule from class_name to target_class, if it doesn't already exist
                    if (
                        class_name not in class_linkages
                        or target_class not in class_linkages[class_name]
                    ):
                        if class_name not in class_linkages:
                            class_linkages[class_name] = {}
                        if target_class not in class_linkages[class_name]:
                            class_linkages[class_name][target_class] = {}
                        match_group = self.class_has_explicit_groups(
                            class_name
                        ) and self.class_has_explicit_groups(target_class)
                        if match_group:
                            class_linkages[class_name][target_class] = {
                                "source_slot": [
                                    TrackingSlots.SOURCE_FILE_AND_ROW,
                                    get_extra_slot_for_flag_prefix(GROUP_FLAG_PREFIX),
                                ],
                                "target_slot": [
                                    TrackingSlots.SOURCE_FILE_AND_ROW,
                                    get_extra_slot_for_flag_prefix(GROUP_FLAG_PREFIX),
                                ],
                            }
                        else:
                            class_linkages[class_name][target_class] = {
                                "source_slot": [TrackingSlots.SOURCE_FILE_AND_ROW],
                                "target_slot": [TrackingSlots.SOURCE_FILE_AND_ROW],
                            }
        # If there is custom ID code in the config file then add it
        if custom_id_code := self.config.get(ConfigKeys.CUSTOM_ID_CODE, None):
            custom_id_code_df = pd.DataFrame(custom_id_code)
            if len(custom_id_code_df):
                # Rename all code columns to be in the correct format, and the correct indexing
                columns = []
                code_idx = 0
                for col in custom_id_code_df.columns:
                    if col.startswith(IDCodeColumns.CODE_PREFIX):
                        columns.append(
                            f"{IDCodeColumns.CODE_PREFIX}{IDCodeColumns.CODE_SUFFIX}".format(
                                code_idx
                            )
                        )
                        code_idx += 1
                    else:
                        columns.append(col)
                custom_id_code_df.columns = columns
                # Append the new custom code
                id_code_df = pd.concat(
                    [id_code_df, custom_id_code_df], ignore_index=True
                )
        # Drop duplicate rows
        id_code_df = id_code_df.drop_duplicates(
            subset=[IDCodeColumns.CLASS, IDCodeColumns.SLOT],
            keep="last",
            ignore_index=True,
        )
        id_code_config = {"class_linkages": class_linkages}

        output_id_code_file = None
        output_id_code_config_file = None
        if output_dir:
            # Save id_code_df and id_code_config to disk
            output_id_code_file = os.path.join(output_dir, ID_CODE_FILE)
            output_id_code_config_file = os.path.join(output_dir, ID_CODE_CONFIG_FILE)
            os.makedirs(output_dir, exist_ok=True)
            save_data_frame(id_code_df, output_id_code_file, index=False)
            with open(output_id_code_config_file, "w") as f:
                yaml.safe_dump(id_code_config, f)

        return (
            id_code_df,
            output_id_code_file,
            id_code_config,
            output_id_code_config_file,
        )

    def class_has_explicit_groups(self, class_name: str) -> bool:
        return (
            len(
                self.class_groups.get(class_name, {}).get(
                    MetaConfigKeys.EXPLICIT_GROUPS_KEY, []
                )
            )
            > 0
        )

    def get_table_long_name(self, table_short_name: str) -> Optional[str]:
        """Get the long table name of the specified short table name.

        Args:
            table_short_name (str): The short table name to get the long table name of.

        Returns:
            Optional[str]: The long table name of table_short_name, or None if table_short_name
                is unrecognized.
        """
        tables = self.config.get(ConfigKeys.TABLES_TO_SHORTNAMES, {})
        tables = [k for k, v in tables.items() if v == table_short_name]
        return tables[0] if len(tables) > 0 else None

    def get_table_short_name(self, table_long_name: str) -> Optional[str]:
        """Get the short name of the specified table.

        For example, the short name for the "measures" table might be "mr".

        Args:
            table_long_name (str): The table name to get the short name of.

        Returns:
            Optional[str]: The short name of the table, or None if the table is not recognized.
        """
        return self.config.get(ConfigKeys.TABLES_TO_SHORTNAMES, {}).get(
            table_long_name, None
        )
