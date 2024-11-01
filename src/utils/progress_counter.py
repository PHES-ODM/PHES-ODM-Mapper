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
progress = ProgressCounter(bar_totals, multiple_bars=not is_ipython, install_output_hooks=not is_ipython)
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

from tqdm import tqdm
import sys
from typing import Dict, Optional, List
import logging
import time

DEFAULT_ENCODING = sys.getdefaultencoding()

# Maximum allowable width (in characters) of the description of a tqdm bar
MAX_DESC_WIDTH = 20
# Width (in characters) of the slider portion of the progress bar.
BAR_WIDTH = 80
# Format of a tqdm bar passed tqdm() constructor as bar_format parameter.
# %(maxdesc) and %(barwidth) receive the width of the description and the
# width of the slider part of the bar.
BAR_FORMAT = (
    "{desc:<%(maxdesc)d.%(maxdesc)d}{percentage:3.0f}%%|{bar:%(barwidth)d}{r_bar}\x1b[K"
)

# Passed as mininterval and maxinterval to tqdm() constructor
TQDM_MININTERVAL = 0.2
TQDM_MAXINTERVAL = 10.0

# Key used to access the total bar (eg. when calling ProgressCounter.show_bar() and ProgressCounter.has_bar())
TOTAL_KEY = None


class HookWriter(object):
    """
    Intercepts output (eg. to a logging.StreamHandler, sys.stdout, or sys.stderr) and modifies the text
    to ensure that output looks nice while a ProgressCounter is running. The main purpose is to clear
    the output line before writing output, to clear any artifacts left by a tqdm bar.
    """

    def __init__(self, stream, progress_counter):
        # at_new_line is True whenever we are at the start of a line for this particular HookWriter.
        # If we are at the start of a line then we clear the line and force return to the start
        # before writing text.
        # If we're not at the start we do not clear the line or return to the start before writing text.
        self.at_new_line = True
        self.progress_counter = progress_counter
        self.stream = stream
        if isinstance(stream, logging.StreamHandler):
            # For StreamHandlers (ie. a handler for logging), replace the stream with ourself
            # so we can intercept all output to modify it.
            self.output_stream = stream.stream
            self.stream.setStream(self)
        else:
            # For non-StreamHandlers (eg. stdout and stderr), just save the stream, we will
            # write our modified output to it.
            self.output_stream = stream
        self.flush()

    def restore(self):
        """Restore the original stream so that we no longer intercept output of the stream.

        This will restore streams for a logging.StreamHandler. For others, such as sys.stdout
        and sys.stderr, they should be restored manually by the caller (eg. sys.stdout = original_stdout)
        """
        if isinstance(self.stream, logging.StreamHandler):
            self.stream.setStream(self.output_stream)

    def write(self, msg):
        """Write handler. Called when writing to the original stream that we're intercepting.

        Args:
            msg: The text to write.
        """
        if isinstance(msg, bytes):
            msg = msg.decode(DEFAULT_ENCODING)
        orig_msg = msg

        if self.at_new_line:
            # Clear whole line and force return to start of line
            self.output_stream.write("\x1b[2K\r")

        # For this particular Writer, we are at the beginning of a line when at_new_line is True.
        # In the next call to write, we will clear the line when at_new_line is True
        self.at_new_line = orig_msg.endswith("\n")

        # Any new lines should consist of a new line followed immediately by a clear line
        msg = msg.replace("\n", "\n\x1b[2K")

        # Output the text
        self.output_stream.write(msg)

        if self.progress_counter:
            # A ProgressCounter is currently running, so tell it to redraw the progress bars on
            # the next frame
            self.progress_counter.refresh_next_update()

    def flush(self):
        self.output_stream.flush()


class SingleBar(object):
    def __init__(
        self, title: str, bar_format: str, total: int, position: int, show_bar: bool
    ):
        """Create a single progress bar. This is a wrapper to a tqdm bar.

        Args:
            title (str): The title/description of the bar, passed to tqdm constructor as the desc
                parameter.
            bar_format (str): The format of the bar, passed to tqdm constructor.
            total (int): The total count for the bar, passed to tqdm constructor.
            position (int): The vertical position of the bar, passed to tqdm constructor.
            show_bar (bool): If True then immediately create and show the bar. If False then the
                bar is not created, it must be created later by calling show_bar().
        """
        self.title = title
        self.bar_format = bar_format
        self.position = position
        self.total = total
        self.count = 0
        self.percent_complete = 0
        self.bar = None

        if show_bar:
            self.show_bar()

    def show_bar(self):
        """Show the bar by creating the tqdm bar."""
        if self.bar is None:
            self.bar = tqdm(
                desc=self.title,
                bar_format=self.bar_format,
                total=self.total,
                position=self.position,
                mininterval=TQDM_MININTERVAL,
                maxinterval=TQDM_MAXINTERVAL,
            )
            self.bar.update(self.count)

    def hide_bar(self):
        """Close the bar.

        The bar is first refreshed then destroyed. Any previous output is not erased, but the bar is no longer updated and no longer exists.
        """
        if self.bar is not None:
            self.bar.refresh()
            self.bar.close()
        self.bar = None

    def update(self, inc: int):
        """Update the bar count by increasing the progress by inc.

        Args:
            inc (int): The number of increments to increase the bar count by. This is passed to tqdm.update(inc)
        """
        self.count += inc
        self.percent_complete = self.count / self.total * 100
        if self.bar is not None:
            self.bar.update(inc)
            if self.count >= self.total:
                self.refresh()

    def refresh(self):
        """Redraw the bar."""
        if self.bar:
            self.bar.refresh()

    def close(self):
        """Close and delete the bar."""
        if self.bar is not None:
            self.bar.close()
            self.bar = None


