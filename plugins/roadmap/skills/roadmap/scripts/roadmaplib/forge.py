"""Forge access: GitLab (through `glab api`) and GitHub (through `gh api`).

Both adapters return the same plain dictionaries so publish and sync do not
care which forge they talk to:

  issue: {ref, url, id, number, project, title, state ("open"|"closed"), body,
          labels, updated_at, epic_number}
  epic:  {ref, url, id, number, title, body}
  merge request: {ref, url, number, project, title, body, state
          ("open"|"merged"|"closed"), draft, updated_at, pipeline, pipeline_url}

Credentials stay inside glab and gh; this module never reads or prints them.
Writes go through WriteGuard, which refuses deletes and closes outright.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from urllib.parse import quote


class ForgeError(Exception):
    pass


class NotFound(ForgeError):
    pass


class WriteGuard:
    """publish may create and update, never close or delete."""

    def check(self, method: str, path: str, body) -> None:
        if method.upper() == "DELETE":
            raise ForgeError(f"refusing to delete on the forge: {path}")
        text = json.dumps(body or {})
        if '"state_event"' in text or re.search(r'"state":\s*"closed"', text):
            raise ForgeError(f"refusing to close anything on the forge: {path}")


# --- transports -------------------------------------------------------------


class RecordedTransport:
    """Answers reads from a dictionary keyed "GET path". Used by tests and demos.

    Writes are refused: a recorded transport is for dry runs.
    """

    def __init__(self, responses: dict):
        self.responses = responses

    def get(self, path: str):
        key = f"GET {path}"
        if key not in self.responses:
            raise NotFound(f"no recorded response for {key}")
        return self.responses[key]

    def get_all(self, path: str) -> list:
        return list(self.get(path))

    def send(self, method: str, path: str, body=None):
        raise ForgeError(f"recorded responses cannot write ({method} {path}); this is a dry run")


class CliTransport:
    """Calls the forge API through `glab api` or `gh api`, which hold the login."""

    def __init__(self, kind: str, host: str | None):
        self.kind = kind
        self.host = host
        self.tool = "glab" if kind == "gitlab" else "gh"
        if not shutil.which(self.tool):
            raise ForgeError(f"{self.tool} is not installed; it is needed to reach {kind}")
        self.guard = WriteGuard()

    def _run(self, args: list[str], body=None):
        cmd = [self.tool, "api"]
        if self.host and not (self.kind == "github" and self.host == "github.com"):
            cmd += ["--hostname", self.host]
        cmd += args
        proc = subprocess.run(cmd, input=json.dumps(body) if body is not None else None,
                              capture_output=True, text=True)
        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout).strip().splitlines()
            msg = msg[-1] if msg else "unknown error"
            if "404" in msg or "Not Found" in msg:
                raise NotFound(f"{args[-1]}: {msg}")
            raise ForgeError(f"{self.tool} api {args[-1]} failed: {msg}")
        out = proc.stdout.strip()
        return json.loads(out) if out else {}

    def get(self, path: str):
        return self._run([path])

    def get_all(self, path: str) -> list:
        out, page = [], 1
        sep = "&" if "?" in path else "?"
        while True:
            chunk = self.get(f"{path}{sep}per_page=100&page={page}")
            if not isinstance(chunk, list):
                raise ForgeError(f"expected a list from {path}")
            out.extend(chunk)
            if len(chunk) < 100:
                return out
            page += 1

    def send(self, method: str, path: str, body=None):
        self.guard.check(method, path, body)
        args = ["-X", method.upper(), path]
        if body is not None:
            args = ["-X", method.upper(), "-H", "Content-Type: application/json", "--input", "-", path]
        return self._run(args, body)


# --- references -------------------------------------------------------------

ISSUE_REF = re.compile(r"^(?P<project>[\w.-]+(?:/[\w.-]+)*)#(?P<n>\d+)$")
EPIC_REF = re.compile(r"^(?P<group>[\w.-]+(?:/[\w.-]+)*)&(?P<n>\d+)$")


def split_issue_ref(ref: str) -> tuple[str, int]:
    m = ISSUE_REF.match(ref or "")
    if not m:
        raise ForgeError(f'"{ref}" is not an issue reference like group/project#12')
    return m["project"], int(m["n"])


def enc(path: str) -> str:
    return quote(path, safe="")


# --- adapters ---------------------------------------------------------------


class GitLab:
    kind = "gitlab"
    epic_word = "group epic"

    def __init__(self, transport, host: str | None, project: str | None, group: str | None):
        self.t = transport
        self.host = host
        self.project = project
        self.group = group
        self._open_cache: dict[str, list] = {}

    # issues
    def _issue(self, d: dict) -> dict:
        refs = d.get("references") or {}
        project = refs.get("full", "").rsplit("#", 1)[0] or None
        return {"ref": refs.get("full"), "url": d.get("web_url"), "id": d.get("id"), "number": d.get("iid"),
                "project": project, "project_id": d.get("project_id"), "title": d.get("title", ""),
                "state": "closed" if d.get("state") == "closed" else "open", "body": d.get("description") or "",
                "labels": list(d.get("labels") or []), "updated_at": d.get("updated_at"),
                "epic_number": (d.get("epic") or {}).get("iid") or d.get("epic_iid"),
                "epic_id": (d.get("epic") or {}).get("id")}

    def get_issue(self, ref: str) -> dict:
        project, n = split_issue_ref(ref)
        return self._issue(self.t.get(f"projects/{enc(project)}/issues/{n}"))

    def open_issues(self, project: str) -> list[dict]:
        if project not in self._open_cache:
            raw = self.t.get_all(f"projects/{enc(project)}/issues?state=opened")
            self._open_cache[project] = [self._issue(d) for d in raw]
        return self._open_cache[project]

    def create_issue(self, project: str, title: str, body: str, epic: dict | None) -> dict:
        payload = {"title": title, "description": body}
        if epic and epic.get("id"):
            payload["epic_id"] = epic["id"]
        return self._issue(self.t.send("POST", f"projects/{enc(project)}/issues", payload))

    def update_issue_body(self, issue: dict, body: str) -> None:
        self.t.send("PUT", f"projects/{enc(issue['project'])}/issues/{issue['number']}", {"description": body})

    def in_epic(self, issue: dict, epic: dict) -> bool:
        return bool(epic.get("number")) and issue.get("epic_number") == epic["number"]

    def add_to_epic(self, issue: dict, epic: dict) -> None:
        self.t.send("PUT", f"projects/{enc(issue['project'])}/issues/{issue['number']}", {"epic_id": epic["id"]})

    def blocked_by(self, issue: dict) -> set[str]:
        links = self.t.get_all(f"projects/{enc(issue['project'])}/issues/{issue['number']}/links")
        return {(d.get("references") or {}).get("full") for d in links if d.get("link_type") == "is_blocked_by"}

    def add_blocked_by(self, issue: dict, dep: dict) -> None:
        self.t.send("POST", f"projects/{enc(issue['project'])}/issues/{issue['number']}/links",
                    {"target_project_id": dep.get("project_id") or dep["project"],
                     "target_issue_iid": dep["number"], "link_type": "is_blocked_by"})

    # epics
    def _epic(self, d: dict, group: str) -> dict:
        return {"ref": f"{group}&{d.get('iid')}", "url": d.get("web_url"), "id": d.get("id"),
                "number": d.get("iid"), "title": d.get("title", ""), "body": d.get("description") or ""}

    def get_epic(self, ref: str) -> dict:
        m = EPIC_REF.match(ref or "")
        if not m:
            raise ForgeError(f'"{ref}" is not a GitLab epic reference like group&12')
        return self._epic(self.t.get(f"groups/{enc(m['group'])}/epics/{m['n']}"), m["group"])

    def create_epic(self, title: str, body: str) -> dict:
        if not self.group:
            raise ForgeError('set forge "group" in roadmap.json to create GitLab epics')
        return self._epic(self.t.send("POST", f"groups/{enc(self.group)}/epics",
                                      {"title": title, "description": body}), self.group)

    def update_epic_body(self, epic: dict, body: str) -> None:
        group = epic["ref"].rsplit("&", 1)[0]
        self.t.send("PUT", f"groups/{enc(group)}/epics/{epic['number']}", {"description": body})

    def epic_issues(self, epic: dict) -> list[dict]:
        group = epic["ref"].rsplit("&", 1)[0]
        return [self._issue(d) for d in self.t.get_all(f"groups/{enc(group)}/epics/{epic['number']}/issues")]

    # merge requests
    def _mr(self, d: dict) -> dict:
        refs = d.get("references") or {}
        full = refs.get("full") or ""
        pipe = d.get("head_pipeline") or d.get("pipeline") or {}
        return {"ref": full, "url": d.get("web_url"), "number": d.get("iid"),
                "project": full.rsplit("!", 1)[0] or None, "title": d.get("title", ""),
                "body": d.get("description") or "",
                "state": {"opened": "open", "merged": "merged"}.get(d.get("state"), "closed"),
                "draft": bool(d.get("draft") or d.get("work_in_progress")), "updated_at": d.get("updated_at"),
                "pipeline": pipe.get("status"), "pipeline_url": pipe.get("web_url")}

    def related_mrs(self, issue: dict) -> list[dict]:
        raw = self.t.get_all(f"projects/{enc(issue['project'])}/issues/{issue['number']}/related_merge_requests")
        out = []
        for d in raw:
            mr = self._mr(d)
            if mr["state"] == "open" and not mr["pipeline"] and mr["project"]:
                try:
                    mr = self._mr(self.t.get(f"projects/{enc(mr['project'])}/merge_requests/{mr['number']}"))
                except NotFound:
                    pass
            out.append(mr)
        return out

    def open_mrs(self, project: str) -> list[dict]:
        return [self._mr(d) for d in self.t.get_all(f"projects/{enc(project)}/merge_requests?state=opened")]

    def mr_mentions(self, mr: dict) -> set[str]:
        """Issue references an MR's title or description makes, as full refs."""
        text = f"{mr['title']}\n{mr['body']}"
        refs = {m.group(0) for m in re.finditer(r"[\w.-]+(?:/[\w.-]+)+#\d+", text)}
        refs |= {f"{mr['project']}#{n}" for n in re.findall(r"(?<![\w/&!])#(\d+)", text)}
        return refs


