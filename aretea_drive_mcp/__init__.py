"""Aretea Drive MCP connector (read-only, v1).

Two decoupled hops:
- client hop: identity-only OAuth (FastMCP GoogleProvider) — establishes *who*, grants no Drive.
- drive hop: one fixed service account (3 read scopes, no delegation) — the data boundary.

See docs/ARCHITECTURE.md for the full contract.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
