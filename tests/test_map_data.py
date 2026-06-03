"""Tests for odm_map.mapper.map_data"""

import pytest
import pandas as pd
from unittest.mock import patch

from linkml_runtime import SchemaView

from odm_map.mapper.map_data import run_mapper, DataMapper
from odm_map.utils.extra_and_tracking_slots import (
    TrackingSlots,
    EXTRA_SLOT_PREFIX,
)


# ---------------------------------------------------------------------------
# Minimal LinkML schema for testing
# ---------------------------------------------------------------------------

SOURCE_SCHEMA_YAML = """\
id: https://example.org/test_map_source
name: test_map_source
imports:
  - linkml:types
prefixes:
  src: https://example.org/test_map_source/
  linkml: https://w3id.org/linkml/
default_prefix: src
default_range: string

classes:
  Container:
    tree_root: true

  SampleData:
    attributes:
      sampleId:
        range: string
        identifier: true
        required: true
      siteId:
        range: string
        required: false
      value:
        range: string
        required: false
"""

TARGET_SCHEMA_YAML = """\
id: https://example.org/test_map_target
name: test_map_target
imports:
  - linkml:types
prefixes:
  tgt: https://example.org/test_map_target/
  linkml: https://w3id.org/linkml/
default_prefix: tgt
default_range: string

classes:
  Container:
    tree_root: true

  OutputData:
    attributes:
      outputId:
        range: string
        identifier: true
        required: true
      label:
        range: string
        required: false
      score:
        range: string
        required: false
"""


@pytest.fixture
def source_schema_path(tmp_path):
    p = tmp_path / "source_schema.yaml"
    p.write_text(SOURCE_SCHEMA_YAML)
    return p


@pytest.fixture
def target_schema_path(tmp_path):
    p = tmp_path / "target_schema.yaml"
    p.write_text(TARGET_SCHEMA_YAML)
    return p


@pytest.fixture
def source_schema(source_schema_path):
    return SchemaView(str(source_schema_path))


@pytest.fixture
def target_schema(target_schema_path):
    return SchemaView(str(target_schema_path))


# ---------------------------------------------------------------------------
# TestRunMapper
# ---------------------------------------------------------------------------


class TestRunMapper:
    def test_returns_file_index_and_mapped_data(self, source_schema):
        mapped = {"SampleData": [{"sampleId": "s1"}]}
        with patch("odm_map.mapper.map_data.Session") as MockSession:
            mock_session = MockSession.return_value
            mock_session.transform.return_value = mapped
            idx, result = run_mapper(
                data={"SampleData": [{"sampleId": "s1"}]},
                mapper_spec={},
                source_schema=source_schema,
                file_index=3,
            )
        assert idx == 3
        assert result is mapped

    def test_file_index_none_returned_unchanged(self, source_schema):
        with patch("odm_map.mapper.map_data.Session") as MockSession:
            MockSession.return_value.transform.return_value = {}
            idx, _ = run_mapper(
                data={},
                mapper_spec={},
                source_schema=source_schema,
                file_index=None,
            )
        assert idx is None

    def test_sets_source_schema_on_session(self, source_schema):
        with patch("odm_map.mapper.map_data.Session") as MockSession:
            mock_session = MockSession.return_value
            mock_session.transform.return_value = {}
            run_mapper(
                data={},
                mapper_spec={"id": "test"},
                source_schema=source_schema,
            )
        mock_session.set_source_schema.assert_called_once_with(source_schema)

    def test_sets_mapper_spec_on_session(self, source_schema):
        spec = {"id": "https://example.org/mapper"}
        with patch("odm_map.mapper.map_data.Session") as MockSession:
            mock_session = MockSession.return_value
            mock_session.transform.return_value = {}
            run_mapper(
                data={},
                mapper_spec=spec,
                source_schema=source_schema,
            )
        mock_session.set_object_transformer.assert_called_once_with(spec)

    def test_unrestricted_eval_is_applied(self, source_schema):
        with patch("odm_map.mapper.map_data.Session") as MockSession:
            mock_session = MockSession.return_value
            mock_session.transform.return_value = {}
            run_mapper(
                data={},
                mapper_spec={},
                source_schema=source_schema,
                unrestricted_eval=True,
            )
        assert mock_session.object_transformer.unrestricted_eval is True

    def test_transform_called_with_data(self, source_schema):
        data = {"SampleData": [{"sampleId": "s1"}]}
        with patch("odm_map.mapper.map_data.Session") as MockSession:
            mock_session = MockSession.return_value
            mock_session.transform.return_value = {}
            run_mapper(data=data, mapper_spec={}, source_schema=source_schema)
        mock_session.transform.assert_called_once_with(data)


