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

# Default logging format
# DEFAULT_LOGGER_FORMAT = "%(levelname)s %(asctime)s %(filename)s:%(lineno)d: %(message)s"
DEFAULT_LOGGER_FORMAT = "**%(levelname)s** %(message)s"
# Alternate logging formats to use for specific logging levels. See MultiFormatter
ALTERNATE_LOGGER_FORMATS = {logging.INFO: "%(message)s"}

LOGGER_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


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


def get_logger(name: str, level: Optional[str] = logging.INFO) -> logging.Logger:
    """Get the logger with the specified name, setting is configuration as well as output format.
    The name can be any arbitrary string. For example:

        logger = get_logger(__name__)

    Args:
        name (str): The name to give to the logger. This can be any arbitrary string and is
            typically the name of the caller.
        level (Optional[str], optional): The logging level of the logger. Defaults to logging.INFO.

    Returns:
        logging.Logger: The logging object.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        MultiFormatter(
            fmt=DEFAULT_LOGGER_FORMAT,
            alternate_fmts=ALTERNATE_LOGGER_FORMATS,
            datefmt=LOGGER_DATE_FORMAT,
        )
    )
    logging.basicConfig(
        handlers=[handler],
        level=level,
    )

    logger = logging.getLogger(name)
    if level:
        logger.setLevel(level)
    return logger


def make_logger_bullet_list(items: List, bullet: str = "- ", indent: int = 4) -> str:
    """Make a bullet list string consisting of the specified items.

    Args:
        items (List): The items to make a list of. Each item will be indented on a new
            line and have an optional bullet string.
        bullet (str, optional): The string to use as a bullet, which immediately precedes
            each item in the output string. Can be set to "" if no bullet is desired.
            Defaults to "- ".
        indent (int, optional): Number of blank characters to indent each item. The indent
            string will appear at the start of a line, immediately before the bullet.
            Can be set to 0 if no indent is desired. Defaults to 4.

    Returns:
        str: _description_
    """
    items = [
        f"{' '*indent}{bullet.format(idx=idx+1)}{item}"
        for idx, item in enumerate(items)
    ]
    return "\n".join(items)
