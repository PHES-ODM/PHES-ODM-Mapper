"""Tests for odm_map.id_generator.row_index_lookup.RowIndexLookup"""

import numpy as np

from odm_map.id_generator.id_na import EMPTY_OBJ
from odm_map.id_generator.id_value import IDValue
from odm_map.id_generator.row_index_lookup import RowIndexLookup

# ---------------------------------------------------------------------------
# Constructor and all_lookup_slots / is_lookup_slot
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_creates_lookup_for_each_slot(self):
        lookup = RowIndexLookup(["slot1", "slot2"])
        assert lookup.is_lookup_slot("slot1")
        assert lookup.is_lookup_slot("slot2")

    def test_unknown_slot_is_not_lookup(self):
        lookup = RowIndexLookup(["slot1"])
        assert not lookup.is_lookup_slot("other")

    def test_all_lookup_slots_returns_all(self):
        lookup = RowIndexLookup(["a", "b", "c"])
        assert set(lookup.all_lookup_slots()) == {"a", "b", "c"}

    def test_duplicate_slots_deduplicated(self):
        lookup = RowIndexLookup(["a", "a", "b"])
        assert lookup.all_lookup_slots().count("a") == 1

    def test_empty_slots_list(self):
        lookup = RowIndexLookup([])
        assert lookup.all_lookup_slots() == []


# ---------------------------------------------------------------------------
# add_index / get_indices
# ---------------------------------------------------------------------------


class TestAddAndGetIndices:
    def test_add_and_retrieve_single_index(self):
        lookup = RowIndexLookup(["slot1"])
        lookup.add_index("slot1", "valA", 0)
        assert list(lookup.get_indices("slot1", "valA")) == [0]

    def test_add_multiple_indices_for_same_value(self):
        lookup = RowIndexLookup(["slot1"])
        lookup.add_index("slot1", "valA", 0)
        lookup.add_index("slot1", "valA", 1)
        lookup.add_index("slot1", "valA", 2)
        assert list(lookup.get_indices("slot1", "valA")) == [0, 1, 2]

    def test_get_indices_sorted(self):
        lookup = RowIndexLookup(["slot1"])
        lookup.add_index("slot1", "v", 5)
        lookup.add_index("slot1", "v", 1)
        lookup.add_index("slot1", "v", 3)
        indices = list(lookup.get_indices("slot1", "v"))
        assert indices == sorted(indices)

    def test_get_indices_nonexistent_value_returns_empty(self):
        lookup = RowIndexLookup(["slot1"])
        assert list(lookup.get_indices("slot1", "missing")) == []

    def test_add_index_for_new_slot_not_in_constructor(self):
        lookup = RowIndexLookup(["slot1"])
        lookup.add_index("slot2", "v", 0)
        assert list(lookup.get_indices("slot2", "v")) == [0]

    def test_na_values_mapped_to_same_key(self):
        lookup = RowIndexLookup(["slot1"])
        lookup.add_index("slot1", None, 0)
        lookup.add_index("slot1", float("nan"), 1)
        lookup.add_index("slot1", np.nan, 2)
        indices = list(lookup.get_indices("slot1", None))
        assert 0 in indices
        assert 1 in indices
        assert 2 in indices

    def test_empty_obj_treated_as_na(self):
        lookup = RowIndexLookup(["slot1"])
        lookup.add_index("slot1", EMPTY_OBJ, 0)
        lookup.add_index("slot1", None, 1)
        indices = list(lookup.get_indices("slot1", None))
        assert 0 in indices
        assert 1 in indices

    def test_idvalue_key_maps_by_string(self):
        lookup = RowIndexLookup(["slot1"])
        v = IDValue("abc")
        lookup.add_index("slot1", v, 0)
        assert list(lookup.get_indices("slot1", "abc")) == [0]


# ---------------------------------------------------------------------------
# slot_has_value
# ---------------------------------------------------------------------------


class TestSlotHasValue:
    def test_true_when_value_added(self):
        lookup = RowIndexLookup(["slot1"])
        lookup.add_index("slot1", "x", 0)
        assert lookup.slot_has_value("slot1", "x")

    def test_false_when_value_not_added(self):
        lookup = RowIndexLookup(["slot1"])
        assert not lookup.slot_has_value("slot1", "x")

    def test_false_for_unknown_slot(self):
        lookup = RowIndexLookup(["slot1"])
        assert not lookup.slot_has_value("other", "x")

    def test_na_value_present(self):
        lookup = RowIndexLookup(["slot1"])
        lookup.add_index("slot1", None, 0)
        assert lookup.slot_has_value("slot1", None)
        assert lookup.slot_has_value("slot1", float("nan"))


# ---------------------------------------------------------------------------
# change_value_at_index
# ---------------------------------------------------------------------------


class TestChangeValueAtIndex:
    def test_moves_index_from_old_to_new_value(self):
        lookup = RowIndexLookup(["slot1"])
        lookup.add_index("slot1", "valA", 0)
        lookup.add_index("slot1", "valA", 1)
        lookup.add_index("slot1", "valA", 2)
        lookup.add_index("slot1", "valB", 3)

        lookup.change_value_at_index("slot1", 1, "valA", "valB")

        assert list(lookup.get_indices("slot1", "valA")) == [0, 2]
        assert 1 in list(lookup.get_indices("slot1", "valB"))
        assert 3 in list(lookup.get_indices("slot1", "valB"))

    def test_change_to_na(self):
        lookup = RowIndexLookup(["slot1"])
        lookup.add_index("slot1", "valA", 0)
        lookup.change_value_at_index("slot1", 0, "valA", None)
        assert list(lookup.get_indices("slot1", "valA")) == []
        assert 0 in list(lookup.get_indices("slot1", None))

    def test_change_from_na(self):
        lookup = RowIndexLookup(["slot1"])
        lookup.add_index("slot1", None, 0)
        lookup.change_value_at_index("slot1", 0, None, "valB")
        assert list(lookup.get_indices("slot1", None)) == []
        assert list(lookup.get_indices("slot1", "valB")) == [0]

    def test_old_value_cleaned_up_when_empty(self):
        lookup = RowIndexLookup(["slot1"])
        lookup.add_index("slot1", "onlyIdx", 0)
        lookup.change_value_at_index("slot1", 0, "onlyIdx", "newVal")
        assert not lookup.slot_has_value("slot1", "onlyIdx")

    def test_same_value_noop(self):
        lookup = RowIndexLookup(["slot1"])
        lookup.add_index("slot1", "v", 0)
        lookup.change_value_at_index("slot1", 0, "v", "v")
        assert list(lookup.get_indices("slot1", "v")) == [0]


# ---------------------------------------------------------------------------
# repr / str
# ---------------------------------------------------------------------------


class TestReprStr:
    def test_repr_returns_string(self):
        lookup = RowIndexLookup(["slot1"])
        assert isinstance(repr(lookup), str)

    def test_str_returns_string(self):
        lookup = RowIndexLookup(["slot1"])
        assert isinstance(str(lookup), str)