class TestRunMapperWorker:
    def test_init_sets_worker_schema(self, source_schema):
        from odm_map.mapper import map_data as md

        md._init_map_worker(source_schema)
        assert md._WORKER_SOURCE_SCHEMA is source_schema

    def test_worker_uses_initialized_schema(self, source_schema):
        from odm_map.mapper import map_data as md

        # The worker must read the schema from the per-worker global (set by the Pool
        # initializer) rather than receiving it as a per-task argument.
        md._init_map_worker(source_schema)
        with patch("odm_map.mapper.map_data.Session") as MockSession:
            mock_session = MockSession.return_value
            mock_session.transform.return_value = {"OutputData": []}
            idx, _ = md._run_mapper_worker(
                file_index=5,
                data={"SampleData": [{"sampleId": "s1"}]},
                mapper_spec={},
                unrestricted_eval=False,
            )
        assert idx == 5
        mock_session.set_source_schema.assert_called_once_with(source_schema)


class TestRunWithNoTargetSchema:
    def test_run_without_target_schema_does_not_crash(
        self, source_schema_path, tmp_path
    ):
        # A target schema is optional. When none is supplied, run() must not try to add
        # tracking-slot derivations (which require a target schema) and must not crash.
        mappers_dir = tmp_path / "mappers"
        mappers_dir.mkdir()
        # The mapper file only needs to be valid YAML here; run_mapper is patched out.
        (mappers_dir / "m.yaml").write_text("class_derivations: {}\n")
        output_dir = tmp_path / "out"

        data_frames = {
            "SampleData": [pd.DataFrame({"sampleId": ["S1"], "value": ["10"]})]
        }

        with patch("odm_map.mapper.map_data.run_mapper") as mock_run:
            mock_run.return_value = (0, {})
            dm = DataMapper()
            result, _ = dm.run(
                data_files=None,
                data_frames=data_frames,
                output_dir=str(output_dir),
                source_schema_file=str(source_schema_path),
                target_schema_file=None,
                mappers_dir=str(mappers_dir),
            )

        # run_mapper was invoked (mapping proceeded) and no exception was raised.
        assert mock_run.called
        assert result == {}


# ---------------------------------------------------------------------------
# TestSortMappedData
# ---------------------------------------------------------------------------