class EmptyCounter(object):
    def __init__(self, *args, **kwargs):
        args, kwargs
        pass

    def __enter__(self):
        pass

    def __exit__(self, exception_type, exception_value, exception_traceback):
        exception_type, exception_value, exception_traceback

    def show_bar(self, title: Optional[str]):
        title
        pass

    def update(self, title: str, inc: int):
        title, inc
        pass

    def refresh_next_update(self):
        pass

    def close(self):
        pass

    def get_progress_report(self, separator: str = " / ") -> str:
        separator
        return "Empty Counter"

    def has_bar(self, title: str) -> bool:
        title
        return False


class ProgressCounter(object):
    def __init__(
        self,
        totals: Dict,
        multiple_bars: bool = False,
        total_title: str = "TOTAL",
        full_refresh_duration: Optional[float] = 0.5,
        full_refresh_iters: Optional[int] = None,
        install_output_hooks: bool = True,
    ):
        """A ProgressCounter consists of multiple counts with a separate progress bar for each count. Either all progress bars can be shown
        at once, or just a single progress bar can be shown at a time.

        Args:
            totals (Dict): A dictionary where the keys are the titles of all progress bars to create, and the values are the
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
            total_title (str, optional): The description to use for the total progress bar, which shows the overall total of
                all counts combined. Defaults to "TOTAL".
            full_refresh_duration (Optional[float], optional): If not None, then a float representing how many seconds between
                each full refresh of all progress bars when update() is called. A full refresh redraws all visible bars. Defaults to 0.5.
            full_refresh_iters (Optional[int], optional): If not None, then an int representing how many increments of the total
                progress to wait before performing a full refresh of all bars. A full refresh redraws all visible bars. Defaults to None.
            install_output_hooks (bool, optional): If True, then install all output hooks to intercept output from either logging
                or stdout/stderr, to clean up output so that it looks nicer with the progress bars (ie returning to the start of the
                line and clearing lines to ensure no artifacts of tqdm bars are shown when scrolling the progress bars). When in a Jupyter
                notebook or something similar, it may be best to set this to False. Defaults to True.
        """
        self.current_visible_bar = None

        self.full_refresh_duration = full_refresh_duration
        self.full_refresh_iters = full_refresh_iters
        self.last_refresh_time = time.time()
        self.last_refresh_iter = 0
        self.total_title = total_title
        self.install_output_hooks = install_output_hooks

        # Create the bar format
        titles = list(totals.keys()) + [self.total_title]
        bar_format = self.calc_bar_format(titles)

        # Create all progress bars (except for total bar)
        self.progress_bars = {
            title: SingleBar(
                title=title,
                bar_format=bar_format,
                total=total,
                position=i if multiple_bars else 0,
                show_bar=multiple_bars,
            )
            for i, (title, total) in enumerate(totals.items())
        }

        self.multiple_bars = multiple_bars
        self.refresh_next = False

        # Create the main total bar (at bottom)
        total = sum(totals.values())
        total_position = len(self.progress_bars) if self.multiple_bars else 0
        self.progress_bars[TOTAL_KEY] = SingleBar(
            title=self.total_title,
            bar_format=bar_format,
            total=total,
            position=total_position,
            show_bar=multiple_bars,
        )

    def calc_bar_format(self, titles: List[str]) -> str:
        """Calculate the bar_format (as passed to the tqdm() constructor) used for a set of bars with the specified titles.

        The titles are used to determine the width of the tqdm bar descriptions, so that we have the smallest width that fits
        all titles (up to a maximum allowable width, after which we might clip the longer titles).

        Args:
            titles (List[str]): List of all titles in our set of bars.

        Returns:
            str: The bar format, which should be passed to the tqdm() constructor.
        """
        max_desc = max([len(t) for t in titles]) + 1
        max_desc = min(max_desc, MAX_DESC_WIDTH)
        bar_width = BAR_WIDTH - max_desc
        bar_format = BAR_FORMAT % {"maxdesc": max_desc, "barwidth": bar_width}
        return bar_format

    def has_bar(self, title: str) -> bool:
        """Determine if the bar with the specified title exists.

        Args:
            title (str): The title to test. Should be one of the titles passed as the totals parameter to the ProgressCounter
                constructor, or TOTAL_KEY for the total bar.

        Returns:
            bool: True if a bar with the specified title exists, False otherwise. If True then other functions such as show_bar
                can be called with the title.
        """
        return title in self.progress_bars

    def show_bar(self, title: str):
        """Show/create the bar with the specified title.

        If the ProgressCounter was created with multiple_bars=False, then all other bars will be hidden and deleted before
        the new bar is shown.

        Args:
            title (str): The title of the bar to show. Should be one of the titles passed as the totals parameter to the
                ProgressCounter constructor, or TOTAL_KEY for the total bar.
        """
        if not self.multiple_bars:
            # Hide all other bars
            for cur_title, cur_bar in self.progress_bars.items():
                if cur_title != title:
                    cur_bar.hide_bar()
        self.progress_bars[title].show_bar()

    def __enter__(self):
        self._install_hooks()

    def __exit__(self, exception_type, exception_value, exception_traceback):
        exception_type, exception_value, exception_traceback
        self.close()

    def refresh_next_update(self):
        """Call this to force a redraw of all visible bars in the next call to update()."""
        self.refresh_next = True

    def update(self, title: str, inc: int):
        """Update the bar with the specified title by increasing its count by inc.

        Args:
            title (str): The title of the bar to update. Should be one of the titles passed as the totals parameter to the
                ProgressCounter constructor. Do not pass TOTAL_KEY, as the total bar is updated automatically when each
                of the other bars are updated.
            inc (int): Amount to increase the bar's count by.
        """
        assert title != TOTAL_KEY

        bar = self.progress_bars[title]
        bar.update(inc)

        total_bar = self.progress_bars[TOTAL_KEY]
        total_bar.update(inc)

        # Refresh all bars every self.full_refresh_iters iterations or self.full_refresh_duration seconds
        if (
            self.refresh_next
            or (
                self.full_refresh_iters is not None
                and total_bar.count - self.last_refresh_iter >= self.full_refresh_iters
            )
            or (
                self.full_refresh_duration is not None
                and (time.time() - self.last_refresh_time) >= self.full_refresh_duration
            )
        ):
            self.refresh_next = False
            self.last_refresh_time = time.time()
            self.last_refresh_iter = total_bar.count
            for bar in self.progress_bars.values():
                if bar:
                    bar.refresh()
            total_bar.refresh()

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
        self.hook_handlers = {h: HookWriter(h, self) for h in handlers}
        # Hide cursor
        sys.stdout.write("\x1b[?25l")
        # Replace stdout and stderr (for intercepting calls to print() and any new StreamHandler created after
        # installing the hooks)
        sys.stdout = self.stdout_hook = HookWriter(sys.stdout, self)
        sys.stderr = self.stderr_hook = HookWriter(sys.stderr, self)

    def _flush_hooks(self):
        """Flush all output hooks, if any were installed when calling the constructor with install_output_hooks=True."""
        if not self.install_output_hooks:
            return

        self.stdout_hook.flush()
        self.stderr_hook.flush()
        for writer in self.hook_handlers.values():
            writer.flush()

    def _uninstall_hooks(self):
        """Unisntall all output hooks, if any were installed when calling the constructor with install_output_hooks=True."""
        if not self.install_output_hooks:
            return

        self._flush_hooks()

        # Restore stdout and stderr
        sys.stdout = self.stdout_hook.stream
        sys.stderr = self.stderr_hook.stream
        # Restore all StreamHandlers
        for writer in self.hook_handlers.values():
            writer.restore()

        # Show cursor
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


if __name__ == "__main__":
    import time

    bar_totals = {
        "measures": 5000,
        "protocols": 10000,
        "samples": 500,
    }

    is_ipython = "get_ipython" in globals()
    progress = ProgressCounter(
        bar_totals, multiple_bars=not is_ipython, install_output_hooks=not is_ipython
    )
    with progress:
        # import random
        # bar_counts = { title: 0 for title in bar_totals.keys() }
        # i = -1
        # while True:
        #     i += 1
        #     titles = [k for k, v in bar_counts.items() if v < bar_totals[k]]
        #     if len(titles) == 0:
        #         break
        #     title = random.choice(titles)
        #     inc = 1
        #     bar_counts[title] += inc
        #     progress.update(title, inc)
        #     if i % 1000 == 0:
        #         print("Progress:", progress.get_progress_report())
        #     time.sleep(0.0005)

        for current_bar, current_total in bar_totals.items():
            progress.show_bar(
                current_bar
            )  # Only has an effect if multiple_bars is False
            for i in range(current_total):
                if i % 1000 == 0:
                    print("Progress:", progress.get_progress_report())
                progress.update(current_bar, 1)
                time.sleep(0.0005)
    print("Final Progress:", progress.get_progress_report())
