"""Tests for odm_map.utils.extra_and_tracking_slots"""

import pandas as pd
import pytest
from linkml_runtime import SchemaView

from odm_map.utils.clean_exit_error import CleanExitError
from odm_map.utils.extra_and_tracking_slots import (
    EXTRA_SLOT_PREFIX,
    TRACKING_SLOT_PREFIX,
    TRACKING_SLOT_SUFFIX,
    TrackingSlots,
    add_extra_and_tracking_slot_derivations,
    add_extra_and_tracking_slots_to_schema,
    add_extra_and_tracking_slots_to_schema_class,
    add_source_tracking_columns,
    drop_extra_slots,
    drop_tracking_slots,
    get_extra_and_tracking_slots_from_data,
    get_tracking_slots,
    is_extra_or_tracking_slot,
    is_extra_slot,
    is_tracking_slot,
    load_data_with_source_tracking_columns,
    make_tracking_slot_name,
)

# ---------------------------------------------------------------------------
# make_tracking_slot_name
# ---------------------------------------------------------------------------


class TestMakeTrackingSlotName:
    def test_format(self):
        name = make_tracking_slot_name("source_row")
        assert name.startswith(TRACKING_SLOT_PREFIX)
        assert name.endswith(TRACKING_SLOT_SUFFIX)
        assert "source_row" in name

    def test_predefined_slots(self):
        assert TrackingSlots.SOURCE_CLASS == make_tracking_slot_name("source_class")
        assert TrackingSlots.SOURCE_ROW == make_tracking_slot_name("source_row")
        assert TrackingSlots.SOURCE_FILE == make_tracking_slot_name("source_file")
        assert TrackingSlots.SOURCE_FILE_AND_ROW == make_tracking_slot_name(
            "source_file_and_row"
        )


# ---------------------------------------------------------------------------
# is_tracking_slot
# ---------------------------------------------------------------------------


class TestIsTrackingSlot:
    def test_true_for_tracking_slot(self):
        slot = make_tracking_slot_name("my_slot")
        assert is_tracking_slot(slot) is True

    def test_true_for_predefined(self):
        assert is_tracking_slot(TrackingSlots.SOURCE_ROW) is True
        assert is_tracking_slot(TrackingSlots.SOURCE_CLASS) is True

    def test_false_for_regular_column(self):
        assert is_tracking_slot("siteID") is False
        assert is_tracking_slot("_extra_foo") is False

    def test_false_for_partial_match(self):
        assert is_tracking_slot("(__not_closed") is False
        assert is_tracking_slot("not_opened__)") is False


# ---------------------------------------------------------------------------
# is_extra_slot
# ---------------------------------------------------------------------------


class TestIsExtraSlot:
    def test_true_for_extra_slot(self):
        assert is_extra_slot("_extra_foo") is True
        assert is_extra_slot("_extra_some_value") is True

    def test_false_for_regular_column(self):
        assert is_extra_slot("siteID") is False

    def test_false_for_tracking_slot(self):
        assert is_extra_slot(TrackingSlots.SOURCE_ROW) is False

    def test_prefix_only_still_extra(self):
        assert is_extra_slot(EXTRA_SLOT_PREFIX) is True


# ---------------------------------------------------------------------------
# is_extra_or_tracking_slot
# ---------------------------------------------------------------------------


class TestIsExtraOrTrackingSlot:
    def test_tracking_slot_is_true(self):
        assert is_extra_or_tracking_slot(TrackingSlots.SOURCE_CLASS) is True

    def test_extra_slot_is_true(self):
        assert is_extra_or_tracking_slot("_extra_bar") is True

    def test_regular_column_is_false(self):
        assert is_extra_or_tracking_slot("siteID") is False
        assert is_extra_or_tracking_slot("value") is False


# ---------------------------------------------------------------------------
# drop_extra_slots
# ---------------------------------------------------------------------------


