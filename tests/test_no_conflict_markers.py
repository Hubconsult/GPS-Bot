"""Ensure repository does not contain unresolved merge conflict markers."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


# Build patterns without embedding the raw merge markers directly in the source
# file.  Keeping them literal caused this test module to fail the check against
# itself, so we compose the strings dynamically instead.
CONFLICT_PATTERNS = ("<" * 7, "=" * 7, ">" * 7)


def _list_tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    )
    repo_root = Path(__file__).resolve().parents[1]
    return [repo_root / Path(path_str) for path_str in result.stdout.splitlines()]


@pytest.mark.parametrize("file_path", _list_tracked_files())
def test_file_has_no_conflict_markers(file_path: Path) -> None:
    """Fail if any tracked file still contains merge conflict markers."""
    # Binary files may raise decoding errors, so skip them quietly
    try:
        text = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
    except FileNotFoundError:
        pytest.fail(f"Tracked file missing on disk: {file_path}")

    for marker in CONFLICT_PATTERNS:
        assert marker not in text, f"Found merge marker '{marker}' in {file_path}"
