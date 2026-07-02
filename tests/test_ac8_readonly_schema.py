"""AC8 — the served tool schema contains ONLY read tools (no mutation verbs)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from aretea_drive_mcp.toolsets import drive
from fastmcp import FastMCP

FORBIDDEN_VERBS = (
    "create",
    "update",
    "delete",
    "share",
    "permission",
    "write",
    "insert",
    "remove",
    "move",
    "copy",
    "trash",
    "add",
    "set",
)
EXPECTED = {"drive_search", "drive_get_metadata", "drive_read_file"}


async def _tool_names(app: FastMCP) -> set[str]:
    # FastMCP 3.4.2: list_tools() -> list[Tool], each with .name.
    tools = await app.list_tools()
    return {t.name for t in tools}


@pytest.mark.asyncio
async def test_only_read_tools_are_registered() -> None:
    app = FastMCP(name="test")
    drive.register(app, client=MagicMock(), max_read_chars=1000)

    names = await _tool_names(app)
    assert names == EXPECTED
    for name in names:
        assert not any(verb in name.lower() for verb in FORBIDDEN_VERBS), name
