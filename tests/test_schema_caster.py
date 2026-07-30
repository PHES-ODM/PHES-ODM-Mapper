"""Tests for odm_map.utils.schema_caster"""

import numpy as np
import pandas as pd
import pytest
from linkml_runtime import SchemaView

from odm_map.utils.schema_caster import SchemaCaster

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
      latitude:
        range: float
      count:
        range: integer
      tags:
        range: string
        multivalued: true
"""


@pytest.fixture
def schema():
    return SchemaView(SCHEMA_YAML)


@pytest.fixture
def schema_path(tmp_path):
    p = tmp_path / "schema.yaml"
    p.write_text(SCHEMA_YAML)
    return p


@pytest.fixture
def caster(schema):
    return SchemaCaster(schema)


# ---------------------------------------------------------------------------
# SchemaCaster init
# ---------------------------------------------------------------------------


class TestSchemaCasterInit:
    def test_init_with_schema_view(self, schema):
        caster = SchemaCaster(schema)
        assert caster.schema is schema

    def test_init_with_schema_path(self, schema_path):
        caster = SchemaCaster(schema_path)
        assert caster.schema is not None

    def test_cast_functions_contains_non_root_classes(self, caster):
        assert "Sites" in caster.cast_functions
        assert "Container" not in caster.cast_functions

    def test_cast_functions_contains_expected_slots(self, caster):
        assert "latitude" in caster.cast_functions["Sites"]
        assert "count" in caster.cast_functions["Sites"]
        assert "siteID" in caster.cast_functions["Sites"]


# ---------------------------------------------------------------------------
# cast_value
# ---------------------------------------------------------------------------


class TestCastValue:
    def test_string_to_float(self, caster):
        result = caster.cast_value("3.14", "Sites", "latitude")
        assert result == pytest.approx(3.14)
        assert isinstance(result, float)

    def test_string_to_int(self, caster):
        result = caster.cast_value("42", "Sites", "count")
        assert result == 42
        assert isinstance(result, int)

    def test_string_slot_stays_string(self, caster):
        result = caster.cast_value("my_site", "Sites", "siteID")
        assert result == "my_site"
        assert isinstance(result, str)

    def test_int_input_cast_to_float(self, caster):
        result = caster.cast_value(3, "Sites", "latitude")
        assert result == pytest.approx(3.0)

    def test_uncastable_float_returned_unchanged(self, caster):
        result = caster.cast_value("not_a_number", "Sites", "latitude")
        assert result == "not_a_number"

    def test_nan_returned_unchanged_for_float(self, caster):
        result = caster.cast_value(float("nan"), "Sites", "latitude")
        assert pd.isna(result)

    def test_nan_returned_unchanged_for_int(self, caster):
        result = caster.cast_value(float("nan"), "Sites", "count")
        assert pd.isna(result)

    def test_unknown_class_raises_value_error(self, caster):
        with pytest.raises(ValueError, match="Unknown class"):
            caster.cast_value("x", "NonExistentClass", "someSlot")

    def test_unknown_slot_raises_value_error(self, caster):
        with pytest.raises(ValueError, match="Unknown slot"):
            caster.cast_value("x", "Sites", "nonExistentSlot")

    def test_multivalued_string_to_list(self, caster):
        result = caster.cast_value("a,b,c", "Sites", "tags")
        assert isinstance(result, list)
        assert result == ["a", "b", "c"]

    def test_already_list_passes_through(self, caster):
        result = caster.cast_value(["x", "y"], "Sites", "tags")
        assert result == ["x", "y"]


# ---------------------------------------------------------------------------
# cast_df
# ---------------------------------------------------------------------------


class TestCastDf:
    def _make_df(self):
        return pd.DataFrame(
            {
                "siteID": ["s1", "s2"],
                "name": ["Site A", "Site B"],
                "latitude": ["1.5", "2.7"],
                "count": ["10", "20"],
            }
        )

    def test_casts_float_column(self, caster):
        df = self._make_df()
        result = caster.cast_df(df, "Sites", inline=False)
        assert result["latitude"].iloc[0] == pytest.approx(1.5)
        assert result["latitude"].iloc[1] == pytest.approx(2.7)

    def test_casts_integer_column(self, caster):
        df = self._make_df()
        result = caster.cast_df(df, "Sites", inline=False)
        assert result["count"].iloc[0] == 10
        assert isinstance(result["count"].iloc[0], (int, np.integer))

    def test_inline_false_original_unchanged(self, caster):
        df = self._make_df()
        caster.cast_df(df, "Sites", inline=False)
        assert df["latitude"].iloc[0] == "1.5"

    def test_inline_true_modifies_df(self, caster):
        df = self._make_df()
        result = caster.cast_df(df, "Sites", inline=True)
        assert result is df
        assert df["latitude"].iloc[0] == pytest.approx(1.5)

    def test_string_column_stays_string(self, caster):
        df = self._make_df()
        result = caster.cast_df(df, "Sites", inline=False)
        assert result["name"].iloc[0] == "Site A"

    def test_missing_column_does_not_raise(self, caster):
        df = pd.DataFrame({"siteID": ["s1"]})
        result = caster.cast_df(df, "Sites", inline=False)
        assert list(result.columns) == ["siteID"]

    def test_unknown_class_raises_value_error(self, caster):
        df = pd.DataFrame({"col": ["val"]})
        with pytest.raises(ValueError, match="Unknown class"):
            caster.cast_df(df, "UnknownClass")

    def test_uncastable_values_left_unchanged(self, caster):
        df = pd.DataFrame(
            {
                "siteID": ["s1"],
                "name": ["A"],
                "latitude": ["not_a_float"],
                "count": ["10"],
            }
        )
        result = caster.cast_df(df, "Sites", inline=False)
        assert result["latitude"].iloc[0] == "not_a_float"
