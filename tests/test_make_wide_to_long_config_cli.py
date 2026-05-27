"""Tests for odm_map.prepare_wide_to_long.make_wide_to_long_config_cli"""

import pytest
import yaml
import pandas as pd
from unittest.mock import patch

from odm_map.prepare_wide_to_long.make_wide_to_long_config_cli import (
    MakeWideToLongConfig,
)
from odm_map.prepare_wide_to_long.wide_column_utils import ConfigKeys


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_parts_df(rows):
    """Build a minimal 'parts' DataFrame for MakeWideToLongConfig."""
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# MakeWideToLongConfig.make
# ---------------------------------------------------------------------------


class TestMakeWideToLongConfig:
    @pytest.fixture
    def parts_df(self):
        return _make_parts_df(
            [
                {
                    "partID": "covN1",
                    "partType": "measurements",
                    "mmaSet": "covN1Set",
                    "status": "active",
                    "partInstr": None,
                },
                {
                    "partID": "ph",
                    "partType": "measurements",
                    "mmaSet": "phSet",
                    "status": "active",
                    "partInstr": None,
                },
                {
                    "partID": "pcr",
                    "partType": "methods",
                    "mmaSet": "pcrSet",
                    "status": "active",
                    "partInstr": None,
                },
                {
                    "partID": "samples",
                    "partType": "tables",
                    "mmaSet": None,
                    "status": "active",
                    "partInstr": "sm",
                },
                {
                    "partID": "measures",
                    "partType": "tables",
                    "mmaSet": None,
                    "status": "active",
                    "partInstr": "mr",
                },
                {
                    "partID": "old",
                    "partType": "measurements",
                    "mmaSet": "oldSet",
                    "status": "retired",
                    "partInstr": None,
                },
            ]
        )

    def test_partid_to_mmaset_populated(self, parts_df, tmp_path):
        output_file = str(tmp_path / "config.yaml")
        with patch(
            "odm_map.prepare_wide_to_long.make_wide_to_long_config_cli.read_data_frame",
            return_value=parts_df,
        ):
            cfg = MakeWideToLongConfig(
                data_dictionary="fake.xlsx", config_template=None
            )
            cfg.make(output_file)

        assert cfg.config[ConfigKeys.PARTID_TO_MMASET]["covN1"] == "covN1Set"
        assert cfg.config[ConfigKeys.PARTID_TO_MMASET]["ph"] == "phSet"
        assert cfg.config[ConfigKeys.PARTID_TO_MMASET]["pcr"] == "pcrSet"

    def test_retired_parts_excluded(self, parts_df, tmp_path):
        output_file = str(tmp_path / "config.yaml")
        with patch(
            "odm_map.prepare_wide_to_long.make_wide_to_long_config_cli.read_data_frame",
            return_value=parts_df,
        ):
            cfg = MakeWideToLongConfig(
                data_dictionary="fake.xlsx", config_template=None
            )
            cfg.make(output_file)

        assert "old" not in cfg.config[ConfigKeys.PARTID_TO_MMASET]

    def test_tables_to_shortnames_populated(self, parts_df, tmp_path):
        output_file = str(tmp_path / "config.yaml")
        with patch(
            "odm_map.prepare_wide_to_long.make_wide_to_long_config_cli.read_data_frame",
            return_value=parts_df,
        ):
            cfg = MakeWideToLongConfig(
                data_dictionary="fake.xlsx", config_template=None
            )
            cfg.make(output_file)

        assert cfg.config[ConfigKeys.TABLES_TO_SHORTNAMES]["samples"] == "sm"
        assert cfg.config[ConfigKeys.TABLES_TO_SHORTNAMES]["measures"] == "mr"

    def test_non_table_parts_not_in_tables_to_shortnames(self, parts_df, tmp_path):
        output_file = str(tmp_path / "config.yaml")
        with patch(
            "odm_map.prepare_wide_to_long.make_wide_to_long_config_cli.read_data_frame",
            return_value=parts_df,
        ):
            cfg = MakeWideToLongConfig(
                data_dictionary="fake.xlsx", config_template=None
            )
            cfg.make(output_file)

        shortnames = cfg.config[ConfigKeys.TABLES_TO_SHORTNAMES]
        assert "covN1" not in shortnames
        assert "ph" not in shortnames

    def test_output_yaml_file_created(self, parts_df, tmp_path):
        output_file = str(tmp_path / "config.yaml")
        with patch(
            "odm_map.prepare_wide_to_long.make_wide_to_long_config_cli.read_data_frame",
            return_value=parts_df,
        ):
            cfg = MakeWideToLongConfig(
                data_dictionary="fake.xlsx", config_template=None
            )
            cfg.make(output_file)

        assert (tmp_path / "config.yaml").exists()

    def test_output_yaml_is_valid(self, parts_df, tmp_path):
        output_file = str(tmp_path / "config.yaml")
        with patch(
            "odm_map.prepare_wide_to_long.make_wide_to_long_config_cli.read_data_frame",
            return_value=parts_df,
        ):
            cfg = MakeWideToLongConfig(
                data_dictionary="fake.xlsx", config_template=None
            )
            cfg.make(output_file)

        with open(output_file) as f:
            loaded = yaml.safe_load(f)

        assert ConfigKeys.PARTID_TO_MMASET in loaded
        assert ConfigKeys.TABLES_TO_SHORTNAMES in loaded

    def test_config_template_values_preserved(self, parts_df, tmp_path):
        template_file = tmp_path / "template.yaml"
        template_content = {
            "see_headers": {
                "aggregation": {"short_name": "hAg", "slot": "mr_aggregation"}
            }
        }
        with open(template_file, "w") as f:
            yaml.safe_dump(template_content, f)

        output_file = str(tmp_path / "config.yaml")
        with patch(
            "odm_map.prepare_wide_to_long.make_wide_to_long_config_cli.read_data_frame",
            return_value=parts_df,
        ):
            cfg = MakeWideToLongConfig(
                data_dictionary="fake.xlsx",
                config_template=str(template_file),
            )
            cfg.make(output_file)

        assert ConfigKeys.SEE_HEADERS in cfg.config
        assert "aggregation" in cfg.config[ConfigKeys.SEE_HEADERS]

    def test_only_methods_and_measurements_in_mmaset(self, tmp_path):
        parts_df = _make_parts_df(
            [
                {
                    "partID": "covN1",
                    "partType": "measurements",
                    "mmaSet": "covN1Set",
                    "status": "active",
                    "partInstr": None,
                },
                {
                    "partID": "pcr",
                    "partType": "methods",
                    "mmaSet": "pcrSet",
                    "status": "active",
                    "partInstr": None,
                },
                {
                    "partID": "samples",
                    "partType": "tables",
                    "mmaSet": "tabSet",
                    "status": "active",
                    "partInstr": "sm",
                },
            ]
        )
        output_file = str(tmp_path / "config.yaml")
        with patch(
            "odm_map.prepare_wide_to_long.make_wide_to_long_config_cli.read_data_frame",
            return_value=parts_df,
        ):
            cfg = MakeWideToLongConfig(
                data_dictionary="fake.xlsx", config_template=None
            )
            cfg.make(output_file)

        # "samples" is a table type, should NOT appear in partid_to_mmaset even if it has mmaSet
        assert "samples" not in cfg.config[ConfigKeys.PARTID_TO_MMASET]
        assert "covN1" in cfg.config[ConfigKeys.PARTID_TO_MMASET]
        assert "pcr" in cfg.config[ConfigKeys.PARTID_TO_MMASET]

    def test_empty_active_parts(self, tmp_path):
        parts_df = _make_parts_df(
            [
                {
                    "partID": "old",
                    "partType": "measurements",
                    "mmaSet": "oldSet",
                    "status": "retired",
                    "partInstr": None,
                },
            ]
        )
        output_file = str(tmp_path / "config.yaml")
        with patch(
            "odm_map.prepare_wide_to_long.make_wide_to_long_config_cli.read_data_frame",
            return_value=parts_df,
        ):
            cfg = MakeWideToLongConfig(
                data_dictionary="fake.xlsx", config_template=None
            )
            cfg.make(output_file)

        assert cfg.config[ConfigKeys.PARTID_TO_MMASET] == {}
        assert cfg.config[ConfigKeys.TABLES_TO_SHORTNAMES] == {}
