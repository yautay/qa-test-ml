from __future__ import annotations

import os
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


def _env_or_none(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


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
    branch = _env_or_none("APP_GIT_BRANCH") or _run_git(["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    tag = _env_or_none("APP_GIT_TAG") or _run_git(["tag", "--points-at", "HEAD"])
    if not tag:
        tag = _run_git(["describe", "--tags", "--always"])
    tag = tag or "unknown"
    last_commit = _env_or_none("APP_GIT_LAST_COMMIT") or _run_git(["rev-parse", "HEAD"]) or "unknown"
    committer = _env_or_none("APP_GIT_COMMITTER") or _run_git(["show", "-s", "--format=%cn", "HEAD"]) or "unknown"
    date = _env_or_none("APP_GIT_COMMIT_DATE") or _run_git(["show", "-s", "--format=%cI", "HEAD"]) or "unknown"

    return GitMetadata(
        branch=branch,
        tag=tag,
        last_commit=last_commit,
        committer=committer,
        date=date,
    )


def _clear_git_metadata_cache() -> None:
    get_git_metadata.cache_clear()
