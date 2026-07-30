"""Tests for odm_map.cleaner.clean_data"""

import numpy as np
import pandas as pd
import pytest

from odm_map.cleaner.clean_data import (
    MAX_LOG_KEY_LENGTH,
    DataCleaner,
    LogColumns,
    Logs,
)
from odm_map.utils.extra_and_tracking_slots import (
    EXTRA_SLOT_PREFIX,
    TrackingSlots,
)

# ---------------------------------------------------------------------------
# Minimal LinkML schema for testing
# ---------------------------------------------------------------------------

SCHEMA_YAML = """\
id: https://example.org/test_clean
name: test_clean
imports:
  - linkml:types
prefixes:
  test: https://example.org/test_clean/
  linkml: https://w3id.org/linkml/
default_prefix: test
default_range: string

enums:
  TemperatureUnit:
    permissible_values:
      degree Celsius (C) [UO:0000027]: {}
      degree Fahrenheit (F): {}
  StatusEnum:
    permissible_values:
      Active: {}
      Inactive: {}
      Pending Review: {}

classes:
  Measurement:
    attributes:
      sample_id:
        range: string
        identifier: true
        required: true
      temperature:
        range: TemperatureUnit
        required: false
      status:
        range: StatusEnum
        required: false
      code:
        range: string
        pattern: "^[A-Z]{2}-[0-9]{4}$"
        required: false
      notes:
        range: string
        required: false
"""

CLASS_NAME = "Measurement"
ONTOLOGY_REGEX = r"\[[A-Za-z0-9_]+:[A-Za-z0-9_]+\]$"


@pytest.fixture
def schema_path(tmp_path):
    schema_file = tmp_path / "test_clean_schema.yaml"
    schema_file.write_text(SCHEMA_YAML)
    return schema_file


@pytest.fixture
def cleaner(schema_path):
    return DataCleaner(schema=str(schema_path))


# ---------------------------------------------------------------------------
# TestAddToLog
# ---------------------------------------------------------------------------


class TestAddToLog:
    def test_add_single_dict(self):
        dc = DataCleaner()
        dc.add_to_log("key", {"col": "val"})
        assert dc.log_lines["key"] == [{"col": "val"}]

    def test_add_list_of_dicts(self):
        dc = DataCleaner()
        dc.add_to_log("key", [{"a": 1}, {"a": 2}])
        assert len(dc.log_lines["key"]) == 2

    def test_log_key_too_long_raises(self):
        dc = DataCleaner()
        with pytest.raises(ValueError):
            dc.add_to_log("x" * (MAX_LOG_KEY_LENGTH + 1), {"a": 1})

    def test_log_key_exactly_max_length_ok(self):
        dc = DataCleaner()
        key = "x" * MAX_LOG_KEY_LENGTH
        dc.add_to_log(key, {"a": 1})
        assert key in dc.log_lines

    def test_multiple_keys_are_independent(self):
        dc = DataCleaner()
        dc.add_to_log("key1", {"a": 1})
        dc.add_to_log("key2", {"b": 2})
        assert len(dc.log_lines["key1"]) == 1
        assert len(dc.log_lines["key2"]) == 1

    def test_accumulates_multiple_calls(self):
        dc = DataCleaner()
        dc.add_to_log("key", {"a": 1})
        dc.add_to_log("key", {"a": 2})
        assert len(dc.log_lines["key"]) == 2


# ---------------------------------------------------------------------------
# TestMoveLogLinesToDfs
# ---------------------------------------------------------------------------


class TestMoveLogLinesToDfs:
    def test_returns_none_when_no_lines(self):
        dc = DataCleaner()
        assert dc.move_log_lines_to_dfs("nonexistent") is None

    def test_converts_to_dataframe(self):
        dc = DataCleaner()
        dc.add_to_log("key", [{"col": "a"}, {"col": "b"}])
        df = dc.move_log_lines_to_dfs("key")
        assert isinstance(df, pd.DataFrame)
        assert list(df["col"]) == ["a", "b"]

    def test_clears_log_lines_after_conversion(self):
        dc = DataCleaner()
        dc.add_to_log("key", {"col": "val"})
        dc.move_log_lines_to_dfs("key")
        assert "key" not in dc.log_lines

    def test_appends_to_existing_log_df(self):
        dc = DataCleaner()
        dc.add_to_log("key", {"col": "first"})
        dc.move_log_lines_to_dfs("key")
        dc.add_to_log("key", {"col": "second"})
        dc.move_log_lines_to_dfs("key")
        assert len(dc.log_dfs["key"]) == 2

    def test_log_key_too_long_raises(self):
        dc = DataCleaner()
        with pytest.raises(ValueError):
            dc.move_log_lines_to_dfs("x" * (MAX_LOG_KEY_LENGTH + 1))


