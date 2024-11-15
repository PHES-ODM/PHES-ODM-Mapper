from typing import Optional
import sys
import os

sys.path.append(os.path.dirname(__file__))

from base_counter import BaseCounter


class EmptyCounter(BaseCounter):
    def __init__(self, *args, **kwargs):
        args, kwargs
        pass

    def __enter__(self):
        pass

    def __exit__(self, exception_type, exception_value, exception_traceback):
        exception_type, exception_value, exception_traceback
        pass

    def show_bar(self, barid: Optional[str]):
        barid
        pass

    def update(self, barid: str, inc: int):
        barid, inc
        pass

    def refresh_next_update(self):
        pass

    def close(self):
        pass

    def get_progress_report(self, separator: str = " / ") -> str:
        separator
        return "Empty Counter"

    def has_bar(self, barid: str) -> bool:
        barid
        return False
