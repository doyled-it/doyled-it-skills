"""check-mr: fail a merge request that names no issue on the agreed roadmap.

Runs offline in a merge request pipeline (GitLab CI, GitHub Actions, Forgejo
Actions) or by hand. A merge request names a roadmap issue when its title or
description has the issue's short name, its forge reference (or "#12" in the
same project), or its URL. The merge request templates put this on a
"Roadmap issue:" line and a "Closes #N" line.
"""

from __future__ import annotations

import json
import os
import re
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


def check(raw: dict, title: str, body: str, project: str | None) -> Result:
    """Does the merge request name an issue on the agreed roadmap?"""
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
