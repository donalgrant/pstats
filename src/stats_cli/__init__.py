"""stats: column statistics for whitespace-delimited numeric data."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("stats-cli")
except PackageNotFoundError:  # running from a source tree without installing
    __version__ = "0+unknown"
