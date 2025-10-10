import os
from typing import List, Union, Dict, Optional
from pathlib import Path
import yaml
from enum import Enum
import re
import tempfile
import zipfile

from linkml_runtime import SchemaView

from odm_map.utils.logger import get_logger, make_logger_bullet_list
from odm_map.utils.clean_exit_error import CleanExitError

MODULE_DIR = Path(os.path.dirname(__file__)) / ".." / "data" / "modules"
CONFIG_FILE = "config.yaml"

logger = get_logger(__name__)

# Keys in the config file
MODULE_TITLE_KEY = "title"
MODULE_SOURCE_SCHEMA_KEY = "source_schema"
MODULE_IF_KEY = "if"
MODULE_STEPS_KEY = "steps"
# Keys within a step in the config file
MODULE_ACTION_KEY = "action"
MODULE_PARAMS_KEY = "params"

# Name of the shared module, that has data accesible to any of the other modules
SHARED_MODULE = "_shared"

# Shared tag in all file paths of a module config file.
# eg. "{shared}/ids/general_v2_id_code.xlsx" in config.yaml will point to "ids/general_v2_id_code.xlsx"
# in the shared module.
SHARED_DIR_TAG = "{shared}"
# Temporary directory tag in all file paths of a module config file.
# eg. "{temp}/mappers/schema/schema.yaml" in config.yaml will point to "mappers/schema/schema.yaml"
# in the temporary directory
TEMP_DIR_TAG = "{temp}"

# Also available below: ModulesEnum for all available installed modules (based on get_all_modules(include_titles=False))


def get_all_modules(include_titles: bool = False) -> List[str]:
    """Get a list of builtin all modules available in the modules directory.

    Args:
        include_titles (bool, optional): If True the include the titles (form the config files)
            of all modules in the list of modules.

    Returns:
        List[str]: List of all available modules.
    """
    try:
        modules = [
            d
            for d in os.listdir(MODULE_DIR)
            if (MODULE_DIR / d).is_dir() and d != SHARED_MODULE
        ]
        modules = sorted(modules)

        if include_titles:
            with_titles = []

            def _add_with_title(module_name: str, title: str):
                with_titles.append(f"{module_name} ({title})")

            # Go through all modules and retrieve the MODULE_TITLE_KEY from the config file
            for module_name in modules:
                config_file = MODULE_DIR / module_name / CONFIG_FILE
                if not os.path.isfile(config_file):
                    _add_with_title(module_name, "Missing config file")
                    continue
                with open(config_file, "r") as f:
                    config = yaml.safe_load(f)
                _add_with_title(
                    module_name, config.get(MODULE_TITLE_KEY, "No title available")
                )
            modules = with_titles

        return modules
    except Exception:
        return []


# Enum names: Replace non-alphanumeric with _. Replace leading number (#) with _#
_all_modules = get_all_modules(include_titles=False)
_all_modules = {
    re.sub("^([0-9]){1}", "_\\1", re.sub("[^A-Za-z0-9]", "_", m)): m
    for m in _all_modules
}
# Enumeration for all available modules
ModulesEnum = Enum("ModulesEnum", _all_modules)


