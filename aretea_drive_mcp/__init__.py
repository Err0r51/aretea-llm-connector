"""Aretea Drive MCP connector (read-only, v1).

Two decoupled hops:
- client hop: identity-only OAuth (FastMCP GoogleProvider) — establishes *who*, grants no Drive.
- drive hop: one fixed service account (3 read scopes, no delegation) — the data boundary.

See docs/ARCHITECTURE.md for the full contract.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

# Single in-source floor version, read from the installed distribution metadata (pyproject
# `project.version`) — NOT hardcoded here (PRD 3 AC10). The human-facing release label is the
# `vX.Y.Z` git tag / GitHub Release, mapped from the deployed SHA; this floor is a fallback that
# surfaces at /health when the SHA is unavailable.
try:
    __version__ = version("aretea-drive-mcp")  # hyphenated distribution name, not the import name
except PackageNotFoundError:  # running from a raw checkout without an installed dist
    __version__ = "0.0.0"

__all__ = ["__version__"]
