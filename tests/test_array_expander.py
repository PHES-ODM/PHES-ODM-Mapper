"""Tests for odm_map.expander.array_expander.ArrayExpander"""

import pandas as pd
import pytest
import yaml

from odm_map.expander.array_expander import ArrayExpander, ConfigKeys


@pytest.fixture
def expander(tmp_path):
    config = {"expand_columns": {"measures": ["value"]}}
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(config))
    return ArrayExpander(str(config_file))


# ---------------------------------------------------------------------------
# expand_with_column — basic expansion
# ---------------------------------------------------------------------------


class TestExpandWithColumn:
    def test_expands_yaml_list_string(self, expander):
        # Expansion requires a non-empty config; config=None parses YAML but does not create rows
        df = pd.DataFrame({"measure": ["Orange", "Blue"], "value": ["[1, 2]", "3"]})
        config = {ConfigKeys.EXPAND: True}
        result = expander.expand_with_column(df, "value", config, "measures")
        # Orange [1,2] -> 2 rows; Blue "3" -> unchanged (not a list)
        assert len(result) == 3
        assert 1 in result["value"].tolist()
        assert 2 in result["value"].tolist()

    def test_expands_python_list(self, expander):
        df = pd.DataFrame({"measure": ["A"], "value": [[10, 20, 30]]})
        config = {ConfigKeys.EXPAND: True}
        result = expander.expand_with_column(df, "value", config, "measures")
        assert len(result) == 3
        assert set(result["value"].tolist()) == {10, 20, 30}

    def test_non_array_row_unchanged(self, expander):
        df = pd.DataFrame({"measure": ["A", "B"], "value": ["scalar", "[1, 2]"]})
        config = {ConfigKeys.EXPAND: True}
        result = expander.expand_with_column(df, "value", config, "measures")
        # "scalar" is not a list so stays; "B" has [1,2] -> 2 rows
        assert len(result) == 3
        assert "scalar" in result["value"].tolist()

    def test_other_columns_copied(self, expander):
        df = pd.DataFrame({"measure": ["Orange"], "value": [[1, 2]]})
        config = {ConfigKeys.EXPAND: True}
        result = expander.expand_with_column(df, "value", config, "measures")
        assert list(result["measure"]) == ["Orange", "Orange"]

    def test_config_none_parses_yaml_but_does_not_expand(self, expander):
        # With config=None expansion is skipped; the YAML string is parsed to a list in-place
        df = pd.DataFrame({"measure": ["A"], "value": ["[1, 2]"]})
        result = expander.expand_with_column(df, "value", None, "measures")
        assert len(result) == 1
        assert isinstance(result["value"].iloc[0], list)

    def test_no_arrays_df_unchanged(self, expander):
        df = pd.DataFrame({"measure": ["A", "B"], "value": ["x", "y"]})
        result = expander.expand_with_column(df, "value", None, "measures")
        assert len(result) == 2

    def test_empty_dataframe(self, expander):
        df = pd.DataFrame({"measure": [], "value": []})
        result = expander.expand_with_column(df, "value", None, "measures")
        assert len(result) == 0

    def test_invalid_yaml_list_string_skipped(self, expander):
        df = pd.DataFrame({"measure": ["A"], "value": ["[unclosed"]})
        result = expander.expand_with_column(df, "value", None, "measures")
        # "[unclosed" starts and ends with "[" but yaml parse fails -> row skipped
        assert len(result) == 1

    # -------------------------------------------------------------------------
    # remove_nulls option
    # -------------------------------------------------------------------------

    def test_remove_nulls(self, expander):
        df = pd.DataFrame({"value": [[None, "a", "", "b"]]})
        config = {ConfigKeys.REMOVE_NULLS_KEY: True}
        result = expander.expand_with_column(df, "value", config, "measures")
        values = result["value"].tolist()
        assert None not in values
        assert "" not in values
        assert "a" in values and "b" in values

    def test_remove_nulls_false_keeps_nulls(self, expander):
        df = pd.DataFrame({"value": [[None, "a"]]})
        config = {ConfigKeys.REMOVE_NULLS_KEY: False}
        result = expander.expand_with_column(df, "value", config, "measures")
        assert len(result) == 2

    # -------------------------------------------------------------------------
    # select_items option
    # -------------------------------------------------------------------------

    def test_select_items_single_index(self, expander):
        df = pd.DataFrame({"value": [["x", "y", "z"]]})
        config = {ConfigKeys.SELECT_ITEMS: 0}
        result = expander.expand_with_column(df, "value", config, "measures")
        assert result["value"].tolist() == ["x"]

    def test_select_items_last_index(self, expander):
        df = pd.DataFrame({"value": [["x", "y", "z"]]})
        config = {ConfigKeys.SELECT_ITEMS: -1}
        result = expander.expand_with_column(df, "value", config, "measures")
        assert result["value"].tolist() == ["z"]

    def test_select_items_list_of_indices(self, expander):
        df = pd.DataFrame({"value": [["a", "b", "c", "d"]]})
        config = {ConfigKeys.SELECT_ITEMS: [0, 2]}
        result = expander.expand_with_column(df, "value", config, "measures")
        assert set(result["value"].tolist()) == {"a", "c"}

    def test_select_items_out_of_range_ignored(self, expander):
        df = pd.DataFrame({"value": [["a", "b"]]})
        config = {ConfigKeys.SELECT_ITEMS: [0, 99]}
        result = expander.expand_with_column(df, "value", config, "measures")
        assert result["value"].tolist() == ["a"]

    def test_select_items_deduplicates(self, expander):
        df = pd.DataFrame({"value": [["a", "b", "c"]]})
        # indices 0 and -3 both point to index 0
        config = {ConfigKeys.SELECT_ITEMS: [0, -3]}
        result = expander.expand_with_column(df, "value", config, "measures")
        assert result["value"].tolist() == ["a"]

    # -------------------------------------------------------------------------
    # expand=False option
    # -------------------------------------------------------------------------

    def test_expand_false_keeps_array(self, expander):
        df = pd.DataFrame({"value": [[1, 2, 3]]})
        config = {ConfigKeys.EXPAND: False}
        result = expander.expand_with_column(df, "value", config, "measures")
        assert len(result) == 1
        assert isinstance(result["value"].iloc[0], list)

    # -------------------------------------------------------------------------
    # max_length option (only logs, doesn't drop)
    # -------------------------------------------------------------------------

    def test_max_length_does_not_alter_data(self, expander):
        df = pd.DataFrame({"value": [["a", "b", "c"]]})
        config = {ConfigKeys.MAX_LENGTH: 1}
        result = expander.expand_with_column(df, "value", config, "measures")
        # max_length just logs an error, doesn't remove data
        assert len(result) == 3

    # -------------------------------------------------------------------------
    # Result is a copy (original df unchanged)
    # -------------------------------------------------------------------------

    def test_returns_copy_not_inplace(self, expander):
        df = pd.DataFrame({"measure": ["A"], "value": [[1, 2]]})
        original_len = len(df)
        expander.expand_with_column(df, "value", None, "measures")
        assert len(df) == original_len


