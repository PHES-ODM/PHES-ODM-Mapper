"""Tests for odm_map.prepare_wide_to_long.wide_column_expander"""

import pytest
import pandas as pd
from unittest.mock import MagicMock

from odm_map.utils.extra_and_tracking_slots import make_tracking_slot_name
from odm_map.prepare_wide_to_long.wide_column_expander import (
    ColumnType,
    SeeHeaders,
    WideColumnExpander,
)
from odm_map.prepare_wide_to_long.wide_column_utils import ConfigKeys


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config():
    return {
        ConfigKeys.TABLES_TO_SHORTNAMES: {
            "measures": "mr",
            "samples": "sm",
            "sites": "si",
            "protocolSteps": "ps",
        },
        ConfigKeys.PARTID_TO_MMASET: {
            "covN1": "covN1Set",
            "ph": "phSet",
        },
        ConfigKeys.SEE_HEADERS: {
            "aggregation": {
                "short_name": "hAg",
                "slot": "mr_aggregation",
            },
            "unit": {
                "short_name": "hUn",
                "slot": "mr_unit",
            },
            "measure": {
                "short_name": "hMe",
                "slot": "mr_measure",
            },
            "compartment": {
                "short_name": "hCo",
                "slot": "mr_compartment",
            },
        },
    }


@pytest.fixture
def expander(config):
    """WideColumnExpander with a mock schema assigned after construction."""
    exp = WideColumnExpander(
        config=config,
        source_class_name="odm_wide",
        target_schema=None,
    )
    mock_schema = MagicMock()
    mock_slot = MagicMock()
    mock_slot.name = "sampleID"
    mock_schema.induced_slot.return_value = mock_slot
    exp.target_schema = mock_schema
    return exp


@pytest.fixture
def expander_no_schema(config):
    """WideColumnExpander with no schema (for methods that don't use the schema)."""
    return WideColumnExpander(
        config=config,
        source_class_name="odm_wide",
        target_schema=None,
    )


# ---------------------------------------------------------------------------
# is_part_equal_at_index
# ---------------------------------------------------------------------------


class TestIsPartEqualAtIndex:
    def test_single_string_match(self, expander_no_schema):
        col_parts = [["sm"], ["sampleID"]]
        assert expander_no_schema.is_part_equal_at_index(col_parts, "sm", 0) is True

    def test_single_string_no_match(self, expander_no_schema):
        col_parts = [["sm"], ["sampleID"]]
        assert expander_no_schema.is_part_equal_at_index(col_parts, "mr", 0) is False

    def test_list_match(self, expander_no_schema):
        col_parts = [["2", "AND", "a", "b"]]
        assert (
            expander_no_schema.is_part_equal_at_index(
                col_parts, ["2", "AND", "a", "b"], 0
            )
            is True
        )

    def test_list_no_match_different_length(self, expander_no_schema):
        col_parts = [["2", "AND", "a"]]
        assert (
            expander_no_schema.is_part_equal_at_index(
                col_parts, ["2", "AND", "a", "b"], 0
            )
            is False
        )

    def test_second_index(self, expander_no_schema):
        col_parts = [["ps"], ["mes"]]
        assert expander_no_schema.is_part_equal_at_index(col_parts, "mes", 1) is True

    def test_string_converted_to_list_internally(self, expander_no_schema):
        col_parts = [["ps"]]
        assert expander_no_schema.is_part_equal_at_index(col_parts, "ps", 0) is True


# ---------------------------------------------------------------------------
# get_all_parts / get_next_part
# ---------------------------------------------------------------------------