class TestSortMappedData:
    def _df(self, rows):
        return pd.DataFrame(rows)

    def test_sorts_by_source_class_then_file_then_row(self):
        dm = DataMapper()
        df = self._df(
            [
                {
                    TrackingSlots.SOURCE_CLASS: "B",
                    TrackingSlots.SOURCE_FILE: "f1",
                    TrackingSlots.SOURCE_ROW: 1,
                    "v": "b1",
                },
                {
                    TrackingSlots.SOURCE_CLASS: "A",
                    TrackingSlots.SOURCE_FILE: "f1",
                    TrackingSlots.SOURCE_ROW: 2,
                    "v": "a2",
                },
                {
                    TrackingSlots.SOURCE_CLASS: "A",
                    TrackingSlots.SOURCE_FILE: "f1",
                    TrackingSlots.SOURCE_ROW: 1,
                    "v": "a1",
                },
            ]
        )
        result = dm.sort_mapped_data(df)
        assert result["v"].tolist() == ["a1", "a2", "b1"]

    def test_index_is_reset_after_sort(self):
        dm = DataMapper()
        df = self._df(
            [
                {
                    TrackingSlots.SOURCE_CLASS: "B",
                    TrackingSlots.SOURCE_FILE: "f1",
                    TrackingSlots.SOURCE_ROW: 1,
                },
                {
                    TrackingSlots.SOURCE_CLASS: "A",
                    TrackingSlots.SOURCE_FILE: "f1",
                    TrackingSlots.SOURCE_ROW: 1,
                },
            ]
        )
        result = dm.sort_mapped_data(df)
        assert list(result.index) == [0, 1]

    def test_already_sorted_unchanged(self):
        dm = DataMapper()
        df = self._df(
            [
                {
                    TrackingSlots.SOURCE_CLASS: "A",
                    TrackingSlots.SOURCE_FILE: "f1",
                    TrackingSlots.SOURCE_ROW: 1,
                    "v": "x",
                },
                {
                    TrackingSlots.SOURCE_CLASS: "A",
                    TrackingSlots.SOURCE_FILE: "f1",
                    TrackingSlots.SOURCE_ROW: 2,
                    "v": "y",
                },
            ]
        )
        result = dm.sort_mapped_data(df)
        assert result["v"].tolist() == ["x", "y"]

    def test_original_df_not_modified(self):
        dm = DataMapper()
        df = self._df(
            [
                {
                    TrackingSlots.SOURCE_CLASS: "B",
                    TrackingSlots.SOURCE_FILE: "f1",
                    TrackingSlots.SOURCE_ROW: 1,
                },
                {
                    TrackingSlots.SOURCE_CLASS: "A",
                    TrackingSlots.SOURCE_FILE: "f1",
                    TrackingSlots.SOURCE_ROW: 1,
                },
            ]
        )
        original_index = list(df.index)
        dm.sort_mapped_data(df)
        assert list(df.index) == original_index

    def test_sorts_by_source_row_numerically(self):
        dm = DataMapper()
        df = self._df(
            [
                {
                    TrackingSlots.SOURCE_CLASS: "A",
                    TrackingSlots.SOURCE_FILE: "f1",
                    TrackingSlots.SOURCE_ROW: 10,
                    "v": "last",
                },
                {
                    TrackingSlots.SOURCE_CLASS: "A",
                    TrackingSlots.SOURCE_FILE: "f1",
                    TrackingSlots.SOURCE_ROW: 2,
                    "v": "first",
                },
            ]
        )
        result = dm.sort_mapped_data(df)
        assert result["v"].tolist() == ["first", "last"]

    def test_stable_sort_preserves_equal_row_order(self):
        dm = DataMapper()
        df = self._df(
            [
                {
                    TrackingSlots.SOURCE_CLASS: "A",
                    TrackingSlots.SOURCE_FILE: "f1",
                    TrackingSlots.SOURCE_ROW: 1,
                    "v": "x1",
                },
                {
                    TrackingSlots.SOURCE_CLASS: "A",
                    TrackingSlots.SOURCE_FILE: "f1",
                    TrackingSlots.SOURCE_ROW: 1,
                    "v": "x2",
                },
            ]
        )
        result = dm.sort_mapped_data(df)
        # Stable sort means x1 still comes before x2
        assert result["v"].tolist() == ["x1", "x2"]

    def test_single_row_returns_same_row(self):
        dm = DataMapper()
        df = self._df(
            [
                {
                    TrackingSlots.SOURCE_CLASS: "A",
                    TrackingSlots.SOURCE_FILE: "f1",
                    TrackingSlots.SOURCE_ROW: 1,
                    "v": "only",
                },
            ]
        )
        result = dm.sort_mapped_data(df)
        assert result["v"].tolist() == ["only"]

    def test_sorts_by_source_file_as_secondary_key(self):
        dm = DataMapper()
        df = self._df(
            [
                {
                    TrackingSlots.SOURCE_CLASS: "A",
                    TrackingSlots.SOURCE_FILE: "f2",
                    TrackingSlots.SOURCE_ROW: 1,
                    "v": "f2",
                },
                {
                    TrackingSlots.SOURCE_CLASS: "A",
                    TrackingSlots.SOURCE_FILE: "f1",
                    TrackingSlots.SOURCE_ROW: 1,
                    "v": "f1",
                },
            ]
        )
        result = dm.sort_mapped_data(df)
        assert result["v"].tolist() == ["f1", "f2"]


