"""Tests for odm_map.prepare_wide_to_long.wide_column_utils"""

from odm_map.utils.extra_and_tracking_slots import EXTRA_SLOT_PREFIX
from odm_map.prepare_wide_to_long.wide_column_utils import (
    AND_VALUE_SEPARATOR,
    ConfigKeys,
    FlagPrefixes,
    MeasureTableColumns,
    ProtocolStepsTableColumns,
    RECOGNIZED_FLAG_PREFIXES,
    WideColumnValues,
    column_and_flags_of_column,
    column_and_groups_of_column,
    column_with_flags,
    column_without_flags,
    get_column_flags,
    get_extra_slot_for_flag_prefix,
    get_flag_prefix,
    groups_of_column,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConfigKeys:
    def test_tables_to_shortnames(self):
        assert ConfigKeys.TABLES_TO_SHORTNAMES == "tables_to_shortnames"

    def test_partid_to_mmaset(self):
        assert ConfigKeys.PARTID_TO_MMASET == "partid_to_mmaset"

    def test_see_headers(self):
        assert ConfigKeys.SEE_HEADERS == "see_headers"

    def test_custom_id_code(self):
        assert ConfigKeys.CUSTOM_ID_CODE == "custom_id_code"

    def test_see_headers_short_name(self):
        assert ConfigKeys.SEE_HEADERS_SHORT_NAME == "short_name"

    def test_see_headers_slot(self):
        assert ConfigKeys.SEE_HEADERS_SLOT == "slot"


class TestWideColumnValues:
    def test_column_part_separator(self):
        assert WideColumnValues.COLUMN_PART_SEPARATOR == "_"

    def test_measure_tag(self):
        assert WideColumnValues.COLUMN_MEASURE_TAG == "mes"

    def test_method_tag(self):
        assert WideColumnValues.COLUMN_METHOD_TAG == "met"

    def test_protocol_steps_tag(self):
        assert WideColumnValues.COLUMN_PROTOCOL_STEPS_TAG == "ps"

    def test_and_tag(self):
        assert WideColumnValues.AND_TAG == "AND"

    def test_or_tag(self):
        assert WideColumnValues.OR_TAG == "OR"

    def test_value_tag(self):
        assert WideColumnValues.VALUE_TAG == "value"

    def test_flag_separator(self):
        assert WideColumnValues.COLUMN_FLAG_SEPARATOR == "."


class TestMeasureTableColumns:
    def test_compartment(self):
        assert MeasureTableColumns.COMPARTMENT == "mr_compartment"

    def test_specimen(self):
        assert MeasureTableColumns.SPECIMEN == "mr_specimen"

    def test_fraction(self):
        assert MeasureTableColumns.FRACTION == "mr_fraction"

    def test_measure(self):
        assert MeasureTableColumns.MEASURE == "mr_measure"

    def test_unit(self):
        assert MeasureTableColumns.UNIT == "mr_unit"

    def test_aggregation(self):
        assert MeasureTableColumns.AGGREGATION == "mr_aggregation"

    def test_index(self):
        assert MeasureTableColumns.INDEX == "mr_index"

    def test_value(self):
        assert MeasureTableColumns.VALUE == "mr_value"


class TestProtocolStepsTableColumns:
    def test_method(self):
        assert ProtocolStepsTableColumns.METHOD == "ps_method"

    def test_measure(self):
        assert ProtocolStepsTableColumns.MEASURE == "ps_measure"

    def test_value(self):
        assert ProtocolStepsTableColumns.VALUE == "ps_value"

    def test_unit(self):
        assert ProtocolStepsTableColumns.UNIT == "ps_unit"

    def test_aggregation(self):
        assert ProtocolStepsTableColumns.AGGREGATION == "ps_aggregation"


class TestFlagPrefixes:
    def test_group_prefix(self):
        assert FlagPrefixes.GROUP_FLAG_PREFIX == "g"

    def test_link_prefix(self):
        assert FlagPrefixes.LINK_FLAG_PREFIX == "l"

    def test_recognized_contains_group(self):
        assert FlagPrefixes.GROUP_FLAG_PREFIX in RECOGNIZED_FLAG_PREFIXES

    def test_recognized_contains_link(self):
        assert FlagPrefixes.LINK_FLAG_PREFIX in RECOGNIZED_FLAG_PREFIXES

    def test_recognized_is_list(self):
        assert isinstance(RECOGNIZED_FLAG_PREFIXES, list)


class TestAndValueSeparator:
    def test_is_dot(self):
        assert AND_VALUE_SEPARATOR == "."


# ---------------------------------------------------------------------------
# get_flag_prefix
# ---------------------------------------------------------------------------


class TestGetFlagPrefix:
    def test_group_prefix(self):
        assert get_flag_prefix("g123") == FlagPrefixes.GROUP_FLAG_PREFIX

    def test_link_prefix(self):
        assert get_flag_prefix("l456") == FlagPrefixes.LINK_FLAG_PREFIX

    def test_exact_group_prefix(self):
        assert get_flag_prefix("g") == FlagPrefixes.GROUP_FLAG_PREFIX

    def test_exact_link_prefix(self):
        assert get_flag_prefix("l") == FlagPrefixes.LINK_FLAG_PREFIX

    def test_unrecognized_returns_none(self):
        assert get_flag_prefix("x999") is None

    def test_number_only_returns_none(self):
        assert get_flag_prefix("123") is None

    def test_empty_string_returns_none(self):
        assert get_flag_prefix("") is None


# ---------------------------------------------------------------------------
# get_extra_slot_for_flag_prefix
# ---------------------------------------------------------------------------


class TestGetExtraSlotForFlagPrefix:
    def test_returns_string(self):
        result = get_extra_slot_for_flag_prefix("g")
        assert isinstance(result, str)

    def test_starts_with_extra_slot_prefix(self):
        result = get_extra_slot_for_flag_prefix("g")
        assert result.startswith(EXTRA_SLOT_PREFIX)

    def test_contains_prefix_value(self):
        result = get_extra_slot_for_flag_prefix("g")
        assert "g" in result

    def test_different_prefixes_produce_different_slots(self):
        result_g = get_extra_slot_for_flag_prefix("g")
        result_l = get_extra_slot_for_flag_prefix("l")
        assert result_g != result_l
        assert "l" in result_l


# ---------------------------------------------------------------------------
# get_column_flags
# ---------------------------------------------------------------------------


class TestGetColumnFlags:
    def test_no_separator_returns_empty(self):
        assert get_column_flags("mr_measure") == []

    def test_single_group_flag(self):
        flags = get_column_flags("mr_measure.g123")
        assert "g123" in flags

    def test_filter_by_group_prefix(self):
        flags = get_column_flags("mr_measure.g123.l456", flag_prefix="g")
        assert "g123" in flags
        assert "l456" not in flags

    def test_filter_by_link_prefix(self):
        flags = get_column_flags("mr_measure.g123.l456", flag_prefix="l")
        assert "l456" in flags
        assert "g123" not in flags

    def test_ignore_group_prefix(self):
        flags = get_column_flags("mr_measure.g123.l456", ignore_prefixes="g")
        assert "g123" not in flags
        assert "l456" in flags

    def test_ignore_link_prefix(self):
        flags = get_column_flags("mr_measure.g1.l2", ignore_prefixes="l")
        assert "l2" not in flags
        assert "g1" in flags

    def test_remove_flag_prefix_group(self):
        flags = get_column_flags(
            "mr_measure.g123", flag_prefix="g", remove_flag_prefix=True
        )
        assert "123" in flags
        assert "g123" not in flags

    def test_remove_flag_prefix_list(self):
        flags = get_column_flags(
            "mr_measure.g1.l2", flag_prefix=["g", "l"], remove_flag_prefix=True
        )
        assert "1" in flags
        assert "2" in flags

    def test_integer_only_flag_ignored(self):
        flags = get_column_flags("mr_measure.123")
        assert flags == []

    def test_unrecognized_prefix_excluded(self):
        flags = get_column_flags("mr_measure.x99")
        assert flags == []

    def test_no_duplicates(self):
        flags = get_column_flags("mr_measure.g1.g1")
        assert flags.count("g1") == 1

    def test_multiple_flags_returned(self):
        flags = get_column_flags("mr_measure.g1.l2")
        assert len(flags) == 2

    def test_flag_prefix_as_list(self):
        flags = get_column_flags("mr_measure.g5", flag_prefix=["g"])
        assert "g5" in flags

    def test_ignore_prefixes_as_list(self):
        flags = get_column_flags("mr_measure.g1.l2", ignore_prefixes=["g", "l"])
        assert flags == []


# ---------------------------------------------------------------------------
# column_without_flags
# ---------------------------------------------------------------------------


class TestColumnWithoutFlags:
    def test_no_flags_unchanged(self):
        assert column_without_flags("mr_measure") == "mr_measure"

    def test_removes_single_flag(self):
        assert column_without_flags("mr_measure.g123") == "mr_measure"

    def test_removes_multiple_flags(self):
        assert column_without_flags("mr_measure.g1.l2") == "mr_measure"

    def test_preserves_underscore_column_name(self):
        assert column_without_flags("sm_sampleID.g5") == "sm_sampleID"

    def test_empty_string(self):
        assert column_without_flags("") == ""

    def test_separator_at_start(self):
        result = column_without_flags(".g1")
        assert result == ""


# ---------------------------------------------------------------------------
# column_with_flags
# ---------------------------------------------------------------------------


class TestColumnWithFlags:
    def test_adds_single_string_flag(self):
        result = column_with_flags("mr_measure", "g1")
        assert result == "mr_measure.g1"

    def test_adds_list_of_flags(self):
        result = column_with_flags("mr_measure", ["g1", "l2"])
        assert result == "mr_measure.g1.l2"

    def test_empty_list_unchanged(self):
        result = column_with_flags("mr_measure", [])
        assert result == "mr_measure"

    def test_none_unchanged(self):
        result = column_with_flags("mr_measure", None)
        assert result == "mr_measure"

    def test_uses_flag_separator(self):
        result = column_with_flags("mr_measure", "g1")
        assert WideColumnValues.COLUMN_FLAG_SEPARATOR in result

    def test_roundtrip_preserves_base_name(self):
        original = "sm_sampleID"
        with_flags = column_with_flags(original, ["g5", "l3"])
        assert column_without_flags(with_flags) == original

    def test_three_flags(self):
        result = column_with_flags("col", ["g1", "l2", "g3"])
        assert result == "col.g1.l2.g3"


# ---------------------------------------------------------------------------
# groups_of_column
# ---------------------------------------------------------------------------


class TestGroupsOfColumn:
    def test_no_group_returns_empty_list(self):
        assert groups_of_column("mr_measure") == []

    def test_returns_group_flag(self):
        result = groups_of_column("mr_measure.g1")
        assert "g1" in result

    def test_remove_prefix(self):
        result = groups_of_column("mr_measure.g123", remove_flag_prefix=True)
        assert "123" in result
        assert "g123" not in result

    def test_link_flag_is_not_a_group(self):
        result = groups_of_column("mr_measure.l456")
        assert result == []

    def test_multiple_group_flags(self):
        result = groups_of_column("mr_measure.g1.g2")
        assert "g1" in result


# ---------------------------------------------------------------------------
# column_and_groups_of_column
# ---------------------------------------------------------------------------


class TestColumnAndGroupsOfColumn:
    def test_no_group_returns_empty_list(self):
        col, groups = column_and_groups_of_column("mr_measure")
        assert col == "mr_measure"
        assert groups == []

    def test_returns_base_col_and_group(self):
        col, groups = column_and_groups_of_column("mr_measure.g1")
        assert col == "mr_measure"
        assert "g1" in groups

    def test_link_flag_not_treated_as_group(self):
        col, groups = column_and_groups_of_column("mr_measure.l5")
        assert col == "mr_measure"
        assert groups == []

    def test_remove_prefix(self):
        col, groups = column_and_groups_of_column(
            "mr_measure.g99", remove_flag_prefix=True
        )
        assert col == "mr_measure"
        assert "99" in groups
        assert "g99" not in groups

    def test_complex_column(self):
        col, groups = column_and_groups_of_column("sm_sampleID.g10.l5")
        assert col == "sm_sampleID"
        assert "g10" in groups


# ---------------------------------------------------------------------------
# column_and_flags_of_column
# ---------------------------------------------------------------------------


class TestColumnAndFlagsOfColumn:
    def test_no_flags_returns_empty(self):
        col, flags = column_and_flags_of_column("mr_measure", flag_prefix="g")
        assert col == "mr_measure"
        assert flags == []

    def test_matching_prefix(self):
        col, flags = column_and_flags_of_column("mr_measure.g1", flag_prefix="g")
        assert col == "mr_measure"
        assert "g1" in flags

    def test_non_matching_prefix_empty(self):
        col, flags = column_and_flags_of_column("mr_measure.l1", flag_prefix="g")
        assert flags == []

    def test_remove_flag_prefix(self):
        col, flags = column_and_flags_of_column(
            "mr_measure.g5", flag_prefix="g", remove_flag_prefix=True
        )
        assert "5" in flags
        assert "g5" not in flags

    def test_base_column_always_stripped(self):
        col, _ = column_and_flags_of_column("sm_sampleID.g3.l4", flag_prefix="g")
        assert col == "sm_sampleID"
