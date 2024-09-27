"""
All members of class FunctionBindings are accessible from ID code files (in Python code) via the namespace "fn".

For example:
    fn.makeid("a", "b", ...)
    fn.datetimetz(["2024-09-13", "12:15:15 pm", "UTC-04:00"])
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from typing import Any, List
from datetime import datetime
from dateutil.parser import parse
import pytz

from utils.general_utils import get_logger

logger = get_logger(__name__)

# Formats of date, time, and timezone strings used for inputs to fn.datetimetz.
# We attempt parsing the input string with each format in order until parsing is successful.
# A value of "pytz" will pass the input string to pytz.timezone
# A value of "dateutil" will pass the input string to dateutil.parser.parse
# All other values are used as the format parameter for datetime.strptime
DATE_TIME_TIMEZONE_FORMATS = [
    # Date formats
    [
        "dateutil",
        # "%Y-%m-%d"
    ],
    # Time formats
    [
        "dateutil",
        # "%H:%M:%S.%f",
        # "%H:%M:%S",
        # "%H:%M",
        # "%I:%M:%S.%f %p",
        # "%I:%M:%S %p",
        # "%I:%M %p",
    ],
    # Timezone formats
    ["UTC%z", "%z", "pytz"],
]

# Output format for date, time, and time-zone for fn.datetimetz (as passed to datetime.strftime)
# Full format will be "{OUTPUT_DATE_FORMAT}{OUTPUT_DATE_TIME_SEPARATOR}{OUTPUT_TIME_FORMAT}{OUTPUT_TZ_FORMAT}"
# OUTPUT_DATE_TIME_SEPARATOR is included only if both date and time are available
# eg: "%Y-%m-%dT%H:%M:%S%z"
OUTPUT_DATE_FORMAT = "%Y-%m-%d"
OUTPUT_TIME_FORMAT = "%H:%M:%S"
OUTPUT_TZ_FORMAT = "%z"
OUTPUT_DATE_TIME_SEPARATOR = "T"


class FunctionBindings:
    """All functions/properties accessible from ID code using the global fn object (eg. fn.makeid("a", "b", "c"))."""

    def __init__(self, generator):
        self.generator = generator

    @property
    def rownum(self) -> int:
        return self.generator.current_row_index

    @property
    def sourceclass(self) -> str:
        return self.generator.get_current_source_class_and_row()[0]

    @property
    def sourcerow(self) -> int:
        return self.generator.get_current_source_class_and_row()[1]

    def makeid(self, *args) -> str:
        """Create an ID out of the list of values.

        Args:
            *args: The list of values to convert to an ID. We will convert them to strings and concatenate
                them. The leading character is lower case, and the first character of each item in the list
                becomes uppercase.

        Returns:
            str: The ID generated from the list of values.
        """
        firstcap = False
        if not args:
            return None
        args = [str(v).replace(" ", "") for v in args]
        args = [v for v in args if len(v)]
        # Make first character of each element uppercase. The first element has a first character that is
        # lowercase unless firstcap is True (in which case we uppercase it)
        args = [
            "%s%s" % (v[0].upper() if (idx or firstcap) else v[0].lower(), v[1:])
            for idx, v in enumerate(args)
        ]
        v = "".join(args)
        return v

    def datetimetz(self, d: List[str]) -> str:
        """Convert the input date, time, and timezone strings into a single string in the format
        YYYY-mm-ddTHH:MM:SS+/-hhmm (eg. 2024-09-16T10:10:00-0700)

        Args:
            d (List[str]): List of strings, consisting of the date, time, and timezone. Multiple
                formats are supported for each component. See DATE_TIME_TIMEZONE_FORMATS.

        Returns:
            str: The date, time, and timezone combined into a single string. If the timezone
                input is empty, then the timezone part of the output string is ommitted (eg.
                2024-09-16T10:10:00). If the time input is empty, then both the time and timezone
                part of the output string is ommitted (eg. 2024-09-16). If the date part is
                empty, then the date is ommitted in the output string (eg. 10:10:00-0700 or 10:10:00).
                Any input date component that cannot be parsed will be treated as empty.
        """
        if len(d) > 3:
            logger.warning(
                f"datetimetz expects at most 3 items as input, {len(d)} were found: {d}"
            )
            return ""

        # We will convert each element in d to an element in objects. d[0] is the date, d[1] the time,
        # and d[2] the timezone.
        objects = [None, None, None]
        # Make sure the length of d is the same as the length of objects
        d = d.copy()[: len(objects)]
        while len(d) < len(objects):
            d.append(None)

        # Convert each item in d to a datetime or timezone object
        for idx, (val, cur_formats, cur_format_name) in enumerate(
            zip(d, DATE_TIME_TIMEZONE_FORMATS, ["date", "time", "time zone"])
        ):
            if val == "" or val is None:
                continue
            for fmt in cur_formats:
                try:
                    if fmt == "pytz":
                        date_obj = pytz.timezone(val)
                    elif fmt == "dateutil":
                        date_obj = parse(val)
                    else:
                        date_obj = datetime.strptime(val, fmt)
                    objects[idx] = date_obj
                    break
                except Exception:
                    pass
            if objects[idx] is None:
                logger.warning(f"Could not parse {cur_format_name}: {val}")

        date_obj, time_obj, time_zone_obj = objects

        # Calculate output format, based on which available input objects we have.
        # eg. If only the date is available: 2024-09-16
        #     If date and time both available: 2024-09-16T07:14:00
        #     If date, time, and timezone available: 2024-09-16T07:00:00-0500
        output_format = ""
        if date_obj is not None:
            output_format = OUTPUT_DATE_FORMAT
        if time_obj is not None:
            time_format = OUTPUT_TIME_FORMAT
            if output_format:
                output_format = (
                    f"{output_format}{OUTPUT_DATE_TIME_SEPARATOR}{time_format}"
                )
            else:
                output_format = time_format
            if time_zone_obj is not None:
                output_format = f"{output_format}{OUTPUT_TZ_FORMAT}"
        if not output_format:
            logger.warning(
                f"No output format available for date/time/timezone for input: {d}"
            )
            return ""

        # Create the single datetime object that contains all of the date, time, and timezone
        dt = None
        if date_obj is not None and time_obj is not None:
            # Both date and time available
            dt = datetime.combine(date_obj.date(), time_obj.time())
        elif date_obj is not None:
            # Only date available
            dt = date_obj
        elif time_obj is not None:
            # Only time available
            dt = time_obj
        if dt is not None and time_zone_obj is not None:
            # Timezone is available, so add it to the dt object. time_zone_obj is either a datetime object
            # (created from datetime.strptime) or a BaseTzInfo object (created by pytz.timezone)
            dt = dt.replace(
                tzinfo=time_zone_obj
                if isinstance(time_zone_obj, pytz.tzinfo.BaseTzInfo)
                else time_zone_obj.tzinfo
            )
        if dt is None:
            logger.warning(f"No datetime object created from input: {d}")
            return ""

        # v = dt.isoformat()
        v = dt.strftime(output_format)
        return v

    def countrows(self, class_name: str, slot: str, equals: Any) -> int:
        """Count number of rows in class class_name where the value in the slot is equal to any value in equals.

        Args:
            class_name (str): The class to count the rows in.
            slot (str): The slot in the class where we match to the equals parameter.
            equals (Any): The value(s) to match. If a list or tuple then we match any of the values in the list. If not a list
                then we only match the single value.

        Returns:
            int: The number of rows in the class where the value in the slot matches equals.
        """
        rows = self.generator.get_rows_equal(class_name, slot, equals)
        return len(rows) if rows is not None else 0
