from typing import Optional
from abc import abstractmethod, ABC


class BaseCounter(ABC):
    def __init__(self, *args, **kwargs): ...

    @abstractmethod
    def __enter__(self): ...

    @abstractmethod
    def __exit__(self, exception_type, exception_value, exception_traceback): ...

    @abstractmethod
    def show_bar(self, barid: Optional[str]): ...

    @abstractmethod
    def update(self, barid: str, inc: int): ...

    @abstractmethod
    def close(self): ...

    @abstractmethod
    def get_progress_report(self, separator: str = " / ") -> str: ...

    @abstractmethod
    def has_bar(self, barid: str) -> bool: ...
