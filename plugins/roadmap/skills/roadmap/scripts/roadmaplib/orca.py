"""Read Orca tasks (read-only) so sync can match workers to roadmap issues.

Orca task titles and worker briefs start with the issue's short name and link,
for example "ranking-model acme/search#12: rank results by open rate".
"""

from __future__ import annotations

import json
import shutil
import subprocess

FINISHED = {"completed", "failed", "cancelled", "canceled", "abandoned", "stopped", "done"}


def parse_tasks(raw) -> list[dict]:
    """Accept the CLI's {"ok", "result": {"tasks": [...]}} envelope, {"tasks": [...]}, or a list."""
    if isinstance(raw, dict):
        raw = raw.get("result", raw)
        raw = raw.get("tasks", []) if isinstance(raw, dict) else raw
    return [{"id": t.get("id"), "status": t.get("status", ""), "title": t.get("title", "")}
            for t in raw or [] if isinstance(t, dict)]


# Tasks a worker is actually running. Others ("ready", "blocked", "pending",
# "queued") are waiting, so they have not started anything early.
STARTED = {"dispatched", "running", "in_progress", "active", "working", "started"}


def active(tasks: list[dict]) -> list[dict]:
    """Tasks not finished: running or waiting."""
    return [t for t in tasks if t["status"] not in FINISHED]


def started(tasks: list[dict]) -> list[dict]:
    """Tasks a worker is running now."""
    return [t for t in tasks if t["status"] in STARTED]


def read_run(run: str) -> list[dict]:
    if not shutil.which("orca"):
        raise RuntimeError("the orca CLI is not installed")
    proc = subprocess.run(["orca", "orchestration", "task-list", "--run", run, "--json"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        lines = (proc.stderr or proc.stdout).strip().splitlines()
        raise RuntimeError(lines[-1] if lines else "orca failed")
    return parse_tasks(json.loads(proc.stdout))


def tasks_from_args(data: dict, args):
    """Tasks to check, or a string saying why Orca was not checked."""
    if getattr(args, "no_orca", False):
        return "Orca not checked (--no-orca)."
    if getattr(args, "orca_json", None):
        with open(args.orca_json) as fh:
            return parse_tasks(json.load(fh))
    cfg = data.get("orca") if isinstance(data.get("orca"), dict) else {}
    run = getattr(args, "orca_run", None) or cfg.get("run")
    if not isinstance(run, str) or not run:
        return 'Orca not checked: set "orca": {"run": ...} in roadmap.json or pass --orca-run.'
    try:
        return read_run(run)
    except (RuntimeError, json.JSONDecodeError) as exc:
        return f"Orca not checked: {exc}"


def match(task: dict, items: dict) -> str | None:
    """The roadmap issue a task belongs to: its title starts with the short name or the forge ref."""
    title = task["title"].strip()
    low = title.lower()
    best = None
    for iid, it in items.items():
        keys = [iid.lower()] + [k.lower() for k in (it.get("ref"), it.get("url")) if k]
        for k in keys:
            if low.startswith(k) and (len(low) == len(k) or not (low[len(k)].isalnum() or low[len(k)] == "-")):
                if best is None or len(k) > best[1]:
                    best = (iid, len(k))
    return best[0] if best else None
