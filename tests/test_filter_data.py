"""Tests for odm_map.filter.filter_data"""

import pandas as pd
from pathlib import Path

from odm_map.filter.filter_data import DataFilter, FilterConfigColumns
from odm_map.filter.filter_funcs import DROP_COLUMN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A minimal single-row config that is always valid but does nothing when run.
# Used in tests that only need a DataFilter instance, not a specific filter config.
_NOOP_ROW = {
    FilterConfigColumns.INPUT_FILTER: "",
    FilterConfigColumns.OUTPUT_FILTER: "f",
    FilterConfigColumns.CLASS: "C",
    FilterConfigColumns.SLOT: "",
    FilterConfigColumns.OPERATION: "create_filter",
    FilterConfigColumns.VALUE: "True",
}


def write_config(tmp_path, rows: list[dict]) -> Path:
    """Write a filter config CSV to tmp_path and return the path.

    Requires at least one row because an empty config triggers a pandas
    edge-case in DataFilter.__init__ (apply on 0-row df yields float64 Series).
    """
    assert rows, "rows must be non-empty; use _NOOP_ROW for placeholder configs"
    cols = [
        FilterConfigColumns.INPUT_FILTER,
        FilterConfigColumns.OUTPUT_FILTER,
        FilterConfigColumns.CLASS,
        FilterConfigColumns.SLOT,
        FilterConfigColumns.OPERATION,
        FilterConfigColumns.VALUE,
    ]
    df = pd.DataFrame(rows, columns=cols)
    path = tmp_path / "config.csv"
    df.to_csv(path, index=False)
    return path


def noop_filter(tmp_path) -> DataFilter:
    """Create a DataFilter with a single harmless row (used when the config doesn't matter)."""
    config_path = write_config(tmp_path, [_NOOP_ROW])
    return DataFilter(config_path)


def write_data_csv(tmp_path, name: str, df: pd.DataFrame) -> Path:
    path = tmp_path / name
    df.to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# DataFilter.__init__
# ---------------------------------------------------------------------------


class TestDataFilterInit:
    def test_loads_config_file(self, tmp_path):
        config_path = write_config(
            tmp_path,
            [
                {
                    "inputFilter": "f",
                    "outputFilter": "f",
                    "class": "C",
                    "slot": "s",
                    "operation": "create_filter",
                    "value": "True",
                },
            ],
        )
        df_filter = DataFilter(config_path)
        assert len(df_filter.config_df) == 1

    def test_drops_fully_empty_rows(self, tmp_path):
        config_path = write_config(
            tmp_path,
            [
                {
                    "inputFilter": "f",
                    "outputFilter": "f",
                    "class": "C",
                    "slot": "s",
                    "operation": "create_filter",
                    "value": "True",
                },
                {
                    "inputFilter": "",
                    "outputFilter": "",
                    "class": "",
                    "slot": "",
                    "operation": "",
                    "value": "",
                },
            ],
        )
        df_filter = DataFilter(config_path)
        assert len(df_filter.config_df) == 1

    def test_yaml_parses_boolean_true(self, tmp_path):
        config_path = write_config(
            tmp_path,
            [
                {
                    "inputFilter": "",
                    "outputFilter": "f",
                    "class": "C",
                    "slot": "",
                    "operation": "create_filter",
                    "value": "True",
                },
            ],
        )
        df_filter = DataFilter(config_path)
        val = df_filter.config_df[FilterConfigColumns.VALUE].iloc[0]
        assert val == True  # noqa: E712 — comparing against numpy bool

    def test_yaml_parses_boolean_false(self, tmp_path):
        config_path = write_config(
            tmp_path,
            [
                {
                    "inputFilter": "",
                    "outputFilter": "f",
                    "class": "C",
                    "slot": "",
                    "operation": "create_filter",
                    "value": "False",
                },
            ],
        )
        df_filter = DataFilter(config_path)
        val = df_filter.config_df[FilterConfigColumns.VALUE].iloc[0]
        assert val == False  # noqa: E712 — comparing against numpy bool

    def test_yaml_parses_list_value(self, tmp_path):
        config_path = write_config(
            tmp_path,
            [
                {
                    "inputFilter": "f",
                    "outputFilter": "f",
                    "class": "C",
                    "slot": "s",
                    "operation": "exclude_equals",
                    "value": "[a, b]",
                },
            ],
        )
        df_filter = DataFilter(config_path)
        val = df_filter.config_df[FilterConfigColumns.VALUE].iloc[0]
        assert val == ["a", "b"]

    def test_yaml_parses_string_value(self, tmp_path):
        config_path = write_config(
            tmp_path,
            [
                {
                    "inputFilter": "f",
                    "outputFilter": "f",
                    "class": "C",
                    "slot": "s",
                    "operation": "exclude_equals",
                    "value": "keep_first",
                },
            ],
        )
        df_filter = DataFilter(config_path)
        val = df_filter.config_df[FilterConfigColumns.VALUE].iloc[0]
        assert val == "keep_first"

    def test_config_columns_are_strings(self, tmp_path):
        config_path = write_config(
            tmp_path,
            [
                {
                    "inputFilter": "f",
                    "outputFilter": "f",
                    "class": "C",
                    "slot": "s",
                    "operation": "create_filter",
                    "value": "True",
                },
            ],
        )
        df_filter = DataFilter(config_path)
        row = df_filter.config_df.iloc[0]
        assert isinstance(row[FilterConfigColumns.OPERATION], str)
        assert isinstance(row[FilterConfigColumns.CLASS], str)


