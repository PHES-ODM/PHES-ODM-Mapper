"""Tests for odm_map.enum_hierarchy.enum_hierarchy_selector"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from linkml_runtime import SchemaView
from linkml_runtime.linkml_model import SlotDefinition

from odm_map.enum_hierarchy.enum_hierarchy_selector import (
    ConfigKeys,
    EnumHierarchySelector,
)

# Minimal schema for testing:
#   FruitEnum: apple is_a fruit is_a food
#   ColorEnum: red is_a color
#   TestRecord: two multivalued-enum slots (categories/FruitEnum, colors/ColorEnum),
#               one non-multivalued-enum slot (single_category/FruitEnum),
#               one non-multivalued-string slot (name)
_SCHEMA_YAML = """
id: http://example.org/test
name: test
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
default_range: string
enums:
  FruitEnum:
    permissible_values:
      food: {}
      fruit:
        is_a: food
      apple:
        is_a: fruit
  ColorEnum:
    permissible_values:
      color: {}
      red:
        is_a: color
classes:
  TestRecord:
    attributes:
      id:
        identifier: true
        range: string
      categories:
        range: FruitEnum
        multivalued: true
      colors:
        range: ColorEnum
        multivalued: true
      single_category:
        range: FruitEnum
        multivalued: false
      name:
        range: string
