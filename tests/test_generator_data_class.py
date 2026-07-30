"""Tests for odm_map.id_generator.generator_data.GeneratorData"""

import textwrap

import numpy as np
import pandas as pd
import pytest
from linkml_runtime import SchemaView

from odm_map.id_generator.generator_data import INITIAL_ID_PREFIX, GeneratorData

SCHEMA_STR = textwrap.dedent("""
    id: https://example.org/test
    name: TestSchema
    imports:
    - linkml:types
    prefixes:
      linkml: https://w3id.org/linkml/
    default_range: string
    classes:
      samples:
        attributes:
          sampleID:
            identifier: true
          sampleName:
            range: string
          siteID:
            range: string
""")


@pytest.fixture
def schema():
    return SchemaView(SCHEMA_STR)


@pytest.fixture
def sample_df():
    return pd.DataFrame(
        {
            "sampleID": ["s001", "s002", "s003"],
            "sampleName": ["Sample 1", "Sample 2", "Sample 3"],
            "siteID": ["site1", "site1", "site2"],
        }
    )


@pytest.fixture
def gd_no_gen(schema, sample_df):
    return GeneratorData(
        class_name="samples",
        input_data=[sample_df.copy()],
        primary_key="sampleID",
        schema=schema,
        generated_slots_for_selectors={},
    )


@pytest.fixture
def gd_with_gen(schema, sample_df):
    return GeneratorData(
        class_name="samples",
        input_data=[sample_df.copy()],
        primary_key="sampleID",
        schema=schema,
        generated_slots_for_selectors={None: ["sampleID"]},
    )


# ---------------------------------------------------------------------------
# __len__
# ---------------------------------------------------------------------------


class TestLen:
    def test_returns_number_of_rows(self, gd_no_gen):
        assert len(gd_no_gen) == 3

    def test_with_gen_same_row_count(self, gd_with_gen):
        assert len(gd_with_gen) == 3


# ---------------------------------------------------------------------------
# has_column
# ---------------------------------------------------------------------------


class TestHasColumn:
    def test_existing_column_true(self, gd_no_gen):
        assert gd_no_gen.has_column("sampleID")

    def test_another_existing_column_true(self, gd_no_gen):
        assert gd_no_gen.has_column("sampleName")

    def test_unknown_column_false(self, gd_no_gen):
        assert not gd_no_gen.has_column("nonexistentColumn")

    def test_empty_string_false(self, gd_no_gen):
        assert not gd_no_gen.has_column("")


# ---------------------------------------------------------------------------
# get_column_index
# ---------------------------------------------------------------------------


class TestGetColumnIndex:
    def test_returns_int_for_string_col(self, gd_no_gen):
        idx = gd_no_gen.get_column_index("sampleID")
        assert isinstance(idx, int)
        assert idx >= 0

    def test_different_columns_have_different_indices(self, gd_no_gen):
        idx_a = gd_no_gen.get_column_index("sampleID")
        idx_b = gd_no_gen.get_column_index("sampleName")
        assert idx_a != idx_b

    def test_returns_list_for_list_of_cols(self, gd_no_gen):
        result = gd_no_gen.get_column_index(["sampleID", "sampleName"])
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(i, int) for i in result)

    def test_list_order_preserved(self, gd_no_gen):
        idx_single_a = gd_no_gen.get_column_index("sampleID")
        idx_single_b = gd_no_gen.get_column_index("sampleName")
        result = gd_no_gen.get_column_index(["sampleID", "sampleName"])
        assert result[0] == idx_single_a
        assert result[1] == idx_single_b

    def test_index_matches_column_position(self, gd_no_gen):
        # The precomputed index map must agree with the actual column order.
        for col in gd_no_gen.columns:
            assert gd_no_gen.get_column_index(col) == gd_no_gen.columns.index(col)

    def test_unknown_column_raises_value_error(self, gd_no_gen):
        with pytest.raises(ValueError):
            gd_no_gen.get_column_index("no_such_column")


# ---------------------------------------------------------------------------
# get_data_value
# ---------------------------------------------------------------------------


class TestGetDataValue:
    def test_returns_correct_value(self, gd_no_gen):
        val = gd_no_gen.get_data_value("sampleName", 0)
        assert val == "Sample 1"

    def test_second_row(self, gd_no_gen):
        val = gd_no_gen.get_data_value("sampleName", 1)
        assert val == "Sample 2"

    def test_third_row_site_id(self, gd_no_gen):
        val = gd_no_gen.get_data_value("siteID", 2)
        assert val == "site2"

    def test_generated_slot_cleared_to_empty_obj_when_has_code(self, gd_with_gen):
        from odm_map.id_generator.id_na import isna

        val = gd_with_gen.get_data_value("sampleID", 0)
        assert isna(val)


