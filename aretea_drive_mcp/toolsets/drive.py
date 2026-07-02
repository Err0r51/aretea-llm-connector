"""The read-only Drive toolset (FR3/FR4/FR6).

Only read tools are defined — there is no create/update/delete/share/permission tool anywhere in
this module, which is what makes AC8 hold structurally rather than by policy.

⚠ The ``@app.tool`` decorator shape is the documented FastMCP 3.x API; verify it registers as
expected against fastmcp 3.4.2 at build.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from aretea_drive_mcp.gdrive.client import DriveClient


def truncate(content: str, cap: int) -> tuple[str, bool]:
    """Cap output at `cap` chars, stating the truncation explicitly (AC11 — never silent).

    Pure and unit-testable. Returns ``(possibly_truncated_content, was_truncated)``.
    """
    if len(content) <= cap:
        return content, False
    note = (
        f"\n\n[TRUNCATED: output exceeded the {cap:,}-char cap "
        f"({len(content):,} chars total). Use `cell_range`/`sheet` or `page_token` to read more.]"
    )
    return content[:cap] + note, True


def register(app: FastMCP, *, client: DriveClient, max_read_chars: int) -> None:
    """Register the three read tools on `app`, bound to a scoped `DriveClient`."""

    @app.tool
    async def drive_search(
        query: str, page_size: int = 25, page_token: str | None = None
    ) -> dict[str, Any]:
        """Search the AI-Visible Shared Drive.

        `query` is a Google Drive `files.list` query (e.g. `name contains 'budget'`). Returns
        matching files (id, name, mimeType, modifiedTime, owners, webViewLink, size) and a
        `next_page_token` for paging. Only files in the curated corpus are ever returned.
        """
        return await client.search(query, page_size=page_size, page_token=page_token)

    @app.tool
    async def drive_get_metadata(file_id: str) -> dict[str, Any]:
        """Get metadata for one file in the AI-Visible drive (refuses files outside it)."""
        return await client.get_metadata(file_id)

    @app.tool
    async def drive_read_file(
        file_id: str, sheet: str | None = None, cell_range: str | None = None
    ) -> dict[str, Any]:
        """Read a file's text content at basic fidelity.

        Docs → plain text; Sheets → cell values (no formulas), optionally scoped by `sheet` or A1
        `cell_range`; Slides → per-slide text (no layout); plain-text files → their text; binaries
        (PDF/Office) → a placeholder note (extraction is a v1 fast-follow). Large output is
        truncated with an explicit note (`truncated: true`); page with `cell_range`/`sheet`.
        """
        result = await client.read_file(file_id, sheet=sheet, cell_range=cell_range)
        content, was_truncated = truncate(result["content"], max_read_chars)
        return {
            "mime_type": result["mime_type"],
            "name": result.get("name"),
            "content": content,
            "truncated": was_truncated,
        }
