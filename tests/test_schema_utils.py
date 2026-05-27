"""Tests for odm_map.utils.schema_utils"""

import pytest
from linkml_runtime import SchemaView

from odm_map.utils.schema_utils import (
    all_classes_without_tree_root,
    all_primary_keys,
    find_class,
    get_class,
    get_primary_key,
    get_ranges_of_slot,
    get_ranges_of_slot_defn,
    get_slot_definition,
    remove_ignored_text_from_class_name,
    validate_columns_with_schema,
)


SCHEMA_YAML = """\
id: https://example.org/test
name: test_schema
imports:
  - linkml:types
prefixes:
  ex: https://example.org/test/
  linkml: https://w3id.org/linkml/
default_prefix: ex
default_range: string

classes:
  Container:
    tree_root: true

  Sites:
    attributes:
      siteID:
        range: string
        identifier: true
        required: true
      name:
        range: string
        required: false
      latitude:
        range: float
        required: false

  Measures:
    attributes:
      measureID:
        range: string
        identifier: true
        required: true
      value:
        range: float
        required: false
      count:
        range: integer
        required: false
"""

NO_PK_SCHEMA_YAML = """\
id: https://example.org/nopk
name: nopk
imports:
  - linkml:types
prefixes:
  linkml: https://w3id.org/linkml/
default_prefix: https://example.org/nopk/
default_range: string

classes:
  NoPK:
    attributes:
      name:
        range: string
"""


@pytest.fixture
def schema():
    return SchemaView(SCHEMA_YAML)


@pytest.fixture
def schema_path(tmp_path):
    p = tmp_path / "test_schema.yaml"
    p.write_text(SCHEMA_YAML)
    return p


# ---------------------------------------------------------------------------
# all_classes_without_tree_root
# ---------------------------------------------------------------------------


class TestAllClassesWithoutTreeRoot:
    def test_excludes_tree_root(self, schema):
        classes = all_classes_without_tree_root(schema)
        assert "Container" not in classes

    def test_includes_non_tree_root_classes(self, schema):
        classes = all_classes_without_tree_root(schema)
        assert "Sites" in classes
        assert "Measures" in classes

    def test_returns_list(self, schema):
        assert isinstance(all_classes_without_tree_root(schema), list)

    def test_count_is_correct(self, schema):
        classes = all_classes_without_tree_root(schema)
        assert len(classes) == 2


# ---------------------------------------------------------------------------
# get_primary_key
# ---------------------------------------------------------------------------


class TestGetPrimaryKey:
    def test_sites_primary_key(self, schema):
        assert get_primary_key("Sites", schema) == "siteID"

    def test_measures_primary_key(self, schema):
        assert get_primary_key("Measures", schema) == "measureID"

    def test_raises_when_no_primary_key(self):
        schema = SchemaView(NO_PK_SCHEMA_YAML)
        with pytest.raises(ValueError, match="primary key"):
            get_primary_key("NoPK", schema)


# ---------------------------------------------------------------------------
# all_primary_keys
# ---------------------------------------------------------------------------


class TestAllPrimaryKeys:
    def test_returns_all_non_root_classes(self, schema):
        pks = all_primary_keys(schema)
        assert "Sites" in pks
        assert "Measures" in pks

    def test_excludes_tree_root(self, schema):
        pks = all_primary_keys(schema)
        assert "Container" not in pks

    def test_correct_key_values(self, schema):
        pks = all_primary_keys(schema)
        assert pks["Sites"] == "siteID"
        assert pks["Measures"] == "measureID"

    def test_keys_are_sorted(self, schema):
        pks = all_primary_keys(schema)
        assert list(pks.keys()) == sorted(pks.keys())


# ---------------------------------------------------------------------------
# get_slot_definition
# ---------------------------------------------------------------------------


class TestGetSlotDefinition:
    def test_returns_dict(self, schema):
        result = get_slot_definition("Sites", "siteID", schema)
        assert isinstance(result, dict)

    def test_known_slot_returns_non_none(self, schema):
        result = get_slot_definition("Sites", "name", schema)
        assert result is not None

    def test_raises_on_unknown_slot_by_default(self, schema):
        with pytest.raises(Exception):
            get_slot_definition("Sites", "nonExistentSlot", schema)

    def test_returns_none_on_unknown_slot_no_exception(self, schema):
        result = get_slot_definition(
            "Sites", "nonExistentSlot", schema, exception_on_error=False
        )
        assert result is None


# ---------------------------------------------------------------------------
# get_ranges_of_slot
# ---------------------------------------------------------------------------


class TestGetRangesOfSlot:
    def test_string_range(self, schema):
        ranges = get_ranges_of_slot("Sites", "siteID", schema)
        assert "string" in ranges

    def test_float_range(self, schema):
        ranges = get_ranges_of_slot("Sites", "latitude", schema)
        assert "float" in ranges

    def test_integer_range(self, schema):
        ranges = get_ranges_of_slot("Measures", "count", schema)
        assert "integer" in ranges

    def test_list_of_slots(self, schema):
        ranges = get_ranges_of_slot("Sites", ["siteID", "latitude"], schema)
        assert "string" in ranges
        assert "float" in ranges

    def test_no_duplicates(self, schema):
        ranges = get_ranges_of_slot("Sites", ["siteID", "name"], schema)
        assert len(ranges) == len(set(ranges))

    def test_empty_for_nonexistent_slot_no_exception(self, schema):
        ranges = get_ranges_of_slot("Sites", "nope", schema, exception_on_error=False)
        assert ranges == []


# ---------------------------------------------------------------------------
# get_ranges_of_slot_defn
# ---------------------------------------------------------------------------


