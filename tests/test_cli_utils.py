"""Tests for odm_map.utils.cli_utils"""

import pytest
import pandas as pd
from pathlib import Path
from linkml_runtime import SchemaView

from odm_map.utils.cli_utils import (
    CLASS_PREFIX_SEPARATOR,
    get_file_info,
    get_input_data_files,
    get_input_data_files_from_dir,
)
from odm_map.utils.clean_exit_error import CleanExitError


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

  Measures:
    attributes:
      measureID:
        range: string
        identifier: true
        required: true
      value:
        range: float
"""


@pytest.fixture
def schema():
    return SchemaView(SCHEMA_YAML)


@pytest.fixture
def schema_path(tmp_path):
    p = tmp_path / "test_schema.yaml"
    p.write_text(SCHEMA_YAML)
    return p


def write_csv(path: Path, content: str = "siteID,name\ns1,Site1\n") -> Path:
    path.write_text(content)
    return path


# ---------------------------------------------------------------------------
# get_file_info
# ---------------------------------------------------------------------------


class TestGetFileInfo:
    def test_csv_mapped_to_class_by_filename(self, tmp_path, schema):
        f = write_csv(tmp_path / "Sites.csv")
        result = get_file_info(f, schema=schema)
        assert "Sites" in result
        assert str(f) in [str(x) for x in result["Sites"]]

    def test_tsv_recognized(self, tmp_path, schema):
        f = write_csv(tmp_path / "Sites.tsv")
        result = get_file_info(f, schema=schema)
        assert "Sites" in result

    def test_txt_recognized(self, tmp_path, schema):
        f = write_csv(tmp_path / "Sites.txt")
        result = get_file_info(f, schema=schema)
        assert "Sites" in result

    def test_class_lookup_is_case_insensitive(self, tmp_path, schema):
        f = write_csv(tmp_path / "sites.csv")
        result = get_file_info(f, schema=schema)
        assert "Sites" in result

    def test_nonexistent_file_raises(self, tmp_path, schema):
        with pytest.raises(CleanExitError):
            get_file_info(
                tmp_path / "notexist.csv", schema=schema, exception_on_error=True
            )

    def test_nonexistent_file_no_exception_returns_none(self, tmp_path, schema):
        result = get_file_info(
            tmp_path / "notexist.csv", schema=schema, exception_on_error=False
        )
        assert result is None

    def test_unrecognized_extension_raises(self, tmp_path, schema):
        f = tmp_path / "data.json"
        f.write_text("{}")
        with pytest.raises(CleanExitError):
            get_file_info(f, schema=schema, exception_on_error=True)

    def test_unrecognized_extension_no_exception_returns_none(self, tmp_path, schema):
        f = tmp_path / "data.json"
        f.write_text("{}")
        result = get_file_info(f, schema=schema, exception_on_error=False)
        assert result is None

    def test_class_prefix_explicit(self, tmp_path, schema):
        data_file = write_csv(tmp_path / "data.csv", "measureID,value\nm1,1.0\n")
        prefixed = f"Measures{CLASS_PREFIX_SEPARATOR}{data_file}"
        result = get_file_info(Path(prefixed), schema=schema, parse_class_prefix=True)
        assert "Measures" in result

    def test_no_schema_uses_filename_as_class(self, tmp_path):
        f = write_csv(tmp_path / "Sites.csv")
        result = get_file_info(f, schema=None)
        assert "Sites" in result

    def test_excel_file_sheets_mapped_to_classes(self, tmp_path, schema):
        df = pd.DataFrame({"siteID": ["s1"], "name": ["Site1"]})
        excel_path = tmp_path / "data.xlsx"
        df.to_excel(excel_path, sheet_name="Sites", index=False)
        result = get_file_info(excel_path, schema=schema)
        assert "Sites" in result

    def test_unrecognized_class_in_filename_raises(self, tmp_path, schema):
        f = write_csv(tmp_path / "Unknown.csv")
        with pytest.raises(CleanExitError):
            get_file_info(f, schema=schema, exception_on_error=True)

    def test_unrecognized_class_in_filename_no_exception_returns_none(
        self, tmp_path, schema
    ):
        f = write_csv(tmp_path / "Unknown.csv")
        result = get_file_info(f, schema=schema, exception_on_error=False)
        assert result is None


# ---------------------------------------------------------------------------
# get_input_data_files_from_dir
# ---------------------------------------------------------------------------


class TestGetInputDataFilesFromDir:
    def test_finds_csv_file(self, tmp_path, schema):
        write_csv(tmp_path / "Sites.csv")
        result = get_input_data_files_from_dir(tmp_path, schema=schema)
        assert "Sites" in result

    def test_finds_multiple_classes(self, tmp_path, schema):
        write_csv(tmp_path / "Sites.csv")
        write_csv(tmp_path / "Measures.csv", "measureID,value\nm1,1.0\n")
        result = get_input_data_files_from_dir(tmp_path, schema=schema)
        assert "Sites" in result
        assert "Measures" in result

    def test_nonexistent_directory_raises(self, tmp_path, schema):
        with pytest.raises(CleanExitError):
            get_input_data_files_from_dir(tmp_path / "doesnotexist", schema=schema)

    def test_unrecognized_files_ignored(self, tmp_path, schema):
        (tmp_path / "README.md").write_text("ignored")
        (tmp_path / "data.json").write_text("{}")
        result = get_input_data_files_from_dir(tmp_path, schema=schema)
        assert isinstance(result, dict)

    def test_keys_are_sorted(self, tmp_path, schema):
        write_csv(tmp_path / "Sites.csv")
        write_csv(tmp_path / "Measures.csv", "measureID,value\nm1,1.0\n")
        result = get_input_data_files_from_dir(tmp_path, schema=schema)
        assert list(result.keys()) == sorted(result.keys())

    def test_empty_directory_returns_empty_dict(self, tmp_path, schema):
        result = get_input_data_files_from_dir(tmp_path, schema=schema)
        assert result == {}


# ---------------------------------------------------------------------------
# get_input_data_files
# ---------------------------------------------------------------------------


class TestGetInputDataFiles:
    def test_single_file_input(self, tmp_path, schema):
        f = write_csv(tmp_path / "Sites.csv")
        result = get_input_data_files([str(f)], schema=schema)
        assert "Sites" in result

    def test_directory_input(self, tmp_path, schema):
        write_csv(tmp_path / "Sites.csv")
        result = get_input_data_files([str(tmp_path)], schema=schema)
        assert "Sites" in result

    def test_nonexistent_input_raises(self, tmp_path, schema):
        with pytest.raises(CleanExitError):
            get_input_data_files([str(tmp_path / "notexist.csv")], schema=schema)

    def test_multiple_inputs_merged(self, tmp_path, schema):
        d1 = tmp_path / "d1"
        d1.mkdir()
        d2 = tmp_path / "d2"
        d2.mkdir()
        write_csv(d1 / "Sites.csv")
        write_csv(d2 / "Measures.csv", "measureID,value\nm1,1.0\n")
        result = get_input_data_files([str(d1), str(d2)], schema=schema)
        assert "Sites" in result
        assert "Measures" in result

    def test_same_class_files_from_multiple_dirs_combined(self, tmp_path, schema):
        d1 = tmp_path / "d1"
        d1.mkdir()
        d2 = tmp_path / "d2"
        d2.mkdir()
        write_csv(d1 / "Sites.csv", "siteID,name\ns1,A\n")
        write_csv(d2 / "Sites.csv", "siteID,name\ns2,B\n")
        result = get_input_data_files([str(d1), str(d2)], schema=schema)
        assert len(result["Sites"]) == 2

    def test_excel_file_input(self, tmp_path, schema):
        df = pd.DataFrame({"siteID": ["s1"], "name": ["Site1"]})
        excel_path = tmp_path / "data.xlsx"
        df.to_excel(excel_path, sheet_name="Sites", index=False)
        result = get_input_data_files([str(excel_path)], schema=schema)
        assert "Sites" in result