class TestGetAllParts:
    def test_simple_attribute_two_parts(self, expander_no_schema):
        parts = expander_no_schema.get_all_parts("sm_sampleID")
        assert parts == [["sm"], ["sampleID"]]

    def test_measure_column_eight_parts(self, expander_no_schema):
        parts = expander_no_schema.get_all_parts("wat_sa_liq_covN1_gch_me_1_value")
        assert len(parts) == 8
        assert parts[0] == ["wat"]
        assert parts[3] == ["covN1"]
        assert parts[7] == ["value"]

    def test_protocol_steps_measure_seven_parts(self, expander_no_schema):
        parts = expander_no_schema.get_all_parts("ps_mes_covN1_gch_me_1_value")
        assert len(parts) == 7
        assert parts[0] == ["ps"]
        assert parts[1] == ["mes"]

    def test_protocol_steps_method_four_parts(self, expander_no_schema):
        parts = expander_no_schema.get_all_parts("ps_met_someMethod_value")
        assert len(parts) == 4
        assert parts[0] == ["ps"]
        assert parts[1] == ["met"]

    def test_and_aggregation_expands_correctly(self, expander_no_schema):
        # sm_2_AND_collPer_collNum → [["sm"], ["2", "AND", "collPer", "collNum"]]
        parts = expander_no_schema.get_all_parts("sm_2_AND_collPer_collNum")
        assert len(parts) == 2
        assert parts[0] == ["sm"]
        assert parts[1][0] == "2"
        assert parts[1][1] == "AND"
        assert "collPer" in parts[1]
        assert "collNum" in parts[1]

    def test_group_flag_stripped_before_parsing(self, expander_no_schema):
        parts = expander_no_schema.get_all_parts("sm_sampleID.g5")
        assert parts == [["sm"], ["sampleID"]]

    def test_digit_index_part(self, expander_no_schema):
        parts = expander_no_schema.get_all_parts("wat_sa_liq_covN1_gch_me_1_value")
        assert parts[6] == ["1"]

    def test_digit_as_last_part_single_element(self, expander_no_schema):
        parts = expander_no_schema.get_all_parts("a_b_3")
        assert parts[2] == ["3"]

    def test_or_aggregation_expands_correctly(self, expander_no_schema):
        # ps_mes_2_OR_covN1_ph_gch_me_1_value (OR tag)
        parts = expander_no_schema.get_all_parts("ps_mes_2_OR_covN1_ph_gch_me_1_value")
        # The "2_OR_covN1_ph" forms the third part
        assert parts[2][1] == "OR"
        assert "covN1" in parts[2]
        assert "ph" in parts[2]


# ---------------------------------------------------------------------------
# get_table_long_name / get_table_short_name
# ---------------------------------------------------------------------------


class TestGetTableNames:
    def test_long_name_from_short_mr(self, expander_no_schema):
        assert expander_no_schema.get_table_long_name("mr") == "measures"

    def test_long_name_from_short_sm(self, expander_no_schema):
        assert expander_no_schema.get_table_long_name("sm") == "samples"

    def test_long_name_unknown_returns_none(self, expander_no_schema):
        assert expander_no_schema.get_table_long_name("zz") is None

    def test_short_name_from_long_measures(self, expander_no_schema):
        assert expander_no_schema.get_table_short_name("measures") == "mr"

    def test_short_name_from_long_samples(self, expander_no_schema):
        assert expander_no_schema.get_table_short_name("samples") == "sm"

    def test_short_name_unknown_returns_none(self, expander_no_schema):
        assert expander_no_schema.get_table_short_name("nonexistent") is None

    def test_protocol_steps_table(self, expander_no_schema):
        assert expander_no_schema.get_table_long_name("ps") == "protocolSteps"
        assert expander_no_schema.get_table_short_name("protocolSteps") == "ps"


# ---------------------------------------------------------------------------
# get_and_values
# ---------------------------------------------------------------------------


class TestGetAndValues:
    def test_none_returns_list_of_nones(self, expander_no_schema):
        result = expander_no_schema.get_and_values(None, 3)
        assert result == [None, None, None]

    def test_num_values_one_returns_val_as_list(self, expander_no_schema):
        result = expander_no_schema.get_and_values("hello", 1)
        assert result == ["hello"]

    def test_num_values_zero_returns_empty(self, expander_no_schema):
        result = expander_no_schema.get_and_values("hello", 0)
        assert result == []

    def test_splits_by_dot(self, expander_no_schema):
        result = expander_no_schema.get_and_values("24.12", 2)
        assert result == ["24", "12"]

    def test_truncates_extra_values(self, expander_no_schema):
        result = expander_no_schema.get_and_values("1.2.3", 2)
        assert result == ["1", "2"]

    def test_pads_missing_values_with_none(self, expander_no_schema):
        result = expander_no_schema.get_and_values("1", 3)
        assert len(result) == 3
        assert result[0] == "1"
        assert result[1] is None
        assert result[2] is None

    def test_none_returns_correct_count(self, expander_no_schema):
        result = expander_no_schema.get_and_values(None, 5)
        assert len(result) == 5
        assert all(v is None for v in result)


