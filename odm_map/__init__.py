import importlib.metadata

try:
    __version__ = importlib.metadata.version(__package__) if __package__ else None
except importlib.metadata.PackageNotFoundError:
    # The package is not installed (e.g. running from a source checkout).
    __version__ = None