class PipelineModule(object):
    def __init__(self, module: Optional[str], module_path: Optional[Union[str, Path]]):
        self._config: Dict = None
        self.source_schema: SchemaView = None
        # A name for the module. For informational purposes
        self.module_name = None
        # If the module is a zip file, then this is the temporary directory object of the
        # extracted zip file. This is a tempfile.TemporaryDirectory object, and cleanup()
        # should be called on the object in the destructor.
        self.module_temp_dir_obj = None
        # self.builtin_module is True if the module is one of the built-in ones (ie. in the
        # MODULE_DIR). If it is False then the module is an external one.
        self.builtin_module = False

        if module:
            # Built-in module has been specified. The module is the name of a directory in
            # MODULE_DIR.
            self.module_name = module
            self.module_dir = MODULE_DIR / module if module else Path(module_path)
            self.module_dir = Path(self.module_dir).resolve()
            self.original_module_path = self.module_dir
            self.builtin_module = True

            if not self.module_dir.is_dir():
                # Named module does not exist, exit with an error telling the user which installed
                # modules are available.
                all_modules = make_logger_bullet_list(
                    get_all_modules(include_titles=True)
                )
                raise CleanExitError(
                    f"Module '{module}' does not exist. Available modules are:\n{all_modules}"
                )
        elif module_path:
            self.original_module_path = module_path
            if os.path.splitext(module_path)[1].lower() == ".zip":
                self.extract_module(module_path)
            elif os.isdir(module_path):
                self.module_dir = Path(module_path).resolve()
                self.module_name = os.path.basename(self.module_dir)
            else:
                raise CleanExitError(
                    f"Module path must be either a zip file or a directory: {module_path}"
                )
        else:
            raise CleanExitError('One of "module" or "module_path" must be specified')

    def __str__(self):
        if self.builtin_module:
            return self.module_name
        return str(self.original_module_path)

    def __del__(self):
        if self.module_temp_dir_obj:
            self.module_temp_dir_obj.cleanup()
            self.module_temp_dir_obj = None

    def extract_module(self, module_path: Union[str, Path]):
        """Extract the zip module at the specified path to a temporary directory.

        Args:
            module_path (Union[str, Path]): The path to the module, which must be a zip file.
                The zip file should contain files and a directory structure like any regular
                directory module.
        """
        temp_dir = tempfile.TemporaryDirectory()
        with zipfile.ZipFile(module_path, "r") as z:
            z.extractall(temp_dir.name)

        self.module_temp_dir_obj = temp_dir
        self.module_dir = None

        # Find the top-level config file
        top_module_dir = Path(self.module_temp_dir_obj.name).resolve()
        for root, _, files in os.walk(top_module_dir):
            if CONFIG_FILE in files:
                self.module_dir = top_module_dir / root
                break

        # Make sure we found the top-level config file
        if self.module_dir is None:
            raise CleanExitError(f"Module config file not found for {self}")

        self.module_name = os.path.basename(module_path)

    def get_source_schema(self) -> Optional[Path]:
        """Get the path of the source schema specified in the configuration file for the module.

        Returns:
            Optional[Path]: The path to the source schema of the module.
        """
        source_schema = self.config.get(MODULE_SOURCE_SCHEMA_KEY)
        return self.get_module_path(source_schema) if source_schema else None

    def get_source_schema_view(self) -> SchemaView:
        """Get the SchemaView of the source schema specified in the configuration file for the module.

        Returns:
            SchemaView: The SchemaView for the source schema.
        """
        if self.source_schema is None:
            self.source_schema = SchemaView(self.get_source_schema())
        return self.source_schema

    @property
    def config(self) -> Dict:
        """Get the main config file for the module.

        Raises:
            CleanExitError: The module config file does not exist.

        Returns:
            Dict: The configuration of the module.
        """
        if self._config is None:
            config_file = self.get_module_config_path()
            if not config_file.is_file():
                raise CleanExitError(f"Module config file not found at {config_file}")
            with open(config_file) as f:
                self._config = yaml.safe_load(f)
        return self._config

    def get_module_config_path(self) -> Path:
        """Get the path for the main module configuration file.

        Returns:
            Path: The path to the module config file.
        """
        return self.get_module_path(CONFIG_FILE)

    def set_temp_dir(self, temp_dir: Union[str, Path]):
        self.temp_dir = Path(temp_dir)

    def get_module_path(self, relative_path: Union[str, List[str]]) -> Optional[Path]:
        """Get the full path of a relative path within a module. This can be used to
        retrieve the path of files within the module.

        Args:
            relative_path (Union[str, List[str]]): The relative path to retrieve within the module,
                such as a path to the config file.

        Returns:
            Optional[Path]: The full path of the specified relative path, within the module. None
                if relative_path is None.
        """
        if not relative_path:
            return None
        if isinstance(relative_path, list):
            return [self.get_module_path(p) for p in relative_path]

        if relative_path.startswith(SHARED_DIR_TAG):
            shared_dir = (MODULE_DIR / SHARED_MODULE).resolve()
            relative_path = relative_path[len(SHARED_DIR_TAG) + 1 :]
            return shared_dir / relative_path

        if relative_path.startswith(TEMP_DIR_TAG):
            relative_path = relative_path[len(TEMP_DIR_TAG) + 1 :]
            return self.temp_dir / relative_path

        return self.module_dir / relative_path