# ---------------------------------------------------------------------------
# get_column_type
# ---------------------------------------------------------------------------


class TestGetColumnType:
    def test_tracking_slot(self, expander_no_schema):
        tracking_col = make_tracking_slot_name("source_class")
        assert (
            expander_no_schema.get_column_type(tracking_col) == ColumnType.TRACKING_SLOT
        )

    def test_attribute_column(self, expander_no_schema):
        assert expander_no_schema.get_column_type("sm_sampleID") == ColumnType.ATTRIBUTE

    def test_sites_attribute(self, expander_no_schema):
        assert expander_no_schema.get_column_type("si_siteID") == ColumnType.ATTRIBUTE

    def test_measure_column_eight_parts(self, expander_no_schema):
        col = "wat_sa_liq_covN1_gch_me_1_value"
        assert expander_no_schema.get_column_type(col) == ColumnType.MEASURE

    def test_protocol_step_measure_seven_parts(self, expander_no_schema):
        col = "ps_mes_covN1_gch_me_1_value"
        assert (
            expander_no_schema.get_column_type(col) == ColumnType.PROTOCOL_STEP_MEASURE
        )

    def test_protocol_step_method_four_parts(self, expander_no_schema):
        col = "ps_met_someMethod_value"
        assert (
            expander_no_schema.get_column_type(col) == ColumnType.PROTOCOL_STEP_METHOD
        )

    def test_ps_mes_wrong_part_count_returns_none(self, expander_no_schema):
        col = "ps_mes_covN1_gch"  # 4 parts instead of 7
        assert expander_no_schema.get_column_type(col) is None

    def test_ps_met_wrong_part_count_returns_none(self, expander_no_schema):
        col = "ps_met_someMethod_extra_extra"  # 5 parts instead of 4
        assert expander_no_schema.get_column_type(col) is None

    def test_unrecognized_three_parts_returns_none(self, expander_no_schema):
        col = "abc_def_ghi"  # 3 parts, unknown short name
        assert expander_no_schema.get_column_type(col) is None

    def test_attribute_column_with_group_flag(self, expander_no_schema):
        col = "sm_sampleID.g5"
        assert expander_no_schema.get_column_type(col) == ColumnType.ATTRIBUTE


# ---------------------------------------------------------------------------
# get_duplicate_columns
# ---------------------------------------------------------------------------


class TestGetDuplicateColumns:
    def test_no_duplicates_returns_empty(self, expander_no_schema):
        df = pd.DataFrame({"col_a": [1], "col_b": [2]})
        result = expander_no_schema.get_duplicate_columns(df)
        assert result == {}

    def test_finds_dot_integer_duplicate(self, expander_no_schema):
        df = pd.DataFrame({"col_a": [1], "col_a.1": [2]})
        result = expander_no_schema.get_duplicate_columns(df)
        assert "col_a" in result
        assert "col_a.1" in result["col_a"]

    def test_groups_multiple_duplicates(self, expander_no_schema):
        df = pd.DataFrame({"col_a": [1], "col_a.1": [2], "col_a.2": [3]})
        result = expander_no_schema.get_duplicate_columns(df)
        assert len(result["col_a"]) >= 2

    def test_non_integer_suffix_not_a_duplicate(self, expander_no_schema):
        df = pd.DataFrame({"col_a": [1], "col_a.foo": [2]})
        result = expander_no_schema.get_duplicate_columns(df)
        assert "col_a" not in result

    def test_base_column_included_in_list(self, expander_no_schema):
        df = pd.DataFrame({"col_a": [1], "col_a.1": [2]})
        result = expander_no_schema.get_duplicate_columns(df)
        assert "col_a" in result["col_a"]


# ---------------------------------------------------------------------------
# merge_duplicate_columns
# ---------------------------------------------------------------------------