class TestGetRangesOfSlotDefn:
    def test_dict_with_range(self):
        result = get_ranges_of_slot_defn({"range": "string"})
        assert "string" in result

    def test_empty_dict_returns_empty(self):
        result = get_ranges_of_slot_defn({})
        assert result == []

    def test_list_of_dicts(self):
        result = get_ranges_of_slot_defn([{"range": "string"}, {"range": "float"}])
        assert "string" in result
        assert "float" in result

    def test_no_duplicates(self):
        result = get_ranges_of_slot_defn([{"range": "string"}, {"range": "string"}])
        assert result.count("string") == 1

    def test_any_of_ranges(self):
        result = get_ranges_of_slot_defn(
            {"any_of": [{"range": "float"}, {"range": "integer"}]}
        )
        assert "float" in result
        assert "integer" in result

    def test_any_of_overrides_range(self):
        result = get_ranges_of_slot_defn(
            {"range": "string", "any_of": [{"range": "float"}, {"range": "integer"}]}
        )
        assert "float" in result
        assert "integer" in result


# ---------------------------------------------------------------------------
# validate_columns_with_schema
# ---------------------------------------------------------------------------


class TestValidateColumnsWithSchema:
    def test_no_warnings_for_complete_columns(self, schema):
        columns = ["siteID", "name", "latitude"]
        warnings = validate_columns_with_schema(
            columns, schema, "Sites", "test.csv", show_log=False
        )
        assert warnings == []

    def test_warns_about_missing_required_column(self, schema):
        columns = ["name", "latitude"]
        warnings = validate_columns_with_schema(
            columns, schema, "Sites", "test.csv", show_log=False
        )
        assert any("siteID" in w and "REQUIRED" in w for w in warnings)

    def test_warns_about_missing_optional_column(self, schema):
        columns = ["siteID"]
        warnings = validate_columns_with_schema(
            columns, schema, "Sites", "test.csv", show_log=False
        )
        assert any("name" in w or "latitude" in w for w in warnings)

    def test_warns_about_unrecognized_column(self, schema):
        columns = ["siteID", "name", "latitude", "BOGUS"]
        warnings = validate_columns_with_schema(
            columns, schema, "Sites", "test.csv", show_log=False
        )
        assert any("BOGUS" in w for w in warnings)

    def test_accepts_schema_path(self, schema_path):
        columns = ["siteID", "name", "latitude"]
        warnings = validate_columns_with_schema(
            columns, schema_path, "Sites", "test.csv", show_log=False
        )
        assert warnings == []

    def test_returns_list(self, schema):
        warnings = validate_columns_with_schema(
            ["siteID"], schema, "Sites", "f.csv", show_log=False
        )
        assert isinstance(warnings, list)


# ---------------------------------------------------------------------------
# remove_ignored_text_from_class_name
# ---------------------------------------------------------------------------


class TestRemoveIgnoredTextFromClassName:
    def test_removes_text_after_square_bracket(self):
        assert remove_ignored_text_from_class_name("Sites[2024]") == "Sites"

    def test_removes_text_after_round_bracket(self):
        assert remove_ignored_text_from_class_name("Sites(info)") == "Sites"

    def test_no_brackets_unchanged(self):
        assert remove_ignored_text_from_class_name("Sites") == "Sites"

    def test_square_bracket_before_round_bracket(self):
        result = remove_ignored_text_from_class_name("Sites[2024](more)")
        assert result == "Sites"

    def test_complex_string(self):
        result = remove_ignored_text_from_class_name("1 - WWMeasure (2024-11-30)")
        assert "WWMeasure" in result
        assert "2024" not in result


# ---------------------------------------------------------------------------
# find_class
# ---------------------------------------------------------------------------


class TestFindClass:
    def test_finds_exact_class(self, schema):
        result = find_class("Sites", schema, ignore_case=False)
        assert result == "Sites"

    def test_finds_class_as_substring(self, schema):
        result = find_class("1 - Sites (extra)", schema, ignore_case=False)
        assert result == "Sites"

    def test_case_insensitive(self, schema):
        result = find_class("sites", schema, ignore_case=True)
        assert result == "Sites"

    def test_case_sensitive_no_match_returns_none(self, schema):
        result = find_class("sites", schema, ignore_case=False)
        assert result is None

    def test_no_match_returns_none(self, schema):
        result = find_class("UnknownXYZ", schema, ignore_case=True)
        assert result is None

    def test_schema_none_returns_cleaned_name(self):
        result = find_class("Sites[2024]", None, ignore_case=True)
        assert result == "Sites"

    def test_longest_match_wins(self, schema):
        result = find_class("Measures something", schema, ignore_case=False)
        assert result == "Measures"


# ---------------------------------------------------------------------------
# get_class
# ---------------------------------------------------------------------------


class TestGetClass:
    def test_exact_case_match(self, schema):
        assert get_class("Sites", schema, ignore_case=False) == "Sites"

    def test_wrong_case_returns_none_when_case_sensitive(self, schema):
        assert get_class("sites", schema, ignore_case=False) is None

    def test_case_insensitive_returns_correctly_cased(self, schema):
        assert get_class("sites", schema, ignore_case=True) == "Sites"

    def test_unknown_class_returns_none(self, schema):
        assert get_class("NonExistent", schema, ignore_case=True) is None

    def test_schema_none_returns_cleaned_name(self):
        result = get_class("Sites[old]", None, ignore_case=False)
        assert result == "Sites"

    def test_removes_bracket_text_before_lookup(self, schema):
        result = get_class("Sites[2024]", schema, ignore_case=True)
        assert result == "Sites"