# ---------------------------------------------------------------------------
# DataFilter.load_data
# ---------------------------------------------------------------------------


class TestLoadData:
    def test_loads_single_csv(self, tmp_path):
        df_filter = noop_filter(tmp_path)

        source = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        csv_path = write_data_csv(tmp_path, "source.csv", source)

        result = df_filter.load_data({"MyClass": [csv_path]})
        assert "MyClass" in result
        assert list(result["MyClass"]["a"]) == [1, 2]

    def test_loads_multiple_files_concat(self, tmp_path):
        df_filter = noop_filter(tmp_path)

        df1 = pd.DataFrame({"a": [1, 2]})
        df2 = pd.DataFrame({"a": [3, 4]})
        p1 = write_data_csv(tmp_path, "f1.csv", df1)
        p2 = write_data_csv(tmp_path, "f2.csv", df2)

        result = df_filter.load_data({"C": [p1, p2]})
        assert len(result["C"]) == 4

    def test_loads_multiple_classes(self, tmp_path):
        df_filter = noop_filter(tmp_path)

        df_a = pd.DataFrame({"x": [1]})
        df_b = pd.DataFrame({"y": [2]})
        pa = write_data_csv(tmp_path, "a.csv", df_a)
        pb = write_data_csv(tmp_path, "b.csv", df_b)

        result = df_filter.load_data({"ClassA": [pa], "ClassB": [pb]})
        assert "ClassA" in result
        assert "ClassB" in result

    def test_empty_data_files_returns_empty_dict(self, tmp_path):
        df_filter = noop_filter(tmp_path)
        result = df_filter.load_data({})
        assert result == {}


# ---------------------------------------------------------------------------
# DataFilter.save_data
# ---------------------------------------------------------------------------


class TestSaveData:
    def test_saves_csv_files(self, tmp_path):
        df_filter = noop_filter(tmp_path)

        data = {"MyClass": pd.DataFrame({"a": [1, 2]})}
        output_dir = tmp_path / "output"
        df_filter.save_data(data, output_dir)

        assert (output_dir / "MyClass.csv").exists()

    def test_creates_output_dir_if_missing(self, tmp_path):
        df_filter = noop_filter(tmp_path)

        data = {"C": pd.DataFrame({"v": [1]})}
        output_dir = tmp_path / "new" / "nested" / "dir"
        df_filter.save_data(data, output_dir)

        assert output_dir.is_dir()

    def test_returns_output_files_dict(self, tmp_path):
        df_filter = noop_filter(tmp_path)

        data = {"C": pd.DataFrame({"v": [1]})}
        output_dir = tmp_path / "out"
        result = df_filter.save_data(data, output_dir)

        assert "C" in result
        assert len(result["C"]) == 1
        assert result["C"][0] == output_dir / "C.csv"

    def test_saved_content_matches_input(self, tmp_path):
        df_filter = noop_filter(tmp_path)

        original = pd.DataFrame({"a": [10, 20], "b": ["x", "y"]})
        data = {"D": original.copy()}
        output_dir = tmp_path / "out"
        df_filter.save_data(data, output_dir)

        saved = pd.read_csv(output_dir / "D.csv")
        assert list(saved["a"]) == [10, 20]
        assert list(saved["b"]) == ["x", "y"]

    def test_saves_multiple_classes(self, tmp_path):
        df_filter = noop_filter(tmp_path)

        data = {
            "Alpha": pd.DataFrame({"v": [1]}),
            "Beta": pd.DataFrame({"v": [2]}),
        }
        output_dir = tmp_path / "out"
        result = df_filter.save_data(data, output_dir)

        assert (output_dir / "Alpha.csv").exists()
        assert (output_dir / "Beta.csv").exists()
        assert set(result.keys()) == {"Alpha", "Beta"}


