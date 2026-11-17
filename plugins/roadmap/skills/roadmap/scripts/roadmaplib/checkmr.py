"""check-mr: fail a merge request that names no issue on the agreed roadmap.

Runs offline in a merge request pipeline (GitLab CI, GitHub Actions, Forgejo
Actions) or by hand. A merge request names a roadmap issue when its title or
description has the issue's short name, its forge reference (or "#12" in the
same project), or its URL. The merge request templates put this on a
"Roadmap issue:" line and a "Closes #N" line.

A merge request that changes only the roadmap (roadmap.json and its rendered
page) passes without naming an issue: that is the lead's agreed change, or the
synced roadmap.json from the scheduled job. In CI the changed files are read
from git against the merge request's base commit (renames count as a delete and
an add, so renaming code to roadmap.html is not a roadmap change), and the
agreed roadmap is read from that base commit too: a merge request cannot add an
issue to roadmap.json, or agree a draft, and then name it.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field

from . import model

TEMPLATE_HINT = ('Add a line "Roadmap issue: <short name> <link>" and "Closes #N" to the description, '
                 "naming the issue on the agreed roadmap this change delivers. If the work is not on the "
                 "roadmap, propose a roadmap change to the program lead first.")


@dataclass
class Result:
    ok: bool
    message: str
    issue: str | None = None
    warnings: list[str] = field(default_factory=list)


def _named(it: dict, text: str, project: str | None) -> bool:
    low = text.lower()
    if re.search(rf"(?<![\w/-]){re.escape(it['id'])}(?![\w-])", low):
        return True
    ref = it.get("ref")
    if ref and re.search(rf"(?<![\w/.-]){re.escape(ref)}(?!\d)", text):
        return True
    if ref and project and ref.rsplit("#", 1)[0] == project:
        if re.search(rf"(?<![\w/&!#]){re.escape('#' + ref.rsplit('#', 1)[1])}(?!\d)", text):
            return True
    url = model.safe_url(it.get("url"))
    return bool(url and re.search(rf"{re.escape(url.rstrip('/'))}(?![\w/])", text))


def _norm(path: str) -> str:
    return os.path.normpath(os.path.relpath(os.path.abspath(path)))


def roadmap_only(changed: list[str] | None, roadmap_path: str | None) -> bool:
    """True when every changed file is the roadmap or its rendered page."""
    if not changed or not roadmap_path:
        return False
    own = {_norm(roadmap_path), _norm(str(os.path.splitext(roadmap_path)[0]) + ".html")}
    return all(_norm(c) in own for c in changed)


def check(raw: dict | None, title: str, body: str, project: str | None, changed: list[str] | None = None,
          roadmap_path: str | None = None) -> Result:
    """Does the merge request name an issue on the agreed roadmap, or change only the roadmap?"""
    if roadmap_only(changed, roadmap_path):
        return Result(True, f"Changes only the roadmap ({', '.join(sorted(set(changed)))}); the program lead "
                            "reviews it, and no roadmap issue is needed.")
    if raw is None:
        return Result(False, "The merge request's base commit has no roadmap.json, so there is no agreed roadmap to "
                             "check against. Add the roadmap in a merge request of its own first.")
    if not raw.get("agreed"):
        return Result(False, 'The roadmap is a draft. Merge requests are checked against an agreed roadmap: '
                             'get the program lead\'s agreement and set "agreed": true.')
    data = model.normalize(raw)
    items = model.issues_by_id(data)
    text = f"{title or ''}\n{body or ''}"
    named = [it for it in data["issues"] if isinstance(it, dict) and it.get("id") and _named(it, text, project)]
    if not named:
        return Result(False, f"This merge request names no issue on the agreed roadmap. {TEMPLATE_HINT}")
    it = named[0]
    label = f'{it["id"]}' + (f' ({it["ref"]})' if it.get("ref") else "")
    warnings = []
    waiting = [d for d in it["depends_on"] if d in items and items[d]["status"] != "done"]
    if waiting:
        warnings.append(f"{it['id']} depends on issues that are not Done yet: {', '.join(waiting)}")
    if it["status"] == "done":
        warnings.append(f"{it['id']} is already Done on the roadmap")
    others = [x["id"] for x in named[1:]]
    more = f" (also names {', '.join(others)})" if others else ""
    return Result(True, f"Names roadmap issue {label}, status {model.STATUSES[it['status']]}{more}.", it["id"], warnings)


def from_ci(env=None) -> tuple[str, str, str | None]:
    """Title, description and project of the merge request this pipeline runs for."""
    env = os.environ if env is None else env
    if env.get("GITLAB_CI"):
        if "CI_MERGE_REQUEST_TITLE" not in env:
            raise ValueError("this GitLab pipeline is not a merge request pipeline "
                             "(run the job only for merge_request_event)")
        return (env.get("CI_MERGE_REQUEST_TITLE", ""), env.get("CI_MERGE_REQUEST_DESCRIPTION", ""),
                env.get("CI_MERGE_REQUEST_PROJECT_PATH") or env.get("CI_PROJECT_PATH"))
    if any(env.get(k) for k in ("GITHUB_ACTIONS", "FORGEJO_ACTIONS", "GITEA_ACTIONS")):
        path = env.get("GITHUB_EVENT_PATH")
        if not path:
            raise ValueError("GITHUB_EVENT_PATH is not set")
        with open(path) as fh:
            pr = (json.load(fh) or {}).get("pull_request")
        if not pr:
            raise ValueError("this workflow run is not for a pull request (run it on pull_request)")
        return pr.get("title") or "", pr.get("body") or "", env.get("GITHUB_REPOSITORY")
    raise ValueError("not in a GitLab, GitHub or Forgejo merge request pipeline; pass --title and --body instead")


def ci_base(env=None) -> str | None:
    """The merge request's base commit in CI, when the forge gives it."""
    env = os.environ if env is None else env
    if env.get("GITLAB_CI"):
        return env.get("CI_MERGE_REQUEST_DIFF_BASE_SHA") or None
    path = env.get("GITHUB_EVENT_PATH")
    if path:
        try:
            with open(path) as fh:
                return (((json.load(fh) or {}).get("pull_request") or {}).get("base") or {}).get("sha")
        except (OSError, ValueError):
            return None
    return None


