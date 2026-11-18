#!/usr/bin/env python3
"""Roadmap hooks for Claude Code, and a notify program for Codex.

  roadmap_hook.py post-tool-use   after a Bash command that merges a merge request or
                                  closes an issue: run a read-only sync of the issues it
                                  touched and tell the agent what changed
  roadmap_hook.py stop            at the end of a turn: sync only the roadmap issues this
                                  turn changed (named in a git commit, push, merge or tag,
                                  or a merge request or issue command it ran; at most
                                  MAX_STOP_ISSUES). Drift the agent can fix blocks the turn
                                  with a short message saying what to do; other drift on
                                  those issues is shown, not blocked. A turn that changed
                                  no roadmap issue makes no forge call
  roadmap_hook.py codex-notify J  Codex "notify" program (J is its JSON payload): the same
                                  check, sent to a desktop notification (Codex cannot block)

Every mode syncs at most MAX_STOP_ISSUES issues and names the rest in a note.

It does nothing, and says nothing, without a roadmap of this tool's shape
(ROADMAP_FILE, else roadmap.json in the working directory or at the git root,
with "epics" and "issues" lists), never writes anything, and fails open: a slow or
unreachable forge, a missing tool or any error gives a one-line warning, never a
blocked turn. Standard library only; Python 3.11 or newer.

A command counts as a change only when git, glab, gh, tea or fj is the command
itself (after cd, env assignments or a wrapper such as env), not text inside
echo, grep or quotes.

Settings (environment): ROADMAP_FILE, ROADMAP_HOOK_TIMEOUT (seconds, default 20),
ROADMAP_HOOK_NOTIFIER (Codex: command that receives the message as its argument).
Tests also use ROADMAP_HOOK_RECORDED and ROADMAP_HOOK_NOW.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "skills" / "roadmap" / "scripts"
CLI = SCRIPTS / "roadmap.py"

# Commands that change work on the forge or in git: the issues they name are the
# ones the agent changed. Reading roadmap.json or running validate names every
# issue and changes none. (tool: {area: subcommands})
GIT_CHANGES = {"commit", "push", "merge", "tag"}
FORGE_CHANGES = {
    "glab": {"mr": {"create", "merge", "update", "close", "reopen", "note"},
             "issue": {"create", "update", "close", "reopen", "note"}},
    "gh": {"pr": {"create", "merge", "edit", "close", "reopen", "comment"},
           "issue": {"create", "edit", "close", "reopen", "comment"}},
    "tea": {area: {"create", "merge", "edit", "close", "reopen"} for area in ("pr", "pulls", "issue", "issues")},
    "fj": {"pr": {"create", "merge", "edit", "close", "comment"}, "issue": {"create", "edit", "close", "comment"}},
}
# After these the roadmap may be behind the forge (the PostToolUse check).
MERGE_OR_CLOSE = {("glab", "mr", "merge"), ("gh", "pr", "merge"), ("glab", "issue", "close"),
                  ("gh", "issue", "close"), ("tea", "pr", "merge"), ("tea", "pulls", "merge"),
                  ("tea", "issue", "close"), ("tea", "issues", "close"), ("fj", "pr", "merge"),
                  ("fj", "issue", "close")}
WRAPPERS = {"env", "command", "time", "nohup", "sudo", "exec", "builtin"}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SEPARATORS = {";", "&", "&&", "|", "||", "|&", "(", ")", ";;"}
GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
# Issues any one hook run syncs at most; each costs two or three forge calls.
MAX_STOP_ISSUES = 5
DEFAULT_TIMEOUT = 20
TRANSCRIPT_TAIL = 2_000_000


def find_roadmap(cwd: str) -> Path | None:
    env = os.environ.get("ROADMAP_FILE")
    if env:
        return Path(env) if Path(env).is_file() else None
    here = Path(cwd or ".") / "roadmap.json"
    if here.is_file():
        return here
    try:
        top = subprocess.run(["git", "-C", cwd or ".", "rev-parse", "--show-toplevel"], capture_output=True,
                             text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    candidate = Path(top) / "roadmap.json" if top else None
    return candidate if candidate and candidate.is_file() else None


def touched(data: dict, text: str) -> list[str]:
    """Roadmap issues the text names by short name, forge reference or URL."""
    sys.path.insert(0, str(SCRIPTS))
    from roadmaplib import checkmr, model

    project = (data.get("forge") or {}).get("project")
    items = model.normalize(data)["issues"]
    return [it["id"] for it in items if isinstance(it, dict) and it.get("id") and checkmr._named(it, text, project)]


def _tokens(line: str) -> list[str]:
    import shlex

    lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    return list(lexer)


def _simple_commands(command: str) -> list[list[str]]:
    """The words of each simple command in a shell command line, split at ; && || | ( ) and newlines.

    Each line is read on its own, so a comment ends at its line. A line shlex
    cannot read (an apostrophe in a heredoc, or one line of a quoted message
    over several lines) is read up to its first quote, which still finds the
    command word at its start.
    """
    tokens = []
    for line in command.splitlines():
        try:
            tokens += _tokens(line) + [";"]
        except ValueError:
            cut = min([i for i in (line.find("'"), line.find('"')) if i >= 0], default=len(line))
            try:
                tokens += _tokens(line[:cut]) + [";"]
            except ValueError:
                tokens.append(";")
    out, cur = [], []
    for tok in tokens:
        if tok in SEPARATORS:
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append(tok)
    if cur:
        out.append(cur)
    return out


def _command_words(words: list[str]) -> tuple[str, ...]:
    """(tool, subcommand...) of one simple command: the tool and its first plain words."""
    i = 0
    while i < len(words) and (ASSIGNMENT.match(words[i]) or words[i] in WRAPPERS):
        i += 1
    if i >= len(words):
        return ()
    tool = os.path.basename(words[i])
    rest, j = [], i + 1
    while j < len(words) and len(rest) < 2:
        w = words[j]
        if tool == "git" and w in GIT_OPTIONS_WITH_VALUE:
            j += 2
            continue
        if w.startswith("-"):
            j += 1
            continue
        rest.append(w)
        j += 1
    return (tool, *rest)


def _actions(command: str) -> list[tuple[str, ...]]:
    return [_command_words(words) for words in _simple_commands(command)]


def runs_change(command: str) -> bool:
    """True when the command line runs git or a forge CLI to change work (not text inside echo or quotes)."""
    for act in _actions(command):
        if len(act) >= 2 and act[0] == "git" and act[1] in GIT_CHANGES:
            return True
        if len(act) >= 3 and act[2] in FORGE_CHANGES.get(act[0], {}).get(act[1], ()):
            return True
    return False


def runs_merge_or_close(command: str) -> bool:
    return any(act[:3] in MERGE_OR_CLOSE for act in _actions(command))


def run_sync(path: Path, ids: list[str]) -> tuple[dict | None, str | None]:
    """The sync report as a dict, or None and why it could not be had."""
    cmd = [sys.executable, str(CLI), "sync", str(path), "--json", "--no-orca", "--only", ",".join(ids)]
    if os.environ.get("ROADMAP_HOOK_RECORDED"):
        cmd += ["--recorded", os.environ["ROADMAP_HOOK_RECORDED"]]
    if os.environ.get("ROADMAP_HOOK_NOW"):
        cmd += ["--now", os.environ["ROADMAP_HOOK_NOW"]]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=path.parent,
                              timeout=float(os.environ.get("ROADMAP_HOOK_TIMEOUT") or DEFAULT_TIMEOUT))
    except subprocess.TimeoutExpired:
        return None, "the forge did not answer in time"
    except OSError as exc:
        return None, f"could not run the roadmap command ({exc.strerror})"
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        last = (proc.stdout or proc.stderr).strip().splitlines()[-1:] or ["no output"]
        return None, last[0][:200]
    if report.get("errors"):
        return None, f"{len(report['errors'])} forge call(s) failed"
    return report, None


def findings(report: dict, ids: list[str], changed: list[str], data: dict) -> tuple[list[str], list[str]]:
    """(to fix now, to show only): drift the agent can fix on issues it changed, and the rest."""
    from roadmaplib import sync

    refs = {it.get("ref"): it["id"] for it in data.get("issues", []) if isinstance(it, dict) and it.get("ref")}
    fix, show = [], []
    behind = sorted({c["issue"] for c in report.get("status_changes", [])} |
                    {t["issue"] for t in report.get("gate_ticks", [])})
    for group, out in (([b for b in behind if b in changed], fix), ([b for b in behind if b not in changed], show)):
        if group:
            out.append(f"roadmap.json is behind the forge for {', '.join(group)}: run `roadmap.py sync roadmap.json "
                       "--write`, re-render, and send the short update")
    for d in report.get("drift", []):
        target = refs.get(d["target"], d["target"])
        if target not in ids:
            continue
        line = f"[{d['kind']}] {target}: {d['message']}"
        (fix if d["kind"] in sync.AGENT_DRIFT and target in changed else show).append(line)
    return fix, show


def check(cwd: str, text: str, ids_if_none: str = "",
          limit: int | None = None) -> tuple[list[str], list[str], str | None, list[str]]:
    """(to fix, to show, warning, issues checked) for the work the text names.

    Everything the text names counts as changed. limit caps how many issues
    are synced; the rest are named in a note.
    """
    path = find_roadmap(cwd)
    if path is None:
        return [], [], None, []
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return [], [], None, []   # not a roadmap this tool can read: another tool's file, say nothing
    if not (isinstance(data, dict) and isinstance(data.get("issues"), list) and isinstance(data.get("epics"), list)):
        return [], [], None, []
    if sys.version_info < (3, 11):
        return [], [], "roadmap check skipped: it needs Python 3.11 or newer", []
    ids = touched(data, text)
    if not ids and ids_if_none == "active":
        ids = [it["id"] for it in data.get("issues", []) if isinstance(it, dict)
               and it.get("status") in ("in_progress", "in_review") and it.get("ref")]
    if not ids:
        return [], [], None, []
    skipped = []
    if limit is not None and len(ids) > limit:
        ids, skipped = ids[:limit], ids[limit:]
    report, why = run_sync(path, ids)
    if report is None:
        return [], [], f"roadmap check skipped: {why}", ids
    fix, show = findings(report, ids, ids, data)
    if skipped:
        show.append(f"{len(skipped)} more changed issue(s) not checked here ({', '.join(skipped[:8])}); "
                    "run `roadmap.py sync roadmap.json` for all of them")
    return fix, show, None, ids


def _transcript_text(path: str | None) -> str:
    if not path:
        return ""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - TRANSCRIPT_TAIL))
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _is_turn_start(line: dict) -> bool:
    """A prompt the person typed: a user line that is not a tool result or a meta line."""
    if not isinstance(line, dict) or line.get("type") != "user" or line.get("isMeta"):
        return False
    content = (line.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    return isinstance(content, list) and not any(isinstance(b, dict) and b.get("type") == "tool_result"
                                                 for b in content)


def _commands(transcript: str) -> str:
    """The Bash commands this turn ran that change work (git commits, merge requests, issue commands)."""
    found = []

    def walk(x):
        if isinstance(x, dict):
            if x.get("type") == "tool_use" and x.get("name") == "Bash":
                command = str((x.get("input") or {}).get("command") or "")
                if runs_change(command):
                    found.append(command)
                return
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    for line in transcript.splitlines():
        try:
            entry = json.loads(line)
            if _is_turn_start(entry):
                found = []
            walk(entry)
        except (json.JSONDecodeError, RecursionError):
            continue
    return "\n".join(found)


def stop(payload: dict) -> dict | None:
    if payload.get("stop_hook_active"):
        return None   # this turn was already continued by this hook once
    changes = _commands(_transcript_text(payload.get("transcript_path")))
    if not changes:
        return None   # this turn changed nothing: no forge call
    fix, show, warning, _ = check(payload.get("cwd") or os.getcwd(), changes, limit=MAX_STOP_ISSUES)
    if warning:
        return {"systemMessage": warning}
    if fix:
        reason = "Roadmap drift on work this turn changed. Fix it before finishing:\n- " + "\n- ".join(fix[:6])
        return {"decision": "block", "reason": reason[:880]}
    if show:
        note = "Roadmap notes on issues this turn changed (for the lead or the team; nothing to fix now): "
        return {"systemMessage": (note + "; ".join(show))[:600]}
    return None


def post_tool_use(payload: dict) -> dict | None:
    command = ((payload.get("tool_input") or {}).get("command")) or ""
    if payload.get("tool_name") not in (None, "Bash") or not runs_merge_or_close(command):
        return None
    fix, show, warning, ids = check(payload.get("cwd") or os.getcwd(), command, ids_if_none="active",
                                    limit=MAX_STOP_ISSUES)
    if warning:
        return {"systemMessage": warning}
    if not ids:
        return None
    found = fix + show
    summary = (f"Roadmap sync after `{command[:80]}` (read-only, issues {', '.join(ids)}): "
               + ("; ".join(found) if found else "no drift on these issues."))
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": summary[:1500]}}


def codex_notify(raw: str) -> None:
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return
    if payload.get("type") != "agent-turn-complete":
        return
    text = "\n".join(map(str, payload.get("input-messages") or [])) + "\n" + str(payload.get("last-assistant-message"))
    found, _, warning, _ = check(payload.get("cwd") or os.getcwd(), text, limit=MAX_STOP_ISSUES)
    message = warning or ("Roadmap drift: " + "; ".join(found) if found else "")
    if message:
        notify(message[:300])


def notify(message: str) -> None:
    custom = os.environ.get("ROADMAP_HOOK_NOTIFIER")
    if custom:
        cmd = [custom, message]
    elif sys.platform == "darwin" and shutil.which("osascript"):
        cmd = ["osascript", "-e", f"display notification {json.dumps(message)} with title \"Roadmap\""]
    elif shutil.which("notify-send"):
        cmd = ["notify-send", "Roadmap", message]
    else:
        print(message, file=sys.stderr)
        return
    try:
        subprocess.run(cmd, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        print(message, file=sys.stderr)


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else ""
    try:
        if mode == "codex-notify":
            codex_notify(argv[2] if len(argv) > 2 else "")
            return 0
        payload = json.loads(sys.stdin.read() or "{}")
        out = stop(payload) if mode == "stop" else post_tool_use(payload) if mode == "post-tool-use" else None
    except Exception as exc:  # fail open: a hook must never break the session
        out = {"systemMessage": f"roadmap check skipped: {type(exc).__name__}: {exc}"[:300]}
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
