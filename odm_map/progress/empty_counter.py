from typing import Optional

from odm_map.progress.base_counter import BaseCounter


class EmptyCounter(BaseCounter):
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        pass

    def __exit__(self, exception_type, exception_value, exception_traceback):
        pass

    def show_bar(self, barid: Optional[str]):
        pass

    def update(self, barid: str, inc: int):
        pass

    def close(self):
        pass

    def get_progress_report(self, separator: str = " / ") -> str:
        return "Empty Counter"

    def has_bar(self, barid: str) -> bool:
        return False