class TestDropExtraSlots:
    def test_drops_extra_columns(self):
        df = pd.DataFrame(
            {
                "siteID": [1],
                "_extra_something": ["x"],
                "_extra_other": ["y"],
            }
        )
        result = drop_extra_slots(df)
        assert "_extra_something" not in result.columns
        assert "_extra_other" not in result.columns
        assert "siteID" in result.columns

    def test_no_extra_columns_unchanged(self):
        df = pd.DataFrame({"a": [1], "b": [2]})
        result = drop_extra_slots(df)
        assert list(result.columns) == ["a", "b"]

    def test_tracking_columns_not_dropped(self):
        df = pd.DataFrame(
            {
                "siteID": [1],
                TrackingSlots.SOURCE_CLASS: ["sites"],
                "_extra_foo": ["x"],
            }
        )
        result = drop_extra_slots(df)
        assert TrackingSlots.SOURCE_CLASS in result.columns
        assert "_extra_foo" not in result.columns


# ---------------------------------------------------------------------------
# drop_tracking_slots
# ---------------------------------------------------------------------------


class TestDropTrackingSlots:
    def test_drops_tracking_columns(self):
        df = pd.DataFrame(
            {
                "siteID": ["s1"],
                TrackingSlots.SOURCE_CLASS: ["sites"],
                TrackingSlots.SOURCE_ROW: [0],
                TrackingSlots.SOURCE_FILE: ["file.csv"],
                TrackingSlots.SOURCE_FILE_AND_ROW: ["file.csv/0"],
            }
        )
        result = drop_tracking_slots(df)
        assert TrackingSlots.SOURCE_CLASS not in result.columns
        assert TrackingSlots.SOURCE_ROW not in result.columns
        assert "siteID" in result.columns

    def test_extra_columns_not_dropped(self):
        df = pd.DataFrame(
            {
                "_extra_foo": ["x"],
                TrackingSlots.SOURCE_ROW: [0],
            }
        )
        result = drop_tracking_slots(df)
        assert "_extra_foo" in result.columns
        assert TrackingSlots.SOURCE_ROW not in result.columns


# ---------------------------------------------------------------------------
# get_tracking_slots
# ---------------------------------------------------------------------------


class TestGetTrackingSlots:
    def test_returns_list_of_strings(self):
        slots = get_tracking_slots()
        assert isinstance(slots, list)
        assert all(isinstance(s, str) for s in slots)

    def test_contains_predefined_slots(self):
        slots = get_tracking_slots()
        assert TrackingSlots.SOURCE_CLASS in slots
        assert TrackingSlots.SOURCE_ROW in slots
        assert TrackingSlots.SOURCE_FILE in slots
        assert TrackingSlots.SOURCE_FILE_AND_ROW in slots

    def test_all_are_tracking_slots(self):
        for slot in get_tracking_slots():
            assert is_tracking_slot(slot), f"{slot!r} should be a tracking slot"


# ---------------------------------------------------------------------------
# add_source_tracking_columns
# ---------------------------------------------------------------------------


class TestAddSourceTrackingColumns:
    def test_adds_required_columns(self):
        df = pd.DataFrame({"siteID": ["s1", "s2", "s3"]})
        add_source_tracking_columns(df, "sites", "sites.csv")
        assert TrackingSlots.SOURCE_CLASS in df.columns
        assert TrackingSlots.SOURCE_ROW in df.columns
        assert TrackingSlots.SOURCE_FILE in df.columns
        assert TrackingSlots.SOURCE_FILE_AND_ROW in df.columns

    def test_source_class_value(self):
        df = pd.DataFrame({"siteID": ["s1"]})
        add_source_tracking_columns(df, "measures", "measures.csv")
        assert df[TrackingSlots.SOURCE_CLASS].iloc[0] == "measures"

    def test_source_file_value(self):
        df = pd.DataFrame({"siteID": ["s1"]})
        add_source_tracking_columns(df, "sites", "my_file.csv")
        assert df[TrackingSlots.SOURCE_FILE].iloc[0] == "my_file.csv"

    def test_source_row_values(self):
        df = pd.DataFrame({"siteID": ["s1", "s2", "s3"]})
        add_source_tracking_columns(df, "sites", "sites.csv")
        assert list(df[TrackingSlots.SOURCE_ROW]) == [0, 1, 2]

    def test_source_file_and_row_contains_file_and_row(self):
        df = pd.DataFrame({"siteID": ["s1", "s2"]})
        add_source_tracking_columns(df, "sites", "f.csv")
        combined = df[TrackingSlots.SOURCE_FILE_AND_ROW].iloc[0]
        assert "f.csv" in combined
        assert "0" in combined

    def test_empty_dataframe(self):
        df = pd.DataFrame({"siteID": []})
        add_source_tracking_columns(df, "sites", "sites.csv")
        assert TrackingSlots.SOURCE_FILE_AND_ROW in df.columns


