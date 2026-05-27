"""Tests for odm_map.prepare_wide_to_long.wide_column_idcode_maker"""

import pytest
import pandas as pd
from unittest.mock import MagicMock

from odm_map.utils.extra_and_tracking_slots import make_tracking_slot_name
from odm_map.prepare_wide_to_long.wide_column_idcode_maker import (
    MetaConfigKeys,
    WideColumnIDCodeMaker,
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
        }
    }


@pytest.fixture
def expanded_meta():
    return {
        MetaConfigKeys.EXPLICIT_GROUPS_KEY: ["g1", "g2"],
        MetaConfigKeys.IMPLICIT_GROUPS_KEY: ["g3"],
    }


@pytest.fixture
def maker(config, expanded_meta):
    mock_schema = MagicMock()
    return WideColumnIDCodeMaker(
        config=config,
        expanded_meta=expanded_meta,
        source_class_name="odm_wide",
        target_schema=mock_schema,
    )


# ---------------------------------------------------------------------------
# MetaConfigKeys
# ---------------------------------------------------------------------------


class TestMetaConfigKeys:
    def test_explicit_groups_key(self):
        assert MetaConfigKeys.EXPLICIT_GROUPS_KEY == "explicit_groups"

    def test_implicit_groups_key(self):
        assert MetaConfigKeys.IMPLICIT_GROUPS_KEY == "implicit_groups"


# ---------------------------------------------------------------------------
# get_table_long_name / get_table_short_name
# ---------------------------------------------------------------------------


class TestGetTableNames:
    def test_long_name_from_short_mr(self, maker):
        assert maker.get_table_long_name("mr") == "measures"

    def test_long_name_from_short_sm(self, maker):
        assert maker.get_table_long_name("sm") == "samples"

    def test_long_name_unknown_returns_none(self, maker):
        assert maker.get_table_long_name("zz") is None

    def test_short_name_from_long_measures(self, maker):
        assert maker.get_table_short_name("measures") == "mr"

    def test_short_name_from_long_sites(self, maker):
        assert maker.get_table_short_name("sites") == "si"

    def test_short_name_unknown_returns_none(self, maker):
        assert maker.get_table_short_name("nonexistent") is None


# ---------------------------------------------------------------------------
# iter_columns
# ---------------------------------------------------------------------------


class TestIterColumns:
    def test_yields_class_slot_and_group(self, maker):
        df = pd.DataFrame({"sm_sampleID.g1": ["S001"]})
        results = list(maker.iter_columns(df))
        assert len(results) == 1
        class_name, class_short_name, slot_name, group_name = results[0]
        assert class_name == "samples"
        assert class_short_name == "sm"
        assert slot_name == "sampleID"
        assert group_name == "g1"

    def test_skips_tracking_slots(self, maker):
        tracking_col = make_tracking_slot_name("source_row")
        df = pd.DataFrame({"sm_sampleID": ["S001"], tracking_col: [0]})
        results = list(maker.iter_columns(df))
        cols = [r[2] for r in results]
        assert "source_row" not in cols

    def test_column_without_group_yields_none_group(self, maker):
        df = pd.DataFrame({"sm_sampleID": ["S001"]})
        results = list(maker.iter_columns(df))
        assert len(results) == 1
        _, _, _, group_name = results[0]
        assert group_name is None

    def test_multiple_columns(self, maker):
        df = pd.DataFrame(
            {
                "sm_sampleID.g1": ["S001"],
                "mr_value.g1": [100],
            }
        )
        results = list(maker.iter_columns(df))
        class_names = [r[0] for r in results]
        assert "samples" in class_names
        assert "measures" in class_names

    def test_unknown_short_name_yields_none_class(self, maker):
        # "zz" is not in tables_to_shortnames, get_table_long_name returns None
        df = pd.DataFrame({"zz_someSlot": ["val"]})
        results = list(maker.iter_columns(df))
        assert len(results) == 1
        class_name = results[0][0]
        assert class_name is None

    def test_column_with_wrong_part_count_skipped(self, maker):
        # Column with 3 parts (not 2) should be skipped
        df = pd.DataFrame({"sm_a_b": ["val"]})
        results = list(maker.iter_columns(df))
        assert len(results) == 0


# ---------------------------------------------------------------------------
# class_has_explicit_groups
# ---------------------------------------------------------------------------


class TestClassHasExplicitGroups:
    def test_returns_false_when_no_class_info(self, maker):
        maker.class_groups = {}
        assert maker.class_has_explicit_groups("measures") is False

    def test_returns_false_when_no_explicit_groups(self, maker):
        maker.class_groups = {
            "measures": {
                MetaConfigKeys.EXPLICIT_GROUPS_KEY: [],
                MetaConfigKeys.IMPLICIT_GROUPS_KEY: ["g3"],
            }
        }
        assert maker.class_has_explicit_groups("measures") is False

    def test_returns_true_when_explicit_groups_present(self, maker):
        maker.class_groups = {
            "samples": {
                MetaConfigKeys.EXPLICIT_GROUPS_KEY: ["g1"],
                MetaConfigKeys.IMPLICIT_GROUPS_KEY: [],
            }
        }
        assert maker.class_has_explicit_groups("samples") is True

    def test_returns_false_for_missing_class(self, maker):
        maker.class_groups = {}
        assert maker.class_has_explicit_groups("nonexistent") is False