# ---------------------------------------------------------------------------
# get_rows_at_index
# ---------------------------------------------------------------------------


class TestGetRowsAtIndex:
    def test_single_index_returns_2d_array(self, gd_no_gen):
        result = gd_no_gen.get_rows_at_index(0)
        assert isinstance(result, np.ndarray)
        assert result.ndim == 2
        assert result.shape[0] == 1

    def test_list_of_indices_returns_correct_shape(self, gd_no_gen):
        result = gd_no_gen.get_rows_at_index([0, 1])
        assert result.shape[0] == 2

    def test_correct_row_content(self, gd_no_gen):
        result = gd_no_gen.get_rows_at_index(0)
        idx = gd_no_gen.get_column_index("sampleName")
        assert result[0, idx] == "Sample 1"

    def test_multiple_rows_correct_content(self, gd_no_gen):
        result = gd_no_gen.get_rows_at_index([0, 2])
        idx = gd_no_gen.get_column_index("siteID")
        assert result[0, idx] == "site1"
        assert result[1, idx] == "site2"


# ---------------------------------------------------------------------------
# get_all_generated_slots
# ---------------------------------------------------------------------------


class TestGetAllGeneratedSlots:
    def test_no_generated_slots_returns_empty(self, gd_no_gen):
        assert gd_no_gen.get_all_generated_slots() == []

    def test_with_gen_returns_slot_list(self, gd_with_gen):
        slots = gd_with_gen.get_all_generated_slots()
        assert "sampleID" in slots

    def test_deduplication(self, schema):
        gd = GeneratorData(
            class_name="samples",
            input_data=[
                pd.DataFrame(
                    {
                        "sampleID": ["s001"],
                        "sampleName": ["Sample 1"],
                        "siteID": ["site1"],
                    }
                )
            ],
            primary_key="sampleID",
            schema=schema,
            generated_slots_for_selectors={None: ["sampleID"], "extra": ["sampleID"]},
        )
        slots = gd.get_all_generated_slots()
        assert slots.count("sampleID") == 1


# ---------------------------------------------------------------------------
# get_generated_slots_with_selectors
# ---------------------------------------------------------------------------


class TestGetGeneratedSlotsWithSelectors:
    def test_no_gen_returns_empty_for_none_selector(self, gd_no_gen):
        assert gd_no_gen.get_generated_slots_with_selectors([None]) == []

    def test_with_gen_none_selector_returns_slots(self, gd_with_gen):
        slots = gd_with_gen.get_generated_slots_with_selectors([None])
        assert "sampleID" in slots

    def test_unknown_selector_returns_empty(self, gd_with_gen):
        assert (
            gd_with_gen.get_generated_slots_with_selectors(["unknown_selector"]) == []
        )

    def test_multiple_selectors(self, schema):
        gd = GeneratorData(
            class_name="samples",
            input_data=[
                pd.DataFrame(
                    {
                        "sampleID": ["s001"],
                        "sampleName": ["Sample 1"],
                        "siteID": ["site1"],
                    }
                )
            ],
            primary_key="sampleID",
            schema=schema,
            generated_slots_for_selectors={None: ["sampleID"], "pooled": ["siteID"]},
        )
        slots = gd.get_generated_slots_with_selectors([None, "pooled"])
        assert "sampleID" in slots
        assert "siteID" in slots


# ---------------------------------------------------------------------------
# make_initial_slot_names_if_generated_slots
# ---------------------------------------------------------------------------


class TestMakeInitialSlotNamesIfGeneratedSlots:
    def test_generated_slot_gets_prefix(self, gd_with_gen):
        result = gd_with_gen.make_initial_slot_names_if_generated_slots("sampleID")
        assert result == [f"{INITIAL_ID_PREFIX}sampleID"]

    def test_non_generated_slot_unchanged(self, gd_with_gen):
        result = gd_with_gen.make_initial_slot_names_if_generated_slots("sampleName")
        assert result == ["sampleName"]

    def test_list_input_mixed(self, gd_with_gen):
        result = gd_with_gen.make_initial_slot_names_if_generated_slots(
            ["sampleID", "sampleName"]
        )
        assert result[0] == f"{INITIAL_ID_PREFIX}sampleID"
        assert result[1] == "sampleName"

    def test_no_generated_slots_all_unchanged(self, gd_no_gen):
        result = gd_no_gen.make_initial_slot_names_if_generated_slots("sampleID")
        assert result == ["sampleID"]

    def test_returns_copy_not_original_list(self, gd_with_gen):
        original = ["sampleID", "sampleName"]
        gd_with_gen.make_initial_slot_names_if_generated_slots(original)
        assert original == ["sampleID", "sampleName"]


