"""
All members of class DataBindings are accessible from ID code files (in Python code) via various namespaces, including dat and datEmpty.
They provide access to linked values within all the known target tables. Follow dat or datEmpty with the target table name. For example:

    dat.samples.sampleID
    dat.addresses.get_first_linked_value("addressID")
"""

from typing import Optional, List, Union, Dict, Any
import traceback

from odm_map.utils.logger import get_logger
from odm_map.id_generator.id_na import isna
from odm_map.id_generator.generator_config_keys import ConfigKeys
from odm_map.id_generator.id_value import IDValue

# Value to use if a value from one of the classes/tables is empty.
EMPTY_VALUE = "empty"

logger = get_logger(__name__)


class DataBindings:
    """All data bindings accessible from ID generation code through the dat object (eg. dat.samples.sampleID)."""

    def __init__(
        self,
        generator,
        root_class: Optional[str],
        sub_class_names: Optional[List[str]],
        prefix: Optional[str] = None,
        replace_empty_values: bool = True,
    ):
        """Constructor for DataBindings.

        Args:
            generator (IDGenerator): The ID Generator that the bindings are for.
            root_class (Optional[str]): The name of the class that this binding is for. A class name is a table name.
                If this is set then this binding represents a single table, and we retrieve an attribute on the
                binding to get values within a column of the table. If root_class is None then it is the top-level
                binding that contains all the classes (ie. tables). In this case, sub_class_names must be set to
                a list of all the recognized tables, and to retrieve any of these tables we retrieve an attribute
                on the binding to get the binding for the table (which we can in turn retrieve columns from). For
                example, bindingsObj.table. Since a new binding is returned when accessing this attribute, we can
                use the returned binding to then retrieve columns of the class, eg. bindingsObj.table.column. The
                actual row that is retrieved depends on the current_row_index of the generator.
            sub_class_names (Optional[List[str]]): If root_class is None, then sub_class_names must be set to a list
                of all the recognized classes (ie. tables). To retrieve the bindings for one of these classes, we
                would retrieve the attribute (using the name of the class) on this binding. For example,
                bindingsObj.column. The actual row that is retrieved depends on the current_row_index of the generator.
            prefix (Optional[str], Optional): The prefix used to access this data binding. This is for informational
                and debugging purposes, and represents how the data binding is accessed from custom ID code. eg. "dat",
                "datEmpty".
            replace_empty_values (bool, Optional): If True, then replace any empty values returned by this binding
                with the value EMPTY_VALUE.
        """
        self.generator = generator
        self.root_class = root_class
        self.prefix = prefix
        self.replace_empty_values = replace_empty_values
        if sub_class_names:
            self.sub_classes = {
                class_name: DataBindings(
                    generator,
                    root_class=class_name,
                    sub_class_names=[],
                    replace_empty_values=self.replace_empty_values,
                )
                for class_name in sub_class_names
            }
        else:
            self.sub_classes = None

    def __str__(self) -> str:
        if self.sub_classes is None:
            sub_classes = None
        else:
            sub_classes = list(self.sub_classes.keys())
        return f"DataBindings(root_class={self.root_class}, sub_classes={sub_classes})"

    def __getattr__(self, name) -> Any:
        if self.sub_classes:
            return self.sub_classes[name]

        try:
            v = self.get_first_linked_value(name)
        except Exception as e:
            print(traceback.format_exc())
            raise e

        return v

    def get(self, name) -> Any:
        return self.__getattr__(name)

    def get_named_linkage_path(self, source_class: str, linkage_path_name: str):
        named_class_linkages = self.generator.config.get(
            ConfigKeys.NAMED_CLASS_LINKAGES
        )
        if named_class_linkages is None:
            raise ValueError(
                f"Named linkage path '{linkage_path_name}' specified for get_first_linked_value, but no named linkage paths specified in config file"
            )
        named_class_linkage = named_class_linkages.get(linkage_path_name)
        if named_class_linkage is None:
            raise ValueError(
                f"Named linkage path '{linkage_path_name}' does not exist in config file"
            )
        linkage_path = named_class_linkage.get(source_class, {}).get(
            self.root_class, {}
        )
        if not linkage_path:
            raise ValueError(
                f"Named linkage path '{linkage_path}' exists but no path from soure class '{source_class}' to target class '{self.root_class}' in config file"
            )
        return linkage_path

    def has_column(self, name: str) -> bool:
        """Check if we have the specified column.

        Args:
            name (str): The column to check if it exists.

        Returns:
            bool: True if the column exists, False otherwise.
        """
        if self.root_class is None:
            return False
        return self.generator.data[self.root_class].has_column(name)

    def get_first_linked_value(
        self,
        target_slot: str,
        linkage_path: Union[str, Dict, List[Dict]] = None,
        ignore_current_row: bool = False,
    ) -> Any:
        # source_class and source_index are the current class and row being generated by the generator.
        # self.root_class and target_slot are the class and slot that we want to get the value of. The row
        # we retrieve the value from depends on which rows in self.root_class are linked to the row
        # in source_class at index source_index.
        source_class = self.generator.current_class
        source_index = self.generator.current_row_index

        if isinstance(linkage_path, str):
            linkage_path = self.get_named_linkage_path(source_class, linkage_path)

        v = self.generator.get_first_linked_value(
            source_class,
            source_index,
            self.root_class,
            target_slot,
            linkage_path=linkage_path,
            generate_index_if_primary_key=not self.replace_empty_values,
            ignore_current_row=ignore_current_row,
        )
        if (
            not self.replace_empty_values
            and isinstance(v, IDValue)
            and self.generator.data[self.root_class].primary_key == target_slot
            and not v.is_index_generated()
        ):
            logger.error(
                f"Retrieved IDValue from primary key {self.prefix}.{self.root_class}.{target_slot} (source row: {source_class}:{source_index}) that has not yet had its index generated"
            )

        # Convert float to integer if it has no decimals
        if isinstance(v, float) and not isna(v):
            if int(v) == v:
                v = int(v)

        def _is_empty(v: Any) -> bool:
            if isna(v) or v == "":
                return True
            if isinstance(v, list):
                v = [s for s in v if not _is_empty(s)]
                return len(v) == 0
            return False

        # Replace empty values
        if self.replace_empty_values:
            if _is_empty(v):
                v = EMPTY_VALUE
        else:
            if isna(v):
                v = ""

        return v
