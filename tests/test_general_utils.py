"""Tests for odm_map.utils.general_utils"""

import os
import pytest
import pandas as pd

from odm_map.utils.general_utils import (
    choose_ignore_case_value,
    get_unique_output_file,
    make_multivalued,
    merge_dicts_of_lists,
    order_columns,
    parse_df_values,
    parse_numeric,
    read_data_frame,
    save_data_frame,
    select_func_kwargs,
    strip_whitespace,
)


# ---------------------------------------------------------------------------
# order_columns
# ---------------------------------------------------------------------------


class TestOrderColumns:
    def test_all_columns_reordered(self):
        df = pd.DataFrame({"b": [1], "a": [2], "c": [3]})
        result = order_columns(df, ["a", "b", "c"])
        assert list(result.columns) == ["a", "b", "c"]

    def test_extra_columns_appended(self):
        df = pd.DataFrame({"b": [1], "a": [2], "c": [3]})
        result = order_columns(df, ["a"])
        assert result.columns[0] == "a"
        assert set(result.columns) == {"a", "b", "c"}

    def test_columns_not_in_df_cause_keyerror(self):
        df = pd.DataFrame({"a": [1], "b": [2]})
        with pytest.raises(KeyError):
            order_columns(df, ["a", "z", "b"])

    def test_empty_column_order(self):
        df = pd.DataFrame({"a": [1], "b": [2]})
        result = order_columns(df, [])
        assert set(result.columns) == {"a", "b"}

    def test_returns_copy(self):
        df = pd.DataFrame({"a": [1], "b": [2]})
        result = order_columns(df, ["a", "b"])
        result["a"] = 99
        assert df["a"].iloc[0] == 1


# ---------------------------------------------------------------------------
# strip_whitespace
# ---------------------------------------------------------------------------


class TestStripWhitespace:
    def test_strips_strings(self):
        df = pd.DataFrame({"name": ["  Alice  ", " Bob"], "val": [1, 2]})
        result = strip_whitespace(df)
        assert result["name"].tolist() == ["Alice", "Bob"]

    def test_leaves_non_strings_unchanged(self):
        df = pd.DataFrame({"val": [1.5, None, 3]})
        result = strip_whitespace(df)
        assert result["val"].iloc[0] == 1.5
        assert pd.isna(result["val"].iloc[1])

    def test_empty_strings_stay_empty(self):
        df = pd.DataFrame({"name": ["  ", ""]})
        result = strip_whitespace(df)
        assert result["name"].tolist() == ["", ""]


# ---------------------------------------------------------------------------
# choose_ignore_case_value
# ---------------------------------------------------------------------------


class TestChooseIgnoreCaseValue:
    def test_returns_correctly_cased_value(self):
        result = choose_ignore_case_value("HELLO", ["Hello", "World"])
        assert result == "Hello"

    def test_exact_match(self):
        result = choose_ignore_case_value("Hello", ["Hello", "World"])
        assert result == "Hello"

    def test_not_found_returns_original_by_default(self):
        result = choose_ignore_case_value("missing", ["Hello", "World"])
        assert result == "missing"

    def test_not_found_returns_none_when_flagged(self):
        result = choose_ignore_case_value(
            "missing", ["Hello", "World"], return_same_if_missing=False
        )
        assert result is None

    def test_non_string_returned_unchanged(self):
        assert choose_ignore_case_value(42, ["Hello"]) == 42
        assert choose_ignore_case_value(None, ["Hello"]) is None

    def test_precomputed_lowercase_allowable(self):
        allowable = ["FooBar", "BazQux"]
        lc = [v.lower() for v in allowable]
        result = choose_ignore_case_value(
            "foobar", allowable, lowercase_allowable_values=lc
        )
        assert result == "FooBar"

    def test_case_insensitive_match_lowercase_input(self):
        result = choose_ignore_case_value("world", ["Hello", "World"])
        assert result == "World"


# ---------------------------------------------------------------------------
# parse_numeric
# ---------------------------------------------------------------------------