# ---------------------------------------------------------------------------
# TestCleanFormatAndMatchColumns
# ---------------------------------------------------------------------------


class TestCleanFormatAndMatchColumns:
    def _df(self, *cols):
        return pd.DataFrame({col: ["val"] for col in cols})

    def test_lowercase(self, cleaner):
        result = cleaner.clean_format_and_match_columns(
            self._df("TEMPERATURE"), CLASS_NAME, "lowercase"
        )
        assert "temperature" in result.columns

    def test_uppercase(self, cleaner):
        result = cleaner.clean_format_and_match_columns(
            self._df("temperature"), CLASS_NAME, "uppercase"
        )
        # "TEMPERATURE".lower() == "temperature" → case-insensitive match
        assert "temperature" in result.columns

    def test_alpha_numeric_underscore(self, cleaner):
        # "sample id" (space) → "sample_id"
        result = cleaner.clean_format_and_match_columns(
            self._df("sample id"), CLASS_NAME, "alpha_numeric_underscore"
        )
        assert "sample_id" in result.columns

    def test_single_underscores(self, cleaner):
        result = cleaner.clean_format_and_match_columns(
            self._df("sample__id"), CLASS_NAME, "single_underscores"
        )
        assert "sample_id" in result.columns

    def test_trim_trailing_underscores(self, cleaner):
        result = cleaner.clean_format_and_match_columns(
            self._df("status_"), CLASS_NAME, "trim_trailing_underscores"
        )
        assert "status" in result.columns

    def test_trim_whitespace(self, cleaner):
        result = cleaner.clean_format_and_match_columns(
            self._df(" status "), CLASS_NAME, "trim_whitespace"
        )
        assert "status" in result.columns

    def test_remove_chars(self, cleaner):
        # "s-t-a-t-u-s" → remove "-" → "status"
        result = cleaner.clean_format_and_match_columns(
            self._df("s-t-a-t-u-s"), CLASS_NAME, [{"remove_chars": "-"}]
        )
        assert "status" in result.columns

    def test_remove_special(self, cleaner):
        # "code!" → remove "!" → "code"
        result = cleaner.clean_format_and_match_columns(
            self._df("code!"), CLASS_NAME, "remove_special"
        )
        assert "code" in result.columns

    def test_unrecognized_column_removed(self, cleaner):
        result = cleaner.clean_format_and_match_columns(
            self._df("status", "xyz_unrecognized"), CLASS_NAME, "lowercase"
        )
        assert "status" in result.columns
        assert "xyz_unrecognized" not in result.columns

    def test_missing_schema_column_added_with_none(self, cleaner):
        result = cleaner.clean_format_and_match_columns(
            self._df("sample_id"), CLASS_NAME, "lowercase"
        )
        for col in ["temperature", "status", "code", "notes"]:
            assert col in result.columns
            assert result[col].isna().all()

    def test_extra_slot_preserved(self, cleaner):
        extra = EXTRA_SLOT_PREFIX + "mymeta"
        result = cleaner.clean_format_and_match_columns(
            self._df("sample_id", extra), CLASS_NAME, "lowercase"
        )
        assert extra in result.columns

    def test_tracking_slot_preserved(self, cleaner):
        result = cleaner.clean_format_and_match_columns(
            self._df("sample_id", TrackingSlots.SOURCE_CLASS), CLASS_NAME, "lowercase"
        )
        assert TrackingSlots.SOURCE_CLASS in result.columns

    def test_duplicate_normalized_columns_keep_first(self, cleaner):
        # "Status" and "status" both lowercase to the schema column "status".
        df = pd.DataFrame({"Status": ["first"], "status": ["second"]})
        result = cleaner.clean_format_and_match_columns(df, CLASS_NAME, "lowercase")
        # No duplicate labels: exactly one "status" column.
        assert list(result.columns).count("status") == 1
        # The first matching column is the one that is kept.
        assert result["status"].iloc[0] == "first"

    def test_column_formatting_to_empty_string_dropped(self, cleaner):
        # "!!!" with remove_special becomes "" — it must be dropped, not crash.
        df = pd.DataFrame({"!!!": ["x"], "status": ["y"]})
        result = cleaner.clean_format_and_match_columns(
            df, CLASS_NAME, "remove_special"
        )
        assert "status" in result.columns
        assert "" not in result.columns

    def test_unrecognized_class_returns_df_unchanged(self, cleaner):
        df = self._df("status")
        result = cleaner.clean_format_and_match_columns(df, "NoSuchClass", "lowercase")
        assert result.equals(df)

    def test_unrecognized_option_raises(self, cleaner):
        with pytest.raises(
            ValueError, match="Unrecognized format_and_match_columns option"
        ):
            cleaner.clean_format_and_match_columns(
                self._df("status"), CLASS_NAME, "not_a_real_option"
            )

    def test_format_true_matches_case_insensitively(self, cleaner):
        # True → no formatting, just case-insensitive matching
        result = cleaner.clean_format_and_match_columns(
            self._df("Status"), CLASS_NAME, True
        )
        assert "status" in result.columns

    def test_multiple_ops_applied_in_order(self, cleaner):
        # "SAMPLE ID" → lowercase → "sample id" → alpha_numeric_underscore → "sample_id"
        result = cleaner.clean_format_and_match_columns(
            self._df("SAMPLE ID"), CLASS_NAME, ["lowercase", "alpha_numeric_underscore"]
        )
        assert "sample_id" in result.columns

    def test_original_df_not_modified(self, cleaner):
        df = self._df("status")
        original_cols = list(df.columns)
        cleaner.clean_format_and_match_columns(df, CLASS_NAME, "lowercase")
        assert list(df.columns) == original_cols

    def test_logs_column_name_change(self, cleaner):
        cleaner.clean_format_and_match_columns(
            self._df("STATUS"), CLASS_NAME, "lowercase"
        )
        assert Logs.COLUMN_NAME_CHANGE in cleaner.log_lines

    def test_logs_removed_unrecognized_column(self, cleaner):
        cleaner.clean_format_and_match_columns(
            self._df("xyz_bad"), CLASS_NAME, "lowercase"
        )
        assert Logs.COLUMN_REMOVED in cleaner.log_lines

    def test_logs_missing_columns(self, cleaner):
        # Only providing sample_id; others logged as missing
        cleaner.clean_format_and_match_columns(
            self._df("sample_id"), CLASS_NAME, "lowercase"
        )
        assert Logs.COLUMNS_MISSING in cleaner.log_lines

    def test_remove_chars_multiple_chars(self, cleaner):
        # Remove both "-" and "." from "s-t.a.t-u-s" → "status"
        result = cleaner.clean_format_and_match_columns(
            self._df("s-t.a.t-u-s"), CLASS_NAME, [{"remove_chars": "-."}]
        )
        assert "status" in result.columns


