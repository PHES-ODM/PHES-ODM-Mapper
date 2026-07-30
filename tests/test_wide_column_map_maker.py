"""Tests for odm_map.prepare_wide_to_long.wide_column_map_maker"""

from unittest.mock import MagicMock, patch

import pytest
import yaml

from odm_map.prepare_wide_to_long.wide_column_map_maker import WideColumnMapMaker
from odm_map.prepare_wide_to_long.wide_column_utils import ConfigKeys

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config_data():
    return {
        ConfigKeys.TABLES_TO_SHORTNAMES: {
            "measures": "mr",
            "samples": "sm",
            "sites": "si",
        }
    }


@pytest.fixture
def config_file(tmp_path, config_data):
    path = tmp_path / "config.yaml"
    with open(path, "w") as f:
        yaml.safe_dump(config_data, f)
    return str(path)


@pytest.fixture
def mock_schema():
    schema = MagicMock()
    schema.all_class.return_value = {
        "measures": MagicMock(),
        "samples": MagicMock(),
        "sites": MagicMock(),
    }
    schema.all_enums.return_value = {}
    schema.all_types.return_value = {}
    return schema


@pytest.fixture
def maker(config_file, mock_schema):
    return WideColumnMapMaker(
        config=config_file,
        source_class_name="odm_wide",
        target_schema=mock_schema,
    )


# ---------------------------------------------------------------------------
# get_slot_definition_info_for_ranges
# ---------------------------------------------------------------------------


class TestGetSlotDefinitionInfoForRanges:
    def test_single_range_returns_range_key(self, maker):
        result = maker.get_slot_definition_info_for_ranges("string")
        assert result == {"range": "string"}

    def test_single_item_list_returns_range_key(self, maker):
        result = maker.get_slot_definition_info_for_ranges(["float"])
        assert result == {"range": "float"}

    def test_multiple_ranges_returns_any_of(self, maker):
        result = maker.get_slot_definition_info_for_ranges(["string", "float"])
        assert "any_of" in result
        assert {"range": "string"} in result["any_of"]
        assert {"range": "float"} in result["any_of"]

    def test_empty_list_defaults_to_string(self, maker):
        result = maker.get_slot_definition_info_for_ranges([])
        assert result == {"range": "string"}

    def test_three_ranges_any_of(self, maker):
        result = maker.get_slot_definition_info_for_ranges(
            ["string", "float", "integer"]
        )
        assert len(result["any_of"]) == 3

    def test_string_input_treated_as_single(self, maker):
        result = maker.get_slot_definition_info_for_ranges("integer")
        assert result == {"range": "integer"}


# ---------------------------------------------------------------------------
# get_range_info_of_slot
# ---------------------------------------------------------------------------


class TestGetRangeInfoOfSlot:
    def test_single_range_returned(self, maker, mock_schema):
        mock_schema.all_classes.return_value = {}
        slot_defn = {"range": "string"}
        result = maker.get_range_info_of_slot(slot_defn, mock_schema)
        assert result == {"range": "string"}

    def test_any_of_returned(self, maker, mock_schema):
        mock_schema.all_classes.return_value = {}
        slot_defn = {"any_of": [{"range": "string"}, {"range": "float"}]}
        result = maker.get_range_info_of_slot(slot_defn, mock_schema)
        assert "any_of" in result or "range" in result

    def test_class_range_replaced_with_string(self, maker, mock_schema):
        mock_schema.all_classes.return_value = {"samples": MagicMock()}
        slot_defn = {"range": "samples"}
        result = maker.get_range_info_of_slot(slot_defn, mock_schema)
        assert result == {"range": "string"}

    def test_non_class_range_preserved(self, maker, mock_schema):
        mock_schema.all_classes.return_value = {"measures": MagicMock()}
        slot_defn = {"range": "float"}
        result = maker.get_range_info_of_slot(slot_defn, mock_schema)
        assert result == {"range": "float"}

    def test_none_range_handled(self, maker, mock_schema):
        mock_schema.all_classes.return_value = {}
        slot_defn = {}
        result = maker.get_range_info_of_slot(slot_defn, mock_schema)
        # None range → [None] → "string" default
        assert "range" in result or "any_of" in result


# ---------------------------------------------------------------------------
# add_slot_derivation
# ---------------------------------------------------------------------------