class TestParseNumeric:
    def test_integer_string(self):
        assert parse_numeric("42") == 42
        assert isinstance(parse_numeric("42"), int)

    def test_negative_integer_string(self):
        assert parse_numeric("-7") == -7

    def test_float_string(self):
        assert parse_numeric("3.14") == 3.14
        assert isinstance(parse_numeric("3.14"), float)

    def test_non_numeric_string_unchanged(self):
        assert parse_numeric("hello") == "hello"

    def test_leading_zero_string_unchanged(self):
        assert parse_numeric("09021") == "09021"

    def test_underscore_string_unchanged(self):
        assert parse_numeric("123_456") == "123_456"

    def test_non_string_unchanged(self):
        assert parse_numeric(5) == 5
        assert parse_numeric(3.14) == 3.14
        assert parse_numeric(None) is None

    def test_string_without_digit_unchanged(self):
        assert parse_numeric("abc") == "abc"

    def test_float_with_no_integer_match(self):
        result = parse_numeric("1.0")
        assert result == 1.0
        assert isinstance(result, float)

    def test_zero_string(self):
        assert parse_numeric("0") == 0
        assert isinstance(parse_numeric("0"), int)


# ---------------------------------------------------------------------------
# parse_df_values
# ---------------------------------------------------------------------------


class TestParseDfValues:
    def test_converts_numeric_strings_inline(self):
        df = pd.DataFrame({"a": ["1", "2"], "b": ["3.5", "hello"]})
        result = parse_df_values(df, inline=True)
        assert result["a"].tolist() == [1, 2]
        assert result["b"].iloc[0] == 3.5
        assert result["b"].iloc[1] == "hello"

    def test_inline_false_original_unchanged(self):
        df = pd.DataFrame({"a": ["1", "2"]})
        result = parse_df_values(df, inline=False)
        assert df["a"].tolist() == ["1", "2"]
        assert result["a"].tolist() == [1, 2]

    def test_inline_true_modifies_df(self):
        df = pd.DataFrame({"x": ["10"]})
        result = parse_df_values(df, inline=True)
        assert df["x"].iloc[0] == 10
        assert result is df


# ---------------------------------------------------------------------------
# merge_dicts_of_lists
# ---------------------------------------------------------------------------


class TestMergeDictsOfLists:
    def test_no_overlap(self):
        result = merge_dicts_of_lists([{"a": [1, 2]}, {"b": [3]}])
        assert result == {"a": [1, 2], "b": [3]}

    def test_overlapping_keys(self):
        result = merge_dicts_of_lists([{"a": [1, 2]}, {"a": [3, 4]}])
        assert result == {"a": [1, 2, 3, 4]}

    def test_none_items_ignored(self):
        result = merge_dicts_of_lists([{"a": [1]}, None, {"a": [2]}])
        assert result == {"a": [1, 2]}

    def test_empty_list_of_dicts(self):
        result = merge_dicts_of_lists([])
        assert result == {}

    def test_single_dict(self):
        result = merge_dicts_of_lists([{"x": [10, 20]}])
        assert result == {"x": [10, 20]}


# ---------------------------------------------------------------------------
# make_multivalued
# ---------------------------------------------------------------------------


class TestMakeMultivalued:
    def test_json_list_string(self):
        result = make_multivalued('["a", "b", "c"]')
        assert result == ["a", "b", "c"]

    def test_yaml_list_string(self):
        result = make_multivalued("- a\n- b\n- c\n")
        assert result == ["a", "b", "c"]

    def test_comma_separated(self):
        result = make_multivalued("a, b, c")
        assert result == ["a", "b", "c"]

    def test_semicolon_separated(self):
        result = make_multivalued("x;y;z")
        assert result == ["x", "y", "z"]

    def test_single_string_no_delimiter(self):
        result = make_multivalued("hello")
        assert result == ["hello"]

    def test_already_a_list(self):
        result = make_multivalued([1, 2, 3])
        assert result == [1, 2, 3]

    def test_tuple_converted_to_list(self):
        result = make_multivalued((1, 2))
        assert result == [1, 2]

    def test_non_string_scalar_wrapped(self):
        assert make_multivalued(42) == [42]
        assert make_multivalued(None) == [None]


# ---------------------------------------------------------------------------
# get_unique_output_file
# ---------------------------------------------------------------------------