# ---------------------------------------------------------------------------
# get_extra_and_tracking_slots_from_data
# ---------------------------------------------------------------------------


class TestGetExtraAndTrackingSlots:
    def test_finds_tracking_slots_in_dataframe(self):
        df = pd.DataFrame(
            {
                "siteID": ["s1"],
                TrackingSlots.SOURCE_CLASS: ["sites"],
                "_extra_foo": ["x"],
            }
        )
        result = get_extra_and_tracking_slots_from_data({"sites": df})
        assert TrackingSlots.SOURCE_CLASS in result["sites"]
        assert "_extra_foo" in result["sites"]
        assert "siteID" not in result["sites"]

    def test_finds_slots_from_list_of_dicts(self):
        rows = [{"siteID": "s1", TrackingSlots.SOURCE_ROW: 0, "_extra_bar": "v"}]
        result = get_extra_and_tracking_slots_from_data({"sites": rows})
        assert TrackingSlots.SOURCE_ROW in result["sites"]
        assert "_extra_bar" in result["sites"]

    def test_empty_class_data_skipped(self):
        result = get_extra_and_tracking_slots_from_data({"sites": []})
        assert "sites" not in result

    def test_regular_columns_not_included(self):
        df = pd.DataFrame({"siteID": ["s1"], "name": ["Site A"]})
        result = get_extra_and_tracking_slots_from_data({"sites": df})
        assert result.get("sites", []) == []


# ---------------------------------------------------------------------------
# Shared schema fixture for schema-dependent tests
# ---------------------------------------------------------------------------

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

  Measures:
    attributes:
      measureID:
        range: string
        identifier: true
      value:
        range: string
