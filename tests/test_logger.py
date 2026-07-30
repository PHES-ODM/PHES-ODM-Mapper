"""Tests for odm_map.utils.logger"""

import logging

from odm_map.utils.logger import (
    DEFAULT_LEVEL,
    MultiFormatter,
    get_logger,
    make_logger_bullet_list,
)

# ---------------------------------------------------------------------------
# MultiFormatter
# ---------------------------------------------------------------------------


class TestMultiFormatter:
    def test_default_format_used_for_unmatched_level(self):
        fmt = MultiFormatter(
            fmt="DEFAULT: %(message)s",
            alternate_fmts={logging.INFO: "INFO: %(message)s"},
        )
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )
        result = fmt.format(record)
        assert result.startswith("DEFAULT:")

    def test_alternate_format_used_for_matching_level(self):
        fmt = MultiFormatter(
            fmt="DEFAULT: %(message)s",
            alternate_fmts={logging.INFO: "INFO: %(message)s"},
        )
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )
        result = fmt.format(record)
        assert result.startswith("INFO:")

    def test_no_alternate_fmts_always_uses_default(self):
        fmt = MultiFormatter(fmt="DEFAULT: %(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        result = fmt.format(record)
        assert result.startswith("DEFAULT:")

    def test_original_fmt_restored_after_format(self):
        fmt = MultiFormatter(
            fmt="DEFAULT: %(message)s",
            alternate_fmts={logging.DEBUG: "DEBUG: %(message)s"},
        )
        rec_debug = logging.LogRecord(
            name="t",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="d",
            args=(),
            exc_info=None,
        )
        rec_warn = logging.LogRecord(
            name="t",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="w",
            args=(),
            exc_info=None,
        )
        fmt.format(rec_debug)
        result = fmt.format(rec_warn)
        assert result.startswith("DEFAULT:")


# ---------------------------------------------------------------------------
# get_logger
# ---------------------------------------------------------------------------


class TestGetLogger:
    def test_returns_logger_instance(self):
        logger = get_logger("test_logger_instance")
        assert isinstance(logger, logging.Logger)

    def test_logger_has_at_least_one_handler(self):
        logger = get_logger("test_logger_handlers")
        assert len(logger.handlers) > 0

    def test_custom_level_applied(self):
        logger = get_logger("test_logger_debug_level", level=logging.DEBUG)
        assert logger.level == logging.DEBUG

    def test_default_level_applied(self):
        logger = get_logger("test_logger_default_level_check")
        assert logger.level == DEFAULT_LEVEL

    def test_same_name_returns_same_object(self):
        l1 = get_logger("unique_logger_same_name_test")
        l2 = get_logger("unique_logger_same_name_test")
        assert l1 is l2

    def test_handler_not_duplicated_on_second_call(self):
        name = "test_no_duplicate_handlers"
        l1 = get_logger(name)
        initial_count = len(l1.handlers)
        get_logger(name)
        assert len(l1.handlers) == initial_count


# ---------------------------------------------------------------------------
# make_logger_bullet_list
# ---------------------------------------------------------------------------


class TestMakeLoggerBulletList:
    def test_contains_all_items(self):
        result = make_logger_bullet_list(["item1", "item2", "item3"])
        assert "item1" in result
        assert "item2" in result
        assert "item3" in result

    def test_default_bullet_present(self):
        result = make_logger_bullet_list(["a", "b"])
        assert "- a" in result
        assert "- b" in result

    def test_custom_bullet(self):
        result = make_logger_bullet_list(["a", "b"], bullet="* ")
        assert "* a" in result
        assert "* b" in result

    def test_numbered_bullet(self):
        result = make_logger_bullet_list(["x", "y", "z"], bullet="{idx}. ")
        assert "1. x" in result
        assert "2. y" in result
        assert "3. z" in result

    def test_default_indent_is_four_spaces(self):
        result = make_logger_bullet_list(["a"])
        assert result.startswith("    ")

    def test_zero_indent(self):
        result = make_logger_bullet_list(["a"], indent=0)
        assert result.startswith("-")

    def test_custom_indent(self):
        result = make_logger_bullet_list(["a"], indent=2)
        assert result.startswith("  ")

    def test_last_end_applied_to_final_item(self):
        result = make_logger_bullet_list(["a", "b"], end="\n", last_end="END")
        assert result.endswith("END")

    def test_intermediate_items_use_end(self):
        result = make_logger_bullet_list(["a", "b", "c"], end="\n", last_end="")
        lines = result.split("\n")
        assert lines[0].endswith("a")
        assert lines[1].endswith("b")

    def test_empty_list_returns_empty_string(self):
        result = make_logger_bullet_list([])
        assert result == ""

    def test_single_item_uses_last_end(self):
        result = make_logger_bullet_list(["only"], end="\n", last_end="")
        assert not result.endswith("\n")
