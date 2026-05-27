"""Tests for standalone functions in odm_map.id_generator.generator_data"""

from odm_map.id_generator.generator_data import (
    match_len,
    add_code_selector_to_slot,
    remove_code_selectors_from_slot,
    get_slot_and_selectors_from_slot,
    get_code_selectors_from_string,
)


# ---------------------------------------------------------------------------
# match_len
# ---------------------------------------------------------------------------


class TestMatchLen:
    def test_common_prefix_length(self):
        assert match_len("hello", "hi") == 1

    def test_full_prefix_match(self):
        assert match_len("hello", "hello123") == 5

    def test_no_common_prefix(self):
        assert match_len("hello", "bye") == 0

    def test_partial_middle_match(self):
        assert match_len("hello", "heilo") == 2

    def test_identical_strings(self):
        assert match_len("abc", "abc") == 3

    def test_first_string_empty(self):
        assert match_len("", "hello") == 0

    def test_second_string_empty(self):
        assert match_len("hello", "") == 0

    def test_both_strings_empty(self):
        assert match_len("", "") == 0

    def test_non_string_coerced_to_string(self):
        assert match_len(123, 124) == 2

    def test_single_character_match(self):
        assert match_len("a", "a") == 1

    def test_single_character_no_match(self):
        assert match_len("a", "b") == 0

    def test_first_shorter_full_match(self):
        assert match_len("ab", "abcdef") == 2

    def test_second_shorter_full_match(self):
        assert match_len("abcdef", "ab") == 2


# ---------------------------------------------------------------------------
# add_code_selector_to_slot
# ---------------------------------------------------------------------------


class TestAddCodeSelectorToSlot:
    def test_adds_selector_with_colon(self):
        assert add_code_selector_to_slot("sampleID", "pooled") == "sampleID:pooled"

    def test_adds_empty_selector(self):
        assert add_code_selector_to_slot("sampleID", "") == "sampleID:"

    def test_adds_none_selector_as_string(self):
        result = add_code_selector_to_slot("sampleID", None)
        assert result == "sampleID:None"

    def test_slot_already_has_colon(self):
        result = add_code_selector_to_slot("sampleID:main", "extra")
        assert result == "sampleID:main:extra"


# ---------------------------------------------------------------------------
# remove_code_selectors_from_slot
# ---------------------------------------------------------------------------


class TestRemoveCodeSelectorsFromSlot:
    def test_removes_selector(self):
        assert remove_code_selectors_from_slot("sampleID:pooled,main") == "sampleID"

    def test_no_selector_returns_unchanged(self):
        assert remove_code_selectors_from_slot("sampleID") == "sampleID"

    def test_empty_selector_after_colon(self):
        assert remove_code_selectors_from_slot("sampleID:") == "sampleID"

    def test_non_string_returned_unchanged(self):
        assert remove_code_selectors_from_slot(42) == 42

    def test_none_returned_unchanged(self):
        assert remove_code_selectors_from_slot(None) is None

    def test_multiple_selectors_removed(self):
        assert remove_code_selectors_from_slot("slot:a,b,c") == "slot"


# ---------------------------------------------------------------------------
# get_slot_and_selectors_from_slot
# ---------------------------------------------------------------------------


class TestGetSlotAndSelectorsFromSlot:
    def test_no_selector_returns_none_in_list(self):
        slot, selectors = get_slot_and_selectors_from_slot("sampleID")
        assert slot == "sampleID"
        assert selectors == [None]

    def test_single_selector(self):
        slot, selectors = get_slot_and_selectors_from_slot("sampleID:pooled")
        assert slot == "sampleID"
        assert selectors == ["pooled"]

    def test_multiple_selectors(self):
        slot, selectors = get_slot_and_selectors_from_slot("sampleID:pooled,main")
        assert slot == "sampleID"
        assert selectors == ["pooled", "main"]

    def test_empty_selector_becomes_none(self):
        slot, selectors = get_slot_and_selectors_from_slot("sampleID:")
        assert slot == "sampleID"
        assert selectors == [None]

    def test_blank_selector_in_middle(self):
        slot, selectors = get_slot_and_selectors_from_slot("sampleID:pooled,,main")
        assert slot == "sampleID"
        assert selectors == ["pooled", None, "main"]

    def test_non_string_returns_none_and_empty_list(self):
        slot, selectors = get_slot_and_selectors_from_slot(42)
        assert slot is None
        assert selectors == []

    def test_none_returns_none_and_empty_list(self):
        slot, selectors = get_slot_and_selectors_from_slot(None)
        assert slot is None
        assert selectors == []


# ---------------------------------------------------------------------------
# get_code_selectors_from_string
# ---------------------------------------------------------------------------


class TestGetCodeSelectorsFromString:
    def test_single_selector(self):
        assert get_code_selectors_from_string("pooled") == ["pooled"]

    def test_multiple_selectors(self):
        assert get_code_selectors_from_string("pooled,main") == ["pooled", "main"]

    def test_empty_string_returns_none_in_list(self):
        assert get_code_selectors_from_string("") == [None]

    def test_blank_selector_in_middle_becomes_none(self):
        assert get_code_selectors_from_string("pooled,,main") == [
            "pooled",
            None,
            "main",
        ]

    def test_non_string_returns_none_in_list(self):
        assert get_code_selectors_from_string(42) == [None]

    def test_none_returns_none_in_list(self):
        assert get_code_selectors_from_string(None) == [None]

    def test_leading_empty_becomes_none(self):
        result = get_code_selectors_from_string(",pooled")
        assert result == [None, "pooled"]

    def test_trailing_empty_becomes_none(self):
        result = get_code_selectors_from_string("pooled,")
        assert result == ["pooled", None]
