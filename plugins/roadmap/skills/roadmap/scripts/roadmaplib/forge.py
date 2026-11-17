"""Forge access: GitLab (through `glab api`), GitHub (through `gh api`), and
Forgejo, Gitea or Codeberg (through their REST API).

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

from . import blocks
from .model import safe_url


class ForgeError(Exception):
    pass


class NotFound(ForgeError):
    pass


DRIFT_TITLE = "Roadmap drift"


class WriteGuard:
    """publish may create and update, never close or delete, and never run forge commands.

    The one exception is close_drift_issue: the tool may close its own "Roadmap
    drift" issue when drift is zero. That call passes allow_close=True, and the
    guard then accepts only a bare close (no other field) and still no delete.

    commands=True (GitLab) also refuses a description with a line GitLab would
    run as a quick action (/close, /move ...), which it does even through the
    API (blocks.gitlab_commands: the start of a line, outside code blocks).
    Titles never run commands. GitHub and Forgejo have no such syntax in issue
    descriptions. Every forge refuses a title that is not one line.
    """

    def __init__(self, commands: bool = True):
        self.commands = commands

    def check(self, method: str, path: str, body, allow_close: bool = False) -> None:
        if method.upper() == "DELETE":
            raise ForgeError(f"refusing to delete on the forge: {path}")
        if allow_close:
            if body not in ({"state_event": "close"}, {"state": "closed"}):
                raise ForgeError(f"refusing a close that changes anything else: {path}")
            return
        text = json.dumps(body or {})
        if '"state_event"' in text or re.search(r'"state":\s*"closed"', text):
            raise ForgeError(f"refusing to close anything on the forge: {path}")
        if not isinstance(body, dict):
            return
        title = body.get("title")
        if isinstance(title, str) and blocks.CONTROL.search(title):
            raise ForgeError(f"refusing a title that is not one line: {path}")
        if self.commands:
            for key, value in body.items():
                if key != "title" and isinstance(value, str) and blocks.gitlab_commands(value):
                    raise ForgeError(f"refusing to write {key} with a line GitLab would run as a command "
                                     f"(quick action): {path}")


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


# Token variables glab and gh send to whatever --hostname they are given, and the
# variable that names the host each one belongs to. GH_TOKEN is not listed: gh
# sends it only to github.com.
CLI_TOKENS = {"gitlab": (("GITLAB_TOKEN", "GITLAB_ACCESS_TOKEN", "OAUTH_TOKEN"), "GITLAB_HOST"),
              "github": (("GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"), "GH_HOST")}


def _bare(host: str | None, what: str) -> str | None:
    host = (host or "").strip().lower()
    if not host:
        return None
    if host.startswith("http://"):
        raise ForgeError(f"{what} uses http; the roadmap tool talks to forges over https only")
    host = host.removeprefix("https://").rstrip("/")
    if not BARE_HOST.match(host):
        raise ForgeError(f'{what} "{host[:60]}" must be a bare host name such as gitlab.example.com')
    return host


def cli_host(kind: str, host: str | None, env) -> str | None:
    """The host glab or gh may call, or ForgeError when a token would go to the wrong one.

    With a token variable set, the host is the one named beside the token
    (GITLAB_HOST, CI_SERVER_HOST in GitLab CI, or GH_HOST), never a different
    host from roadmap.json, which anyone could edit. Without one, glab and gh
    use their own stored login for the host, which is never sent elsewhere.
    """
    host = _bare(host, "forge host")
    if kind == "github" and host in (None, "github.com"):
        return host
    tokens, host_var = CLI_TOKENS[kind]
    in_use = [v for v in tokens if env.get(v)]
    if not in_use:
        return host
    named = env.get(host_var)
    source = host_var
    if not named and kind == "gitlab" and env.get("GITLAB_CI"):
        named, source = env.get("CI_SERVER_HOST"), "CI_SERVER_HOST"
    bound = _bare(named, source) or ("gitlab.com" if kind == "gitlab" else None)
    if bound is None:
        raise ForgeError(f"{in_use[0]} is set but {host_var} does not name the host it belongs to; set {host_var}")
    if host and host != bound:
        raise ForgeError(f'roadmap.json names forge host "{host}", but {in_use[0]} belongs to "{bound}" '
                         f"({source if named else 'the default'}); refusing to send it anywhere else. Set "
                         f"{host_var} if the token is for {host}")
    return bound


class CliTransport:
    """Calls the forge API through `glab api` or `gh api`, which hold the login."""

    def __init__(self, kind: str, host: str | None):
        import os

        self.kind = kind
        self.tool = "glab" if kind == "gitlab" else "gh"
        if not shutil.which(self.tool):
            raise ForgeError(f"{self.tool} is not installed; it is needed to reach {kind}")
        self.host = cli_host(kind, host, os.environ)
        if kind == "gitlab":
            self._https_only()
        self.guard = WriteGuard(commands=kind == "gitlab")

    def _https_only(self) -> None:
        """Refuse a glab login set to plain http for this host."""
        try:
            proc = subprocess.run(["glab", "config", "get", "api_protocol", "--host", self.host or "gitlab.com"],
                                  capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return
        if proc.returncode == 0 and str(proc.stdout).strip().lower() == "http":
            raise ForgeError(f"glab is set to plain http for {self.host or 'gitlab.com'}; the roadmap tool talks "
                             "to forges over https only (glab config set api_protocol https)")

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

    def send(self, method: str, path: str, body=None, allow_close: bool = False):
        self.guard.check(method, path, body, allow_close=allow_close)
        args = ["-X", method.upper(), path]
        if body is not None:
            args = ["-X", method.upper(), "-H", "Content-Type: application/json", "--input", "-", path]
        return self._run(args, body)


# Each token variable and the host it may be sent to. CODEBERG_TOKEN belongs to
# codeberg.org; FORGEJO_TOKEN and GITEA_TOKEN belong to the host named in
# FORGEJO_HOST or GITEA_HOST, set beside the token, never in roadmap.json (a
# shared roadmap could name any host).
TOKEN_VARS = (("CODEBERG_TOKEN", None), ("FORGEJO_TOKEN", "FORGEJO_HOST"), ("GITEA_TOKEN", "GITEA_HOST"))
BARE_HOST = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?(?::\d{1,5})?$")


def _same_host_redirects(host: str):
    import urllib.request
    from urllib.parse import urlsplit

    class SameHostRedirects(urllib.request.HTTPRedirectHandler):
        """Follow a redirect only to https on the same host and port."""

        def redirect_request(self, req, fp, code, msg, headers, newurl):
            u = urlsplit(newurl)
            if u.scheme != "https" or u.netloc.lower() != host:
                raise ForgeError(f"refusing a redirect away from https://{host} (HTTP {code})")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    return SameHostRedirects()


class HttpTransport:
    """Forgejo and Gitea REST API over HTTPS (Codeberg runs Forgejo).

    Reads work without a token on public repositories. Writes need a token:
    CODEBERG_TOKEN for codeberg.org, or FORGEJO_TOKEN (or GITEA_TOKEN) with
    FORGEJO_HOST (or GITEA_HOST) naming the host it belongs to. A token is read
    from the environment at call time, sent only over https to its own host,
    never across a redirect to another host or to http, and never stored,
    printed or logged.
    """

    PAGE = 50
    MAX_PAGES = 1000

    def __init__(self, host: str | None):
        host = (host or "codeberg.org").strip().lower()
        if not BARE_HOST.match(host):
            raise ForgeError(f'forge host "{host[:60]}" must be a bare host name such as codeberg.org '
                             "(no scheme, path or user)")
        self.host = host
        self.base = f"https://{host}/api/v1/"
        self.guard = WriteGuard(commands=False)
        import urllib.request

        self._redirects = _same_host_redirects(host)
        self._opener = urllib.request.build_opener(self._redirects)

    def __repr__(self) -> str:
        return f"HttpTransport({self.base!r})"

    def _token(self) -> str | None:
        import os

        for var, host_var in TOKEN_VARS:
            value = os.environ.get(var)
            if not value:
                continue
            bound = "codeberg.org" if host_var is None else (os.environ.get(host_var) or "").strip().lower()
            if bound and bound == self.host:
                return value
        return None

    def _request(self, method: str, path: str, body=None, headers_out: dict | None = None):
        import urllib.error
        import urllib.request

        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method.upper())
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        token = self._token()
        if token:
            req.add_header("Authorization", "token " + token)
        del token
        try:
            with self._opener.open(req, timeout=30) as resp:
                raw = resp.read().decode()
                if headers_out is not None:
                    headers_out.update({k.lower(): v for k, v in dict(resp.headers or {}).items()})
        except urllib.error.HTTPError as exc:
            exc.close()
            if exc.code == 404:
                raise NotFound(f"{path}: not found") from None
            raise ForgeError(f"{method} {path} failed: HTTP {exc.code}") from None
        except urllib.error.URLError:
            raise ForgeError(f"{method} {path} failed: the forge could not be reached") from None
        return json.loads(raw) if raw.strip() else {}

    def get(self, path: str):
        return self._request("GET", path)

    def get_all(self, path: str) -> list:
        """Every page: follows X-Total-Count, or reads until an empty page when the header is missing.

        A server may cap a page below the requested limit, so a short page does
        not mean the last page.
        """
        out: list = []
        sep = "&" if "?" in path else "?"
        for page in range(1, self.MAX_PAGES + 1):
            headers: dict = {}
            chunk = self._request("GET", f"{path}{sep}limit={self.PAGE}&page={page}", headers_out=headers)
            if not isinstance(chunk, list):
                raise ForgeError(f"expected a list from {path}")
            out.extend(chunk)
            total = str(headers.get("x-total-count", ""))
            if not chunk or (total.isdigit() and len(out) >= int(total)):
                return out
        raise ForgeError(f"{path} has more than {self.MAX_PAGES} pages")

    def send(self, method: str, path: str, body=None, allow_close: bool = False):
        self.guard.check(method, path, body, allow_close=allow_close)
        return self._request(method, path, body)


def is_drift_issue(issue: dict, author: str | None) -> bool:
    """The tool's own open drift issue: its title, its marker block, and opened by the token's user."""
    return (issue.get("state") == "open" and blocks.one_line(issue.get("title")) == DRIFT_TITLE
            and blocks.block_content(issue.get("body") or "", blocks.DRIFT_START, blocks.DRIFT_END) is not None
            and bool(author) and issue.get("author") == author)


def _check_drift_issue(issue: dict, author: str | None) -> dict:
    """The issue, re-read from the forge, only if it is the tool's own open drift issue."""
    if not is_drift_issue(issue, author):
        raise ForgeError(f'refusing to close {issue.get("ref")}: it is not the open "{DRIFT_TITLE}" issue '
                         "this tool keeps")
    return issue


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


