# %%
"""
Handles multiple progress bars.

# Usage

```python
import time

bar_totals = {
    "measures" : 5000,
    "protocols" : 10000,
    "samples" : 500,
}

is_ipython = "get_ipython" in globals()
progress = ProgressCounter(bar_totals, multiple_bars=not is_ipython, hide_all=is_ipython)
with progress:
    for current_bar, current_total in bar_totals.items():
        progress.show_bar(current_bar)      # Only has an effect if multiple_bars is False
        for i in range(current_total):
            if i % 1000 == 0:
                print("Progress:", progress.get_progress_report())
            progress.update(current_bar, 1)
            time.sleep(0.0005)
print("Final Progress:", progress.get_progress_report())
```
"""

import sys
from typing import Dict, Optional, List
import logging
import time

from odm_map.progress.hook_writer import HookWriter
from odm_map.progress.single_bar import SingleBar
from odm_map.progress.base_counter import BaseCounter

# Maximum allowable width (in characters) of the description of a tqdm bar
MAX_DESC_WIDTH = 22
# Width (in characters) of the slider portion of the progress bar.
BAR_WIDTH = 50
# Format of a tqdm bar passed tqdm() constructor as bar_format parameter.
# %(maxdesc) and %(barwidth) receive the width of the description and the
# width of the slider part of the bar.
BAR_FORMAT = (
    "{desc:<%(maxdesc)d.%(maxdesc)d}{percentage:3.0f}%%|{bar:%(barwidth)d}{r_bar}\x1b[K"
)

# Key used to access the total bar (eg. when calling ProgressCounter.show_bar() and ProgressCounter.has_bar())
TOTAL_BARID = "<<total_bar>>"

# Hide cursor when progress bar is visible
HIDE_CURSOR = True

HOOK_STDOUT = True
HOOK_STDERR = True