def changed_files(base: str) -> list[str] | None:
    """Files changed since base, from git in the working directory; None when git cannot tell."""
    if not re.fullmatch(r"[0-9a-fA-F]{7,64}", base or ""):
        return None
    try:
        proc = subprocess.run(["git", "-c", f"safe.directory={os.getcwd()}", "diff", "--name-only", "--no-renames",
                               f"{base}...HEAD"],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", f"safe.directory={os.getcwd()}", *args], capture_output=True, text=True,
                          timeout=30)


def base_roadmap(base: str, roadmap_path: str) -> dict | None:
    """roadmap.json as it is at the base commit; None when the base has none.

    The merge request's own copy is never used: it could add the very issue the
    merge request names. ValueError when git cannot read the base commit.
    """
    history = 'fetch the full history (fetch-depth: 0, or GIT_DEPTH: "0" on GitLab)'
    if not re.fullmatch(r"[0-9a-fA-F]{7,64}", base or ""):
        raise ValueError(f"the base commit {str(base)[:70]!r} is not a commit id")
    try:
        found = _git("cat-file", "-e", f"{base}^{{commit}}")
        if found.returncode != 0:
            raise ValueError(f"git cannot find the base commit {base} to read the agreed roadmap from; {history}")
        rel = os.path.relpath(os.path.abspath(roadmap_path)).replace(os.sep, "/")
        shown = _git("show", f"{base}:./{rel}")
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"git could not read the base commit ({exc}); {history}") from None
    if shown.returncode != 0:
        return None
    try:
        raw = json.loads(shown.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"roadmap.json at the base commit {base} is not valid JSON: {exc}") from None
    if not isinstance(raw, dict):
        raise ValueError(f"roadmap.json at the base commit {base} must hold one JSON object")
    return raw
