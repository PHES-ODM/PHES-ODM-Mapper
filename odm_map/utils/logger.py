"""
# Usage:

```python
from utils.logger import get_logger

logger = get_logger(__name__)
logger.info("This is a logging message")
```
"""

from typing import Optional, Dict, List
import sys
import logging

# Set to True for detailed logging output. Typically used for debugging.
DETAILED_LOGGER = False

# Default level for logging
DEFAULT_LEVEL = logging.INFO

if DETAILED_LOGGER:
    # Default logging format
    DEFAULT_LOGGER_FORMAT = (
        "%(levelname)s %(asctime)s %(filename)s:%(lineno)d: %(message)s"
    )
    # Alternate logging formats. See MultiFormatter
    ALTERNATE_LOGGER_FORMATS = None
else:
    # Default logging format
    DEFAULT_LOGGER_FORMAT = "**%(levelname)s** %(message)s"
    # Alternate logging formats. See MultiFormatter
    ALTERNATE_LOGGER_FORMATS = {logging.INFO: "%(message)s"}

LOGGER_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Change the logging level of the LinkML Transformer and others to avoid unwanted logging.
for logger_name in [
    "linkml_map.transformer.object_transformer",
    "linkml_map.transformer.transformer",
    "linkml_runtime.utils.schemaview",
    "pint.util",
]:
    trlogger = logging.getLogger(logger_name)
    trlogger.setLevel("ERROR")


class MultiFormatter(logging.Formatter):
    def __init__(
        self,
        fmt: Optional[str] = None,
        alternate_fmts: Dict[int, str] = None,
        datefmt: Optional[str] = None,
        **kwargs,
    ):
        """Allow different logging formats for different logging levels.

        Args:
            fmt (Optional[str], optional): The default logging format. Defaults to None.
            alternate_fmts (Dict[int, str], optional): Dictionary specifying alternate
                loggin formats to use for different logging levels. The keys are the
                logging levels (eg. logging.INFO, logging.ERROR, ...) and the values
                are the formats used for that logging level. Defaults to None.
            datefmt (Optional[str], optional): Format to use for dates. Defaults to None.
        """
        self.alternate_fmts = alternate_fmts
        super().__init__(fmt=fmt, datefmt=datefmt, **kwargs)

    def format(self, record: logging.LogRecord) -> str:
        fmt = orig_fmt = self._style._fmt
        if self.alternate_fmts is not None:
            fmt = self.alternate_fmts.get(record.levelno, orig_fmt)
        self._style._fmt = fmt
        result = logging.Formatter.format(self, record)
        self._style._fmt = orig_fmt
        return result


def get_logger(name: str, level: Optional[str] = DEFAULT_LEVEL) -> logging.Logger:
    """Get the logger with the specified name, setting is configuration as well as output format.
    The name can be any arbitrary string. For example:

        logger = get_logger(__name__)

    Args:
        name (str): The name to give to the logger. This can be any arbitrary string and is
            typically the name of the caller.
        level (Optional[str], optional): The logging level of the logger. Defaults to DEFAULT_LEVEL.

    Returns:
        logging.Logger: The logging object.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            MultiFormatter(
                fmt=DEFAULT_LOGGER_FORMAT,
                alternate_fmts=ALTERNATE_LOGGER_FORMATS,
                datefmt=LOGGER_DATE_FORMAT,
            )
        )
        logger.addHandler(handler)
    if level:
        logger.setLevel(level)
    return logger


def make_logger_bullet_list(
    items: List,
    bullet: str = "- ",
    end: str = "\n",
    last_end: str = "",
    indent: int = 4,
) -> str:
    """Make a bullet list string consisting of the specified items.

    Args:
        items (List): The items to make a list of. Each item will be indented on a new
            line and have an optional bullet string.
        bullet (str, optional): The string to use as a bullet, which immediately precedes
            each item in the output string. Can be set to "" if no bullet is desired.
            The string interpolation parameter {idx} can be used to specify the 1-based
            index of the item. Defaults to "- ".
        end (str, optional): The string to put at the end of each item. Defaults to "\\n".
        last_end (str, optional): The string to put at the end of the last item (instead of
            end). Defaults to "".
        indent (int, optional): Number of blank characters to indent each item. The indent
            string will appear at the start of a line, immediately before the bullet.
            Can be set to 0 if no indent is desired. Defaults to 4.

    Returns:
        str: A string of the bullet list.
    """
    num_items = len(items)
    items = [
        f"{' ' * indent}{bullet.format(idx=idx + 1)}{item}{end if idx < num_items - 1 else last_end}"
        for idx, item in enumerate(items)
    ]
    return "".join(items)
