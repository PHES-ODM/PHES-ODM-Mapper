"""Tests for odm_map.filter.filter_funcs"""

import pytest
import pandas as pd

from odm_map.filter.filter_funcs import (
    DROP_COLUMN,
    FILTER_FUNCS,
    call_filter_func,
    do_and_filters,
    do_apply_filter,
    do_copy_class,
    do_copy_filter,
    do_create_filter,
    do_delete_class,
    do_delete_filter,
    do_drop_duplicates,
    do_exclude_equals,
    do_include_equals,
    do_invert_filter,
    do_or_filters,
    do_requires_all,
    do_requires_any,
    get_named_filter,
    set_named_filter,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def df():
    return pd.DataFrame(
        {
            "name": ["Alice", "Bob", "Charlie", "Dave"],
            "status": ["active", "inactive", "active", ""],
            "value": [10, 20, 30, None],
        }
    )


@pytest.fixture
def data(df):
    return {"MyClass": df.copy()}


def make_all_true(df):
    return pd.Series([True] * len(df), index=df.index)


def make_all_false(df):
    return pd.Series([False] * len(df), index=df.index)


# ---------------------------------------------------------------------------
# set_named_filter / get_named_filter
# ---------------------------------------------------------------------------


class TestNamedFilter:
    def test_set_and_get(self, df):
        filters = {}
        filt = make_all_true(df)
        set_named_filter(filt, "my_filter", filters)
        result = get_named_filter("my_filter", filters)
        assert result.equals(filt)

    def test_get_missing_raises(self):
        with pytest.raises(ValueError, match="does not exist"):
            get_named_filter("nonexistent", {})

    def test_overwrite_existing(self, df):
        filters = {}
        filt1 = make_all_true(df)
        filt2 = make_all_false(df)
        set_named_filter(filt1, "f", filters)
        set_named_filter(filt2, "f", filters)
        assert get_named_filter("f", filters).equals(filt2)


# ---------------------------------------------------------------------------
# do_create_filter
# ---------------------------------------------------------------------------


class TestDoCreateFilter:
    def test_create_all_true(self, data, df):
        filters = {}
        do_create_filter(filters, data, "f", "MyClass", True)
        assert get_named_filter("f", filters).all()

    def test_create_all_false(self, data, df):
        filters = {}
        do_create_filter(filters, data, "f", "MyClass", False)
        assert not get_named_filter("f", filters).any()

    def test_invalid_value_raises(self, data):
        with pytest.raises(ValueError):
            do_create_filter({}, data, "f", "MyClass", "yes")

    def test_filter_length_matches_dataframe(self, data, df):
        filters = {}
        do_create_filter(filters, data, "f", "MyClass", True)
        assert len(get_named_filter("f", filters)) == len(df)

    def test_filter_index_matches_dataframe_index(self, df):
        # The created filter must align with the DataFrame's actual index, not a fresh
        # RangeIndex, so boolean ops against df columns line up on non-default indices.
        df_reindexed = df.set_index(pd.Index([10, 20, 30, 40]))
        data = {"MyClass": df_reindexed}
        filters = {}
        do_create_filter(filters, data, "f", "MyClass", True)
        filt = get_named_filter("f", filters)
        assert list(filt.index) == [10, 20, 30, 40]
        # Combining with a column-derived mask must not introduce misaligned NaNs.
        combined = filt & (df_reindexed["value"] > 0)
        assert combined.notna().all()


# ---------------------------------------------------------------------------
# do_exclude_equals
# ---------------------------------------------------------------------------


class TestDoExcludeEquals:
    def test_excludes_matching_value(self, data, df):
        filters = {"f": make_all_true(df)}
        do_exclude_equals(filters, data, "f", "f", "MyClass", "status", "active")
        result = get_named_filter("f", filters)
        assert result.sum() == 2  # Bob and Dave remain
        assert not result.iloc[0]  # Alice excluded
        assert not result.iloc[2]  # Charlie excluded

    def test_exclude_list_of_values(self, data, df):
        filters = {"f": make_all_true(df)}
        do_exclude_equals(
            filters, data, "f", "f", "MyClass", "status", ["active", "inactive"]
        )
        result = get_named_filter("f", filters)
        assert result.sum() == 1  # Only Dave (empty string) remains

    def test_exclude_none_treats_as_empty(self, data, df):
        filters = {"f": make_all_true(df)}
        # value=None should exclude rows where value is None or ""
        do_exclude_equals(filters, data, "f", "f", "MyClass", "value", None)
        result = get_named_filter("f", filters)
        # Dave has None value, should be excluded
        assert not result.iloc[3]

    def test_exclude_empty_string_treats_as_none(self, data, df):
        filters = {"f": make_all_true(df)}
        do_exclude_equals(filters, data, "f", "f", "MyClass", "status", "")
        result = get_named_filter("f", filters)
        # Dave has empty string status, should be excluded
        assert not result.iloc[3]

    def test_no_matching_rows_unchanged(self, data, df):
        filters = {"f": make_all_true(df)}
        do_exclude_equals(filters, data, "f", "f", "MyClass", "status", "unknown")
        result = get_named_filter("f", filters)
        assert result.all()


# ---------------------------------------------------------------------------
# do_include_equals
# ---------------------------------------------------------------------------


class TestDoIncludeEquals:
    def test_includes_matching_value(self, data, df):
        filters = {"f": make_all_false(df)}
        do_include_equals(filters, data, "f", "f", "MyClass", "status", "active")
        result = get_named_filter("f", filters)
        assert result.sum() == 2  # Alice and Charlie
        assert result.iloc[0]
        assert result.iloc[2]

    def test_include_list_of_values(self, data, df):
        filters = {"f": make_all_false(df)}
        do_include_equals(
            filters, data, "f", "f", "MyClass", "status", ["active", "inactive"]
        )
        result = get_named_filter("f", filters)
        assert result.sum() == 3  # Alice, Bob, Charlie

    def test_starts_from_existing_true_filter(self, data, df):
        # If filter already has some True, include_equals ORs the new rows in
        filters = {"f": pd.Series([True, False, False, False], index=df.index)}
        do_include_equals(filters, data, "f", "f", "MyClass", "status", "inactive")
        result = get_named_filter("f", filters)
        # Alice (originally True) + Bob (inactive)
        assert result.iloc[0]
        assert result.iloc[1]


# ---------------------------------------------------------------------------
# do_invert_filter
# ---------------------------------------------------------------------------


class TestDoInvertFilter:
    def test_inverts_filter(self, df):
        filters = {"f": make_all_true(df)}
        do_invert_filter(filters, "f", "f_inv")
        assert not get_named_filter("f_inv", filters).any()

    def test_double_invert_is_identity(self, df):
        original = pd.Series([True, False, True, False], index=df.index)
        filters = {"f": original.copy()}
        do_invert_filter(filters, "f", "f_inv")
        do_invert_filter(filters, "f_inv", "f_inv2")
        assert get_named_filter("f_inv2", filters).equals(original)


# ---------------------------------------------------------------------------
# do_copy_filter
# ---------------------------------------------------------------------------


class TestDoCopyFilter:
    def test_copies_filter(self, df):
        filt = pd.Series([True, False, True, False], index=df.index)
        filters = {"f": filt.copy()}
        do_copy_filter(filters, "f", "f_copy")
        assert get_named_filter("f_copy", filters).equals(filt)

    def test_missing_source_raises(self):
        with pytest.raises(ValueError, match="No filter"):
            do_copy_filter({}, "missing", "dest")

    def test_copy_is_independent(self, df):
        filt = pd.Series([True, False, True, False], index=df.index)
        filters = {"f": filt.copy()}
        do_copy_filter(filters, "f", "f_copy")
        # Overwrite original
        filters["f"] = make_all_false(df)
        # Copy should be unchanged
        assert get_named_filter("f_copy", filters).equals(filt)


# ---------------------------------------------------------------------------
# do_delete_filter
# ---------------------------------------------------------------------------


class TestDoDeleteFilter:
    def test_deletes_existing_filter(self, df):
        filters = {"f": make_all_true(df)}
        do_delete_filter(filters, "f")
        assert "f" not in filters

    def test_delete_nonexistent_no_error(self):
        filters = {}
        do_delete_filter(filters, "nonexistent")
        assert filters == {}


# ---------------------------------------------------------------------------
# do_copy_class
# ---------------------------------------------------------------------------


class TestDoCopyClass:
    def test_copies_dataframe(self, data, df):
        do_copy_class(data, "MyClass", "MyClass_copy")
        assert "MyClass_copy" in data
        assert data["MyClass_copy"].equals(data["MyClass"])

    def test_copy_is_independent(self, data, df):
        do_copy_class(data, "MyClass", "MyClass_copy")
        data["MyClass"].iloc[0, 0] = "MODIFIED"
        assert data["MyClass_copy"]["name"].iloc[0] != "MODIFIED"


# ---------------------------------------------------------------------------
# do_delete_class
# ---------------------------------------------------------------------------


class TestDoDeleteClass:
    def test_deletes_class(self, data):
        do_delete_class(data, "MyClass")
        assert "MyClass" not in data

    def test_delete_nonexistent_no_error(self, data):
        do_delete_class(data, "NonExistent")
        assert "MyClass" in data


# ---------------------------------------------------------------------------
# do_or_filters
# ---------------------------------------------------------------------------


class TestDoOrFilters:
    def test_or_two_filters(self, df):
        f1 = pd.Series([True, False, False, False], index=df.index)
        f2 = pd.Series([False, True, False, False], index=df.index)
        filters = {"f1": f1, "f2": f2}
        do_or_filters(filters, "result", ["f1", "f2"])
        result = get_named_filter("result", filters)
        assert result.iloc[0]
        assert result.iloc[1]
        assert not result.iloc[2]

    def test_or_all_false_remains_false(self, df):
        filters = {"f1": make_all_false(df), "f2": make_all_false(df)}
        do_or_filters(filters, "result", ["f1", "f2"])
        assert not get_named_filter("result", filters).any()


# ---------------------------------------------------------------------------
# do_and_filters
# ---------------------------------------------------------------------------


class TestDoAndFilters:
    def test_and_two_filters(self, df):
        f1 = pd.Series([True, True, False, False], index=df.index)
        f2 = pd.Series([True, False, True, False], index=df.index)
        filters = {"f1": f1, "f2": f2}
        do_and_filters(filters, "result", ["f1", "f2"])
        result = get_named_filter("result", filters)
        assert result.iloc[0]
        assert not result.iloc[1]
        assert not result.iloc[2]
        assert not result.iloc[3]

    def test_and_all_true_remains_true(self, df):
        filters = {"f1": make_all_true(df), "f2": make_all_true(df)}
        do_and_filters(filters, "result", ["f1", "f2"])
        assert get_named_filter("result", filters).all()


# ---------------------------------------------------------------------------
# do_drop_duplicates
# ---------------------------------------------------------------------------


class TestDoDropDuplicates:
    def test_keep_first(self):
        df = pd.DataFrame({"id": ["a", "a", "b"], "val": [1, 2, 3]})
        data = {"C": df.copy()}
        filters = {"f": pd.Series([True, True, True], index=df.index)}
        do_drop_duplicates(filters, data, "f", "f", "C", "id", "keep_first")
        result = get_named_filter("f", filters)
        assert result.iloc[0]  # first "a" kept
        assert not result.iloc[1]  # second "a" dropped
        assert result.iloc[2]

    def test_keep_last(self):
        df = pd.DataFrame({"id": ["a", "a", "b"], "val": [1, 2, 3]})
        data = {"C": df.copy()}
        filters = {"f": pd.Series([True, True, True], index=df.index)}
        do_drop_duplicates(filters, data, "f", "f", "C", "id", "keep_last")
        result = get_named_filter("f", filters)
        assert not result.iloc[0]  # first "a" dropped
        assert result.iloc[1]  # second "a" kept
        assert result.iloc[2]

    def test_invalid_value_raises(self):
        df = pd.DataFrame({"id": ["a"]})
        data = {"C": df.copy()}
        filters = {"f": pd.Series([True], index=df.index)}
        with pytest.raises(ValueError):
            do_drop_duplicates(filters, data, "f", "f", "C", "id", "keep_neither")


# ---------------------------------------------------------------------------
# do_requires_any
# ---------------------------------------------------------------------------


class TestDoRequiresAny:
    def test_requires_any_single_slot(self, data, df):
        filters = {"f": make_all_true(df)}
        do_requires_any(filters, data, "f", "f", "MyClass", "value")
        result = get_named_filter("f", filters)
        # Dave has None for value, should be excluded
        assert not result.iloc[3]
        assert result.iloc[0]

    def test_requires_any_multiple_slots(self):
        df = pd.DataFrame({"a": [None, "x", None], "b": [None, None, "y"]})
        data = {"C": df}
        filters = {"f": pd.Series([True, True, True], index=df.index)}
        do_requires_any(filters, data, "f", "f", "C", ["a", "b"])
        result = get_named_filter("f", filters)
        assert not result.iloc[0]  # both None -> excluded
        assert result.iloc[1]  # a="x" -> included
        assert result.iloc[2]  # b="y" -> included

    def test_excludes_empty_strings(self):
        df = pd.DataFrame({"slot": ["", "value"]})
        data = {"C": df}
        filters = {"f": pd.Series([True, True], index=df.index)}
        do_requires_any(filters, data, "f", "f", "C", "slot")
        result = get_named_filter("f", filters)
        assert not result.iloc[0]
        assert result.iloc[1]


# ---------------------------------------------------------------------------
# do_requires_all
# ---------------------------------------------------------------------------


class TestDoRequiresAll:
    def test_requires_all_both_set(self):
        df = pd.DataFrame({"a": ["x", None, "z"], "b": ["1", "2", None]})
        data = {"C": df}
        filters = {"f": pd.Series([True, True, True], index=df.index)}
        do_requires_all(filters, data, "f", "f", "C", ["a", "b"])
        result = get_named_filter("f", filters)
        assert result.iloc[0]  # both set
        assert not result.iloc[1]  # a=None
        assert not result.iloc[2]  # b=None

    def test_requires_all_single_slot(self, data, df):
        filters = {"f": make_all_true(df)}
        do_requires_all(filters, data, "f", "f", "MyClass", "value")
        result = get_named_filter("f", filters)
        assert not result.iloc[3]  # Dave has None value


# ---------------------------------------------------------------------------
# do_apply_filter
# ---------------------------------------------------------------------------


class TestDoApplyFilter:
    def test_apply_filter_normal(self, data, df):
        filt = pd.Series([True, False, True, False], index=df.index)
        filters = {"f": filt}
        do_apply_filter(filters, data, "f", "MyClass", "MyClass", debug_mode=False)
        assert len(data["MyClass"]) == 2

    def test_apply_filter_debug_mode_sets_drop_column(self, data, df):
        filt = pd.Series([True, False, True, False], index=df.index)
        filters = {"f": filt}
        do_apply_filter(filters, data, "f", "MyClass", "MyClass", debug_mode=True)
        assert DROP_COLUMN in data["MyClass"].columns
        drop_col = data["MyClass"][DROP_COLUMN]
        assert drop_col.iloc[1] is True
        assert drop_col.iloc[3] is True

    def test_apply_filter_debug_mode_does_not_mutate_input_frame(self):
        df = pd.DataFrame({"name": ["A", "B"], "value": [1, 2]})
        data = {"MyClass": df}
        filt = pd.Series([True, False], index=df.index)
        filters = {"f": filt}
        do_apply_filter(filters, data, "f", "MyClass", "MyClass", debug_mode=True)
        # The originally-passed frame must not gain the DROP_COLUMN...
        assert DROP_COLUMN not in df.columns
        # ...but the dict's frame (reassigned to a marked copy) carries it.
        assert DROP_COLUMN in data["MyClass"].columns

    def test_apply_filter_normal_does_not_mutate_input_frame(self):
        df = pd.DataFrame({"name": ["A", "B", "C"], "value": [1, 2, 3]})
        data = {"MyClass": df}
        filt = pd.Series([True, False, True], index=df.index)
        filters = {"f": filt}
        do_apply_filter(filters, data, "f", "MyClass", "out", debug_mode=False)
        # The filtered output is a copy; mutating it must not affect the input frame.
        data["out"].loc[:, "value"] = 999
        assert list(df["value"]) == [1, 2, 3]


# ---------------------------------------------------------------------------
# call_filter_func
# ---------------------------------------------------------------------------


class TestCallFilterFunc:
    def test_calls_registered_operation(self, data, df):
        filters = {}
        call_filter_func(
            "create_filter",
            filters=filters,
            data=data,
            output_name="f",
            cls="MyClass",
            value=True,
        )
        assert "f" in filters

    def test_unrecognized_operation_raises(self):
        with pytest.raises(ValueError, match="Unrecognized filter operation"):
            call_filter_func("not_a_real_op")

    def test_all_registered_ops_in_filter_funcs(self):
        expected_ops = {
            "and_filters",
            "apply_filter",
            "copy_filter",
            "copy_class",
            "create_filter",
            "delete_class",
            "drop_duplicates",
            "delete_filter",
            "exclude_equals",
            "include_equals",
            "invert_filter",
            "or_filters",
            "requires_any",
            "requires_all",
        }
        assert expected_ops.issubset(set(FILTER_FUNCS.keys()))