# ---------------------------------------------------------------------------
# TestCheckPatterns
# ---------------------------------------------------------------------------


class TestCheckPatterns:
    def test_matching_values_not_logged(self, cleaner):
        df = pd.DataFrame({"code": ["AB-1234", "ZZ-0000"]})
        cleaner.check_patterns(df, CLASS_NAME)
        assert Logs.MISMATCH_PATTERN not in cleaner.log_lines

    def test_non_matching_values_logged(self, cleaner):
        df = pd.DataFrame({"code": ["ab-1234", "ABCD"]})
        cleaner.check_patterns(df, CLASS_NAME)
        assert Logs.MISMATCH_PATTERN in cleaner.log_lines
        assert len(cleaner.log_lines[Logs.MISMATCH_PATTERN]) == 2

    def test_null_values_skipped(self, cleaner):
        df = pd.DataFrame({"code": [None, np.nan, "AB-1234"]})
        cleaner.check_patterns(df, CLASS_NAME)
        assert Logs.MISMATCH_PATTERN not in cleaner.log_lines

    def test_unrecognized_class_skips(self, cleaner):
        df = pd.DataFrame({"code": ["bad"]})
        cleaner.check_patterns(df, "NoSuchClass")
        assert Logs.MISMATCH_PATTERN not in cleaner.log_lines

    def test_slot_without_pattern_not_logged(self, cleaner):
        df = pd.DataFrame({"notes": ["anything! goes! here!"]})
        cleaner.check_patterns(df, CLASS_NAME)
        assert Logs.MISMATCH_PATTERN not in cleaner.log_lines

    def test_column_not_in_schema_skipped(self, cleaner):
        df = pd.DataFrame({"not_a_schema_col": ["bad_value"]})
        cleaner.check_patterns(df, CLASS_NAME)
        assert Logs.MISMATCH_PATTERN not in cleaner.log_lines

    def test_row_index_is_one_based(self, cleaner):
        df = pd.DataFrame({"code": ["AB-1234", "bad"]})
        cleaner.check_patterns(df, CLASS_NAME)
        entry = cleaner.log_lines[Logs.MISMATCH_PATTERN][0]
        assert entry[LogColumns.ROW] == 2

    def test_mixed_valid_invalid(self, cleaner):
        df = pd.DataFrame({"code": ["AB-1234", "bad", "ZZ-9999", "wrong"]})
        cleaner.check_patterns(df, CLASS_NAME)
        assert len(cleaner.log_lines[Logs.MISMATCH_PATTERN]) == 2

    def test_class_name_in_log_entry(self, cleaner):
        df = pd.DataFrame({"code": ["bad"]})
        cleaner.check_patterns(df, CLASS_NAME)
        entry = cleaner.log_lines[Logs.MISMATCH_PATTERN][0]
        assert entry[LogColumns.CLASS_NAME] == CLASS_NAME
        assert entry[LogColumns.SLOT_NAME] == "code"


