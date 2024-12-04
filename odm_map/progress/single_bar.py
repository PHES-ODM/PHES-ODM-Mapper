from tqdm import tqdm

# Passed as mininterval and maxinterval to tqdm() constructor
TQDM_MININTERVAL = 0.2
TQDM_MAXINTERVAL = 10.0


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

    def set_bar_title(self, title: str):
        """Set the title/description of the bar.

        Args:
            title (str): The new title/description of the bar.
        """
        self.bar.set_description(title)

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
