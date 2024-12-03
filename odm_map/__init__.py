try:
    import importlib.metadata

    __version__ = importlib.metadata.version(__package__) if __package__ else None
except Exception:
    __version__ = None