def command_hold(fg, body: str) -> str | None:
    """Why body must not be written to this forge, or None.

    GitLab runs quick actions in a description it is sent, hand text included.
    Text already on the forge is kept as it is, so a live command line in it
    holds back that one write for a hand fix instead of failing the run.
    """
    if getattr(fg, "kind", "") != "gitlab":
        return None
    found = blocks.gitlab_commands(body)
    if not found:
        return None
    return (f'the line "{blocks.one_line(found[0])[:60]}" is a GitLab quick action, which GitLab would run if '
            "this description were rewritten; remove it or put it in a code block by hand. Nothing was written "
            "to it")


class GitLab:
    kind = "gitlab"
    native_epics = True
    create_sets_epic = True   # epic_id goes in the create call itself: one write
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
                "epic_id": (d.get("epic") or {}).get("id"), "author": (d.get("author") or {}).get("username")}

    def current_user(self) -> str | None:
        """The user the token or login belongs to."""
        return (self.t.get("user") or {}).get("username")

    def get_issue(self, ref: str) -> dict:
        project, n = split_issue_ref(ref)
        return self._issue(self.t.get(f"projects/{enc(project)}/issues/{n}"))

    def all_issues(self, project: str) -> list[dict]:
        """Open and closed issues, so a title match also finds finished work."""
        if project not in self._open_cache:
            raw = self.t.get_all(f"projects/{enc(project)}/issues?state=all")
            self._open_cache[project] = [self._issue(d) for d in raw]
        return self._open_cache[project]

    def blocked_by(self, issue: dict) -> list[dict]:
        links = self.t.get_all(f"projects/{enc(issue['project'])}/issues/{issue['number']}/links")
        return [self._issue(d) for d in links if d.get("link_type") == "is_blocked_by"]

    def create_issue(self, project: str, title: str, body: str, epic: dict | None) -> dict:
        payload = {"title": title, "description": body}
        if epic and epic.get("id"):
            payload["epic_id"] = epic["id"]
        return self._issue(self.t.send("POST", f"projects/{enc(project)}/issues", payload))

    def update_issue_body(self, issue: dict, body: str) -> None:
        self.t.send("PUT", f"projects/{enc(issue['project'])}/issues/{issue['number']}", {"description": body})

    def in_epic(self, issue: dict, epic: dict) -> bool:
        return bool(epic.get("number")) and issue.get("epic_number") == epic["number"]

    def close_drift_issue(self, issue: dict, author: str | None) -> None:
        fresh = _check_drift_issue(self.get_issue(issue["ref"]), author)
        self.t.send("PUT", f"projects/{enc(fresh['project'])}/issues/{fresh['number']}", {"state_event": "close"},
                    allow_close=True)

    def add_to_epic(self, issue: dict, epic: dict) -> None:
        self.t.send("PUT", f"projects/{enc(issue['project'])}/issues/{issue['number']}", {"epic_id": epic["id"]})

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

    def open_epics(self) -> list[dict]:
        if not self.group:
            return []
        return [self._epic(d, self.group) for d in self.t.get_all(f"groups/{enc(self.group)}/epics?state=opened")]

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
    native_epics = True
    create_sets_epic = False  # a sub-issue is a second write, which publish makes and reports itself
    epic_word = "parent issue"

    def __init__(self, transport, host: str | None, project: str | None, group: str | None = None):
        self.t = transport
        self.host = host or "github.com"
        self.project = project
        self._open_cache: dict[str, list] = {}

    @staticmethod
    def _project_of(d: dict, default: str) -> str:
        """The issue's own repository: from repository_url, then repository, then the one asked for."""
        url = d.get("repository_url") or ""
        if "/repos/" in url:
            return url.split("/repos/", 1)[1].strip("/")
        return (d.get("repository") or {}).get("full_name") or default

    def _issue(self, d: dict, project: str) -> dict:
        project = self._project_of(d, project)
        n = d.get("number")
        return {"ref": f"{project}#{n}", "url": d.get("html_url"), "id": d.get("id"), "number": n,
                "project": project, "title": d.get("title", ""),
                "state": "closed" if d.get("state") == "closed" else "open", "body": d.get("body") or "",
                "labels": [lb["name"] if isinstance(lb, dict) else lb for lb in d.get("labels") or []],
                "updated_at": d.get("updated_at"), "epic_number": None,
                "is_pull_request": "pull_request" in d, "author": (d.get("user") or {}).get("login")}

    def current_user(self) -> str | None:
        """The user the token or login belongs to."""
        return (self.t.get("user") or {}).get("login")

    def get_issue(self, ref: str) -> dict:
        project, n = split_issue_ref(ref)
        return self._issue(self.t.get(f"repos/{project}/issues/{n}"), project)

    def all_issues(self, project: str) -> list[dict]:
        if project not in self._open_cache:
            raw = self.t.get_all(f"repos/{project}/issues?state=all")
            self._open_cache[project] = [i for i in (self._issue(d, project) for d in raw)
                                         if not i["is_pull_request"]]
        return self._open_cache[project]

    def open_issues(self, project: str) -> list[dict]:
        return [i for i in self.all_issues(project) if i["state"] == "open"]

    def create_issue(self, project: str, title: str, body: str, epic: dict | None) -> dict:
        """One write: the issue. Publish adds it to its parent with add_to_epic afterwards."""
        return self._issue(self.t.send("POST", f"repos/{project}/issues", {"title": title, "body": body}), project)

    def update_issue_body(self, issue: dict, body: str) -> None:
        self.t.send("PATCH", f"repos/{issue['project']}/issues/{issue['number']}", {"body": body})

    def in_epic(self, issue: dict, epic: dict) -> bool:
        if not epic.get("number"):
            return False
        return issue.get("id") in {i["id"] for i in self.epic_issues(epic)}

    def close_drift_issue(self, issue: dict, author: str | None) -> None:
        fresh = _check_drift_issue(self.get_issue(issue["ref"]), author)
        self.t.send("PATCH", f"repos/{fresh['project']}/issues/{fresh['number']}", {"state": "closed"},
                    allow_close=True)

    def add_to_epic(self, issue: dict, epic: dict) -> None:
        project = epic["ref"].rsplit("#", 1)[0]
        self.t.send("POST", f"repos/{project}/issues/{epic['number']}/sub_issues", {"sub_issue_id": issue["id"]})

    def blocked_by(self, issue: dict) -> list[dict]:
        raw = self.t.get_all(f"repos/{issue['project']}/issues/{issue['number']}/dependencies/blocked_by")
        return [self._issue(d, issue["project"]) for d in raw]

    def add_blocked_by(self, issue: dict, dep: dict) -> None:
        self.t.send("POST", f"repos/{issue['project']}/issues/{issue['number']}/dependencies/blocked_by",
                    {"issue_id": dep["id"]})

    def get_epic(self, ref: str) -> dict:
        issue = self.get_issue(ref)
        return {k: issue[k] for k in ("ref", "url", "id", "number", "title", "body")}

    def open_epics(self) -> list[dict]:
        """Parent issues are ordinary issues, so any open issue can be one."""
        if not self.project:
            return []
        return [{k: i[k] for k in ("ref", "url", "id", "number", "title", "body")}
                for i in self.open_issues(self.project)]

    def create_epic(self, title: str, body: str) -> dict:
        if not self.project:
            raise ForgeError('set forge "project" in roadmap.json to create GitHub parent issues')
        d = self.t.send("POST", f"repos/{self.project}/issues", {"title": title, "body": body})
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


