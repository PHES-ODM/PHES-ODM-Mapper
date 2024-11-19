"""
Load the configuration file for a mapping module.

Usage:

```python
module = ModuleConfig("path/to/config.yaml")

# Can now access any of the following:
module.title            # Title of the module
module.source_schema    # Path to the source schema
module.target_schema    # Path to the target schema
module.mapper_dir       # Directory containing the LinkML-Map schema files
module.pre_id_filters   # CSV or TSV file with the filtering rules that are applied before ID generation
module.id_code          # File containing the ID generation code
module.id_code_sheet    # If id_code is an Excel file, then the name of the sheet to use, or None for the first sheet.
module.id_config        # Configuration for ID generation
```
"""

from typing import Union, List
from pathlib import Path
import yaml
import os

from utils.logger import get_logger, make_logger_bullet_list
from utils.clean_exit_error import CleanExitError

MODULE_DIR = Path(os.path.dirname(__file__)) / ".." / ".." / "data" / "modules"

logger = get_logger(__name__)

CONFIG_FILE = "config.yaml"

# All keys in the config file
TITLE_KEY = "title"
SOURCE_SCHEMA_KEY = "source_schema"
TARGET_SCHEMA_KEY = "target_schema"
MAPPERS_KEY = "mappers"
PRE_ID_FILTERS_KEY = "pre_id_filters"
ID_CODE_KEY = "id_code"
ID_CODE_SHEET_KEY = "id_code_sheet"
ID_CONFIG_KEY = "id_config"


class ModuleConfig(object):
    def __init__(self, module: str, module_dir: Union[str, Path]):
        module_dir = MODULE_DIR / module if module else Path(module_dir)

        self.module_dir = Path(module_dir).resolve()

        if not self.module_dir.is_dir():
            if module:
                all_modules = make_logger_bullet_list(
                    self.get_all_modules(include_titles=True)
                )
                raise CleanExitError(
                    f"Module '{module}' does not exist. Available modules are:\n{all_modules}"
                )
            else:
                raise CleanExitError(
                    f"Module directory does not exist: {str(module_dir.resolve())}"
                )

        config_file = module_dir / CONFIG_FILE
        if not config_file.is_file():
            raise CleanExitError(f"Module config file not found at {config_file}")
        with open(config_file) as f:
            self.config = yaml.safe_load(f)

        if TITLE_KEY not in self.config:
            raise CleanExitError(
                f"No title in the module configuration file was specified. Please ensure the `{TITLE_KEY}` key is set."
            )
        self.title = self.config[TITLE_KEY]

        # Schemas (both required)
        self.source_schema = self._get_config_file(SOURCE_SCHEMA_KEY, required=True)
        self.target_schema = self._get_config_file(TARGET_SCHEMA_KEY, required=True)

        # Mappers (required)
        self.mapper_dir = self._get_config_file(MAPPERS_KEY, required=True)

        # Filters (to apply after mapping)
        self.pre_id_filters = self._get_config_file(PRE_ID_FILTERS_KEY)

        # IDs
        self.id_code = self._get_config_file(ID_CODE_KEY)
        self.id_code_sheet = self.config.get(ID_CODE_SHEET_KEY, None)
        self.id_config = self._get_config_file(ID_CONFIG_KEY)

        logger.debug(f"Module source schema: {self.source_schema}")
        logger.debug(f"Module target schema: {self.target_schema}")
        logger.debug(f"Module mapper directory: {self.mapper_dir}")
        logger.debug(f"Module pre-id filters file: {self.pre_id_filters}")
        logger.debug(f"Module ID code file: {self.id_code}")
        logger.debug(f"Module ID code sheet: {self.id_code_sheet}")
        logger.debug(f"Module ID config file: {self.id_config}")

    def _get_config_file(
        self, config_key: str, required: bool = False
    ) -> Union[Path, None]:
        """Get the specified config value from the module configuration file. The config value is
        for file paths. If the file does not exist in the module directory, then either an Exception
        is raised or None is returned (depending on the required parameter).

        Args:
            config_key (str): The top-level key to get the config value for.
            required (bool, optional): If True and the config key is . Defaults to False.

        Raises:
            RuntimeError: Raised only if required is True. If the config_key does not exist in the
                config file and required is True the an exception is raised. If the config_key exists,
                but the file does not exist in the module and required is True then an exception is raised.

        Returns:
            Union[Path, None]: If the config_key exists and the file specified at the config_key exists
                in the module directory, then the file path (including the module directory) is returned.
                If either the config_key does not exist in the configuration, or the file specified at
                the config_key does not exist in the module directory, then the return value depends
                on the required parameter:
                    1) If required is True, then an exception is raised.
                    2) If required is False, then None is returned.
        """
        val = self.config.get(config_key)
        if not val:
            if required:
                raise CleanExitError(
                    f"Required module configuration key '{config_key}' is required but does not exist in the module configuration file"
                )
            return None

        path = self.module_dir / val
        if not path.exists():
            path_type = "file" if path.suffix else "directory"
            raise CleanExitError(
                f"The specified {path_type} in the module configuration key '{config_key}' does not exist: {path}"
            )
        return path

    @classmethod
    def get_all_modules(cls, include_titles: bool = False) -> List[str]:
        """Get a list of all modules available in the modules directory.

        Args:
            include_titles (bool, optional): If True the include the titles (form the config files)
                of all modules in the list of modules.

        Returns:
            List[str]: List of all available modules.
        """
        modules = [d for d in os.listdir(MODULE_DIR) if (MODULE_DIR / d).is_dir()]
        modules = sorted(modules)

        if include_titles:
            with_titles = []

            def _add_with_title(module_name: str, title: str):
                with_titles.append(f"{module_name} ({title})")

            # Go through all modules and retrieve the TITLE_KEY from the config file
            for module_name in modules:
                config_file = MODULE_DIR / module_name / CONFIG_FILE
                if not os.path.isfile(config_file):
                    _add_with_title(module_name, "Missing config file")
                    continue
                with open(config_file, "r") as f:
                    config = yaml.safe_load(f)
                _add_with_title(
                    module_name, config.get(TITLE_KEY, "No title available")
                )
            modules = with_titles

        return modules