# ---------------------------------------------------------------------------
# TestMakeDataSplits
# ---------------------------------------------------------------------------


class TestMakeDataSplits:
    def test_small_data_returns_unsplit(self):
        dm = DataMapper()
        data = {"A": list(range(10))}
        result = dm.make_data_splits(data, num_splits=4, min_split_size=100)
        assert result == [data]

    def test_splits_correct_number_of_splits(self):
        dm = DataMapper()
        data = {"A": list(range(200))}
        result = dm.make_data_splits(data, num_splits=2, min_split_size=1)
        assert len(result) == 2

    def test_splits_cover_all_rows(self):
        dm = DataMapper()
        rows = list(range(200))
        data = {"A": rows}
        result = dm.make_data_splits(data, num_splits=4, min_split_size=1)
        all_rows = [r for split in result for r in split["A"]]
        assert sorted(all_rows) == rows

    def test_no_duplicate_rows_across_splits(self):
        dm = DataMapper()
        rows = list(range(100))
        data = {"A": rows}
        result = dm.make_data_splits(data, num_splits=3, min_split_size=1)
        all_rows = [r for split in result for r in split["A"]]
        assert len(all_rows) == len(set(all_rows))

    def test_empty_splits_excluded(self):
        dm = DataMapper()
        data = {"A": [1, 2, 3], "B": [10, 20]}
        result = dm.make_data_splits(data, num_splits=10, min_split_size=1)
        for split in result:
            assert all(len(v) > 0 for v in split.values())

    def test_multiple_tables_split_independently(self):
        dm = DataMapper()
        data = {"A": list(range(200)), "B": list(range(100))}
        result = dm.make_data_splits(data, num_splits=2, min_split_size=1)
        assert len(result) == 2

    def test_single_row_no_split_if_below_min(self):
        dm = DataMapper()
        data = {"A": [42]}
        result = dm.make_data_splits(data, num_splits=4, min_split_size=10)
        assert result == [data]

    def test_num_splits_one_returns_original(self):
        dm = DataMapper()
        data = {"A": list(range(500))}
        result = dm.make_data_splits(data, num_splits=1, min_split_size=1)
        assert len(result) == 1
        assert result[0]["A"] == data["A"]

    def test_shorter_table_not_repeated_in_later_splits(self):
        dm = DataMapper()
        # "B" has only 1 row while "A" has 200 — "B" should only appear in the first split
        data = {"A": list(range(200)), "B": [99]}
        result = dm.make_data_splits(data, num_splits=2, min_split_size=1)
        b_in_second = result[1].get("B", [])
        assert len(b_in_second) == 0


# ---------------------------------------------------------------------------
# TestPrepareData
# ---------------------------------------------------------------------------