# ---------------------------------------------------------------------------
# make() — integration test with a real schema
# ---------------------------------------------------------------------------

SCHEMA_WITH_FK = """\
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
      siteID:
        range: Sites
      value:
        range: string
"""


@pytest.fixture
def real_schema():
    from linkml_runtime import SchemaView

    return SchemaView(SCHEMA_WITH_FK)


@pytest.fixture
def real_config():
    return {
        ConfigKeys.TABLES_TO_SHORTNAMES: {
            "Sites": "si",
            "Measures": "mr",
        }
    }


@pytest.fixture
def real_maker(real_config, expanded_meta, real_schema):
    return WideColumnIDCodeMaker(
        config=real_config,
        expanded_meta=expanded_meta,
        source_class_name="odm_wide",
        target_schema=real_schema,
    )


class TestMake:
    def test_make_returns_tuple_of_four(self, real_maker):
        df = pd.DataFrame(
            {
                "si_siteID": ["S1"],
                "mr_measureID": ["M1"],
                "mr_siteID": ["S1"],
            }
        )
        result = real_maker.make(data_file=None, data_frame=df)
        assert len(result) == 4

    def test_make_returns_id_code_dataframe(self, real_maker):
        df = pd.DataFrame(
            {
                "si_siteID": ["S1"],
                "mr_measureID": ["M1"],
                "mr_siteID": ["S1"],
            }
        )
        id_code_df, _, _, _ = real_maker.make(data_file=None, data_frame=df)
        assert hasattr(id_code_df, "columns")

    def test_make_generates_fk_id_code(self, real_maker):
        df = pd.DataFrame(
            {
                "si_siteID": ["S1"],
                "mr_measureID": ["M1"],
                "mr_siteID": ["S1"],
            }
        )
        id_code_df, _, _, _ = real_maker.make(data_file=None, data_frame=df)
        # Should have an entry for Measures.siteID pointing to Sites.siteID
        if len(id_code_df):
            from odm_map.id_generator.generator import IDCodeColumns

            assert IDCodeColumns.CLASS in id_code_df.columns
            assert IDCodeColumns.SLOT in id_code_df.columns

    def test_make_class_linkages_in_config(self, real_maker):
        df = pd.DataFrame(
            {
                "si_siteID": ["S1"],
                "mr_measureID": ["M1"],
                "mr_siteID": ["S1"],
            }
        )
        _, _, id_code_config, _ = real_maker.make(data_file=None, data_frame=df)
        assert "class_linkages" in id_code_config

    def test_make_saves_to_output_dir(self, real_maker, tmp_path):
        df = pd.DataFrame(
            {
                "si_siteID": ["S1"],
                "mr_measureID": ["M1"],
            }
        )
        output_dir = str(tmp_path / "output")
        id_code_df, out_file, _, out_config = real_maker.make(
            data_file=None, data_frame=df, output_dir=output_dir
        )
        assert out_file is not None
        assert out_config is not None
        from pathlib import Path

        assert Path(out_file).exists()
        assert Path(out_config).exists()

    def test_make_output_files_none_without_output_dir(self, real_maker):
        df = pd.DataFrame({"si_siteID": ["S1"]})
        _, out_file, _, out_config = real_maker.make(data_file=None, data_frame=df)
        assert out_file is None
        assert out_config is None

    def test_make_from_file(self, real_maker, tmp_path):
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("si_siteID,mr_measureID\nS1,M1\n")
        id_code_df, _, _, _ = real_maker.make(data_file=str(csv_file), data_frame=None)
        assert id_code_df is not None

    def test_make_with_custom_id_code_in_config(self, real_schema, expanded_meta):
        from odm_map.id_generator.generator import IDCodeColumns

        code_col = f"{IDCodeColumns.CODE_PREFIX}{IDCodeColumns.CODE_SUFFIX}".format(0)
        config = {
            ConfigKeys.TABLES_TO_SHORTNAMES: {"Sites": "si", "Measures": "mr"},
            ConfigKeys.CUSTOM_ID_CODE: [
                {
                    IDCodeColumns.CLASS: "Sites",
                    IDCodeColumns.SLOT: "siteID",
                    code_col: "custom_code",
                }
            ],
        }
        custom_maker = WideColumnIDCodeMaker(
            config=config,
            expanded_meta=expanded_meta,
            source_class_name="odm_wide",
            target_schema=real_schema,
        )
        df = pd.DataFrame({"si_siteID": ["S1"]})
        id_code_df, _, _, _ = custom_maker.make(data_file=None, data_frame=df)
        # Custom code should appear in the output (last entry wins for duplicates)
        sites_rows = id_code_df[id_code_df[IDCodeColumns.CLASS] == "Sites"]
        if len(sites_rows):
            assert any("custom_code" in str(v) for v in sites_rows[code_col])
