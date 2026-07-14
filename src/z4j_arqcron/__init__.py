"""z4j-arqcron - scheduler adapter for arq cron jobs."""

from __future__ import annotations

from z4j_arqcron.scheduler import ArqCronAdapter

try:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("z4j-arqcron")
except PackageNotFoundError:  # source checkout, no installed metadata
    from z4j_core.version import __version__  # type: ignore[no-redef]

__all__ = ["ArqCronAdapter", "__version__"]
