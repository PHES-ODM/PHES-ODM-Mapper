"""Tests for odm_map.progress.empty_counter.EmptyCounter"""

from odm_map.progress.empty_counter import EmptyCounter


class TestEmptyCounter:
    def test_constructor_accepts_positional_args(self):
        counter = EmptyCounter(1, 2, 3)
        assert counter is not None

    def test_constructor_accepts_keyword_args(self):
        counter = EmptyCounter(key="value", other=42)
        assert counter is not None

    def test_context_manager_enter_returns_self(self):
        counter = EmptyCounter()
        result = counter.__enter__()
        assert result is counter

    def test_context_manager_exit_no_exception(self):
        counter = EmptyCounter()
        counter.__exit__(None, None, None)

    def test_context_manager_with_statement(self):
        with EmptyCounter() as c:
            assert isinstance(c, EmptyCounter)

    def test_show_bar_does_nothing(self):
        counter = EmptyCounter()
        counter.show_bar("some_bar")

    def test_show_bar_none_does_nothing(self):
        counter = EmptyCounter()
        counter.show_bar(None)

    def test_update_does_nothing(self):
        counter = EmptyCounter()
        counter.update("some_bar", 10)

    def test_update_zero_does_nothing(self):
        counter = EmptyCounter()
        counter.update("bar", 0)

    def test_close_does_nothing(self):
        counter = EmptyCounter()
        counter.close()

    def test_get_progress_report_returns_string(self):
        counter = EmptyCounter()
        result = counter.get_progress_report()
        assert isinstance(result, str)

    def test_get_progress_report_content(self):
        counter = EmptyCounter()
        assert counter.get_progress_report() == "Empty Counter"

    def test_get_progress_report_custom_separator_ignored(self):
        counter = EmptyCounter()
        assert counter.get_progress_report(separator=" | ") == "Empty Counter"

    def test_has_bar_always_false(self):
        counter = EmptyCounter()
        assert counter.has_bar("any_bar") is False

    def test_has_bar_empty_string(self):
        counter = EmptyCounter()
        assert counter.has_bar("") is False