# ---------------------------------------------------------------------------
# TestCorrectEnums  (via clean_single_data)
# ---------------------------------------------------------------------------


class TestCorrectEnums:
    def _run(self, cleaner, df, correct=True):
        _, result = cleaner.clean_single_data(
            data_file=None,
            data_frame=df,
            output_file=None,
            class_name=CLASS_NAME,
            clean_operations=[{"correct_enums": correct}],
        )
        return result

    def test_wrong_caps_corrected(self, cleaner):
        df = pd.DataFrame({"sample_id": ["s1"], "status": ["active"]})
        result = self._run(cleaner, df)
        assert result["status"].iloc[0] == "Active"

    def test_correct_values_unchanged(self, cleaner):
        df = pd.DataFrame({"sample_id": ["s1"], "status": ["Active"]})
        result = self._run(cleaner, df)
        assert result["status"].iloc[0] == "Active"

    def test_unknown_values_cleared(self, cleaner):
        df = pd.DataFrame({"sample_id": ["s1"], "status": ["UnknownValue"]})
        result = self._run(cleaner, df)
        assert result["status"].iloc[0] is None

    def test_multiple_spaces_normalized(self, cleaner):
        # "Pending  Review" (double space) → normalized → matches "Pending Review"
        df = pd.DataFrame({"sample_id": ["s1"], "status": ["Pending  Review"]})
        result = self._run(cleaner, df)
        assert result["status"].iloc[0] == "Pending Review"

    def test_non_enum_column_unchanged(self, cleaner):
        df = pd.DataFrame({"sample_id": ["s1"], "notes": ["some note"]})
        result = self._run(cleaner, df)
        assert result["notes"].iloc[0] == "some note"

    def test_correct_enums_false_raises(self, cleaner):
        # correct_enums: False doesn't match any branch and falls to the unrecognized-op check
        df = pd.DataFrame({"sample_id": ["s1"], "status": ["active"]})
        with pytest.raises(ValueError, match="Unrecognized clean operation"):
            self._run(cleaner, df, correct=False)

    def test_unknown_values_logged(self, cleaner):
        df = pd.DataFrame({"sample_id": ["s1"], "status": ["bogus"]})
        self._run(cleaner, df)
        assert Logs.UNKNOWN_ENUMS in cleaner.log_lines

    def test_multiple_rows(self, cleaner):
        df = pd.DataFrame(
            {
                "sample_id": ["s1", "s2", "s3"],
                "status": ["active", "INACTIVE", "Pending Review"],
            }
        )
        result = self._run(cleaner, df)
        assert result["status"].tolist() == ["Active", "Inactive", "Pending Review"]


