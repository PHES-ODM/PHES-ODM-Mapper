"""Tests for odm_map.column_dropper.drop_columns.DropColumns"""

import pandas as pd
import pytest

from odm_map.column_dropper.drop_columns import DropColumns
from odm_map.utils.extra_and_tracking_slots import (
    TrackingSlots,
)


@pytest.fixture
def dropper():
    return DropColumns()


def _df_with_extras():
    return pd.DataFrame(
        {
            "siteID": ["s1", "s2"],
            "_extra_foo": ["a", "b"],
            "_extra_bar": ["c", "d"],
            TrackingSlots.SOURCE_CLASS: ["sites", "sites"],
            TrackingSlots.SOURCE_ROW: [0, 1],
        }
    )


class TestDropExtraColumns:
    def test_drops_extra_columns(self, dropper):
        df = _df_with_extras()
        result = dropper.drop_columns(
            data_files=None,
            data_frames={"sites": [df]},
            drop_extra_columns=True,
        )
        result_df = result["sites"][0]
        assert "_extra_foo" not in result_df.columns
        assert "_extra_bar" not in result_df.columns
        assert "siteID" in result_df.columns

    def test_tracking_columns_kept_when_only_extra_dropped(self, dropper):
        df = _df_with_extras()
        result = dropper.drop_columns(
            data_files=None,
            data_frames={"sites": [df]},
            drop_extra_columns=True,
        )
        result_df = result["sites"][0]
        assert TrackingSlots.SOURCE_CLASS in result_df.columns


class TestDropTrackingColumns:
    def test_drops_tracking_columns(self, dropper):
        df = _df_with_extras()
        result = dropper.drop_columns(
            data_files=None,
            data_frames={"sites": [df]},
            drop_tracking_columns=True,
        )
        result_df = result["sites"][0]
        assert TrackingSlots.SOURCE_CLASS not in result_df.columns
        assert TrackingSlots.SOURCE_ROW not in result_df.columns
        assert "siteID" in result_df.columns

    def test_extra_columns_kept_when_only_tracking_dropped(self, dropper):
        df = _df_with_extras()
        result = dropper.drop_columns(
            data_files=None,
            data_frames={"sites": [df]},
            drop_tracking_columns=True,
        )
        result_df = result["sites"][0]
        assert "_extra_foo" in result_df.columns


class TestDropBothExtraAndTracking:
    def test_drops_both(self, dropper):
        df = _df_with_extras()
        result = dropper.drop_columns(
            data_files=None,
            data_frames={"sites": [df]},
            drop_extra_columns=True,
            drop_tracking_columns=True,
        )
        result_df = result["sites"][0]
        assert "_extra_foo" not in result_df.columns
        assert "_extra_bar" not in result_df.columns
        assert TrackingSlots.SOURCE_CLASS not in result_df.columns
        assert TrackingSlots.SOURCE_ROW not in result_df.columns
        assert "siteID" in result_df.columns


class TestNoDrop:
    def test_no_flags_keeps_all_columns(self, dropper):
        df = _df_with_extras()
        original_cols = set(df.columns)
        result = dropper.drop_columns(
            data_files=None,
            data_frames={"sites": [df]},
            drop_extra_columns=False,
            drop_tracking_columns=False,
        )
        result_df = result["sites"][0]
        assert set(result_df.columns) == original_cols


class TestMultipleDataFrames:
    def test_drops_from_all_dataframes(self, dropper):
        df1 = pd.DataFrame({"id": ["a"], "_extra_x": ["1"]})
        df2 = pd.DataFrame({"id": ["b"], "_extra_x": ["2"]})
        result = dropper.drop_columns(
            data_files=None,
            data_frames={"C": [df1, df2]},
            drop_extra_columns=True,
        )
        for df in result["C"]:
            assert "_extra_x" not in df.columns
            assert "id" in df.columns


class TestEmptyDataFrames:
    def test_empty_data_frames_dict(self, dropper):
        result = dropper.drop_columns(
            data_files=None,
            data_frames={},
            drop_extra_columns=True,
        )
        assert result == {}

    def test_none_data_frames_treated_as_empty(self, dropper):
        result = dropper.drop_columns(
            data_files=None,
            data_frames=None,
            drop_extra_columns=True,
        )
        assert result == {}


class TestKeepColumnsInSchemaOnly:
    def test_requires_schema_raises_if_none(self, dropper):
        df = pd.DataFrame({"a": [1], "b": [2]})
        with pytest.raises(ValueError, match="Schema must be specified"):
            dropper.drop_columns(
                data_files=None,
                data_frames={"C": [df]},
                keep_columns_in_schema_only=True,
                schema=None,
            )
