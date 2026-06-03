"""Tests for odm_map.progress.single_bar"""

from odm_map.progress.single_bar import SingleBar


def _hidden_bar(total=10):
    return SingleBar(
        title="initial",
        bar_format="{l_bar}{bar}",
        total=total,
        position=0,
        show_bar=False,
    )


class TestSetBarTitle:
    def test_set_title_on_hidden_bar_does_not_raise(self):
        bar = _hidden_bar()
        # self.bar is None for a hidden bar; setting the title must not raise.
        assert bar.bar is None
        bar.set_bar_title("new title")
        assert bar.title == "new title"

    def test_hidden_bar_uses_updated_title_when_shown(self):
        bar = _hidden_bar()
        bar.set_bar_title("new title")
        bar.show_bar()
        try:
            assert bar.bar is not None
            assert bar.bar.desc == "new title"
        finally:
            bar.close()


class TestUpdate:
    def test_update_on_hidden_bar_tracks_count(self):
        bar = _hidden_bar(total=10)
        bar.update(3)
        assert bar.count == 3
        assert bar.percent_complete == 30