""".strip()


@pytest.fixture(scope="module")
def schema_path(tmp_path_factory):
    d = tmp_path_factory.mktemp("schema")
    f = d / "test_schema.yaml"
    f.write_text(_SCHEMA_YAML)
    return str(f)


@pytest.fixture(scope="module")
def sv(schema_path):
    return SchemaView(schema_path)


def _fruit_slot(name: str = "categories") -> SlotDefinition:
    slot = SlotDefinition(name=name)
    slot.multivalued = True
    slot.range = "FruitEnum"
    return slot


def _default_df(**extra_cols) -> pd.DataFrame:
    """DataFrame with both multivalued-enum columns present (required when running full select)."""
    data = {"categories": ["apple"], "colors": ["red"]}
    data.update(extra_cols)
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# EnumHierarchySelector.__init__
# ---------------------------------------------------------------------------


class TestEnumHierarchySelectorInit:
    def test_accepts_schema_view_directly(self, sv):
        sel = EnumHierarchySelector(schema=sv)
        assert sel.schema is sv

    def test_accepts_string_path_and_creates_schema_view(self, schema_path):
        sel = EnumHierarchySelector(schema=schema_path)
        assert isinstance(sel.schema, SchemaView)

    def test_no_config_leaves_config_none(self, sv):
        sel = EnumHierarchySelector(schema=sv)
        assert sel.config is None

    def test_config_file_loaded(self, sv, tmp_path):
        import yaml

        config_data = {"classes": {"TestRecord": {"slots": ["categories"]}}}
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))
        sel = EnumHierarchySelector(schema=sv, config=config_file)
        assert sel.config == config_data

    def test_config_path_object_accepted(self, sv, tmp_path):
        import yaml

        config_file = tmp_path / "cfg.yaml"
        config_file.write_text(yaml.dump({"classes": {}}))
        sel = EnumHierarchySelector(schema=sv, config=Path(config_file))
        assert sel.config == {"classes": {}}


# ---------------------------------------------------------------------------
# EnumHierarchySelector.select_from_df
# ---------------------------------------------------------------------------


class TestSelectFromDf:
    def test_direct_ancestor_removed(self, sv):
        sel = EnumHierarchySelector(schema=sv)
        df = pd.DataFrame({"categories": ["apple,fruit"]})
        sel.select_from_df(df, "TestRecord", _fruit_slot())
        assert df.loc[0, "categories"] == "apple"

    def test_full_chain_collapsed_to_leaf(self, sv):
        sel = EnumHierarchySelector(schema=sv)
        df = pd.DataFrame({"categories": ["apple,fruit,food"]})
        sel.select_from_df(df, "TestRecord", _fruit_slot())
        assert df.loc[0, "categories"] == "apple"

    def test_intermediate_collapses_to_itself(self, sv):
        # fruit is_a food → only fruit stays
        sel = EnumHierarchySelector(schema=sv)
        df = pd.DataFrame({"categories": ["fruit,food"]})
        sel.select_from_df(df, "TestRecord", _fruit_slot())
        assert df.loc[0, "categories"] == "fruit"

    def test_single_value_unchanged(self, sv):
        sel = EnumHierarchySelector(schema=sv)
        df = pd.DataFrame({"categories": ["apple"]})
        sel.select_from_df(df, "TestRecord", _fruit_slot())
        assert df.loc[0, "categories"] == "apple"

    def test_root_value_unchanged(self, sv):
        sel = EnumHierarchySelector(schema=sv)
        df = pd.DataFrame({"categories": ["food"]})
        sel.select_from_df(df, "TestRecord", _fruit_slot())
        assert df.loc[0, "categories"] == "food"

    def test_multiple_rows_each_processed(self, sv):
        sel = EnumHierarchySelector(schema=sv)
        df = pd.DataFrame({"categories": ["apple,fruit", "fruit,food", "apple"]})
        sel.select_from_df(df, "TestRecord", _fruit_slot())
        assert df.loc[0, "categories"] == "apple"
        assert df.loc[1, "categories"] == "fruit"
        assert df.loc[2, "categories"] == "apple"

    def test_modifies_dataframe_in_place(self, sv):
        sel = EnumHierarchySelector(schema=sv)
        df = pd.DataFrame({"categories": ["apple,fruit"]})
        original_id = id(df)
        sel.select_from_df(df, "TestRecord", _fruit_slot())
        assert id(df) == original_id
        assert df.loc[0, "categories"] == "apple"

    def test_ancestor_cache_prevents_duplicate_schema_calls(self, sv):
        # Replace schema with a mock on the selector (post-construction) to count calls.
        sel = EnumHierarchySelector(schema=sv)
        mock_schema = MagicMock()
        mock_schema.permissible_value_ancestors.return_value = [
            "apple",
            "fruit",
            "food",
        ]
        sel.schema = mock_schema

        df = pd.DataFrame({"categories": ["apple", "apple", "apple"]})
        sel.select_from_df(df, "TestRecord", _fruit_slot())

        assert mock_schema.permissible_value_ancestors.call_count == 1

    def test_unrelated_values_both_kept(self, sv):
        # "apple" and "red" belong to different enums; neither is an ancestor of the other
        sel = EnumHierarchySelector(schema=sv)
        slot = SlotDefinition(name="mixed")
        slot.multivalued = True
        slot.range = "FruitEnum"

        # Mock schema so that neither value removes the other
        sel.schema = MagicMock()
        sel.schema.permissible_value_ancestors.side_effect = lambda val, rng: [val]

        df = pd.DataFrame({"mixed": ["apple,banana"]})
        sel.select_from_df(df, "TestRecord", slot)
        assert set(df.loc[0, "mixed"].split(",")) == {"apple", "banana"}


# ---------------------------------------------------------------------------
# EnumHierarchySelector.select  (no config)
# ---------------------------------------------------------------------------


class TestSelectNoConfig:
    def test_returns_data_frames_dict(self, sv):
        sel = EnumHierarchySelector(schema=sv)
        dfs = {"TestRecord": [_default_df()]}
        result = sel.select(data_frames=dfs)
        assert result is dfs

    def test_processes_multivalued_enum_slot(self, sv):
        sel = EnumHierarchySelector(schema=sv)
        df = _default_df(categories=["apple,fruit"], colors=["red"])
        dfs = {"TestRecord": [df]}
        sel.select(data_frames=dfs)
        assert df.loc[0, "categories"] == "apple"

    def test_skips_non_multivalued_slot(self, sv):
        # single_category is non-multivalued → must not be processed
        sel = EnumHierarchySelector(schema=sv)
        df = _default_df(
            categories=["apple"], colors=["red"], single_category=["apple,fruit"]
        )
        dfs = {"TestRecord": [df]}
        sel.select(data_frames=dfs)
        assert df.loc[0, "single_category"] == "apple,fruit"

    def test_skips_slot_with_non_enum_range(self, sv):
        # name has range=string (not an enum) → must not be processed
        sel = EnumHierarchySelector(schema=sv)
        df = _default_df(categories=["apple"], colors=["red"], name=["fruit,food"])
        dfs = {"TestRecord": [df]}
        sel.select(data_frames=dfs)
        assert df.loc[0, "name"] == "fruit,food"

    def test_multiple_dfs_for_same_class_all_processed(self, sv):
        sel = EnumHierarchySelector(schema=sv)
        df1 = _default_df(categories=["apple,fruit"], colors=["red"])
        df2 = _default_df(categories=["fruit,food"], colors=["red"])
        dfs = {"TestRecord": [df1, df2]}
        sel.select(data_frames=dfs)
        assert df1.loc[0, "categories"] == "apple"
        assert df2.loc[0, "categories"] == "fruit"

    def test_both_multivalued_enum_slots_processed(self, sv):
        sel = EnumHierarchySelector(schema=sv)
        df = _default_df(categories=["apple,fruit"], colors=["red,color"])
        dfs = {"TestRecord": [df]}
        sel.select(data_frames=dfs)
        assert df.loc[0, "categories"] == "apple"
        assert df.loc[0, "colors"] == "red"

    def test_none_data_frames_initialized_internally(self, sv):
        sel = EnumHierarchySelector(schema=sv)
        with patch(
            "odm_map.enum_hierarchy.enum_hierarchy_selector.load_data_frames_for_classes",
            return_value={},
        ):
            result = sel.select(data_frames=None)
        assert isinstance(result, dict)

    def test_data_files_forwarded_to_loader(self, sv):
        sel = EnumHierarchySelector(schema=sv)
        data_files = {"TestRecord": ["file.csv"]}
        with patch(
            "odm_map.enum_hierarchy.enum_hierarchy_selector.load_data_frames_for_classes",
            return_value={},
        ) as mock_load:
            sel.select(data_files=data_files)
        mock_load.assert_called_once()
        assert mock_load.call_args[0][0] is data_files

    def test_max_rows_forwarded_to_loader(self, sv):
        sel = EnumHierarchySelector(schema=sv)
        with patch(
            "odm_map.enum_hierarchy.enum_hierarchy_selector.load_data_frames_for_classes",
            return_value={},
        ) as mock_load:
            sel.select(data_files={"TestRecord": ["f.csv"]}, max_rows=10)
        _, kwargs = mock_load.call_args
        assert kwargs.get("max_rows") == 10

    def test_output_saved_when_output_dir_given(self, sv, tmp_path):
        sel = EnumHierarchySelector(schema=sv)
        dfs = {"TestRecord": [_default_df()]}
        with patch(
            "odm_map.enum_hierarchy.enum_hierarchy_selector.save_data_frame"
        ) as mock_save:
            sel.select(
                data_frames=dfs, output_dir=tmp_path, output_fmt="{class_name}.csv"
            )
        mock_save.assert_called_once()

    def test_no_save_when_output_dir_is_none(self, sv):
        sel = EnumHierarchySelector(schema=sv)
        dfs = {"TestRecord": [_default_df()]}
        with patch(
            "odm_map.enum_hierarchy.enum_hierarchy_selector.save_data_frame"
        ) as mock_save:
            sel.select(data_frames=dfs, output_dir=None)
        mock_save.assert_not_called()

    def test_output_filename_interpolates_class_name(self, sv, tmp_path):
        sel = EnumHierarchySelector(schema=sv)
        dfs = {"TestRecord": [_default_df()]}
        saved_paths = []
        with patch(
            "odm_map.enum_hierarchy.enum_hierarchy_selector.save_data_frame",
            side_effect=lambda df, path: saved_paths.append(str(path)),
        ):
            sel.select(
                data_frames=dfs,
                output_dir=str(tmp_path),
                output_fmt="{class_name}-sel.csv",
            )
        assert len(saved_paths) == 1
        assert saved_paths[0].endswith("TestRecord-sel.csv")


# ---------------------------------------------------------------------------
# EnumHierarchySelector.select  (with config)
# ---------------------------------------------------------------------------


class TestSelectWithConfig:
    def _sel(self, sv, config: dict) -> EnumHierarchySelector:
        sel = EnumHierarchySelector(schema=sv)
        sel.config = config
        return sel

    def test_config_limits_processing_to_listed_slot(self, sv):
        # Config lists only "categories"; "colors" must be unchanged even though it's a multivalued enum slot
        config = {
            ConfigKeys.CLASSES: {"TestRecord": {ConfigKeys.SLOTS: ["categories"]}}
        }
        sel = self._sel(sv, config)
        df = pd.DataFrame({"categories": ["apple,fruit"], "colors": ["red,color"]})
        dfs = {"TestRecord": [df]}
        sel.select(data_frames=dfs)
        assert df.loc[0, "categories"] == "apple"
        assert df.loc[0, "colors"] == "red,color"

    def test_class_absent_from_config_is_skipped(self, sv):
        config = {ConfigKeys.CLASSES: {}}  # TestRecord not listed
        sel = self._sel(sv, config)
        df = pd.DataFrame({"categories": ["apple,fruit"]})
        dfs = {"TestRecord": [df]}
        sel.select(data_frames=dfs)
        assert df.loc[0, "categories"] == "apple,fruit"

    def test_config_with_empty_slots_list_skips_class(self, sv):
        config = {ConfigKeys.CLASSES: {"TestRecord": {ConfigKeys.SLOTS: []}}}
        sel = self._sel(sv, config)
        df = pd.DataFrame({"categories": ["apple,fruit"]})
        dfs = {"TestRecord": [df]}
        sel.select(data_frames=dfs)
        assert df.loc[0, "categories"] == "apple,fruit"

    def test_config_multiple_slots_both_processed(self, sv):
        config = {
            ConfigKeys.CLASSES: {
                "TestRecord": {ConfigKeys.SLOTS: ["categories", "colors"]}
            }
        }
        sel = self._sel(sv, config)
        df = pd.DataFrame({"categories": ["apple,fruit"], "colors": ["red,color"]})
        dfs = {"TestRecord": [df]}
        sel.select(data_frames=dfs)
        assert df.loc[0, "categories"] == "apple"
        assert df.loc[0, "colors"] == "red"
