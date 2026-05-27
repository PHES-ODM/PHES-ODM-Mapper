"""Tests for odm_map.utils.pipeline_module"""

import zipfile
import pytest
import yaml
from pathlib import Path

from odm_map.utils.pipeline_module import (
    CONFIG_FILE,
    MODULE_TITLE_KEY,
    SHARED_MODULE,
    TEMP_DIR_TAG,
    PipelineModule,
    get_all_modules,
)
from odm_map.utils.clean_exit_error import CleanExitError


def make_module_dir(base: Path, module_name: str, title: str = "Test Module") -> Path:
    module_dir = base / module_name
    module_dir.mkdir(parents=True)
    config = {MODULE_TITLE_KEY: title}
    (module_dir / CONFIG_FILE).write_text(yaml.dump(config))
    return module_dir


# ---------------------------------------------------------------------------
# get_all_modules
# ---------------------------------------------------------------------------


class TestGetAllModules:
    def test_returns_list(self):
        result = get_all_modules()
        assert isinstance(result, list)

    def test_shared_module_excluded(self):
        result = get_all_modules()
        assert SHARED_MODULE not in result

    def test_result_is_sorted(self):
        result = get_all_modules()
        assert result == sorted(result)

    def test_include_titles_adds_parenthetical(self):
        result = get_all_modules(include_titles=True)
        if result:
            assert "(" in result[0] and ")" in result[0]

    def test_include_titles_returns_list(self):
        result = get_all_modules(include_titles=True)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# PipelineModule init — directory path
# ---------------------------------------------------------------------------


class TestPipelineModuleInitFromDirectory:
    def test_loads_from_directory(self, tmp_path):
        module_dir = make_module_dir(tmp_path, "my_module")
        pm = PipelineModule(module=None, module_path=str(module_dir))
        assert pm.module_name == "my_module"

    def test_builtin_is_false_for_path_module(self, tmp_path):
        module_dir = make_module_dir(tmp_path, "my_module")
        pm = PipelineModule(module=None, module_path=str(module_dir))
        assert pm.builtin_module is False

    def test_module_dir_is_absolute(self, tmp_path):
        module_dir = make_module_dir(tmp_path, "my_module")
        pm = PipelineModule(module=None, module_path=str(module_dir))
        assert pm.module_dir.is_absolute()

    def test_str_representation_is_path(self, tmp_path):
        module_dir = make_module_dir(tmp_path, "my_module")
        pm = PipelineModule(module=None, module_path=str(module_dir))
        assert str(module_dir) in str(pm)


# ---------------------------------------------------------------------------
# PipelineModule init — error cases
# ---------------------------------------------------------------------------


class TestPipelineModuleInitErrors:
    def test_invalid_module_name_raises(self):
        with pytest.raises(CleanExitError):
            PipelineModule(module="this_module_does_not_exist_12345", module_path=None)

    def test_non_dir_non_zip_path_raises(self, tmp_path):
        bad_path = tmp_path / "not_a_module.txt"
        bad_path.write_text("not a module")
        with pytest.raises(CleanExitError):
            PipelineModule(module=None, module_path=str(bad_path))

    def test_neither_module_nor_path_raises(self):
        with pytest.raises(CleanExitError):
            PipelineModule(module=None, module_path=None)


# ---------------------------------------------------------------------------
# PipelineModule init — zip file
# ---------------------------------------------------------------------------


class TestPipelineModuleInitFromZip:
    def test_loads_from_zip(self, tmp_path):
        module_dir = tmp_path / "zip_contents"
        module_dir.mkdir()
        config = {MODULE_TITLE_KEY: "Zip Module"}
        (module_dir / CONFIG_FILE).write_text(yaml.dump(config))

        zip_path = tmp_path / "my_module.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(module_dir / CONFIG_FILE, CONFIG_FILE)

        pm = PipelineModule(module=None, module_path=str(zip_path))
        assert pm.module_dir is not None

    def test_zip_without_config_raises(self, tmp_path):
        zip_path = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_path, "w"):
            pass
        with pytest.raises(CleanExitError):
            PipelineModule(module=None, module_path=str(zip_path))


# ---------------------------------------------------------------------------
# config property
# ---------------------------------------------------------------------------


class TestPipelineModuleConfig:
    def test_config_loaded_correctly(self, tmp_path):
        module_dir = make_module_dir(tmp_path, "my_module", title="My Title")
        pm = PipelineModule(module=None, module_path=str(module_dir))
        assert pm.config[MODULE_TITLE_KEY] == "My Title"

    def test_config_cached_on_second_access(self, tmp_path):
        module_dir = make_module_dir(tmp_path, "my_module")
        pm = PipelineModule(module=None, module_path=str(module_dir))
        first = pm.config
        second = pm.config
        assert first is second

    def test_missing_config_file_raises(self, tmp_path):
        module_dir = make_module_dir(tmp_path, "my_module")
        pm = PipelineModule(module=None, module_path=str(module_dir))
        (module_dir / CONFIG_FILE).unlink()
        pm._config = None
        with pytest.raises(CleanExitError):
            _ = pm.config


# ---------------------------------------------------------------------------
# get_module_path
# ---------------------------------------------------------------------------


class TestGetModulePath:
    def test_relative_path_resolved_within_module(self, tmp_path):
        module_dir = make_module_dir(tmp_path, "my_module")
        pm = PipelineModule(module=None, module_path=str(module_dir))
        result = pm.get_module_path("config.yaml")
        assert result == module_dir.resolve() / "config.yaml"

    def test_none_returns_none(self, tmp_path):
        module_dir = make_module_dir(tmp_path, "my_module")
        pm = PipelineModule(module=None, module_path=str(module_dir))
        assert pm.get_module_path(None) is None

    def test_empty_string_returns_none(self, tmp_path):
        module_dir = make_module_dir(tmp_path, "my_module")
        pm = PipelineModule(module=None, module_path=str(module_dir))
        assert pm.get_module_path("") is None

    def test_list_of_paths_returns_list(self, tmp_path):
        module_dir = make_module_dir(tmp_path, "my_module")
        pm = PipelineModule(module=None, module_path=str(module_dir))
        results = pm.get_module_path(["a.yaml", "b.yaml"])
        assert isinstance(results, list)
        assert len(results) == 2

    def test_temp_dir_tag_resolved(self, tmp_path):
        module_dir = make_module_dir(tmp_path, "my_module")
        pm = PipelineModule(module=None, module_path=str(module_dir))
        temp_dir = tmp_path / "temp"
        pm.set_temp_dir(temp_dir)
        result = pm.get_module_path(f"{TEMP_DIR_TAG}/schema.yaml")
        assert result == temp_dir / "schema.yaml"

    def test_get_module_config_path(self, tmp_path):
        module_dir = make_module_dir(tmp_path, "my_module")
        pm = PipelineModule(module=None, module_path=str(module_dir))
        result = pm.get_module_config_path()
        assert result.name == CONFIG_FILE