class ProgressCounter(BaseCounter):
    def __init__(
        self,
        totals: Dict,
        multiple_bars: bool = False,
        titles: Dict = None,
        total_title: str = "TOTAL",
        hide_all: bool = False,
        full_refresh_duration: Optional[float] = 0.5,
        full_refresh_iters: Optional[int] = None,
        install_output_hooks: bool = True,
    ):
        """A ProgressCounter consists of multiple counts with a separate progress bar for each count. Either all progress bars can be shown
        at once, or just a single progress bar can be shown at a time.

        Args:
            totals (Dict): A dictionary where the keys are the barids of all progress bars to create, and the values are the
                total count value of each progress bar. For example, the following will create a bar called "measures" with
                a maximum total count of 1000, and another called "samples" with a total of 500:
                    {
                        "measures" : 1000,
                        "samples" : 500,
                    }
            multiple_bars (bool, optional): If True then show all progress bars at once, along with a total progress bar. If
                False then only show one bar at a time. show_bar() can be called to switch between bars to display. When in a
                Jupyter notebook or something similar it is usually best to set this to False to prevent unusual output.
                Defaults to False.
            titles (Dict, optional): If set then a dictionary mapping bar IDs (as found in the totals parameter) to titles.
                If a title is not specified here then the bar ID in the totals parameter is used as the title. To set
                the title of the total bar, use total_title. Defaults to None.
            total_title (str, optional): The description to use for the total progress bar, which shows the overall total of
                all counts combined. Defaults to "TOTAL".
            hide_all (bool, optional): If True then initially hide all the bars.
            full_refresh_duration (Optional[float], optional): If not None, then a float representing how many seconds between
                each full refresh of all progress bars when update() is called. A full refresh redraws all visible bars. Defaults to 0.5.
            full_refresh_iters (Optional[int], optional): If not None, then an int representing how many increments of the total
                progress to wait before performing a full refresh of all bars. A full refresh redraws all visible bars. Defaults to None.
            install_output_hooks (bool, optional): If True, then install all output hooks to intercept output from either logging
                or stdout/stderr, to clean up output so that it looks nicer with the progress bars (ie returning to the start of the
                line and clearing lines to ensure no artifacts of tqdm bars are shown when scrolling the progress bars). When in a Jupyter
                notebook or something similar, it may be best to set this to False. Defaults to True.
        """
        if titles is None:
            titles = {}

        self.entered = False
        self.full_refresh_duration = full_refresh_duration
        self.full_refresh_iters = full_refresh_iters
        self.last_refresh_time = time.time()
        self.last_refresh_iter = 0
        self.total_title = total_title
        self.install_output_hooks = install_output_hooks

        # Create the bar format
        bar_titles = [titles.get(barid, barid) for barid in totals.keys()]
        bar_format = self.calc_bar_format(bar_titles)

        # Create all progress bars (except for total bar)
        self.progress_bars = {
            barid: SingleBar(
                title=titles.get(barid, barid),
                bar_format=bar_format,
                total=total,
                position=i if multiple_bars else 0,
                show_bar=multiple_bars and not hide_all,
            )
            for i, (barid, total) in enumerate(totals.items())
        }

        self.multiple_bars = multiple_bars

        # Create the main total bar (at bottom)
        total = sum(totals.values())
        total_position = len(self.progress_bars) if self.multiple_bars else 0
        self.progress_bars[TOTAL_BARID] = SingleBar(
            title=self.total_title,
            bar_format=bar_format,
            total=total,
            position=total_position,
            show_bar=multiple_bars and not hide_all,
        )

        # If multiple_bars is False then only show the first bar.
        if not multiple_bars and not hide_all:
            self.show_bar(list(self.progress_bars.keys())[0])

    def calc_bar_format(self, titles: List[str]) -> str:
        """Calculate the bar_format (as passed to the tqdm() constructor) used for a set of bars with the specified titles.

        The titles are used to determine the width of the tqdm bar descriptions, so that we have the smallest width that fits
        all titles (up to a maximum allowable width, after which we might clip the longer titles).

        Args:
            titles (List[str]): List of all titles in our set of bars.

        Returns:
            str: The bar format, which should be passed to the tqdm() constructor.
        """
        if titles:
            max_desc = max([len(str(t)) for t in titles]) + 1
        else:
            max_desc = 5
        max_desc = min(max_desc, MAX_DESC_WIDTH)
        bar_width = BAR_WIDTH - max_desc
        bar_format = BAR_FORMAT % {"maxdesc": max_desc, "barwidth": bar_width}
        return bar_format

    def set_bar_title(self, barid: str, title: str):
        """Set the title/description of the specified bar.

        Args:
            barid (str): The ID of the bar to set the title of. Should be one of the barids passed as the totals parameter
                to the ProgressCounter constructor, or TOTAL_BARID for the total bar.
            title (str): The new title/description of the bar.
        """
        bar = self.progress_bars[barid]
        bar.set_bar_title(title)

    def has_bar(self, barid: str) -> bool:
        """Determine if the bar with the specified barid exists.

        Args:
            barid (str): The barid to test. Should be one of the barids passed as the totals parameter to the ProgressCounter
                constructor, or TOTAL_BARID for the total bar.

        Returns:
            bool: True if a bar with the specified barid exists, False otherwise. If True then other functions such as show_bar
                can be called with the barid.
        """
        return barid in self.progress_bars

    def show_bar(self, barid: str):
        """Show/create the bar with the specified barid.

        If the ProgressCounter was created with multiple_bars=False, then all other bars will be hidden and deleted before
        the new bar is shown.

        Args:
            barid (str): The barid of the bar to show. Should be one of the barids passed as the totals parameter to the
                ProgressCounter constructor, or TOTAL_BARID for the total bar.
        """
        if not self.multiple_bars:
            # Hide all other bars
            for cur_barid, cur_bar in self.progress_bars.items():
                if cur_barid != barid:
                    cur_bar.hide_bar()
        self.progress_bars[barid].show_bar()

    def __enter__(self):
        self.entered = True
        self._install_hooks()

    def __exit__(self, exception_type, exception_value, exception_traceback):
        exception_type, exception_value, exception_traceback
        self.close()
        self.entered = False

    def update(self, barid: str, inc: int, force_refresh: bool = False):
        """Update the bar with the specified barid by increasing its count by inc.

        Args:
            barid (str): The barid of the bar to update. Should be one of the barids passed as the totals parameter to the
                ProgressCounter constructor. Do not pass TOTAL_BARID, as the total bar is updated automatically when each
                of the other bars are updated.
            force_refresh (bool): If True then refresh (re-output) all bars immediately. If False then only refresh the
                if the minimum refresh duration or iterations have occurred (according to the full_refresh_duration or
                full_refresh_iters parameters passed to the constructor).
            inc (int): Amount to increase the bar's count by.
        """
        assert barid != TOTAL_BARID
        assert self.entered, "ProgressCounter has not been entered with __enter__() (be sure code is wrapped in 'with progress_counter:')"

        bar = self.progress_bars[barid]
        bar.update(inc)

        total_bar = self.progress_bars[TOTAL_BARID]
        total_bar.update(inc)

        # Refresh all bars every self.full_refresh_iters iterations or self.full_refresh_duration seconds
        if (
            force_refresh
            or (
                self.full_refresh_iters is not None
                and total_bar.count - self.last_refresh_iter >= self.full_refresh_iters
            )
            or (
                self.full_refresh_duration is not None
                and (time.time() - self.last_refresh_time) >= self.full_refresh_duration
            )
        ):
            self.refresh()

    def refresh(self):
        self.last_refresh_time = time.time()
        self.last_refresh_iter = self.progress_bars[TOTAL_BARID].count
        for bar in self.progress_bars.values():
            if bar:
                bar.refresh()

    def flush(self):
        for bar in self.progress_bars.values():
            if bar:
                bar.bar.fp.flush()

    def close(self):
        """Class/delete all tqdm bars and uninstall any output hooks."""
        for bar in self.progress_bars.values():
            if bar:
                bar.close()

        self._uninstall_hooks()

    def _install_hooks(self):
        """Install all output hooks.

        These hooks intercept output to the console so that the text can be slightly modified before output. This
        makes output while a ProgressCounter is running look nicer.
        """
        if not self.install_output_hooks:
            return

        # Get all StreamHandlers from all loggers
        loggers = [logging.root] + [
            logging.getLogger(name) for name in logging.root.manager.loggerDict
        ]
        handlers = set(
            [
                h
                for logger in loggers
                for h in logger.handlers
                if isinstance(h, logging.StreamHandler)
            ]
        )
        # Install the hooks
        self.hook_handlers = {h: HookWriter(h, self.refresh) for h in handlers}
        # Hide cursor
        if HIDE_CURSOR:
            sys.stdout.write("\x1b[?25l")
        # Replace stdout and stderr (for intercepting calls to print() and any new StreamHandler created after
        # installing the hooks)
        if HOOK_STDOUT:
            sys.stdout = self.stdout_hook = HookWriter(sys.stdout, self.refresh)
        if HOOK_STDERR:
            sys.stderr = self.stderr_hook = HookWriter(sys.stderr, self.refresh)

    def _flush_hooks(self):
        """Flush all output hooks, if any were installed when calling the constructor with install_output_hooks=True."""
        if not self.install_output_hooks:
            return

        if HOOK_STDOUT:
            self.stdout_hook.flush()
        if HOOK_STDERR:
            self.stderr_hook.flush()
        for writer in self.hook_handlers.values():
            writer.flush()

    def _uninstall_hooks(self):
        """Unisntall all output hooks, if any were installed when calling the constructor with install_output_hooks=True."""
        if not self.install_output_hooks:
            return

        self._flush_hooks()

        # Restore stdout and stderr
        if HOOK_STDOUT:
            sys.stdout = self.stdout_hook.stream
        if HOOK_STDERR:
            sys.stderr = self.stderr_hook.stream
        # Restore all StreamHandlers
        for writer in self.hook_handlers.values():
            writer.restore()

        # Show cursor
        if HIDE_CURSOR:
            sys.stdout.write("\x1b[?25h")

    def get_progress_report(self, separator: str = " / ") -> str:
        """Get a descriptive string showing the progress (count/total and percent complete) of all
        progress bars, as well as the total progress.

        Args:
            separator (str, optional): The string separator between the info for each progress bar. Defaults to " / ".

        Returns:
            str: The progress of all progress bars.
        """
        data = [
            f"{bar.title}: {bar.count}/{bar.total} ({bar.percent_complete:0.2f}%)"
            for bar in self.progress_bars.values()
        ]

        return separator.join(data)

    def get_count(self, barid: str) -> int:
        return self.progress_bars[barid].count