class TestMergeDuplicateColumns:
    def test_no_duplicates_returns_identical(self, expander_no_schema):
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        result = expander_no_schema.merge_duplicate_columns(df)
        assert list(result.columns) == ["a", "b"]

    def test_merges_taking_first_non_empty(self, expander_no_schema):
        df = pd.DataFrame({"a": ["val", None], "a.1": [None, "val2"]})
        result = expander_no_schema.merge_duplicate_columns(df)
        assert "a" in result.columns
        assert "a.1" not in result.columns
        assert result["a"].iloc[0] == "val"
        assert result["a"].iloc[1] == "val2"

    def test_drops_duplicate_suffix_column(self, expander_no_schema):
        df = pd.DataFrame({"x": [1], "x.1": [None]})
        result = expander_no_schema.merge_duplicate_columns(df)
        assert "x.1" not in result.columns
        assert "x" in result.columns

    def test_preserves_other_columns(self, expander_no_schema):
        df = pd.DataFrame({"a": [1], "a.1": [2], "b": [3]})
        result = expander_no_schema.merge_duplicate_columns(df)
        assert "b" in result.columns


# ---------------------------------------------------------------------------
# get_first_group_number
# ---------------------------------------------------------------------------


class TestGetFirstGroupNumber:
    def test_no_groups_returns_zero(self, expander_no_schema):
        df = pd.DataFrame({"sm_sampleID": [1]})
        result = expander_no_schema.get_first_group_number(df)
        assert result == 0

    def test_returns_max_group_plus_one(self, expander_no_schema):
        df = pd.DataFrame({"sm_sampleID.g3": [1], "mr_measure.g5": [2]})
        result = expander_no_schema.get_first_group_number(df)
        assert result == 6  # max(3, 5) + 1

    def test_single_group(self, expander_no_schema):
        df = pd.DataFrame({"mr_value.g10": [1]})
        result = expander_no_schema.get_first_group_number(df)
        assert result == 11

    def test_no_numeric_groups_returns_zero(self, expander_no_schema):
        # Non-numeric group suffixes should be ignored
        df = pd.DataFrame({"mr_value": [1]})
        result = expander_no_schema.get_first_group_number(df)
        assert result == 0


# ---------------------------------------------------------------------------
# new_current_expanded_rows / update_current_expanded_rows / save
# ---------------------------------------------------------------------------


class TestCurrentExpandedRows:
    def test_new_initializes_none_key(self, expander_no_schema):
        expander_no_schema.new_current_expanded_rows()
        assert None in expander_no_schema.current_expanded_rows

    def test_update_adds_column_without_group(self, expander_no_schema):
        expander_no_schema.new_current_expanded_rows()
        expander_no_schema.update_current_expanded_rows(
            {"sm_sampleID": "S001"},
            row_index=None,
            column_flags=None,
            column_group=None,
        )
        assert expander_no_schema.current_expanded_rows[None]["sm_sampleID"] == "S001"

    def test_update_with_group_appends_flag(self, expander_no_schema):
        expander_no_schema.new_current_expanded_rows()
        expander_no_schema.update_current_expanded_rows(
            {"mr_measure": "covN1"},
            row_index=None,
            column_flags=None,
            column_group="g1",
        )
        current = expander_no_schema.current_expanded_rows[None]
        assert "mr_measure.g1" in current
        assert current["mr_measure.g1"] == "covN1"

    def test_update_with_flags_appends_flags(self, expander_no_schema):
        expander_no_schema.new_current_expanded_rows()
        expander_no_schema.update_current_expanded_rows(
            {"mr_measure": "covN1"},
            row_index=None,
            column_flags=["l5"],
            column_group="g1",
        )
        current = expander_no_schema.current_expanded_rows[None]
        # Should have both group and link flags
        assert any("l5" in k for k in current.keys())

    def test_save_appends_to_all_rows(self, expander_no_schema):
        expander_no_schema.all_expanded_rows = []
        expander_no_schema.new_current_expanded_rows()
        expander_no_schema.update_current_expanded_rows(
            {"sm_sampleID": "S001"},
            row_index=None,
            column_flags=None,
            column_group=None,
        )
        expander_no_schema.save_current_expanded_rows()
        assert len(expander_no_schema.all_expanded_rows) == 1
        assert expander_no_schema.all_expanded_rows[0]["sm_sampleID"] == "S001"

    def test_multiple_saves_accumulate(self, expander_no_schema):
        expander_no_schema.all_expanded_rows = []
        for i in range(3):
            expander_no_schema.new_current_expanded_rows()
            expander_no_schema.update_current_expanded_rows(
                {"idx": i}, row_index=None, column_flags=None, column_group=None
            )
            expander_no_schema.save_current_expanded_rows()
        assert len(expander_no_schema.all_expanded_rows) == 3

    def test_update_new_row_index_creates_entry(self, expander_no_schema):
        expander_no_schema.new_current_expanded_rows()
        expander_no_schema.update_current_expanded_rows(
            {"col": "val"}, row_index=1, column_flags=None, column_group=None
        )
        assert 1 in expander_no_schema.current_expanded_rows