class GitHub:
    kind = "github"
    epic_word = "parent issue"

    def __init__(self, transport, host: str | None, project: str | None, group: str | None = None):
        self.t = transport
        self.host = host or "github.com"
        self.project = project
        self._open_cache: dict[str, list] = {}

    def _issue(self, d: dict, project: str) -> dict:
        n = d.get("number")
        return {"ref": f"{project}#{n}", "url": d.get("html_url"), "id": d.get("id"), "number": n,
                "project": project, "title": d.get("title", ""),
                "state": "closed" if d.get("state") == "closed" else "open", "body": d.get("body") or "",
                "labels": [lb["name"] if isinstance(lb, dict) else lb for lb in d.get("labels") or []],
                "updated_at": d.get("updated_at"), "epic_number": None,
                "is_pull_request": "pull_request" in d}

    def get_issue(self, ref: str) -> dict:
        project, n = split_issue_ref(ref)
        return self._issue(self.t.get(f"repos/{project}/issues/{n}"), project)

    def open_issues(self, project: str) -> list[dict]:
        if project not in self._open_cache:
            raw = self.t.get_all(f"repos/{project}/issues?state=open")
            self._open_cache[project] = [i for i in (self._issue(d, project) for d in raw)
                                         if not i["is_pull_request"]]
        return self._open_cache[project]

    def create_issue(self, project: str, title: str, body: str, epic: dict | None) -> dict:
        issue = self._issue(self.t.send("POST", f"repos/{project}/issues", {"title": title, "body": body}), project)
        if epic and epic.get("id"):
            self.add_to_epic(issue, epic)
        return issue

    def update_issue_body(self, issue: dict, body: str) -> None:
        self.t.send("PATCH", f"repos/{issue['project']}/issues/{issue['number']}", {"body": body})

    def in_epic(self, issue: dict, epic: dict) -> bool:
        if not epic.get("number"):
            return False
        return issue["ref"] in {i["ref"] for i in self.epic_issues(epic)}

    def add_to_epic(self, issue: dict, epic: dict) -> None:
        project = epic["ref"].rsplit("#", 1)[0]
        self.t.send("POST", f"repos/{project}/issues/{epic['number']}/sub_issues", {"sub_issue_id": issue["id"]})

    def blocked_by(self, issue: dict) -> set[str]:
        raw = self.t.get_all(f"repos/{issue['project']}/issues/{issue['number']}/dependencies/blocked_by")
        out = set()
        for d in raw:
            repo = (d.get("repository") or {}).get("full_name") or issue["project"]
            out.add(f"{repo}#{d.get('number')}")
        return out

    def add_blocked_by(self, issue: dict, dep: dict) -> None:
        self.t.send("POST", f"repos/{issue['project']}/issues/{issue['number']}/dependencies/blocked_by",
                    {"issue_id": dep["id"]})

    def get_epic(self, ref: str) -> dict:
        issue = self.get_issue(ref)
        return {k: issue[k] for k in ("ref", "url", "id", "number", "title", "body")}

    def create_epic(self, title: str, body: str) -> dict:
        if not self.project:
            raise ForgeError('set forge "project" in roadmap.json to create GitHub parent issues')
        d = self.t.send("POST", f"repos/{self.project}/issues", {"title": title, "body": body, "labels": ["epic"]})
        issue = self._issue(d, self.project)
        return {k: issue[k] for k in ("ref", "url", "id", "number", "title", "body")}

    def update_epic_body(self, epic: dict, body: str) -> None:
        self.update_issue_body({"project": epic["ref"].rsplit("#", 1)[0], "number": epic["number"]}, body)

    def epic_issues(self, epic: dict) -> list[dict]:
        project = epic["ref"].rsplit("#", 1)[0]
        return [self._issue(d, project) for d in self.t.get_all(f"repos/{project}/issues/{epic['number']}/sub_issues")]

    def _pr(self, d: dict, project: str) -> dict:
        state = "merged" if d.get("merged_at") or d.get("merged") else (
            "open" if d.get("state") == "open" else "closed")
        return {"ref": f"{project}#{d.get('number')}", "url": d.get("html_url"), "number": d.get("number"),
                "project": project, "title": d.get("title", ""), "body": d.get("body") or "", "state": state,
                "draft": bool(d.get("draft")), "updated_at": d.get("updated_at"),
                "pipeline": None, "pipeline_url": None, "head_sha": (d.get("head") or {}).get("sha")}

    def _with_checks(self, pr: dict) -> dict:
        if pr["state"] == "open" and pr.get("head_sha"):
            try:
                st = self.t.get(f"repos/{pr['project']}/commits/{pr['head_sha']}/status")
                pr["pipeline"] = st.get("state")
                pr["pipeline_url"] = f"{pr['url']}/checks" if pr.get("url") else None
            except NotFound:
                pass
        return pr

    def related_mrs(self, issue: dict) -> list[dict]:
        events = self.t.get_all(f"repos/{issue['project']}/issues/{issue['number']}/timeline")
        seen, out = set(), []
        for ev in events:
            src = (ev.get("source") or {}).get("issue") or {}
            if ev.get("event") != "cross-referenced" or "pull_request" not in src:
                continue
            repo = (src.get("repository") or {}).get("full_name") or issue["project"]
            key = (repo, src.get("number"))
            if key in seen:
                continue
            seen.add(key)
            try:
                pr = self._pr(self.t.get(f"repos/{repo}/pulls/{src.get('number')}"), repo)
            except NotFound:
                continue
            out.append(self._with_checks(pr))
        return out

    def open_mrs(self, project: str) -> list[dict]:
        return [self._pr(d, project) for d in self.t.get_all(f"repos/{project}/pulls?state=open")]

    def mr_mentions(self, mr: dict) -> set[str]:
        text = f"{mr['title']}\n{mr['body']}"
        refs = {m.group(0) for m in re.finditer(r"[\w.-]+/[\w.-]+#\d+", text)}
        refs |= {f"{mr['project']}#{n}" for n in re.findall(r"(?<![\w/])#(\d+)", text)}
        return refs


