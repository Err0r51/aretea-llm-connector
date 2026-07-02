"""The toolset seam (NFR6).

A connector is a module exposing::

    def register(app: FastMCP, **deps) -> None

which adds its tools to the shared FastMCP app. Every toolset sits behind the *identical* auth
front (the client hop) — auth and hosting are solved once. A future Slack/HubSpot/Granola connector
is a new module here implementing the same ``register`` contract; nothing about auth changes.

Keeping the seam this thin is deliberate: the whole point of PRD_01 is that connector #2 costs a
module, not a re-solve of auth + hosting.
"""

from __future__ import annotations

from typing import Protocol

from fastmcp import FastMCP


class Toolset(Protocol):
    """Structural type a toolset module satisfies via a module-level ``register`` function."""

    def register(self, app: FastMCP, /, **deps: object) -> None: ...
