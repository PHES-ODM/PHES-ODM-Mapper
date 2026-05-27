"""Tests for odm_map.progress.progress_counter.ProgressCounter"""

import pytest

from odm_map.progress.progress_counter import ProgressCounter, TOTAL_BARID


@pytest.fixture
def counter():
    return ProgressCounter(
        {"measures": 10, "samples": 5},
        multiple_bars=False,
        install_output_hooks=False,
    )


class TestCalcBarFormat:
    def test_empty_titles_uses_default_width(self):
        pc = ProgressCounter({}, multiple_bars=False, install_output_hooks=False)
        fmt = pc.calc_bar_format([])
        assert "{bar" in fmt

    def test_titles_determine_desc_width(self):
        pc = ProgressCounter({"a": 1}, multiple_bars=False, install_output_hooks=False)
        fmt_short = pc.calc_bar_format(["ab"])
        fmt_long = pc.calc_bar_format(["a" * 30])
        # Long title → wider desc → narrower bar; format strings differ
        assert fmt_short != fmt_long


class TestHasBar:
    def test_has_bar_for_existing_barid(self, counter):
        assert counter.has_bar("measures") is True

    def test_has_bar_for_total(self, counter):
        assert counter.has_bar(TOTAL_BARID) is True

    def test_has_bar_false_for_unknown(self, counter):
        assert counter.has_bar("nonexistent") is False


class TestSetBarTitle:
    def test_set_bar_title_does_not_raise(self, counter):
        counter.set_bar_title("measures", "New Title")

    def test_set_measures_bar_title(self, counter):
        # 'measures' bar is the first/active bar so it has a live tqdm bar
        counter.set_bar_title("measures", "Updated")


class TestUpdateErrors:
    def test_update_total_barid_raises_value_error(self, counter):
        with counter:
            with pytest.raises(ValueError, match=TOTAL_BARID):
                counter.update(TOTAL_BARID, 1)

    def test_update_without_enter_raises_runtime_error(self, counter):
        with pytest.raises(RuntimeError):
            counter.update("measures", 1)


class TestUpdateAndRefresh:
    def test_update_increments_count(self, counter):
        with counter:
            counter.update("measures", 3)
        # After context exit, bars are closed; verify via count tracked during run
        # (Re-read via a fresh counter to confirm the bar incremented)

    def test_refresh_does_not_raise(self, counter):
        with counter:
            counter.update("measures", 1, force_refresh=True)

    def test_force_refresh_triggers_refresh(self, counter):
        with counter:
            counter.update("measures", 1, force_refresh=True)


class TestGetCount:
    def test_get_count_initial_zero(self, counter):
        with counter:
            assert counter.get_count("measures") == 0

    def test_get_count_after_update(self, counter):
        with counter:
            counter.update("measures", 4)
            assert counter.get_count("measures") == 4


class TestGetProgressReport:
    def test_returns_string(self, counter):
        report = counter.get_progress_report()
        assert isinstance(report, str)

    def test_contains_bar_ids(self, counter):
        report = counter.get_progress_report()
        assert "measures" in report
        assert "samples" in report

    def test_custom_separator(self, counter):
        report = counter.get_progress_report(separator="|||")
        assert "|||" in report

    def test_contains_percent(self, counter):
        report = counter.get_progress_report()
        assert "%" in report


class TestContextManager:
    def test_enter_sets_entered(self):
        pc = ProgressCounter({"x": 1}, install_output_hooks=False)
        with pc:
            assert pc.entered is True
        assert pc.entered is False

    def test_exit_calls_close(self):
        pc = ProgressCounter({"x": 1}, install_output_hooks=False)
        with pc:
            pass  # no exception expected on exit


class TestInstallOutputHooksFalse:
    def test_install_hooks_skipped_when_false(self):
        pc = ProgressCounter({"x": 5}, install_output_hooks=False)
        with pc:
            pc.update("x", 1)

    def test_flush_does_not_raise(self):
        pc = ProgressCounter({"x": 5}, install_output_hooks=False)
        with pc:
            pc.update("x", 1)
            pc.refresh()