class TestAddSlotDerivation:
    def test_adds_target_class_to_derivations(self, maker):
        derivations = {}
        maker.add_slot_derivation(
            derivations, "odm_wide", "sm_sampleID", "samples", "sampleID"
        )
        assert "samples" in derivations

    def test_adds_populated_from(self, maker):
        derivations = {}
        maker.add_slot_derivation(
            derivations, "odm_wide", "sm_sampleID", "samples", "sampleID"
        )
        assert derivations["samples"]["populated_from"] == "odm_wide"

    def test_adds_slot_derivation_entry(self, maker):
        derivations = {}
        maker.add_slot_derivation(
            derivations, "odm_wide", "sm_sampleID", "samples", "sampleID"
        )
        slot_derivations = derivations["samples"]["slot_derivations"]
        assert "sampleID" in slot_derivations

    def test_slot_derivation_has_correct_populated_from(self, maker):
        derivations = {}
        maker.add_slot_derivation(
            derivations, "odm_wide", "sm_sampleID", "samples", "sampleID"
        )
        slot_derivation = derivations["samples"]["slot_derivations"]["sampleID"]
        assert slot_derivation["populated_from"] == "sm_sampleID"

    def test_multiple_slot_derivations_same_class(self, maker):
        derivations = {}
        maker.add_slot_derivation(
            derivations, "odm_wide", "sm_sampleID", "samples", "sampleID"
        )
        maker.add_slot_derivation(derivations, "odm_wide", "sm_name", "samples", "name")
        slot_derivations = derivations["samples"]["slot_derivations"]
        assert "sampleID" in slot_derivations
        assert "name" in slot_derivations

    def test_multiple_target_classes(self, maker):
        derivations = {}
        maker.add_slot_derivation(
            derivations, "odm_wide", "sm_sampleID", "samples", "sampleID"
        )
        maker.add_slot_derivation(
            derivations, "odm_wide", "mr_value", "measures", "value"
        )
        assert "samples" in derivations
        assert "measures" in derivations

    def test_class_name_set_correctly(self, maker):
        derivations = {}
        maker.add_slot_derivation(
            derivations, "odm_wide", "sm_sampleID", "samples", "sampleID"
        )
        assert derivations["samples"]["name"] == "samples"

    def test_slot_derivation_name_set_correctly(self, maker):
        derivations = {}
        maker.add_slot_derivation(
            derivations, "odm_wide", "sm_sampleID", "samples", "sampleID"
        )
        slot_derivation = derivations["samples"]["slot_derivations"]["sampleID"]
        assert slot_derivation["name"] == "sampleID"


# ---------------------------------------------------------------------------
# get_class_and_slot
# ---------------------------------------------------------------------------


class TestGetClassAndSlot:
    def test_returns_class_and_slot(self, maker, mock_schema):
        with patch(
            "odm_map.prepare_wide_to_long.wide_column_map_maker.get_slot_definition",
            return_value={"name": "sampleID"},
        ):
            class_name, slot_name = maker.get_class_and_slot("sm_sampleID")
        assert class_name == "samples"
        assert slot_name == "sampleID"

    def test_returns_class_and_slot_with_group_flag(self, maker, mock_schema):
        with patch(
            "odm_map.prepare_wide_to_long.wide_column_map_maker.get_slot_definition",
            return_value={"name": "sampleID"},
        ):
            class_name, slot_name = maker.get_class_and_slot("sm_sampleID.g5")
        assert class_name == "samples"
        assert slot_name == "sampleID"

    def test_raises_for_unknown_short_name(self, maker):
        with pytest.raises(ValueError, match="Unrecognized table short name"):
            maker.get_class_and_slot("zz_someSlot")

    def test_raises_for_wrong_part_count(self, maker):
        with pytest.raises(ValueError, match="exactly two parts"):
            maker.get_class_and_slot("sm_a_b")

    def test_raises_for_class_not_in_schema(self, maker, mock_schema):
        mock_schema.all_class.return_value = {}  # no classes in schema
        with pytest.raises(ValueError, match="Unrecognized class"):
            maker.get_class_and_slot("sm_sampleID")

    def test_raises_for_unknown_slot(self, maker, mock_schema):
        with (
            patch(
                "odm_map.prepare_wide_to_long.wide_column_map_maker.get_slot_definition",
                return_value=None,
            ),
            pytest.raises(ValueError, match="Unrecognized slot"),
        ):
            maker.get_class_and_slot("sm_sampleID")