class TestPrepareData:
    def test_recognized_class_included(self, source_schema):
        dm = DataMapper()
        df = pd.DataFrame({"sampleId": ["s1"], "siteId": ["site1"]})
        result = dm.prepare_data({"SampleData": [df]}, source_schema)
        assert "SampleData" in result

    def test_unrecognized_class_excluded(self, source_schema):
        dm = DataMapper()
        df = pd.DataFrame({"col": ["val"]})
        result = dm.prepare_data({"NoSuchClass": [df]}, source_schema)
        assert "NoSuchClass" not in result

    def test_returns_list_of_dicts(self, source_schema):
        dm = DataMapper()
        df = pd.DataFrame({"sampleId": ["s1", "s2"], "siteId": ["a", "b"]})
        result = dm.prepare_data({"SampleData": [df]}, source_schema)
        rows = result["SampleData"]
        assert isinstance(rows, list)
        assert all(isinstance(r, dict) for r in rows)

    def test_row_count_matches_input(self, source_schema):
        dm = DataMapper()
        df = pd.DataFrame({"sampleId": ["s1", "s2", "s3"]})
        result = dm.prepare_data({"SampleData": [df]}, source_schema)
        assert len(result["SampleData"]) == 3

    def test_missing_schema_slots_added(self, source_schema):
        dm = DataMapper()
        # Provide only sampleId, missing siteId and value
        df = pd.DataFrame({"sampleId": ["s1"]})
        result = dm.prepare_data({"SampleData": [df]}, source_schema)
        row = result["SampleData"][0]
        assert "siteId" in row
        assert "value" in row

    def test_unrecognized_columns_dropped(self, source_schema):
        dm = DataMapper()
        df = pd.DataFrame({"sampleId": ["s1"], "nonExistentCol": ["x"]})
        result = dm.prepare_data({"SampleData": [df]}, source_schema)
        row = result["SampleData"][0]
        assert "nonExistentCol" not in row

    def test_input_dataframe_not_mutated(self, source_schema):
        # prepare_data must not add the missing slot columns to the caller's DataFrame.
        dm = DataMapper()
        df = pd.DataFrame({"sampleId": ["s1"]})
        original_columns = list(df.columns)
        dm.prepare_data({"SampleData": [df]}, source_schema)
        assert list(df.columns) == original_columns

    def test_empty_dataframe_skipped(self, source_schema):
        dm = DataMapper()
        df = pd.DataFrame({"sampleId": []})
        result = dm.prepare_data({"SampleData": [df]}, source_schema)
        assert "SampleData" not in result

    def test_none_dataframe_skipped(self, source_schema):
        dm = DataMapper()
        result = dm.prepare_data({"SampleData": [None]}, source_schema)
        assert "SampleData" not in result

    def test_multiple_dataframes_combined(self, source_schema):
        dm = DataMapper()
        df1 = pd.DataFrame({"sampleId": ["s1"]})
        df2 = pd.DataFrame({"sampleId": ["s2"]})
        result = dm.prepare_data({"SampleData": [df1, df2]}, source_schema)
        assert len(result["SampleData"]) == 2

    def test_accepts_schema_path_string(self, source_schema_path):
        dm = DataMapper()
        df = pd.DataFrame({"sampleId": ["s1"]})
        result = dm.prepare_data({"SampleData": [df]}, str(source_schema_path))
        assert "SampleData" in result

    def test_tracking_slots_preserved_when_in_schema(self, source_schema):
        # prepare_data only keeps columns in class_definition.attributes, so tracking
        # slots must be added to the schema first (as DataMapper.run() does).
        from odm_map.utils.extra_and_tracking_slots import (
            add_extra_and_tracking_slots_to_schema,
        )

        dm = DataMapper()
        df = pd.DataFrame(
            {
                "sampleId": ["s1"],
                TrackingSlots.SOURCE_CLASS: ["SampleData"],
                TrackingSlots.SOURCE_FILE: ["file.csv"],
                TrackingSlots.SOURCE_ROW: [1],
            }
        )
        data_frames = {"SampleData": [df]}
        add_extra_and_tracking_slots_to_schema(data_frames, source_schema)
        result = dm.prepare_data(data_frames, source_schema)
        row = result["SampleData"][0]
        assert TrackingSlots.SOURCE_CLASS in row

    def test_tracking_slots_dropped_when_not_in_schema(self, source_schema):
        dm = DataMapper()
        df = pd.DataFrame(
            {
                "sampleId": ["s1"],
                TrackingSlots.SOURCE_CLASS: ["SampleData"],
            }
        )
        result = dm.prepare_data({"SampleData": [df]}, source_schema)
        row = result["SampleData"][0]
        assert TrackingSlots.SOURCE_CLASS not in row


# ---------------------------------------------------------------------------
# TestConvertMappedDataToDataframes
# ---------------------------------------------------------------------------