# ---------------------------------------------------------------------------
# get_code_selectors_from_row
# ---------------------------------------------------------------------------


class TestGetCodeSelectorsFromRow:
    def test_rows_without_code_selector_slot_return_none_list(self, gd_no_gen):
        selectors = gd_no_gen.get_code_selectors_from_row(0)
        assert selectors == [None]

    def test_all_rows_have_none_selector(self, gd_no_gen):
        for i in range(len(gd_no_gen)):
            selectors = gd_no_gen.get_code_selectors_from_row(i)
            assert selectors == [None]


# ---------------------------------------------------------------------------
# make_row_hash
# ---------------------------------------------------------------------------


class TestMakeRowHash:
    def test_returns_int(self, gd_no_gen):
        row = gd_no_gen.get_rows_at_index(0)
        h = gd_no_gen.make_row_hash(row)
        assert isinstance(h, int)

    def test_same_row_same_hash(self, gd_no_gen):
        row = gd_no_gen.get_rows_at_index(0)
        assert gd_no_gen.make_row_hash(row) == gd_no_gen.make_row_hash(row)

    def test_different_rows_different_hashes(self, gd_no_gen):
        row0 = gd_no_gen.get_rows_at_index(0)
        row1 = gd_no_gen.get_rows_at_index(1)
        assert gd_no_gen.make_row_hash(row0) != gd_no_gen.make_row_hash(row1)

    def test_2d_array_with_one_row_works(self, gd_no_gen):
        row = gd_no_gen.get_rows_at_index(0)
        assert row.ndim == 2
        h = gd_no_gen.make_row_hash(row)
        assert isinstance(h, int)

    def test_1d_array_works(self, gd_no_gen):
        row_2d = gd_no_gen.get_rows_at_index(0)
        row_1d = row_2d[0]
        h = gd_no_gen.make_row_hash(row_1d)
        assert isinstance(h, int)


# ---------------------------------------------------------------------------
# get_rows_equal
# ---------------------------------------------------------------------------


class TestGetRowsEqual:
    def test_single_slot_match(self, gd_no_gen):
        gd_no_gen.init_lookup_table([])
        result = gd_no_gen.get_rows_equal("sampleName", "Sample 1")
        assert result is not None
        idx = gd_no_gen.get_column_index("sampleName")
        assert result[0, idx] == "Sample 1"

    def test_no_match_returns_none(self, gd_no_gen):
        gd_no_gen.init_lookup_table([])
        result = gd_no_gen.get_rows_equal("sampleName", "DoesNotExist")
        assert result is None

    def test_multi_slot_match(self, gd_no_gen):
        gd_no_gen.init_lookup_table([])
        result = gd_no_gen.get_rows_equal(
            ["sampleName", "siteID"], [["Sample 1", "site1"]]
        )
        assert result is not None
        assert result.shape[0] >= 1

    def test_multi_slot_no_match(self, gd_no_gen):
        gd_no_gen.init_lookup_table([])
        result = gd_no_gen.get_rows_equal(
            ["sampleName", "siteID"], [["Sample 1", "site2"]]
        )
        assert result is None

    def test_max_rows_limits_results(self, gd_no_gen):
        gd_no_gen.init_lookup_table([])
        result = gd_no_gen.get_rows_equal("siteID", "site1", max_rows=1)
        assert result is not None
        assert result.shape[0] == 1

    def test_return_indices_flag(self, gd_no_gen):
        gd_no_gen.init_lookup_table([])
        rows, indices = gd_no_gen.get_rows_equal(
            "sampleName", "Sample 2", return_indices=True
        )
        assert rows is not None
        assert indices is not None
        assert len(indices) == 1

    def test_ignore_indices_excludes_rows(self, gd_no_gen):
        gd_no_gen.init_lookup_table([])
        rows, indices = gd_no_gen.get_rows_equal("siteID", "site1", return_indices=True)
        assert rows is not None
        assert len(indices) == 2

        excluded = int(indices[0])
        result_after_exclude = gd_no_gen.get_rows_equal(
            "siteID", "site1", ignore_indices=[excluded]
        )
        assert result_after_exclude is not None
        assert result_after_exclude.shape[0] == 1

    def test_return_indices_no_match_returns_none_tuple(self, gd_no_gen):
        gd_no_gen.init_lookup_table([])
        rows, indices = gd_no_gen.get_rows_equal(
            "sampleName", "NoSuchSample", return_indices=True
        )
        assert rows is None
        assert indices is None
