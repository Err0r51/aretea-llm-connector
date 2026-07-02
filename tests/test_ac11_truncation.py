"""AC11 — oversized output is truncated and says so explicitly (never silent)."""

from __future__ import annotations

from aretea_drive_mcp.toolsets.drive import truncate


def test_content_under_cap_is_untouched() -> None:
    content, was_truncated = truncate("hello world", cap=100)
    assert content == "hello world"
    assert was_truncated is False


def test_content_over_cap_is_truncated_with_explicit_note() -> None:
    content, was_truncated = truncate("x" * 500, cap=100)
    assert was_truncated is True
    assert content.startswith("x" * 100)
    assert "TRUNCATED" in content  # the note is explicit, not silent
    assert "500" in content  # states the real total


def test_content_exactly_at_cap_is_not_truncated() -> None:
    content, was_truncated = truncate("y" * 100, cap=100)
    assert was_truncated is False
    assert content == "y" * 100