# ---------------------------------------------------------------------------
# expand_data — the high-level method
# ---------------------------------------------------------------------------


@pytest.fixture
def expander_with_expand(tmp_path):
    # Config that explicitly enables expansion (config=None in expand_data means no expand)
    config = {"expand_columns": {"measures": [{"value": {"expand": True}}]}}
    config_file = tmp_path / "config_expand.yaml"
    config_file.write_text(yaml.dump(config))
    return ArrayExpander(str(config_file))


@pytest.fixture
def expander_no_expand_columns(tmp_path):
    config = {}  # no expand_columns key
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(config))
    return ArrayExpander(str(config_file))


@pytest.fixture
def expander_empty_config(tmp_path):
    # Write a YAML file that evaluates to None
    config_file = tmp_path / "config.yaml"
    config_file.write_text("")
    return ArrayExpander(str(config_file))


class TestExpandData:
    def test_empty_config_returns_inputs_unchanged(self, expander_empty_config):
        df = pd.DataFrame({"value": [[1, 2, 3]]})
        data_frames = {"measures": [df]}
        _files_out, frames_out = expander_empty_config.expand_data(
            data_files={}, data_frames=data_frames
        )
        assert frames_out == data_frames

    def test_no_expand_columns_key_returns_inputs_unchanged(
        self, expander_no_expand_columns
    ):
        df = pd.DataFrame({"value": [[1, 2, 3]]})
        data_frames = {"measures": [df]}
        _files_out, frames_out = expander_no_expand_columns.expand_data(
            data_files={}, data_frames=data_frames
        )
        assert frames_out is data_frames

    def test_basic_expand_from_dataframes(self, expander_with_expand):
        df = pd.DataFrame({"measure": ["A", "B"], "value": [[1, 2], "3"]})
        data_frames = {"measures": [df]}
        _files_out, frames_out = expander_with_expand.expand_data(
            data_files={}, data_frames=data_frames
        )
        result_df = frames_out["measures"][0]
        # [1, 2] expands to 2 rows; "3" is not a list, stays unchanged → 3 total
        assert len(result_df) == 3

    def test_expand_from_file(self, expander_with_expand, tmp_path):
        csv_file = tmp_path / "measures.csv"
        csv_file.write_text('measure,value\nA,"[1, 2]"\nB,3\n')
        _files_out, frames_out = expander_with_expand.expand_data(
            data_files={"measures": [str(csv_file)]}, data_frames={}
        )
        result_df = frames_out["measures"][0]
        assert len(result_df) == 3

    def test_expand_saves_to_output_dir(self, expander_with_expand, tmp_path):
        df = pd.DataFrame({"measure": ["A"], "value": [[10, 20]]})
        output_dir = tmp_path / "output"
        files_out, _frames_out = expander_with_expand.expand_data(
            data_files={}, data_frames={"measures": [df]}, output_dir=str(output_dir)
        )
        assert files_out is not None
        assert "measures" in files_out

    def test_class_not_in_data_frames_skipped(self, expander):
        # config says expand 'measures' but no 'measures' in data_frames
        df = pd.DataFrame({"name": ["A"]})
        data_frames = {"sites": [df]}
        _files_out, frames_out = expander.expand_data(
            data_files={}, data_frames=data_frames
        )
        # sites is not in expand config so it stays as-is; no error
        assert "sites" in frames_out

    def test_returns_none_files_when_no_output_dir(self, expander_with_expand):
        df = pd.DataFrame({"measure": ["A"], "value": [[1, 2]]})
        files_out, _frames_out = expander_with_expand.expand_data(
            data_files={}, data_frames={"measures": [df]}
        )
        assert files_out is None
