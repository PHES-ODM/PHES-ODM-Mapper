"""Tests for odm_map.id_generator.id_value.IDValue"""

from odm_map.id_generator.id_value import IDValue


class TestIDValueStr:
    def test_simple_id_no_index(self):
        assert str(IDValue("myID")) == "myID"

    def test_id_with_index(self):
        assert str(IDValue("myID", 3)) == "myID003"

    def test_id_with_zero_index(self):
        # 0 is falsy, so no index suffix is appended
        assert str(IDValue("myID", 0)) == "myID"

    def test_id_with_none_index(self):
        assert str(IDValue("myID", None)) == "myID"

    def test_none_root_id(self):
        assert str(IDValue(None)) == ""

    def test_none_root_id_with_index(self):
        # None root -> empty string, index appended
        assert str(IDValue(None, 5)) == "005"

    def test_list_root_id_converted_to_string(self):
        v = IDValue(["a", "b"])
        assert str(v) == "['a', 'b']"


class TestIDValueEquality:
    def test_equal_to_string(self):
        assert IDValue("abc") == "abc"
        assert IDValue("abc", 2) == "abc002"

    def test_not_equal_to_different_string(self):
        assert IDValue("abc") != "xyz"

    def test_two_idvalues_equal(self):
        assert IDValue("x", 1) == IDValue("x", 1)

    def test_two_idvalues_not_equal(self):
        assert IDValue("x", 1) != IDValue("x", 2)

    def test_ne_operator(self):
        assert not (IDValue("a") != "a")
        assert IDValue("a") != "b"


class TestIDValueLen:
    def test_length(self):
        v = IDValue("hello")
        assert len(v) == 5

    def test_length_with_index(self):
        v = IDValue("ab", 1)
        assert len(v) == len("ab001")

    def test_empty_length(self):
        assert len(IDValue(None)) == 0


class TestIDValueHash:
    def test_hash_same_as_string_hash(self):
        v = IDValue("myID")
        assert hash(v) == hash("myID")

    def test_usable_as_dict_key(self):
        v = IDValue("key")
        d = {v: "value"}
        assert d[v] == "value"
        assert d["key"] == "value"


class TestIDValueBool:
    def test_non_empty_is_truthy(self):
        assert bool(IDValue("something"))

    def test_empty_is_falsy(self):
        assert not bool(IDValue(None))

    def test_empty_string_root_is_falsy(self):
        assert not bool(IDValue(""))


class TestIDValueIsEmpty:
    def test_none_root_is_empty(self):
        assert IDValue(None).is_empty()

    def test_non_none_root_is_not_empty(self):
        assert not IDValue("x").is_empty()

    def test_empty_string_root_is_not_empty(self):
        # is_empty checks for None, not empty string
        assert not IDValue("").is_empty()


class TestIDValueIsIndexGenerated:
    def test_none_index_not_generated(self):
        assert not IDValue("x").is_index_generated()

    def test_zero_index_is_generated(self):
        assert IDValue("x", 0).is_index_generated()

    def test_positive_index_is_generated(self):
        assert IDValue("x", 5).is_index_generated()


class TestIDValueProperties:
    def test_unindexed_value(self):
        v = IDValue("root", 3)
        assert v.unindexed_value == "root"

    def test_unindexed_value_none(self):
        v = IDValue(None)
        assert v.unindexed_value is None

    def test_index_property(self):
        v = IDValue("x", 7)
        assert v.index == 7

    def test_index_property_none(self):
        v = IDValue("x")
        assert v.index is None

    def test_index_in_progress_default(self):
        v = IDValue("x")
        assert v.index_in_progress is False

    def test_index_in_progress_set_to_true(self):
        v = IDValue("x", index_in_progress=True)
        assert v.index_in_progress is True

    def test_index_in_progress_setter(self):
        v = IDValue("x")
        v.index_in_progress = True
        assert v.index_in_progress is True
        v.index_in_progress = False
        assert v.index_in_progress is False


class TestIDValueGetItem:
    def test_single_character(self):
        v = IDValue("hello")
        assert v[0] == "h"
        assert v[-1] == "o"

    def test_slice(self):
        v = IDValue("hello")
        assert v[1:3] == "el"


class TestIDValueMakeIdStr:
    def test_no_index(self):
        assert IDValue.make_id_str("abc", None) == "abc"

    def test_with_index(self):
        assert IDValue.make_id_str("abc", 2) == "abc002"

    def test_zero_index(self):
        assert IDValue.make_id_str("abc", 0) == "abc"

    def test_none_root(self):
        assert IDValue.make_id_str(None, 1) == "001"