# ---------------------------------------------------------------------------
# get_expanded_config
# ---------------------------------------------------------------------------


class TestGetExpandedConfig:
    def test_returns_dict_with_both_keys(self, expander_no_schema):
        expander_no_schema.explicit_groups = ["g1", "g2"]
        expander_no_schema.implicit_groups = ["g3"]
        result = expander_no_schema.get_expanded_config()
        assert "explicit_groups" in result
        assert "implicit_groups" in result

    def test_explicit_groups_value(self, expander_no_schema):
        expander_no_schema.explicit_groups = ["g1"]
        expander_no_schema.implicit_groups = []
        result = expander_no_schema.get_expanded_config()
        assert result["explicit_groups"] == ["g1"]

    def test_implicit_groups_value(self, expander_no_schema):
        expander_no_schema.explicit_groups = []
        expander_no_schema.implicit_groups = ["g5"]
        result = expander_no_schema.get_expanded_config()
        assert result["implicit_groups"] == ["g5"]


# ---------------------------------------------------------------------------
# get_resolved_single_part_at_index
# ---------------------------------------------------------------------------


class TestGetResolvedSinglePartAtIndex:
    def test_returns_simple_value(self, expander_no_schema):
        col_parts = [["wat"], ["sa"]]
        row = pd.Series({"dummy": "x"})
        val = expander_no_schema.get_resolved_single_part_at_index(
            col_parts, 0, row, allowable_see_headers=None, column_group=None
        )
        assert val == "wat"

    def test_see_header_resolves_from_row(self, expander_no_schema):
        col_parts = [["hAg"]]
        row = pd.Series({"mr_aggregation": "mean"})
        val = expander_no_schema.get_resolved_single_part_at_index(
            col_parts,
            0,
            row,
            allowable_see_headers=SeeHeaders.AGGREGATION,
            column_group=None,
        )
        assert val == "mean"

    def test_see_header_not_in_allowable_returns_unchanged(self, expander_no_schema):
        col_parts = [["hAg"]]
        row = pd.Series({"mr_aggregation": "mean"})
        val = expander_no_schema.get_resolved_single_part_at_index(
            col_parts,
            0,
            row,
            allowable_see_headers=SeeHeaders.UNIT,  # "hAg" not in unit headers
            column_group=None,
        )
        assert val == "hAg"

    def test_see_header_with_group_prefers_grouped_column(self, expander_no_schema):
        col_parts = [["hAg"]]
        row = pd.Series(
            {
                "mr_aggregation": "global_mean",
                "mr_aggregation.g1": "group_mean",
            }
        )
        val = expander_no_schema.get_resolved_single_part_at_index(
            col_parts,
            0,
            row,
            allowable_see_headers=SeeHeaders.AGGREGATION,
            column_group="g1",
        )
        assert val == "group_mean"


# ---------------------------------------------------------------------------
# select_measure_or_method_for_value
# ---------------------------------------------------------------------------


def _make_expander_with_mock_schema(config, mock_schema):
    """Create a WideColumnExpander and inject a mock schema after construction."""
    exp = WideColumnExpander(
        config=config, source_class_name="odm_wide", target_schema=None
    )
    exp.target_schema = mock_schema
    return exp


