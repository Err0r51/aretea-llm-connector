"""AC10 — the duplicated hardcoded ``__version__`` is gone; the single in-source floor is read via
``importlib.metadata`` (from ``pyproject`` ``project.version``).

Invariant-only: this asserts how OUR package sources its version string — no external service.
"""

from __future__ import annotations

import ast
import re
from importlib.metadata import version
from pathlib import Path

import aretea_drive_mcp


def test_version_is_read_from_distribution_metadata() -> None:
    # Equals the installed distribution metadata, not a literal baked into the module.
    assert aretea_drive_mcp.__version__ == version("aretea-drive-mcp")


def test_version_is_nonempty_semverish() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+.*", aretea_drive_mcp.__version__), (
        aretea_drive_mcp.__version__
    )


def test_version_is_read_via_importlib_not_a_top_level_literal() -> None:
    # AC10 guard against regression: the floor must be READ from distribution metadata, never
    # re-hardcoded as a duplicated top-level `__version__ = "X.Y.Z"` (the exact thing removed).
    # A literal fallback inside the try/except is fine — it is nested, not a module-body statement.
    src = Path(aretea_drive_mcp.__file__).read_text(encoding="utf-8")
    assert 'version("aretea-drive-mcp")' in src, "version must be read via importlib.metadata"

    for node in ast.parse(src).body:  # DIRECT module-level statements only
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets
        ):
            assert not isinstance(node.value, ast.Constant), (
                "__version__ must not be a hardcoded top-level literal"
            )
