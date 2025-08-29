# %%
"""
All members of class FunctionBindings are accessible from ID code files (in Python code) via the namespace "fn".

For example:
    fn.makeid("a", "b", ...)
    fn.datetimetz(["2024-09-13", "12:15:15 pm", "UTC-04:00"])
"""

from typing import Any, List, Union, Dict
import datetime
import dateutil.parser
import pytz
import re

from odm_map.utils.logger import get_logger
from odm_map.id_generator.id_value import IDValue

logger = get_logger(__name__)

# Formats of date, time, and timezone strings used for inputs to fn.datetimetz.
# We attempt parsing the input string with each format in order until parsing is successful.
# A value of "pytz" will pass the input string to pytz.timezone
# A value of "dateutil" will pass the input string to dateutil.parser.parse
# All other values are used as the format parameter for datetime.strptime
DATE_TIME_TIMEZONE_FORMATS = [
    # Date formats
    [
        "dateutil_date",
        # "%Y-%m-%d"
    ],
    # Time formats
    [
        "dateutil_time",
        # "%H:%M:%S.%f",
        # "%H:%M:%S",
        # "%H:%M",
        # "%I:%M:%S.%f %p",
        # "%I:%M:%S %p",
        # "%I:%M %p",
    ],
    # Timezone formats
    ["UTC%z", "%z", "pytz", "customtz"],
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
                becomes uppercase. If any of the arguments refer to an IDValue, then the unindexed value is
                used (eg. instead of "mySample001", we use "mySample").

        Returns:
            str: The ID generated from the list of values.
        """
        firstcap = False
        if not args:
            return None

        # We only use the unindexed_value of IDValues. This is because it's possible that
        # the index has not been calculated yet (it gets calculated in the generator when
        # group_primary_key is called to ensure that the primary keys are unique when
        # required)
        args = [v.unindexed_value if isinstance(v, IDValue) else v for v in args]
        # args = [str(v).replace(" ", "") for v in args]
        # Implode arrays to strings
        args = [
            "".join([str(s) for s in v]) if isinstance(v, list) else str(v)
            for v in args
        ]
        args = [re.sub("[^A-Za-z0-9]+", "_", str(v)) for v in args]
        args = [v for v in args if len(v)]
        # Make first character of each element uppercase. The first element has a first character that is
        # lowercase unless firstcap is True (in which case we uppercase it)
        args = [
            "%s%s" % (v[0].upper() if (idx or firstcap) else v[0].lower(), v[1:])
            for idx, v in enumerate(args)
        ]
        v = "".join(args)
        # Remove leading and trailing underscores
        v = re.sub("^_+|_+$", "", v)
        return v

    def _customtz(self, val: str) -> datetime.datetime:
        """Customized parsing of a timezone that isn't handled by other parsing methods.

        This function handles cases such as UTC+4, which we convert to +0400 and pass
        to datetime.strptime(tz, "%z")

        Args:
            val (str): The value to try to parse as a timezone.

        Raises:
            ValueError: val could not be parsed as a timezone.

        Returns:
            datetime: A datetime object that has the timezone set. The date and
                time components of the object should be ignored and the timezone used.
                It can be converted to a string by using %z in datetime.strftime.
        """
        if isinstance(val, str):
            orig_val = val
            val = val.upper()
            if val.startswith("UTC-") or val.startswith("UTC+"):
                delta = val.split("UTC")[1]
            else:
                delta = None
            # delta is the value after the UTC part (eg. 4 for "UTC+4")
            if delta and "_" not in delta:
                # Convert to integer, retrieve the sign and make delta positive
                delta = int(delta)
                if delta < 0:
                    delta = -delta
                    sign = "-"
                else:
                    sign = "+"
                # Add "00" to the end of delta (eg. 4 becomes "400", ie 4 hours)
                if delta >= 0 and delta <= 99:
                    delta *= 100
                # Create the new timezone string and parse it
                val = f"{sign}{delta:04d}"
                tz_obj = datetime.datetime.strptime(val, "%z")
                return tz_obj

        raise ValueError(f"Cannot parse value as timezone: {orig_val}")

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
                    elif fmt == "customtz":
                        date_obj = self._customtz(val)
                    elif fmt == "dateutil":
                        date_obj = dateutil.parser.parse(val)
                    elif fmt == "dateutil_date":
                        # dateutil.parser.parse defaults to today's month, day, or year if there is no
                        # month, day, or year in the string val. We want an error if no date is in val, so
                        # we create two date_objs: If no date is specified for val, then date_obj gets the
                        # date 2000-1-1 and other_date_obj gets the date 2001-2-2. Therefore if the day, month,
                        # or year is missing then date_obj != other_date_obj, but if they are not missing
                        # then date_obj == other_date_obj
                        date_obj = dateutil.parser.parse(
                            val, default=datetime.datetime(2000, 1, 1)
                        )
                        other_date_obj = dateutil.parser.parse(
                            val, default=datetime.datetime(2001, 2, 2)
                        )
                        if date_obj != other_date_obj:
                            # This occurs when no month, day, or year is specified in val
                            date_obj = None
                            raise Exception(f"Not a date: {val}")
                        date_obj = date_obj.date()
                    elif fmt == "dateutil_time":
                        date_obj = dateutil.parser.parse(val)
                        date_obj = date_obj.time()
                    else:
                        date_obj = datetime.datetime.strptime(val, fmt)
                    objects[idx] = date_obj
                    break
                except Exception:
                    pass
            if objects[idx] is None:
                source_file, source_row = (
                    self.generator.get_current_source_file_and_row()
                )
                logger.warning(
                    f"Could not parse {cur_format_name}: {val} (from row {source_row + 1} of file {source_file})"
                )

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
            # logger.warning(
            #     f"No output format available for date/time/timezone for input (class={self.generator.current_class}, row={self.generator.current_row_index}): {d}"
            # )
            return ""

        # Create the single datetime object that contains all of the date, time, and timezone
        dt = None
        if date_obj is not None and time_obj is not None:
            # Both date and time available
            dt = datetime.datetime.combine(
                date_obj if isinstance(date_obj, datetime.date) else date_obj.date(),
                time_obj if isinstance(time_obj, datetime.time) else time_obj.time(),
            )
        elif date_obj is not None:
            # Only date available
            dt = date_obj
        elif time_obj is not None:
            # Only time available
            dt = time_obj
        if dt is not None and time_obj is not None and time_zone_obj is not None:
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

    def countrows(
        self, class_name: str, linkage_path: Union[str, Dict, List[Dict]] = None
    ) -> int:
        """Count number of linked rows (relative to the current class and row) in class class_name. We follow the
        specified linkage path, or the default linkage path if none is specified.

        Args:
            class_name (str): The class to count the rows in.
            linkage_path (Union[str, Dict, List[Dict]]): The linkage path to follow, which can either be
                the dictionary or list of linkage paths, or a named linkage path. Named linkage paths are found
                in the ID generation config file. If None then the default linkage path from the current class
                to class_name is used, as specified in the config file.

        Returns:
            int: The number of rows in the class that are linked to the current class and row index.
        """
        source_class = self.generator.current_class
        source_index = self.generator.current_row_index

        rows = self.generator.get_linked_rows(
            source_class,
            source_index,
            class_name,
            max_rows=None,
            linkage_path=linkage_path,
            return_indices=False,
        )

        return len(rows) if rows is not None else 0

    def datetimeparse(self, d, ignoretz=True) -> Any:
        if not d or not isinstance(d, str):
            return d

        return self.datetimetz([d, d])

    def dateparse(self, d) -> Any:
        if not d or not isinstance(d, str):
            return d
        return self.datetimetz([d])
