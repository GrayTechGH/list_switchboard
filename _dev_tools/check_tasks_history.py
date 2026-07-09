"""Check `_docs/TASKS.md` completed-history retention."""

from __future__ import annotations

import re
import sys
from pathlib import Path


VERSION_HEADING_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+):\s*$")
MAX_COUNTED_VERSIONS = 3


def _version_label(version: tuple[int, int, int]) -> str:
    return "{}.{}.{}".format(*version)


def _counted_key(version: tuple[int, int, int]) -> tuple[int, int]:
    return version[:2]


def find_version_headings(tasks_text: str) -> list[tuple[int, int, int]]:
    headings: list[tuple[int, int, int]] = []
    for line in tasks_text.splitlines():
        match = VERSION_HEADING_RE.match(line)
        if match:
            headings.append(tuple(int(part) for part in match.groups()))
    return headings


def retained_counted_keys(
    versions: list[tuple[int, int, int]],
) -> list[tuple[int, int]]:
    distinct_keys: list[tuple[int, int]] = []
    for version in versions:
        key = _counted_key(version)
        if key not in distinct_keys:
            distinct_keys.append(key)
    return distinct_keys[-MAX_COUNTED_VERSIONS:]


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    tasks_path = repo_root / "_docs" / "TASKS.md"
    tasks_text = tasks_path.read_text(encoding="utf-8")
    versions = find_version_headings(tasks_text)
    allowed_keys = retained_counted_keys(versions)
    stale_versions = [
        version for version in versions if _counted_key(version) not in allowed_keys
    ]

    if stale_versions:
        allowed = ", ".join("{}.{}.x".format(*key) for key in allowed_keys)
        stale = ", ".join(_version_label(version) for version in stale_versions)
        print(
            "TASKS.md completed history keeps stale counted versions: {}".format(
                stale
            ),
            file=sys.stderr,
        )
        print(
            "Keep only the current counted version plus two previous counted "
            "versions: {}.".format(allowed),
            file=sys.stderr,
        )
        return 1

    kept = ", ".join("{}.{}.x".format(*key) for key in allowed_keys)
    print("TASKS.md completed-history retention OK: {}.".format(kept))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
