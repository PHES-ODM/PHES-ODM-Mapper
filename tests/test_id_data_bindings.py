"""Tests for odm_map.id_generator.id_data_bindings.DataBindings"""

from unittest.mock import MagicMock

import pytest

from odm_map.id_generator.generator_config_keys import ConfigKeys
from odm_map.id_generator.id_data_bindings import EMPTY_VALUE, DataBindings
from odm_map.id_generator.id_value import IDValue


def make_gen(current_class="samples", current_row_index=0):
    gen = MagicMock()
    gen.current_class = current_class
    gen.current_row_index = current_row_index
    return gen


# ---------------------------------------------------------------------------
# __str__
# ---------------------------------------------------------------------------


class TestStr:
    def test_str_without_sub_classes_contains_root_class(self):
        gen = make_gen()
        binding = DataBindings(gen, root_class="samples", sub_class_names=[])
        assert "samples" in str(binding)

    def test_str_with_sub_classes_contains_sub_class_names(self):
        gen = make_gen()
        binding = DataBindings(
            gen, root_class=None, sub_class_names=["samples", "sites"]
        )
        s = str(binding)
        assert "samples" in s
        assert "sites" in s

    def test_str_no_sub_classes_shows_none(self):
        gen = make_gen()
        binding = DataBindings(gen, root_class="samples", sub_class_names=None)
        s = str(binding)
        assert "None" in s or "samples" in s


# ---------------------------------------------------------------------------
# __getattr__ with sub_classes
# ---------------------------------------------------------------------------


class TestGetAttrWithSubClasses:
    def test_known_class_returns_data_bindings(self):
        gen = make_gen()
        binding = DataBindings(
            gen, root_class=None, sub_class_names=["samples", "sites"]
        )
        sub = binding.samples
        assert isinstance(sub, DataBindings)
        assert sub.root_class == "samples"

    def test_unknown_class_raises_attribute_error(self):
        gen = make_gen()
        binding = DataBindings(gen, root_class=None, sub_class_names=["samples"])
        with pytest.raises(AttributeError):
            _ = binding.unknown_class


# ---------------------------------------------------------------------------
# __getattr__ without sub_classes (root_class set)
# ---------------------------------------------------------------------------


class TestGetAttrWithRootClass:
    def test_slot_access_calls_get_first_linked_value(self):
        gen = make_gen()
        gen.get_first_linked_value.return_value = "sampleValue"
        gen.data = {"samples": MagicMock()}
        gen.data["samples"].primary_key = "sampleID"

        binding = DataBindings(gen, root_class="samples", sub_class_names=None)
        # Trigger attribute access
        _ = binding.sampleName
        assert gen.get_first_linked_value.called

    def test_slot_access_propagates_value(self):
        gen = make_gen()
        gen.get_first_linked_value.return_value = "hello"
        gen.data = {"samples": MagicMock()}
        gen.data["samples"].primary_key = "sampleID"

        binding = DataBindings(gen, root_class="samples", sub_class_names=None)
        assert binding.sampleName == "hello"


# ---------------------------------------------------------------------------
# get method
# ---------------------------------------------------------------------------


class TestGetMethod:
    def test_get_is_equivalent_to_getattr(self):
        gen = make_gen()
        gen.get_first_linked_value.return_value = "myValue"
        gen.data = {"samples": MagicMock()}
        gen.data["samples"].primary_key = "sampleID"

        binding = DataBindings(gen, root_class="samples", sub_class_names=None)
        assert binding.get("sampleName") == binding.sampleName


# ---------------------------------------------------------------------------
# has_column
# ---------------------------------------------------------------------------


class TestHasColumn:
    def test_root_class_none_always_false(self):
        gen = make_gen()
        binding = DataBindings(gen, root_class=None, sub_class_names=["samples"])
        assert not binding.has_column("sampleID")

    def test_root_class_set_delegates_to_generator_data(self):
        gen = make_gen()
        mock_data = MagicMock()
        mock_data.has_column.return_value = True
        gen.data = {"samples": mock_data}

        binding = DataBindings(gen, root_class="samples", sub_class_names=None)
        result = binding.has_column("sampleID")
        mock_data.has_column.assert_called_once_with("sampleID")
        assert result is True

    def test_root_class_set_column_not_found(self):
        gen = make_gen()
        mock_data = MagicMock()
        mock_data.has_column.return_value = False
        gen.data = {"samples": mock_data}

        binding = DataBindings(gen, root_class="samples", sub_class_names=None)
        assert not binding.has_column("nonexistent")


# ---------------------------------------------------------------------------
# get_named_linkage_path
# ---------------------------------------------------------------------------


