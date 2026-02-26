from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class GitMetadata:
    branch: str
    tag: str
    last_commit: str
    committer: str
    date: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _run_git(args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=_project_root(),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    output = completed.stdout.strip()
    if not output:
        return None
    return output.splitlines()[0].strip() or None


@lru_cache(maxsize=1)
def get_git_metadata() -> GitMetadata:
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    tag = _run_git(["tag", "--points-at", "HEAD"])
    if not tag:
        tag = _run_git(["describe", "--tags", "--always"])
    tag = tag or "unknown"
    last_commit = _run_git(["rev-parse", "HEAD"]) or "unknown"
    committer = _run_git(["show", "-s", "--format=%cn", "HEAD"]) or "unknown"
    date = _run_git(["show", "-s", "--format=%cI", "HEAD"]) or "unknown"

    return GitMetadata(
        branch=branch,
        tag=tag,
        last_commit=last_commit,
        committer=committer,
        date=date,
    )


def _clear_git_metadata_cache() -> None:
    get_git_metadata.cache_clear()