class TestSelectMeasureOrMethodForValue:
    def test_returns_matching_partid(self, config):
        mock_schema = MagicMock()
        mock_enum = MagicMock()
        mock_enum.permissible_values = {"N1_gene": True, "covN1": True}
        mock_schema.get_enum.return_value = mock_enum

        exp = _make_expander_with_mock_schema(config, mock_schema)
        result = exp.select_measure_or_method_for_value("N1_gene", ["covN1", "ph"])
        assert result == "covN1"

    def test_returns_none_if_no_match(self, config):
        mock_schema = MagicMock()
        mock_enum = MagicMock()
        mock_enum.permissible_values = {"someOtherValue": True}
        mock_schema.get_enum.return_value = mock_enum

        exp = _make_expander_with_mock_schema(config, mock_schema)
        result = exp.select_measure_or_method_for_value("unknown_value", ["covN1"])
        assert result is None

    def test_skips_unknown_partid(self, config):
        mock_schema = MagicMock()
        exp = _make_expander_with_mock_schema(config, mock_schema)
        # "unknownPart" is not in PARTID_TO_MMASET → candidate_set is None → skip
        result = exp.select_measure_or_method_for_value("something", ["unknownPart"])
        assert result is None

    def test_checks_candidates_in_order(self, config):
        mock_schema = MagicMock()

        def get_enum_side_effect(name):
            m = MagicMock()
            if name == "covN1Set":
                m.permissible_values = {}
            elif name == "phSet":
                m.permissible_values = {"ph_value": True}
            return m

        mock_schema.get_enum.side_effect = get_enum_side_effect
        exp = _make_expander_with_mock_schema(config, mock_schema)
        result = exp.select_measure_or_method_for_value("ph_value", ["covN1", "ph"])
        assert result == "ph"


# ---------------------------------------------------------------------------
# expand_column_type_attribute
# ---------------------------------------------------------------------------


class TestExpandColumnTypeAttribute:
    def test_basic_expansion(self, expander):
        row = pd.Series({"sm_sampleID": "S001"})
        expander.new_current_expanded_rows()
        result = expander.expand_column_type_attribute(
            col="sm_sampleID",
            row=row,
            column_flags=None,
            column_group=None,
            always_use_group=False,
        )
        assert result is True
        current = expander.current_expanded_rows[None]
        assert "sm_sampleID" in current
        assert current["sm_sampleID"] == "S001"

    def test_group_applied_when_always_use_group(self, expander):
        row = pd.Series({"sm_sampleID": "S001"})
        expander.new_current_expanded_rows()
        result = expander.expand_column_type_attribute(
            col="sm_sampleID",
            row=row,
            column_flags=None,
            column_group="g2",
            always_use_group=True,
        )
        assert result is True
        current = expander.current_expanded_rows[None]
        assert "sm_sampleID.g2" in current

    def test_group_not_applied_when_always_use_group_false(self, expander):
        row = pd.Series({"sm_sampleID": "S001"})
        expander.new_current_expanded_rows()
        result = expander.expand_column_type_attribute(
            col="sm_sampleID",
            row=row,
            column_flags=None,
            column_group="g2",
            always_use_group=False,
        )
        assert result is True
        current = expander.current_expanded_rows[None]
        assert "sm_sampleID" in current
        assert "sm_sampleID.g2" not in current

    def test_unknown_table_returns_false(self, expander):
        row = pd.Series({"zz_col": "val"})
        expander.new_current_expanded_rows()
        result = expander.expand_column_type_attribute(
            col="zz_col",
            row=row,
            column_flags=None,
            column_group=None,
            always_use_group=False,
        )
        assert result is False

    def test_unknown_slot_returns_false_and_skips_column(self, expander):
        # induced_slot returns None when the slot does not exist in the target schema.
        expander.target_schema.induced_slot.return_value = None
        row = pd.Series({"sm_notaslot": "val"})
        expander.new_current_expanded_rows()
        result = expander.expand_column_type_attribute(
            col="sm_notaslot",
            row=row,
            column_flags=None,
            column_group=None,
            always_use_group=False,
        )
        assert result is False
        # The bogus column must not be added to the expanded rows.
        assert "sm_notaslot" not in expander.current_expanded_rows[None]

    def test_unknown_slot_when_induced_slot_raises(self, expander):
        # induced_slot raising is treated the same as a missing slot.
        expander.target_schema.induced_slot.side_effect = ValueError("no such slot")
        row = pd.Series({"sm_notaslot": "val"})
        expander.new_current_expanded_rows()
        result = expander.expand_column_type_attribute(
            col="sm_notaslot",
            row=row,
            column_flags=None,
            column_group=None,
            always_use_group=False,
        )
        assert result is False
        assert "sm_notaslot" not in expander.current_expanded_rows[None]

    def test_and_column_expansion(self, expander):
        row = pd.Series({"sm_2_AND_collPer_collNum": "A.B"})
        expander.new_current_expanded_rows()
        result = expander.expand_column_type_attribute(
            col="sm_2_AND_collPer_collNum",
            row=row,
            column_flags=None,
            column_group=None,
            always_use_group=False,
        )
        assert result is True
        current = expander.current_expanded_rows[None]
        assert "sm_collPer" in current
        assert "sm_collNum" in current
        assert current["sm_collPer"] == "A"
        assert current["sm_collNum"] == "B"


