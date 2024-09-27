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
module.id_config        # Configuration for ID generation
```
"""

from typing import Union
from pathlib import Path
import yaml

from utils.general_utils import get_logger

logger = get_logger(__name__)


class ModuleConfig(object):
    def __init__(self, module_dir: Union[str, Path]):
        self.module_dir = Path(module_dir).resolve()

        with open(module_dir / "config.yaml") as f:
            self.config = yaml.safe_load(f)

        if not module_dir.exists():
            raise RuntimeError(
                f"Module directory does not exist: {str(module_dir.resolve())}"
            )

        if "title" not in self.config:
            raise RuntimeError(
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
        self.id_config = self._get_config_file("id_config")

        logger.info(f"Module source schema: {self.source_schema}")
        logger.info(f"Module target schema: {self.target_schema}")
        logger.info(f"Module mapper directory: {self.mapper_dir}")
        logger.info(f"Module filters file: {self.filters}")
        logger.info(f"Module ID code file: {self.id_code}")
        logger.info(f"Module ID config file: {self.id_config}")

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
        path = self.module_dir / val if val else None
        if not path:
            if required:
                raise RuntimeError(
                    f"Required module configuration key '{config_key}' is required but does not exist in the module configuration file"
                )
            return None

        path = Path(path)
        if not path.exists():
            if required:
                path_type = "file" if path.suffix else "directory"
                raise RuntimeError(
                    f"Required module {path_type} '{path.name}' does not exist at {str(path.resolve())}"
                )
            return None
        return path
