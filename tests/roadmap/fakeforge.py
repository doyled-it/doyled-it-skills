"""A small stateful fake of the GitHub API paths publish uses (tests only, no network).

It keeps issues, sub-issues and blocked-by links in memory, applies writes, and
counts them, so a test can publish twice and check that the second run writes
nothing. Every write goes through the real WriteGuard first.
"""

from __future__ import annotations

import copy
import re

import helpers  # noqa: F401  (puts the roadmap scripts on sys.path)
from roadmaplib import forge


class FakeGitHub:
    def __init__(self, fail_on_write: int | None = None):
        self.issues: dict[tuple[str, int], dict] = {}
        self.sub_issues: dict[tuple[str, int], list[int]] = {}
        self.blocked: dict[tuple[str, int], list[int]] = {}
        self.writes: list[tuple[str, str, dict | None]] = []
        self.fail_on_write = fail_on_write
        self.guard = forge.WriteGuard(commands=False)
        self._next_id = 9000
        self.me: str | None = "roadmap-bot"   # the token's user; None: the forge will not say
        self.user_error: str | None = None     # when set, GET user fails with this message

    # state helpers
    def add_issue(self, repo: str, number: int, title: str, body: str = "", state: str = "open",
                  author: str | None = None) -> dict:
        self._next_id += 1
        d = {"id": self._next_id, "number": number, "title": title, "body": body, "state": state, "labels": [],
             "user": {"login": author or self.me or "someone"},
             "updated_at": "2026-11-16T10:00:00Z", "html_url": f"https://github.com/{repo}/issues/{number}",
             "repository_url": f"https://api.github.com/repos/{repo}"}
        self.issues[(repo, number)] = d
        return d

    def by_id(self, iid: int) -> dict:
        return next(d for d in self.issues.values() if d["id"] == iid)

    def titles(self, repo: str) -> list[str]:
        return [d["title"] for (r, _), d in sorted(self.issues.items()) if r == repo]

    # transport interface
    def get(self, path: str):
        path, _, query = path.partition("?")
        if path == "user":
            if self.user_error:
                raise forge.ForgeError(self.user_error)
            if self.me is None:
                raise forge.ForgeError("GET user failed: HTTP 401")
            return {"login": self.me}
        m = re.fullmatch(r"repos/([^/]+/[^/]+)/issues", path)
        if m:
            state = dict(p.split("=") for p in query.split("&") if p).get("state", "open")
            return [copy.deepcopy(d) for (r, _), d in sorted(self.issues.items())
                    if r == m[1] and (state == "all" or d["state"] == state)]
        if re.fullmatch(r"repos/[^/]+/[^/]+/pulls", path):
            return []
        m = re.fullmatch(r"repos/([^/]+/[^/]+)/issues/(\d+)(/.*)?", path)
        if not m:
            raise forge.NotFound(path)
        key = (m[1], int(m[2]))
        if key not in self.issues:
            raise forge.NotFound(path)
        if m[3] is None:
            return copy.deepcopy(self.issues[key])
        if m[3] == "/sub_issues":
            return [copy.deepcopy(self.by_id(i)) for i in self.sub_issues.get(key, [])]
        if m[3] == "/dependencies/blocked_by":
            return [copy.deepcopy(self.by_id(i)) for i in self.blocked.get(key, [])]
        if m[3] == "/timeline":
            return []
        raise forge.NotFound(path)

    def get_all(self, path: str) -> list:
        return list(self.get(path))

    def send(self, method: str, path: str, body=None, allow_close: bool = False):
        self.guard.check(method, path, body, allow_close=allow_close)
        if self.fail_on_write is not None and len(self.writes) + 1 == self.fail_on_write:
            raise forge.ForgeError(f"{method} {path} failed: HTTP 403")
        self.writes.append((method, path, body))
        m = re.fullmatch(r"repos/([^/]+/[^/]+)/issues", path)
        if method == "POST" and m:
            number = max([n for (r, n) in self.issues if r == m[1]], default=0) + 1
            return copy.deepcopy(self.add_issue(m[1], number, body["title"], body.get("body", "")))
        m = re.fullmatch(r"repos/([^/]+/[^/]+)/issues/(\d+)(/.*)?", path)
        key = (m[1], int(m[2]))
        if method == "PATCH" and m[3] is None:
            self.issues[key].update({k: v for k, v in body.items() if k in ("body", "title", "state")})
            return copy.deepcopy(self.issues[key])
        if method == "POST" and m[3] == "/sub_issues":
            self.sub_issues.setdefault(key, []).append(body["sub_issue_id"])
            return {}
        if method == "POST" and m[3] == "/dependencies/blocked_by":
            self.blocked.setdefault(key, []).append(body["issue_id"])
            return {}
        raise forge.ForgeError(f"fake forge does not handle {method} {path}")


def github(fake: FakeGitHub, project: str = "example-org/search-service") -> forge.GitHub:
    return forge.GitHub(fake, host="github.com", project=project)
