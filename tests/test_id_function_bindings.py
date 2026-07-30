"""Tests for odm_map.id_generator.id_function_bindings.FunctionBindings"""

from unittest.mock import MagicMock

import pytest

from odm_map.id_generator.id_function_bindings import FunctionBindings
from odm_map.id_generator.id_value import IDValue


def make_fn(**kwargs):
    gen = MagicMock()
    gen.current_class = kwargs.get("current_class")
    gen.current_row_index = kwargs.get("current_row_index")
    gen.get_class_short_name.return_value = kwargs.get("class_shortname")
    gen.get_current_source_class_and_row.return_value = (
        kwargs.get("source_class"),
        kwargs.get("source_row"),
    )
    gen.get_current_source_file_and_row.return_value = (
        kwargs.get("source_file"),
        kwargs.get("source_row_num", 0),
    )
    return FunctionBindings(gen)


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    def test_rownum(self):
        fn = make_fn(current_row_index=5)
        assert fn.rownum == 5

    def test_class_name(self):
        fn = make_fn(current_class="samples")
        assert fn.class_name == "samples"

    def test_class_shortname(self):
        fn = make_fn(current_class="samples", class_shortname="smp")
        assert fn.class_shortname == "smp"

    def test_sourceclass(self):
        fn = make_fn(source_class="measures")
        assert fn.sourceclass == "measures"

    def test_sourcerow(self):
        fn = make_fn(source_row=7)
        assert fn.sourcerow == 7


# ---------------------------------------------------------------------------
# makeid
# ---------------------------------------------------------------------------


class TestMakeid:
    def test_no_args_returns_none(self):
        fn = make_fn()
        assert fn.makeid() is None

    def test_single_arg(self):
        fn = make_fn()
        assert fn.makeid("hello") == "hello"

    def test_two_args_camelcase(self):
        fn = make_fn()
        assert fn.makeid("hello", "world") == "helloWorld"

    def test_non_alphanumeric_replaced_with_underscore(self):
        fn = make_fn()
        result = fn.makeid("hello world!")
        assert result == "hello_world"

    def test_leading_trailing_underscores_stripped(self):
        fn = make_fn()
        result = fn.makeid("  public health  ")
        assert not result.startswith("_")
        assert not result.endswith("_")

    def test_starts_with_non_alpha_gets_shortname_prefix(self):
        fn = make_fn(current_class="samples", class_shortname="smp")
        result = fn.makeid("123abc")
        assert result.startswith("smp")

    def test_idvalue_arg_uses_unindexed_value(self):
        fn = make_fn()
        v = IDValue("mySample", 3)
        result = fn.makeid(v)
        assert result == "mySample"

    def test_two_args_lowercases_first_char_of_first(self):
        fn = make_fn()
        result = fn.makeid("Hello", "World")
        assert result[0] == "h"

    def test_two_args_uppercases_first_char_of_second(self):
        fn = make_fn()
        result = fn.makeid("hello", "world")
        assert result == "helloWorld"


# ---------------------------------------------------------------------------
# _customtz
# ---------------------------------------------------------------------------


class TestCustomTz:
    def test_utc_plus_5(self):
        fn = make_fn()
        result = fn._customtz("UTC+5")
        assert result.strftime("%z") == "+0500"

    def test_utc_minus_7(self):
        fn = make_fn()
        result = fn._customtz("UTC-7")
        assert result.strftime("%z") == "-0700"

    def test_utc_plus_5_colon_30(self):
        fn = make_fn()
        result = fn._customtz("UTC+5:30")
        assert result.strftime("%z") == "+0530"

    def test_utc_minus_07_colon_30(self):
        fn = make_fn()
        result = fn._customtz("UTC-07:30")
        assert result.strftime("%z") == "-0730"

    def test_utc_plus_hhmm_form(self):
        fn = make_fn()
        result = fn._customtz("UTC+0530")
        assert result.strftime("%z") == "+0530"

    def test_invalid_string_raises_value_error(self):
        fn = make_fn()
        with pytest.raises(ValueError):
            fn._customtz("notazone")

    def test_non_string_raises_value_error(self):
        fn = make_fn()
        with pytest.raises(ValueError):
            fn._customtz(42)


# ---------------------------------------------------------------------------
# datetimetz
# ---------------------------------------------------------------------------


class TestDatetimetz:
    def test_date_only(self):
        fn = make_fn()
        assert fn.datetimetz(["2024-09-16"]) == "2024-09-16"

    def test_date_and_time(self):
        fn = make_fn()
        assert fn.datetimetz(["2024-09-16", "10:10:00"]) == "2024-09-16T10:10:00"

    def test_date_time_and_timezone(self):
        fn = make_fn()
        result = fn.datetimetz(["2024-09-16", "10:10:00", "UTC-5"])
        assert result == "2024-09-16T10:10:00-0500"

    def test_empty_date_only_time(self):
        fn = make_fn()
        result = fn.datetimetz(["", "10:10:00"])
        assert result == "10:10:00"

    def test_empty_time_only_date(self):
        fn = make_fn()
        result = fn.datetimetz(["2024-09-16", ""])
        assert result == "2024-09-16"

    def test_single_string_treated_as_date_time_tz(self):
        fn = make_fn()
        result = fn.datetimetz("2024-09-16")
        assert result.startswith("2024-09-16")

    def test_too_many_items_returns_empty(self):
        fn = make_fn()
        result = fn.datetimetz(["2024-09-16", "10:10:00", "UTC-5", "extra"])
        assert result == ""

    def test_all_empty_inputs_returns_empty(self):
        fn = make_fn()
        result = fn.datetimetz(["", "", ""])
        assert result == ""