class TestGetNamedLinkagePath:
    def test_no_named_linkages_in_config_raises_value_error(self):
        gen = make_gen()
        gen.config = {}
        binding = DataBindings(gen, root_class="samples", sub_class_names=None)
        with pytest.raises(ValueError, match="no named linkage paths"):
            binding.get_named_linkage_path("samples", "my_path")

    def test_linkage_path_does_not_exist_raises_value_error(self):
        gen = make_gen()
        gen.config = {ConfigKeys.NAMED_CLASS_LINKAGES: {"other_path": {}}}
        binding = DataBindings(gen, root_class="samples", sub_class_names=None)
        with pytest.raises(ValueError, match="does not exist"):
            binding.get_named_linkage_path("samples", "my_path")

    def test_no_route_from_source_to_root_raises_value_error(self):
        gen = make_gen()
        gen.config = {ConfigKeys.NAMED_CLASS_LINKAGES: {"my_path": {"measures": {}}}}
        binding = DataBindings(gen, root_class="samples", sub_class_names=None)
        with pytest.raises(ValueError, match="no path"):
            binding.get_named_linkage_path("measures", "my_path")

    def test_valid_path_returned(self):
        gen = make_gen()
        expected_path = {"slot": "sampleID"}
        gen.config = {
            ConfigKeys.NAMED_CLASS_LINKAGES: {
                "my_path": {"samples": {"samples": expected_path}}
            }
        }
        binding = DataBindings(gen, root_class="samples", sub_class_names=None)
        result = binding.get_named_linkage_path("samples", "my_path")
        assert result == expected_path


# ---------------------------------------------------------------------------
# get_first_linked_value
# ---------------------------------------------------------------------------


class TestGetFirstLinkedValue:
    def _make_binding(self, gen, replace_empty_values=True):
        return DataBindings(
            gen,
            root_class="samples",
            sub_class_names=None,
            replace_empty_values=replace_empty_values,
        )

    def test_calls_generator_get_first_linked_value(self):
        gen = make_gen()
        gen.get_first_linked_value.return_value = "sampleVal"
        gen.data = {"samples": MagicMock()}
        gen.data["samples"].primary_key = "sampleID"

        binding = self._make_binding(gen)
        binding.get_first_linked_value("sampleName")
        assert gen.get_first_linked_value.called

    def test_float_with_no_decimals_converted_to_int(self):
        gen = make_gen()
        gen.get_first_linked_value.return_value = 3.0
        gen.data = {"samples": MagicMock()}
        gen.data["samples"].primary_key = "sampleID"

        binding = self._make_binding(gen)
        result = binding.get_first_linked_value("someSlot")
        assert result == 3
        assert isinstance(result, int)

    def test_float_with_decimals_not_converted(self):
        gen = make_gen()
        gen.get_first_linked_value.return_value = 3.5
        gen.data = {"samples": MagicMock()}
        gen.data["samples"].primary_key = "sampleID"

        binding = self._make_binding(gen)
        result = binding.get_first_linked_value("someSlot")
        assert result == 3.5
        assert isinstance(result, float)

    def test_empty_value_replaced_when_replace_empty_values_true(self):
        gen = make_gen()
        gen.get_first_linked_value.return_value = None
        gen.data = {"samples": MagicMock()}
        gen.data["samples"].primary_key = "sampleID"

        binding = self._make_binding(gen, replace_empty_values=True)
        result = binding.get_first_linked_value("someSlot")
        assert result == EMPTY_VALUE

    def test_empty_value_returns_empty_string_when_replace_empty_values_false(self):
        gen = make_gen()
        gen.get_first_linked_value.return_value = None
        gen.data = {"samples": MagicMock()}
        gen.data["samples"].primary_key = "sampleID"

        binding = self._make_binding(gen, replace_empty_values=False)
        result = binding.get_first_linked_value("someSlot")
        assert result == ""

    def test_non_empty_string_returned_as_is(self):
        gen = make_gen()
        gen.get_first_linked_value.return_value = "myValue"
        gen.data = {"samples": MagicMock()}
        gen.data["samples"].primary_key = "sampleID"

        binding = self._make_binding(gen, replace_empty_values=False)
        result = binding.get_first_linked_value("someSlot")
        assert result == "myValue"

    def test_idvalue_primary_key_no_index_logs_error_no_crash(self):
        gen = make_gen()
        id_val = IDValue("mySample")
        gen.get_first_linked_value.return_value = id_val
        mock_data = MagicMock()
        mock_data.primary_key = "sampleID"
        gen.data = {"samples": mock_data}

        binding = self._make_binding(gen, replace_empty_values=False)
        result = binding.get_first_linked_value("sampleID")
        assert result is not None