# --- choosing a forge -------------------------------------------------------


def detect_from_remote(repo: str) -> tuple[str, str | None]:
    """Forge kind and host from the checkout's origin remote."""
    try:
        url = subprocess.run(["git", "-C", repo, "remote", "get-url", "origin"],
                             capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise ForgeError(f'no forge set in roadmap.json and no git remote in {repo}; set forge.kind') from exc
    m = re.match(r"^(?:\w+://)?(?:[^@/]+@)?([^/:]+)[:/]", url)
    host = m.group(1) if m else None
    return ("github" if host and "github" in host else "gitlab"), host


def make(kind: str, transport, cfg: dict):
    cls = GitLab if kind == "gitlab" else GitHub
    return cls(transport, host=cfg.get("host"), project=cfg.get("project"), group=cfg.get("group"))


def from_args(data: dict, args) -> GitLab | GitHub:
    cfg = dict(data.get("forge") or {})
    kind = getattr(args, "forge", None) or cfg.get("kind")
    if not kind:
        kind, host = detect_from_remote(getattr(args, "repo", "."))
        cfg.setdefault("host", host)
    if getattr(args, "recorded", None):
        with open(args.recorded) as fh:
            transport = RecordedTransport(json.load(fh))
    else:
        transport = CliTransport(kind, cfg.get("host"))
    return make(kind, transport, cfg)
