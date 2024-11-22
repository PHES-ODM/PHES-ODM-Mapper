import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from typing import List, Union, Dict, Tuple
from pathlib import Path
import yaml

from utils.logger import get_logger, make_logger_bullet_list
from utils.clean_exit_error import CleanExitError

MODULE_DIR = Path(os.path.dirname(__file__)) / ".." / ".." / "data" / "modules"
CONFIG_FILE = "config.yaml"

logger = get_logger(__name__)

MODULE_TITLE_KEY = "title"
MODULE_SOURCE_SCHEMA_KEY = "source_schema"


def get_all_modules(include_titles: bool = False) -> List[str]:
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


def get_module_dir(module: str, module_dir: Union[str, Path]) -> Path:
    module_dir = MODULE_DIR / module if module else Path(module_dir)
    module_dir = Path(module_dir).resolve()
    return module_dir


def get_module_config(module: str, module_dir: Union[str, Path]) -> Tuple[Path, Dict]:
    module_dir = get_module_dir(module, module_dir)

    if not module_dir.is_dir():
        if module:
            all_modules = make_logger_bullet_list(get_all_modules(include_titles=True))
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
        config = yaml.safe_load(f)
    return config_file, config


def get_source_schema(module: str, module_dir: Union[str, Path]) -> Path:
    module_dir = get_module_dir(module=module, module_dir=module_dir)
    _, config = get_module_config(module=module, module_dir=module_dir)
    source_schema = config.get(MODULE_SOURCE_SCHEMA_KEY)
    return module_dir / source_schema if source_schema else None