# ---------------------------------------------------------------------------
# datetime
# ---------------------------------------------------------------------------


class TestDatetime:
    def test_date_string(self):
        fn = make_fn()
        result = fn.datetime("2024-09-16")
        assert result.startswith("2024-09-16")

    def test_non_string_returned_unchanged(self):
        fn = make_fn()
        assert fn.datetime(42) == 42

    def test_empty_string_returned_unchanged(self):
        fn = make_fn()
        assert fn.datetime("") == ""

    def test_none_returned_unchanged(self):
        fn = make_fn()
        assert fn.datetime(None) is None


# ---------------------------------------------------------------------------
# date
# ---------------------------------------------------------------------------


class TestDate:
    def test_valid_date(self):
        fn = make_fn()
        assert fn.date("2024-09-16") == "2024-09-16"

    def test_non_string_returned_unchanged(self):
        fn = make_fn()
        assert fn.date(42) == 42

    def test_empty_string_returned_unchanged(self):
        fn = make_fn()
        assert fn.date("") == ""

    def test_none_returned_unchanged(self):
        fn = make_fn()
        assert fn.date(None) is None


# ---------------------------------------------------------------------------
# try_float
# ---------------------------------------------------------------------------


class TestTryFloat:
    def test_float_string(self):
        fn = make_fn()
        assert fn.try_float("3.14") == 3.14

    def test_invalid_string_unchanged(self):
        fn = make_fn()
        assert fn.try_float("abc") == "abc"

    def test_underscore_string_unchanged(self):
        fn = make_fn()
        assert fn.try_float("1_000") == "1_000"

    def test_integer_input(self):
        fn = make_fn()
        assert fn.try_float(42) == 42.0

    def test_int_string(self):
        fn = make_fn()
        assert fn.try_float("5") == 5.0


# ---------------------------------------------------------------------------
# try_int
# ---------------------------------------------------------------------------


class TestTryInt:
    def test_int_string(self):
        fn = make_fn()
        assert fn.try_int("5") == 5

    def test_invalid_string_unchanged(self):
        fn = make_fn()
        assert fn.try_int("abc") == "abc"

    def test_underscore_string_unchanged(self):
        fn = make_fn()
        assert fn.try_int("1_000") == "1_000"

    def test_float_truncated(self):
        fn = make_fn()
        assert fn.try_int(3.9) == 3

    def test_float_string_converted(self):
        fn = make_fn()
        assert fn.try_int("7") == 7


# ---------------------------------------------------------------------------
# has_partial_str_value / has_exact_str_value
# ---------------------------------------------------------------------------


class TestHasStrValue:
    def test_exact_match_true(self):
        fn = make_fn()
        assert fn.has_exact_str_value(["hello", "world"], "hello")

    def test_partial_match_true(self):
        fn = make_fn()
        assert fn.has_partial_str_value(["hello world"], "hello")

    def test_exact_fails_for_partial(self):
        fn = make_fn()
        assert not fn.has_exact_str_value(["hello world"], "hello")

    def test_case_insensitive_exact(self):
        fn = make_fn()
        assert fn.has_exact_str_value(["Hello"], "hello", ignore_case=True)

    def test_case_sensitive_exact_no_match(self):
        fn = make_fn()
        assert not fn.has_exact_str_value(["Hello"], "hello")

    def test_non_string_value_returns_false(self):
        fn = make_fn()
        assert not fn.has_exact_str_value(["hello"], 42)

    def test_none_arr_returns_false(self):
        fn = make_fn()
        assert not fn.has_exact_str_value(None, "hello")

    def test_scalar_input_works(self):
        fn = make_fn()
        assert fn.has_exact_str_value("hello", "hello")

    def test_nan_values_in_list_skipped(self):
        import math

        fn = make_fn()
        assert not fn.has_exact_str_value([float("nan"), math.nan], "hello")

    def test_partial_case_insensitive(self):
        fn = make_fn()
        assert fn.has_partial_str_value(["Hello World"], "hello", ignore_case=True)


# ---------------------------------------------------------------------------
# has_nonempty_value
# ---------------------------------------------------------------------------


class TestHasNonemptyValue:
    def test_nonempty_string_true(self):
        fn = make_fn()
        assert fn.has_nonempty_value("hello")

    def test_empty_string_false(self):
        fn = make_fn()
        assert not fn.has_nonempty_value("")

    def test_none_false(self):
        fn = make_fn()
        assert not fn.has_nonempty_value(None)

    def test_nan_false(self):
        fn = make_fn()
        assert not fn.has_nonempty_value(float("nan"))

    def test_list_with_one_nonempty_true(self):
        fn = make_fn()
        assert fn.has_nonempty_value([None, "value"])

    def test_list_all_empty_false(self):
        fn = make_fn()
        assert not fn.has_nonempty_value([None, ""])

    def test_zero_is_nonempty(self):
        fn = make_fn()
        assert fn.has_nonempty_value(0)

    def test_false_is_nonempty(self):
        fn = make_fn()
        assert fn.has_nonempty_value(False)