# ---------------------------------------------------------------------------
# expand_column_type_measure
# ---------------------------------------------------------------------------


class TestExpandColumnTypeMeasure:
    def test_basic_measure_expansion(self, expander):
        row = pd.Series({"wat_sa_liq_covN1_gch_me_1_value": 100})
        expander.new_current_expanded_rows()
        result = expander.expand_column_type_measure(
            col="wat_sa_liq_covN1_gch_me_1_value",
            row=row,
            column_flags=None,
            column_group="g1",
            always_use_group=True,
        )
        assert result is True
        current = expander.current_expanded_rows[None]
        assert "mr_compartment.g1" in current
        assert current["mr_compartment.g1"] == "wat"
        assert current["mr_specimen.g1"] == "sa"
        assert current["mr_fraction.g1"] == "liq"
        assert current["mr_measure.g1"] == "covN1"
        assert current["mr_unit.g1"] == "gch"
        assert current["mr_aggregation.g1"] == "me"
        assert current["mr_index.g1"] == "1"
        assert current["mr_value.g1"] == 100

    def test_measure_value_captured(self, expander):
        row = pd.Series({"wat_sa_liq_covN1_gch_me_1_value": 42.5})
        expander.new_current_expanded_rows()
        expander.expand_column_type_measure(
            col="wat_sa_liq_covN1_gch_me_1_value",
            row=row,
            column_flags=None,
            column_group="g1",
            always_use_group=True,
        )
        current = expander.current_expanded_rows[None]
        assert current["mr_value.g1"] == 42.5


# ---------------------------------------------------------------------------
# expand_column_type_tracking
# ---------------------------------------------------------------------------


class TestExpandColumnTypeTracking:
    def test_copies_tracking_column_to_all_rows(self, expander_no_schema):
        tracking_col = make_tracking_slot_name("source_row")
        expander_no_schema.new_current_expanded_rows()
        # Add a second row index entry
        expander_no_schema.current_expanded_rows[1] = {}

        row = pd.Series({tracking_col: "file.csv/0"})
        result = expander_no_schema.expand_column_type_tracking(
            col=tracking_col, row=row
        )

        assert result is True
        assert (
            expander_no_schema.current_expanded_rows[None][tracking_col] == "file.csv/0"
        )
        assert expander_no_schema.current_expanded_rows[1][tracking_col] == "file.csv/0"


# ---------------------------------------------------------------------------
# expand_single (integration-level)
# ---------------------------------------------------------------------------


class TestExpandSingle:
    def test_attribute_column_produces_output(self, expander):
        df = pd.DataFrame({"sm_sampleID": ["S001", "S002"]})
        result = expander.expand_single(df)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2
        assert "sm_sampleID" in result.columns

    def test_measure_column_expands_to_multiple_cols(self, expander):
        df = pd.DataFrame({"wat_sa_liq_covN1_gch_me_1_value": [100, 200]})
        result = expander.expand_single(df)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2
        assert any("mr_compartment" in c for c in result.columns)
        assert any("mr_value" in c for c in result.columns)

    def test_tracking_slot_preserved(self, expander):
        tracking_col = make_tracking_slot_name("source_row")
        df = pd.DataFrame(
            {
                "sm_sampleID": ["S001"],
                tracking_col: ["file.csv/0"],
            }
        )
        result = expander.expand_single(df)
        assert tracking_col in result.columns
        assert result[tracking_col].iloc[0] == "file.csv/0"

    def test_explicit_groups_tracked(self, expander):
        df = pd.DataFrame({"sm_sampleID.g5": ["S001"]})
        expander.expand_single(df)
        assert "g5" in expander.explicit_groups

    def test_implicit_groups_tracked(self, expander):
        df = pd.DataFrame({"sm_sampleID": ["S001"]})
        expander.expand_single(df)
        assert len(expander.implicit_groups) > 0