# ---------------------------------------------------------------------------
# DataFilter.run_filter
# ---------------------------------------------------------------------------


class TestRunFilter:
    def _make_filter(self, tmp_path, rows):
        config_path = write_config(tmp_path, rows)
        return DataFilter(config_path)

    def test_run_filter_with_data_dict(self, tmp_path):
        df_filter = self._make_filter(
            tmp_path,
            [
                {
                    "inputFilter": "",
                    "outputFilter": "f",
                    "class": "C",
                    "slot": "",
                    "operation": "create_filter",
                    "value": "True",
                },
                {
                    "inputFilter": "f",
                    "outputFilter": "f",
                    "class": "C",
                    "slot": "status",
                    "operation": "exclude_equals",
                    "value": "inactive",
                },
                {
                    "inputFilter": "f",
                    "outputFilter": "",
                    "class": "C",
                    "slot": "",
                    "operation": "apply_filter",
                    "value": "C",
                },
            ],
        )
        df = pd.DataFrame({"status": ["active", "inactive", "active"]})
        result, output_files = df_filter.run_filter(data={"C": df})

        assert len(result["C"]) == 2
        assert output_files == {}

    def test_run_filter_with_data_files(self, tmp_path):
        df_filter = self._make_filter(
            tmp_path,
            [
                {
                    "inputFilter": "",
                    "outputFilter": "f",
                    "class": "C",
                    "slot": "",
                    "operation": "create_filter",
                    "value": "True",
                },
                {
                    "inputFilter": "f",
                    "outputFilter": "",
                    "class": "C",
                    "slot": "",
                    "operation": "apply_filter",
                    "value": "C",
                },
            ],
        )
        source = pd.DataFrame({"x": [1, 2, 3]})
        csv_path = write_data_csv(tmp_path, "data.csv", source)

        result, _ = df_filter.run_filter(data_files={"C": [csv_path]})
        assert "C" in result
        assert len(result["C"]) == 3

    def test_run_filter_saves_to_output_dir(self, tmp_path):
        df_filter = self._make_filter(
            tmp_path,
            [
                {
                    "inputFilter": "",
                    "outputFilter": "f",
                    "class": "C",
                    "slot": "",
                    "operation": "create_filter",
                    "value": "True",
                },
                {
                    "inputFilter": "f",
                    "outputFilter": "",
                    "class": "C",
                    "slot": "",
                    "operation": "apply_filter",
                    "value": "C",
                },
            ],
        )
        df = pd.DataFrame({"v": [1, 2]})
        output_dir = tmp_path / "out"

        result, output_files = df_filter.run_filter(
            data={"C": df}, output_dir=output_dir
        )

        assert (output_dir / "C.csv").exists()
        assert "C" in output_files

    def test_run_filter_does_not_modify_input_dict(self, tmp_path):
        df_filter = self._make_filter(
            tmp_path,
            [
                {
                    "inputFilter": "",
                    "outputFilter": "f",
                    "class": "C",
                    "slot": "",
                    "operation": "create_filter",
                    "value": "True",
                },
                {
                    "inputFilter": "f",
                    "outputFilter": "f",
                    "class": "C",
                    "slot": "v",
                    "operation": "exclude_equals",
                    "value": "1",
                },
                {
                    "inputFilter": "f",
                    "outputFilter": "",
                    "class": "C",
                    "slot": "",
                    "operation": "apply_filter",
                    "value": "C",
                },
            ],
        )
        df = pd.DataFrame({"v": [1, 2, 3]})
        original_data = {"C": df}
        original_len = len(df)

        df_filter.run_filter(data=original_data)

        assert len(original_data["C"]) == original_len

    def test_run_filter_skips_missing_class(self, tmp_path):
        df_filter = self._make_filter(
            tmp_path,
            [
                {
                    "inputFilter": "f",
                    "outputFilter": "f",
                    "class": "Missing",
                    "slot": "s",
                    "operation": "exclude_equals",
                    "value": "x",
                },
            ],
        )
        df = pd.DataFrame({"s": ["x", "y"]})
        # Should not raise even though "Missing" is not in data
        result, _ = df_filter.run_filter(data={"Other": df})
        assert "Other" in result

    def test_run_filter_debug_mode(self, tmp_path):
        df_filter = self._make_filter(
            tmp_path,
            [
                {
                    "inputFilter": "",
                    "outputFilter": "f",
                    "class": "C",
                    "slot": "",
                    "operation": "create_filter",
                    "value": "True",
                },
                {
                    "inputFilter": "f",
                    "outputFilter": "f",
                    "class": "C",
                    "slot": "status",
                    "operation": "exclude_equals",
                    "value": "bad",
                },
                {
                    "inputFilter": "f",
                    "outputFilter": "",
                    "class": "C",
                    "slot": "",
                    "operation": "apply_filter",
                    "value": "C",
                },
            ],
        )
        df = pd.DataFrame({"status": ["good", "bad", "good"]})
        result, _ = df_filter.run_filter(data={"C": df}, debug_mode=True)

        assert DROP_COLUMN in result["C"].columns
        assert result["C"][DROP_COLUMN].iloc[1] is True

    def test_run_filter_no_output_dir_returns_empty_files(self, tmp_path):
        df_filter = self._make_filter(
            tmp_path,
            [
                {
                    "inputFilter": "",
                    "outputFilter": "f",
                    "class": "C",
                    "slot": "",
                    "operation": "create_filter",
                    "value": "True",
                },
                {
                    "inputFilter": "f",
                    "outputFilter": "",
                    "class": "C",
                    "slot": "",
                    "operation": "apply_filter",
                    "value": "C",
                },
            ],
        )
        df = pd.DataFrame({"v": [1]})
        _, output_files = df_filter.run_filter(data={"C": df})
        assert output_files == {}

    def test_run_filter_include_equals(self, tmp_path):
        df_filter = self._make_filter(
            tmp_path,
            [
                {
                    "inputFilter": "",
                    "outputFilter": "f",
                    "class": "C",
                    "slot": "",
                    "operation": "create_filter",
                    "value": "False",
                },
                {
                    "inputFilter": "f",
                    "outputFilter": "f",
                    "class": "C",
                    "slot": "category",
                    "operation": "include_equals",
                    "value": "keep",
                },
                {
                    "inputFilter": "f",
                    "outputFilter": "",
                    "class": "C",
                    "slot": "",
                    "operation": "apply_filter",
                    "value": "C",
                },
            ],
        )
        df = pd.DataFrame({"category": ["keep", "drop", "keep", "drop"]})
        result, _ = df_filter.run_filter(data={"C": df})

        assert len(result["C"]) == 2
        assert list(result["C"]["category"]) == ["keep", "keep"]

    def test_run_filter_copy_class(self, tmp_path):
        df_filter = self._make_filter(
            tmp_path,
            [
                {
                    "inputFilter": "",
                    "outputFilter": "",
                    "class": "C",
                    "slot": "",
                    "operation": "copy_class",
                    "value": "D",
                },
            ],
        )
        df = pd.DataFrame({"v": [1, 2]})
        result, _ = df_filter.run_filter(data={"C": df})

        assert "D" in result
        assert len(result["D"]) == 2

    def test_run_filter_delete_class(self, tmp_path):
        df_filter = self._make_filter(
            tmp_path,
            [
                {
                    "inputFilter": "",
                    "outputFilter": "",
                    "class": "C",
                    "slot": "",
                    "operation": "delete_class",
                    "value": "",
                },
            ],
        )
        df = pd.DataFrame({"v": [1]})
        result, _ = df_filter.run_filter(data={"C": df})

        assert "C" not in result