class TestConvertMappedDataToDataframes:
    def test_basic_conversion(self, target_schema):
        dm = DataMapper()
        mapped = {"OutputData": [{"outputId": "o1", "label": "L1"}]}
        result = dm.convert_mapped_data_to_dataframes(mapped, target_schema)
        assert "OutputData" in result
        assert isinstance(result["OutputData"][0], pd.DataFrame)

    def test_row_values_preserved(self, target_schema):
        dm = DataMapper()
        mapped = {"OutputData": [{"outputId": "o1", "label": "hello"}]}
        result = dm.convert_mapped_data_to_dataframes(mapped, target_schema)
        df = result["OutputData"][0]
        assert df["label"].iloc[0] == "hello"

    def test_class_name_with_brackets_resolved(self, target_schema):
        dm = DataMapper()
        mapped = {"OutputData[extra_info]": [{"outputId": "o1"}]}
        result = dm.convert_mapped_data_to_dataframes(mapped, target_schema)
        assert "OutputData" in result

    def test_unrecognized_class_excluded(self, target_schema):
        dm = DataMapper()
        mapped = {"NoSuchClass": [{"col": "val"}]}
        result = dm.convert_mapped_data_to_dataframes(mapped, target_schema)
        assert "NoSuchClass" not in result

    def test_missing_schema_columns_added(self, target_schema):
        dm = DataMapper()
        # Only outputId provided; label and score should be added as None
        mapped = {"OutputData": [{"outputId": "o1"}]}
        result = dm.convert_mapped_data_to_dataframes(mapped, target_schema)
        df = result["OutputData"][0]
        assert "label" in df.columns
        assert "score" in df.columns

    def test_missing_columns_have_null_values(self, target_schema):
        dm = DataMapper()
        mapped = {"OutputData": [{"outputId": "o1"}]}
        result = dm.convert_mapped_data_to_dataframes(mapped, target_schema)
        df = result["OutputData"][0]
        assert df["label"].isna().all()

    def test_none_data_skipped(self, target_schema):
        dm = DataMapper()
        mapped = {"OutputData": None}
        result = dm.convert_mapped_data_to_dataframes(mapped, target_schema)
        assert "OutputData" not in result

    def test_target_schema_none_returns_class_as_is(self):
        dm = DataMapper()
        mapped = {"SomeClass": [{"col": "val"}]}
        result = dm.convert_mapped_data_to_dataframes(mapped, target_schema=None)
        assert "SomeClass" in result
        assert isinstance(result["SomeClass"][0], pd.DataFrame)

    def test_target_schema_none_brackets_stripped(self):
        dm = DataMapper()
        mapped = {"SomeClass[detail]": [{"col": "val"}]}
        result = dm.convert_mapped_data_to_dataframes(mapped, target_schema=None)
        assert "SomeClass" in result

    def test_extra_slots_preserved(self, target_schema):
        dm = DataMapper()
        extra_col = EXTRA_SLOT_PREFIX + "myextra"
        mapped = {"OutputData": [{"outputId": "o1", extra_col: "extra_val"}]}
        result = dm.convert_mapped_data_to_dataframes(mapped, target_schema)
        df = result["OutputData"][0]
        assert extra_col in df.columns

    def test_tracking_slots_preserved(self, target_schema):
        dm = DataMapper()
        mapped = {
            "OutputData": [
                {
                    "outputId": "o1",
                    TrackingSlots.SOURCE_CLASS: "SampleData",
                    TrackingSlots.SOURCE_ROW: 1,
                    TrackingSlots.SOURCE_FILE: "file.csv",
                }
            ]
        }
        result = dm.convert_mapped_data_to_dataframes(mapped, target_schema)
        df = result["OutputData"][0]
        assert TrackingSlots.SOURCE_CLASS in df.columns

    def test_multiple_rows_in_dataframe(self, target_schema):
        dm = DataMapper()
        mapped = {
            "OutputData": [
                {"outputId": "o1"},
                {"outputId": "o2"},
                {"outputId": "o3"},
            ]
        }
        result = dm.convert_mapped_data_to_dataframes(mapped, target_schema)
        df = result["OutputData"][0]
        assert len(df) == 3

    def test_empty_data_list_returns_empty_df(self, target_schema):
        dm = DataMapper()
        mapped = {"OutputData": []}
        result = dm.convert_mapped_data_to_dataframes(mapped, target_schema)
        df = result["OutputData"][0]
        assert len(df) == 0
