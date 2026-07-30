"""Tests for odm_map.id_generator.id_na"""

import numpy as np

from odm_map.id_generator.id_na import EMPTY_OBJ, EmptyObject, isna


class TestEmptyObject:
    def test_str_returns_empty_string(self):
        obj = EmptyObject()
        assert str(obj) == ""

    def test_repr_contains_class_name(self):
        obj = EmptyObject()
        assert "EmptyObject" in repr(obj)

    def test_singleton_empty_obj(self):
        # EMPTY_OBJ is defined at module level; it is an EmptyObject instance
        assert isinstance(EMPTY_OBJ, EmptyObject)

    def test_empty_obj_str(self):
        assert str(EMPTY_OBJ) == ""


class TestIsNa:
    def test_none_is_na(self):
        assert isna(None)

    def test_float_nan_is_na(self):
        assert isna(float("nan"))

    def test_numpy_nan_is_na(self):
        assert isna(np.nan)

    def test_empty_obj_is_na(self):
        assert isna(EMPTY_OBJ)

    def test_new_empty_object_is_not_na(self):
        # isna uses identity check (v is EMPTY_OBJ), not isinstance — a fresh instance is NOT NA
        assert not isna(EmptyObject())

    def test_zero_is_not_na(self):
        assert not isna(0)

    def test_empty_string_is_not_na(self):
        assert not isna("")

    def test_non_empty_string_is_not_na(self):
        assert not isna("hello")

    def test_integer_is_not_na(self):
        assert not isna(42)

    def test_false_is_not_na(self):
        assert not isna(False)

    def test_empty_list_is_na(self):
        # A list where all items are NA
        assert isna([None, float("nan")])

    def test_nonempty_list_is_not_na(self):
        # A list with at least one non-NA item
        assert not isna([None, "value"])

    def test_list_with_single_value_is_not_na(self):
        assert not isna([1])

    def test_empty_list_is_na_because_no_non_na_items(self):
        # Empty list: no non-NA items
        assert isna([])