class Forgejo(GitHub):
    """Forgejo, Gitea and Codeberg.

    Forgejo has issue dependencies but no epics, sub-issues or a usable
    parent link, so an epic is a parent issue: its generated section holds the
    flowchart, the status table and a task list of the epic's issues, and that
    task list is the membership. No labels and no milestones are used.
    """

    kind = "forgejo"
    epic_word = "parent issue (Forgejo has no epics)"
    native_epics = False

    def __init__(self, transport, host: str | None, project: str | None, group: str | None = None):
        super().__init__(transport, host or "codeberg.org", project)

    def _issue(self, d: dict, project: str) -> dict:
        out = super()._issue(d, project)
        out["is_pull_request"] = bool(d.get("pull_request"))
        return out

    def all_issues(self, project: str) -> list[dict]:
        if project not in self._open_cache:
            raw = self.t.get_all(f"repos/{project}/issues?state=all&type=issues")
            self._open_cache[project] = [i for i in (self._issue(d, project) for d in raw)
                                         if not i["is_pull_request"]]
        return self._open_cache[project]

    def create_issue(self, project: str, title: str, body: str, epic: dict | None) -> dict:
        return self._issue(self.t.send("POST", f"repos/{project}/issues", {"title": title, "body": body}), project)

    def get_epic(self, ref: str) -> dict:
        project, n = split_issue_ref(ref)
        d = self.t.get(f"repos/{project}/issues/{n}")
        issue = self._issue(d, project)
        out = {k: issue[k] for k in ("ref", "url", "id", "number", "title", "body")}
        out["pinned"] = bool(d.get("pin_order"))
        return out

    def can_pin(self) -> bool:
        if not self.project:
            return False
        try:
            return bool(self.t.get(f"repos/{self.project}/new_pin_allowed").get("issues"))
        except NotFound:
            return False

    def pin(self, epic: dict) -> None:
        project = epic["ref"].rsplit("#", 1)[0]
        self.t.send("POST", f"repos/{project}/issues/{epic['number']}/pin")

    def in_epic(self, issue: dict, epic: dict) -> bool:
        return issue["ref"] in blocks.epic_members(epic.get("body") or "")

    def add_to_epic(self, issue: dict, epic: dict) -> None:
        """Membership is the task list in the epic's generated section, written with it."""

    def blocked_by(self, issue: dict) -> list[dict]:
        raw = self.t.get_all(f"repos/{issue['project']}/issues/{issue['number']}/dependencies")
        return [self._issue(d, issue["project"]) for d in raw]

    def add_blocked_by(self, issue: dict, dep: dict) -> None:
        owner, repo = dep["project"].split("/", 1)
        self.t.send("POST", f"repos/{issue['project']}/issues/{issue['number']}/dependencies",
                    {"owner": owner, "repo": repo, "index": dep["number"]})

    def create_epic(self, title: str, body: str) -> dict:
        if not self.project:
            raise ForgeError('set forge "project" in roadmap.json to create parent issues')
        issue = self._issue(self.t.send("POST", f"repos/{self.project}/issues", {"title": title, "body": body}),
                            self.project)
        return {k: issue[k] for k in ("ref", "url", "id", "number", "title", "body")}

    def epic_issues(self, epic: dict) -> list[dict]:
        """The parent's generated task list, plus every issue that mentions the parent issue.

        The task list is rewritten from the roadmap on every write, so a person
        adds an issue to a Forgejo epic by mentioning the parent from it ("Part
        of #10"); sync then reports it until the roadmap lists it.
        """
        out = []
        for ref in sorted(blocks.epic_members(epic.get("body") or "")):
            try:
                out.append(self.get_issue(ref))
            except NotFound:
                continue
        project = epic["ref"].rsplit("#", 1)[0]
        try:
            events = self.t.get_all(f"repos/{project}/issues/{epic['number']}/timeline")
        except NotFound:
            events = []
        seen = {i["ref"] for i in out}
        for ev in events:
            src = ev.get("ref_issue") or {}
            if not src.get("number") or src.get("pull_request"):
                continue
            issue = self._issue(src, project)
            if issue["project"] != project:
                continue   # a mention from another repository, which anyone can make
            if issue["ref"] not in seen:
                seen.add(issue["ref"])
                out.append(issue)
        return out

    def _pr(self, d: dict, project: str) -> dict:
        pr = super()._pr(d, project)
        if not d.get("draft") and re.match(r"^\s*(wip:|\[wip\]|draft:)", d.get("title", ""), re.IGNORECASE):
            pr["draft"] = True
        return pr

    def _with_checks(self, pr: dict) -> dict:
        if pr["state"] == "open" and pr.get("head_sha"):
            try:
                st = self.t.get(f"repos/{pr['project']}/commits/{pr['head_sha']}/status")
                pr["pipeline"] = st.get("state")
                targets = [x.get("target_url") for x in st.get("statuses") or [] if safe_url(x.get("target_url"))]
                pr["pipeline_url"] = targets[0] if targets else pr.get("url")
            except NotFound:
                pass
        return pr

    def related_mrs(self, issue: dict) -> list[dict]:
        events = self.t.get_all(f"repos/{issue['project']}/issues/{issue['number']}/timeline")
        seen, out = set(), []
        for ev in events:
            src = ev.get("ref_issue") or {}
            if not src.get("pull_request"):
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
    if host and "github" in host:
        return "github", host
    if host and ("codeberg" in host or "forgejo" in host or "gitea" in host):
        return "forgejo", host
    return "gitlab", host