# ---------------------------------------------------------------------------
# TestAddOntologyIds  (via clean_single_data)
# ---------------------------------------------------------------------------


class TestAddOntologyIds:
    def _run(self, cleaner, df, regex=ONTOLOGY_REGEX):
        _, result = cleaner.clean_single_data(
            data_file=None,
            data_frame=df,
            output_file=None,
            class_name=CLASS_NAME,
            clean_operations=[
                {"add_ontology_ids_to_enums": {"match_ontology_id": regex}}
            ],
        )
        return result

    def test_adds_ontology_id(self, cleaner):
        df = pd.DataFrame({"sample_id": ["s1"], "temperature": ["degree celsius (c)"]})
        result = self._run(cleaner, df)
        assert result["temperature"].iloc[0] == "degree Celsius (C) [UO:0000027]"

    def test_wrong_caps_in_data_still_adds_id(self, cleaner):
        df = pd.DataFrame({"sample_id": ["s1"], "temperature": ["Degree Celsius (C)"]})
        result = self._run(cleaner, df)
        assert result["temperature"].iloc[0] == "degree Celsius (C) [UO:0000027]"

    def test_value_without_ontology_id_in_schema_unchanged(self, cleaner):
        # "degree Fahrenheit (F)" has no [ID] in schema → stays as-is
        df = pd.DataFrame(
            {"sample_id": ["s1"], "temperature": ["degree fahrenheit (f)"]}
        )
        result = self._run(cleaner, df)
        assert result["temperature"].iloc[0] == "degree fahrenheit (f)"

    def test_value_already_has_id_unchanged(self, cleaner):
        df = pd.DataFrame(
            {"sample_id": ["s1"], "temperature": ["degree Celsius (C) [UO:0000027]"]}
        )
        result = self._run(cleaner, df)
        assert result["temperature"].iloc[0] == "degree Celsius (C) [UO:0000027]"

    def test_missing_match_ontology_id_raises(self, cleaner):
        df = pd.DataFrame({"sample_id": ["s1"]})
        with pytest.raises(ValueError, match="match_ontology_id"):
            cleaner.clean_single_data(
                data_file=None,
                data_frame=df,
                output_file=None,
                class_name=CLASS_NAME,
                clean_operations=[{"add_ontology_ids_to_enums": True}],
            )

    def test_non_dict_params_raises(self, cleaner):
        df = pd.DataFrame({"sample_id": ["s1"]})
        with pytest.raises(ValueError, match="match_ontology_id"):
            cleaner.clean_single_data(
                data_file=None,
                data_frame=df,
                output_file=None,
                class_name=CLASS_NAME,
                clean_operations=[{"add_ontology_ids_to_enums": "bad"}],
            )

    def test_non_enum_column_unchanged(self, cleaner):
        df = pd.DataFrame({"sample_id": ["s1"], "notes": ["some text"]})
        result = self._run(cleaner, df)
        assert result["notes"].iloc[0] == "some text"


# ---------------------------------------------------------------------------
# TestCleanSingleData
# ---------------------------------------------------------------------------