"""


@pytest.fixture
def schema_view():
    return SchemaView(SCHEMA_YAML)


# ---------------------------------------------------------------------------
# add_source_tracking_columns — duplicate tracking columns raise
# ---------------------------------------------------------------------------


class TestAddSourceTrackingColumnsConflict:
    def test_existing_tracking_slot_raises(self):
        df = pd.DataFrame(
            {
                "siteID": ["s1"],
                TrackingSlots.SOURCE_ROW: [99],
            }
        )
        with pytest.raises(ValueError, match=TrackingSlots.SOURCE_ROW):
            add_source_tracking_columns(df, "sites", "sites.csv")


# ---------------------------------------------------------------------------
# add_extra_and_tracking_slots_to_schema_class
# ---------------------------------------------------------------------------


class TestAddExtraAndTrackingSlotsToSchemaClass:
    def test_adds_tracking_slot_to_class(self, schema_view):
        add_extra_and_tracking_slots_to_schema_class(
            [TrackingSlots.SOURCE_CLASS], "Sites", schema_view
        )
        class_defn = schema_view.schema.classes["Sites"]
        assert TrackingSlots.SOURCE_CLASS in class_defn.slots

    def test_adds_extra_slot_to_class(self, schema_view):
        add_extra_and_tracking_slots_to_schema_class(
            ["_extra_foo"], "Sites", schema_view
        )
        class_defn = schema_view.schema.classes["Sites"]
        assert "_extra_foo" in class_defn.slots

    def test_does_not_duplicate_existing_slot(self, schema_view):
        add_extra_and_tracking_slots_to_schema_class(
            [TrackingSlots.SOURCE_CLASS], "Sites", schema_view
        )
        add_extra_and_tracking_slots_to_schema_class(
            [TrackingSlots.SOURCE_CLASS], "Sites", schema_view
        )
        class_defn = schema_view.schema.classes["Sites"]
        assert class_defn.slots.count(TrackingSlots.SOURCE_CLASS) == 1

    def test_adds_slot_to_top_level_schema(self, schema_view):
        add_extra_and_tracking_slots_to_schema_class(
            ["_extra_bar"], "Sites", schema_view
        )
        assert "_extra_bar" in schema_view.schema.slots


# ---------------------------------------------------------------------------
# add_extra_and_tracking_slots_to_schema
# ---------------------------------------------------------------------------


class TestAddExtraAndTrackingSlotsToSchema:
    def test_adds_slots_from_dataframe(self, schema_view):
        df = pd.DataFrame(
            {
                "siteID": ["s1"],
                TrackingSlots.SOURCE_CLASS: ["Sites"],
                "_extra_tag": ["val"],
            }
        )
        add_extra_and_tracking_slots_to_schema({"Sites": df}, schema_view)
        class_defn = schema_view.schema.classes["Sites"]
        assert TrackingSlots.SOURCE_CLASS in class_defn.slots
        assert "_extra_tag" in class_defn.slots

    def test_skips_class_not_in_schema(self, schema_view):
        df = pd.DataFrame(
            {
                "col": ["v"],
                "_extra_x": ["v"],
            }
        )
        # "Unknown" class is not in the schema — should be silently skipped
        add_extra_and_tracking_slots_to_schema({"Unknown": df}, schema_view)
        # No exception, and Unknown was not added to schema
        assert "Unknown" not in schema_view.schema.classes


# ---------------------------------------------------------------------------
# add_extra_and_tracking_slot_derivations
# ---------------------------------------------------------------------------


class TestAddExtraAndTrackingSlotDerivations:
    def _make_spec(self, source_class="Sites"):
        return {
            "class_derivations": {
                "sites": {
                    "populated_from": source_class,
                    "slot_derivations": {},
                }
            }
        }

    def test_adds_derivation_for_tracking_slot(self, schema_view):
        data = {
            "Sites": pd.DataFrame(
                {
                    "siteID": ["s1"],
                    TrackingSlots.SOURCE_ROW: [0],
                }
            )
        }
        spec = self._make_spec("Sites")
        add_extra_and_tracking_slot_derivations(data, spec, schema_view)
        slot_derivations = spec["class_derivations"]["sites"]["slot_derivations"]
        assert TrackingSlots.SOURCE_ROW in slot_derivations

    def test_existing_derivation_not_overwritten(self, schema_view):
        data = {
            "Sites": pd.DataFrame(
                {
                    "siteID": ["s1"],
                    TrackingSlots.SOURCE_CLASS: ["Sites"],
                }
            )
        }
        spec = self._make_spec("Sites")
        # Pre-populate with existing derivation
        spec["class_derivations"]["sites"]["slot_derivations"][
            TrackingSlots.SOURCE_CLASS
        ] = {
            "name": TrackingSlots.SOURCE_CLASS,
            "populated_from": "custom_source",
        }
        add_extra_and_tracking_slot_derivations(data, spec, schema_view)
        # The existing derivation should be kept unchanged
        derivation = spec["class_derivations"]["sites"]["slot_derivations"][
            TrackingSlots.SOURCE_CLASS
        ]
        assert derivation["populated_from"] == "custom_source"

    def test_returns_dict_of_tracking_slots(self, schema_view):
        data = {
            "Sites": pd.DataFrame(
                {
                    "siteID": ["s1"],
                    TrackingSlots.SOURCE_FILE: ["f.csv"],
                }
            )
        }
        spec = self._make_spec("Sites")
        result = add_extra_and_tracking_slot_derivations(data, spec, schema_view)
        assert isinstance(result, dict)

    def test_skips_class_without_populated_from(self, schema_view):
        data = {"Sites": pd.DataFrame({"siteID": ["s1"], "_extra_x": ["v"]})}
        spec = {
            "class_derivations": {
                "sites": {"slot_derivations": {}}
                # No 'populated_from' key
            }
        }
        result = add_extra_and_tracking_slot_derivations(data, spec, schema_view)
        assert result == {}


# ---------------------------------------------------------------------------
# load_data_with_source_tracking_columns
# ---------------------------------------------------------------------------


class TestLoadDataWithSourceTrackingColumns:
    def test_empty_data_files_raises(self):
        with pytest.raises(CleanExitError, match="No input data found"):
            load_data_with_source_tracking_columns({})

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(CleanExitError, match="does not exist"):
            load_data_with_source_tracking_columns(
                {"Sites": [str(tmp_path / "nonexistent.csv")]}
            )

    def test_basic_loading_returns_dataframes(self, tmp_path):
        csv_file = tmp_path / "sites.csv"
        csv_file.write_text("siteID,name\ns1,Site One\ns2,Site Two\n")
        result = load_data_with_source_tracking_columns({"Sites": [str(csv_file)]})
        assert "Sites" in result
        assert len(result["Sites"]) == 1
        assert len(result["Sites"][0]) == 2

    def test_tracking_columns_added_by_default(self, tmp_path):
        csv_file = tmp_path / "sites.csv"
        csv_file.write_text("siteID\ns1\n")
        result = load_data_with_source_tracking_columns({"Sites": [str(csv_file)]})
        df = result["Sites"][0]
        assert TrackingSlots.SOURCE_CLASS in df.columns
        assert TrackingSlots.SOURCE_ROW in df.columns
        assert TrackingSlots.SOURCE_FILE in df.columns
        assert TrackingSlots.SOURCE_FILE_AND_ROW in df.columns

    def test_add_tracking_columns_false(self, tmp_path):
        csv_file = tmp_path / "sites.csv"
        csv_file.write_text("siteID\ns1\n")
        result = load_data_with_source_tracking_columns(
            {"Sites": [str(csv_file)]},
            add_tracking_columns=False,
        )
        df = result["Sites"][0]
        assert TrackingSlots.SOURCE_CLASS not in df.columns
        assert TrackingSlots.SOURCE_ROW not in df.columns

    def test_max_rows_limits_loaded_rows(self, tmp_path):
        csv_file = tmp_path / "sites.csv"
        csv_file.write_text("siteID\ns1\ns2\ns3\ns4\ns5\n")
        result = load_data_with_source_tracking_columns(
            {"Sites": [str(csv_file)]},
            max_rows=2,
        )
        df = result["Sites"][0]
        assert len(df) == 2

    def test_validate_class_names_unrecognized_raises(self, tmp_path, schema_view):
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text("col\nval\n")
        with pytest.raises(CleanExitError, match="unrecognized table"):
            load_data_with_source_tracking_columns(
                {"BadClass": [str(csv_file)]},
                schema=schema_view,
                validate_class_names=True,
            )

    def test_valid_class_name_loads_with_schema(self, tmp_path, schema_view):
        csv_file = tmp_path / "sites.csv"
        csv_file.write_text("siteID\ns1\n")
        result = load_data_with_source_tracking_columns(
            {"Sites": [str(csv_file)]},
            schema=schema_view,
        )
        assert "Sites" in result

    def test_validate_columns_logs_warnings(self, tmp_path, schema_view, caplog):
        import logging

        csv_file = tmp_path / "sites.csv"
        csv_file.write_text("siteID,unknown_col\ns1,foo\n")
        with caplog.at_level(logging.WARNING):
            load_data_with_source_tracking_columns(
                {"Sites": [str(csv_file)]},
                schema=schema_view,
                validate_columns=True,
            )
        # At least one warning about unrecognized column expected
        assert any("unknown_col" in msg for msg in caplog.messages)

    def test_progress_barid_does_not_raise(self, tmp_path):
        csv_file = tmp_path / "sites.csv"
        csv_file.write_text("siteID\ns1\n")
        result = load_data_with_source_tracking_columns(
            {"Sites": [str(csv_file)]},
            progress_barid="Loading",
        )
        assert "Sites" in result

    def test_multiple_files_for_class(self, tmp_path):
        f1 = tmp_path / "a.csv"
        f2 = tmp_path / "b.csv"
        f1.write_text("siteID\ns1\n")
        f2.write_text("siteID\ns2\n")
        result = load_data_with_source_tracking_columns({"Sites": [str(f1), str(f2)]})
        assert len(result["Sites"]) == 2

    def test_source_class_column_set_correctly(self, tmp_path):
        csv_file = tmp_path / "sites.csv"
        csv_file.write_text("siteID\ns1\n")
        result = load_data_with_source_tracking_columns({"Sites": [str(csv_file)]})
        df = result["Sites"][0]
        assert df[TrackingSlots.SOURCE_CLASS].iloc[0] == "Sites"