if __name__ == "__main__":
    import time

    bar_totals = {
        "measures": 500,
        "instruments": 200,
        "organizations": 500,
        "polygons": 100,
        "protocolSteps": 250,
        "protocols": 1000,
        "qualityReports": 800,
        "samples": 500,
        "sites": 250,
    }
    for key in bar_totals.keys():
        bar_totals[key] *= 100

    logging.basicConfig(
        handlers=[logging.StreamHandler(sys.stdout)],
        format="%(levelname)s %(asctime)s %(filename)s:%(lineno)d: %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    is_ipython = "get_ipython" in globals()
    loggerA = logging.getLogger(__name__)
    progress = ProgressCounter(
        bar_totals, multiple_bars=not is_ipython, hide_all=is_ipython
    )
    loggerB = logging.getLogger(__name__)
    with progress:
        # import random
        # bar_counts = { barid: 0 for barid in bar_totals.keys() }
        # i = -1
        # while True:
        #     i += 1
        #     barids = [k for k, v in bar_counts.items() if v < bar_totals[k]]
        #     if len(barids) == 0:
        #         break
        #     barid = random.choice(barids)
        #     inc = 1
        #     bar_counts[barid] += inc
        #     progress.update(barid, inc)
        #     if i % 1000 == 0:
        #         print("Progress:", progress.get_progress_report())
        #     time.sleep(0.0005)

        import random

        for current_bar, current_total in bar_totals.items():
            progress.show_bar(
                current_bar
            )  # Only has an effect if multiple_bars is False
            for i in range(current_total):
                if random.randint(0, 1000) == 1:
                    # print("Progress:", progress.get_progress_report())
                    # print("Progress", "with", "test")
                    print("Progress", progress.get_count(TOTAL_BARID))
                progress.update(current_bar, 1)
                time.sleep(0.00001)
    print(f"Final Progress: {progress.get_progress_report()}")
