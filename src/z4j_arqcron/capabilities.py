"""arq cron is read-only by design (statically configured)."""

from __future__ import annotations

DEFAULT_CAPABILITIES: frozenset[str] = frozenset({"list", "read"})

__all__ = ["DEFAULT_CAPABILITIES"]