class TestGetUniqueOutputFile:
    def test_non_existing_file_unchanged(self, tmp_path):
        p = tmp_path / "output.csv"
        result = get_unique_output_file(p)
        assert result == p

    def test_existing_file_gets_index(self, tmp_path):
        p = tmp_path / "output.csv"
        p.write_text("data")
        result = get_unique_output_file(p)
        assert result != p
        assert not os.path.exists(result)

    def test_multiple_conflicts_increment_index(self, tmp_path):
        p = tmp_path / "output.csv"
        p.write_text("data")
        first = get_unique_output_file(p)
        first.write_text("data2")
        second = get_unique_output_file(p)
        assert second != p
        assert second != first


# ---------------------------------------------------------------------------
# select_func_kwargs
# ---------------------------------------------------------------------------


class TestSelectFuncKwargs:
    def test_only_valid_kwargs_selected(self):
        def my_func(a, b, c):
            pass

        result = select_func_kwargs(my_func, {"a": 1, "b": 2, "z": 99})
        assert result == {"a": 1, "b": 2}
        assert "z" not in result

    def test_empty_kwargs(self):
        def my_func(a, b):
            pass

        result = select_func_kwargs(my_func, {})
        assert result == {}

    def test_no_matching_kwargs(self):
        def my_func(a):
            pass

        result = select_func_kwargs(my_func, {"z": 1, "y": 2})
        assert result == {}


# ---------------------------------------------------------------------------
# save_data_frame / read_data_frame  (round-trip)
# ---------------------------------------------------------------------------


class TestSaveReadDataFrame:
    def _make_df(self):
        return pd.DataFrame({"name": ["Alice", "Bob"], "value": [1, 2]})

    def test_csv_round_trip(self, tmp_path):
        df = self._make_df()
        path = tmp_path / "test.csv"
        save_data_frame(df, path, index=False)
        result = read_data_frame(str(path))
        assert list(result["name"]) == ["Alice", "Bob"]
        assert list(result["value"]) == [1, 2]

    def test_tsv_round_trip(self, tmp_path):
        df = self._make_df()
        path = tmp_path / "test.tsv"
        save_data_frame(df, path, index=False)
        result = read_data_frame(str(path))
        assert list(result["name"]) == ["Alice", "Bob"]

    def test_yaml_round_trip(self, tmp_path):
        df = self._make_df()
        path = tmp_path / "test.yaml"
        save_data_frame(df, path)
        result = read_data_frame(str(path))
        assert list(result["name"]) == ["Alice", "Bob"]

    def test_save_unsupported_extension_raises(self, tmp_path):
        df = self._make_df()
        with pytest.raises(ValueError):
            save_data_frame(df, tmp_path / "test.json")

    def test_read_unsupported_extension_raises(self, tmp_path):
        path = tmp_path / "test.json"
        path.write_text("{}")
        from odm_map.utils.clean_exit_error import CleanExitError

        with pytest.raises(CleanExitError):
            read_data_frame(str(path))

    def test_save_strips_whitespace(self, tmp_path):
        df = pd.DataFrame({"name": ["  Alice  ", " Bob "]})
        path = tmp_path / "stripped.csv"
        save_data_frame(df, path, index=False)
        result = read_data_frame(str(path))
        assert result["name"].tolist() == ["Alice", "Bob"]

    def test_save_no_strip(self, tmp_path):
        df = pd.DataFrame({"name": ["  Alice  "]})
        path = tmp_path / "nostrip.csv"
        save_data_frame(df, path, strip=False, index=False)
        result = read_data_frame(str(path))
        assert result["name"].tolist() == ["  Alice  "]

    def test_read_dict_spec_for_excel(self, tmp_path):
        df = self._make_df()
        excel_path = tmp_path / "test.xlsx"
        df.to_excel(excel_path, sheet_name="Sheet1", index=False)
        result = read_data_frame({"excel_file": str(excel_path), "sheet": "Sheet1"})
        assert list(result["name"]) == ["Alice", "Bob"]

    def test_creates_output_directory(self, tmp_path):
        df = self._make_df()
        nested = tmp_path / "a" / "b" / "out.csv"
        save_data_frame(df, nested, index=False)
        assert nested.exists()