class TestCleanSingleData:
    def test_same_input_output_raises(self, cleaner, tmp_path):
        same = str(tmp_path / "data.csv")
        with pytest.raises(ValueError):
            cleaner.clean_single_data(
                data_file=same,
                data_frame=None,
                output_file=same,
                class_name=CLASS_NAME,
                clean_operations=[],
            )

    def test_empty_operations_returns_df_unchanged(self, cleaner):
        df = pd.DataFrame({"sample_id": ["s1"], "status": ["Active"]})
        _, result = cleaner.clean_single_data(
            data_file=None,
            data_frame=df,
            output_file=None,
            class_name=CLASS_NAME,
            clean_operations=[],
        )
        assert result.equals(df)

    def test_empty_dict_in_operations_skipped(self, cleaner):
        df = pd.DataFrame({"sample_id": ["s1"], "status": ["Active"]})
        _, result = cleaner.clean_single_data(
            data_file=None,
            data_frame=df,
            output_file=None,
            class_name=CLASS_NAME,
            clean_operations=[{}],
        )
        assert result.equals(df)

    def test_unrecognized_operation_raises(self, cleaner):
        df = pd.DataFrame({"sample_id": ["s1"]})
        with pytest.raises(ValueError, match="Unrecognized clean operation"):
            cleaner.clean_single_data(
                data_file=None,
                data_frame=df,
                output_file=None,
                class_name=CLASS_NAME,
                clean_operations=[{"not_a_real_op": True}],
            )

    def test_multiple_keys_in_one_op_dict_raises(self, cleaner):
        df = pd.DataFrame({"sample_id": ["s1"]})
        with pytest.raises(ValueError, match="single dictionary key"):
            cleaner.clean_single_data(
                data_file=None,
                data_frame=df,
                output_file=None,
                class_name=CLASS_NAME,
                clean_operations=[{"correct_enums": True, "check_patterns": True}],
            )

    def test_check_patterns_logs_mismatches(self, cleaner):
        df = pd.DataFrame({"code": ["bad_value"]})
        cleaner.clean_single_data(
            data_file=None,
            data_frame=df,
            output_file=None,
            class_name=CLASS_NAME,
            clean_operations=[{"check_patterns": True}],
        )
        assert Logs.MISMATCH_PATTERN in cleaner.log_lines

    def test_operations_applied_in_order(self, cleaner):
        # format columns first (lowercase), then correct enum values
        df = pd.DataFrame({"SAMPLE_ID": ["s1"], "STATUS": ["active"]})
        _, result = cleaner.clean_single_data(
            data_file=None,
            data_frame=df,
            output_file=None,
            class_name=CLASS_NAME,
            clean_operations=[
                {"format_and_match_columns": "lowercase"},
                {"correct_enums": True},
            ],
        )
        assert "status" in result.columns
        assert result["status"].iloc[0] == "Active"

    def test_format_and_match_columns_false_skipped(self, cleaner):
        # format_and_match_columns: False → operation not run, column names unchanged
        df = pd.DataFrame({"STATUS": ["Active"]})
        _, result = cleaner.clean_single_data(
            data_file=None,
            data_frame=df,
            output_file=None,
            class_name=CLASS_NAME,
            clean_operations=[{"format_and_match_columns": False}],
        )
        assert "STATUS" in result.columns


# ---------------------------------------------------------------------------
# TestCleanData  (top-level orchestrator)
# ---------------------------------------------------------------------------


class TestCleanData:
    def test_basic_dataframes_cleaned(self, cleaner):
        df = pd.DataFrame({"sample_id": ["s1"], "status": ["active"]})
        _out_files, out_frames = cleaner.clean_data(
            data_files=None,
            data_frames={CLASS_NAME: [df]},
            output_dir=None,
            log_file=None,
            clean_operations=[{"correct_enums": True}],
        )
        assert CLASS_NAME in out_frames
        result = out_frames[CLASS_NAME][0]
        assert result["status"].iloc[0] == "Active"

    def test_multiple_dataframes_for_same_class(self, cleaner):
        df1 = pd.DataFrame({"sample_id": ["s1"], "status": ["active"]})
        df2 = pd.DataFrame({"sample_id": ["s2"], "status": ["inactive"]})
        _, out_frames = cleaner.clean_data(
            data_files=None,
            data_frames={CLASS_NAME: [df1, df2]},
            output_dir=None,
            log_file=None,
            clean_operations=[{"correct_enums": True}],
        )
        assert out_frames[CLASS_NAME][0]["status"].iloc[0] == "Active"
        assert out_frames[CLASS_NAME][1]["status"].iloc[0] == "Inactive"

    def test_saves_cleaned_file(self, cleaner, tmp_path):
        df = pd.DataFrame({"sample_id": ["s1"], "status": ["active"]})
        out_dir = tmp_path / "cleaned"
        _, _out_frames = cleaner.clean_data(
            data_files=None,
            data_frames={CLASS_NAME: [df]},
            output_dir=str(out_dir),
            log_file=None,
            clean_operations=[{"correct_enums": True}],
        )
        assert (out_dir / f"{CLASS_NAME}.csv").exists()

    def test_logs_reset_after_clean_data(self, cleaner):
        df = pd.DataFrame({"sample_id": ["s1"], "status": ["bogus"]})
        cleaner.clean_data(
            data_files=None,
            data_frames={CLASS_NAME: [df]},
            output_dir=None,
            log_file=None,
            clean_operations=[{"correct_enums": True}],
        )
        # save_logs() is called at end of clean_data, which resets log_lines
        assert cleaner.log_lines == {}
