"""Tests for odm_map.utils.clean_exit_error"""

import pytest

from odm_map.utils.clean_exit_error import CleanExitError


class TestCleanExitError:
    def test_is_exception_subclass(self):
        assert issubclass(CleanExitError, Exception)

    def test_can_be_raised_and_caught_as_self(self):
        with pytest.raises(CleanExitError):
            raise CleanExitError("test message")

    def test_can_be_caught_as_exception(self):
        with pytest.raises(Exception):
            raise CleanExitError("test message")

    def test_message_preserved(self):
        try:
            raise CleanExitError("specific error message")
        except CleanExitError as e:
            assert str(e) == "specific error message"

    def test_no_message(self):
        with pytest.raises(CleanExitError):
            raise CleanExitError()

    def test_not_subclass_of_value_error(self):
        assert not issubclass(CleanExitError, ValueError)

    def test_value_error_not_caught_as_clean_exit_error(self):
        with pytest.raises(ValueError):
            try:
                raise ValueError("not a clean exit")
            except CleanExitError:
                pass