def forge_class(kind: str):
    kinds = {"gitlab": GitLab, "github": GitHub, "forgejo": Forgejo, "gitea": Forgejo, "codeberg": Forgejo}
    if kind not in kinds:
        raise ForgeError(f'unknown forge "{kind}"; use gitlab, github or forgejo')
    return kinds[kind]


def make(kind: str, transport, cfg: dict):
    fg = forge_class(kind)(transport, host=cfg.get("host"), project=cfg.get("project"), group=cfg.get("group"))
    fg.pin_epics = bool(cfg.get("pin_epics")) and hasattr(fg, "pin")
    return fg


def from_args(data: dict, args) -> GitLab | GitHub:
    cfg = dict(data.get("forge") or {})
    kind = getattr(args, "forge", None) or cfg.get("kind")
    if not kind:
        kind, host = detect_from_remote(getattr(args, "repo", "."))
        cfg.setdefault("host", host)
    if getattr(args, "recorded", None):
        try:
            with open(args.recorded) as fh:
                transport = RecordedTransport(json.load(fh))
        except (OSError, json.JSONDecodeError) as exc:
            raise ForgeError(f"recorded responses {args.recorded} could not be read: {exc}") from None
    elif forge_class(kind) is Forgejo:
        transport = HttpTransport(cfg.get("host"))
    else:
        transport = CliTransport(kind, cfg.get("host"))
    return make(kind, transport, cfg)
