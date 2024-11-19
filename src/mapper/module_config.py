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
module.filters          # CSV or TSV file with the filtering rules
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


class ModuleConfig(object):
    def __init__(self, module: str, module_dir: Union[str, Path]):
        module_dir = MODULE_DIR / module if module else Path(module_dir)

        self.module_dir = Path(module_dir).resolve()

        if not self.module_dir.is_dir():
            if module:
                all_modules = make_logger_bullet_list(self.get_all_modules())
                raise CleanExitError(
                    f"Module '{module}' does not exist. Available modules are:\n{all_modules}"
                )
            else:
                raise CleanExitError(
                    f"Module directory does not exist: {str(module_dir.resolve())}"
                )

        config_file = module_dir / "config.yaml"
        if not config_file.is_file():
            raise CleanExitError(f"Module config file not found at {config_file}")
        with open(config_file) as f:
            self.config = yaml.safe_load(f)

        if "title" not in self.config:
            raise CleanExitError(
                "No title in the module configuration file was specified. Please ensure the `title` key is set."
            )
        self.title = self.config["title"]

        # Schemas (both required)
        self.source_schema = self._get_config_file("source_schema", required=True)
        self.target_schema = self._get_config_file("target_schema", required=True)

        # Mappers (required)
        self.mapper_dir = self._get_config_file("mappers", required=True)

        # Filters (to apply after mapping)
        self.filters = self._get_config_file("filters")

        # IDs
        self.id_code = self._get_config_file("id_code")
        self.id_code_sheet = self.config.get("id_code_sheet", None)
        self.id_config = self._get_config_file("id_config")

        logger.debug(f"Module source schema: {self.source_schema}")
        logger.debug(f"Module target schema: {self.target_schema}")
        logger.debug(f"Module mapper directory: {self.mapper_dir}")
        logger.debug(f"Module filters file: {self.filters}")
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
    def get_all_modules(cls) -> List[str]:
        """Get a list of all modules available in the modules directory.

        Returns:
            List[str]: List of all available modules.
        """
        dirs = [d for d in os.listdir(MODULE_DIR) if (MODULE_DIR / d).is_dir()]
        return sorted(dirs)
