"""Read Orca tasks (read-only) so sync can match workers to roadmap issues.

Orca task titles and worker briefs start with the issue's short name and link,
for example "ranking-model acme/search#12: rank results by open rate".
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from time import monotonic

from . import model, observation

FINISHED = {"completed", "failed", "cancelled", "canceled", "abandoned", "stopped", "done"}
WORKER_TIMEOUT = 5
OBSERVATION_BUDGET = 15


class RunTask(dict):
    """Keep the observed run and its configured owners alongside the original task fields."""

    def __init__(self, task: dict, run: str, owners: dict, *, qualified: bool = True):
        super().__init__(task)
        self.source_run = run
        self.run_owners = owners
        self.qualified = qualified


class TaskCollection(list):
    """A task list with coverage of the requested runs and of the whole roadmap."""

    def __init__(self):
        super().__init__()
        self.complete = True
        self.requested_complete = True
        self.notes: list[str] = []
        self.observation: dict | None = None

    def unknown(self, context: str, error: str, *, requested: bool = True) -> None:
        self.complete = False
        if requested:
            self.requested_complete = False
        self.notes.append(f"{context}: Unknown ({error}).")


class TaskReadError(ValueError):
    """An Orca response could not establish which tasks were read."""


class _JSONObject(dict):
    """Remember ambiguous keys in a recording so one bad run cannot hide its siblings."""

    def __init__(self, pairs):
        super().__init__()
        self.duplicates = set()
        for key, value in pairs:
            if key in self:
                self.duplicates.add(key)
            self[key] = value


def _check_response(raw) -> None:
    if isinstance(raw, dict):
        if getattr(raw, "duplicates", None):
            raise TaskReadError(f"duplicate keys: {', '.join(sorted(raw.duplicates))}")
        if raw.get("ok", True) is not True or "error" in raw:
            raise TaskReadError(raw.get("error") or "Orca reported an unsuccessful read")


def _result(raw):
    _check_response(raw)
    if isinstance(raw, dict) and "result" in raw:
        raw = raw["result"]
        _check_response(raw)
    return raw


def _containers(layer) -> list[tuple[str, object, dict | None]]:
    if isinstance(layer, list):
        return [("tasks", layer, None)]
    if isinstance(layer, dict):
        return [(key, layer[key], layer) for key in ("tasks", "runs") if key in layer]
    return []


def _task_containers(raw, result) -> tuple[list[tuple[str, object, dict | None]], str | None]:
    """List each container with its own layer for positive evidence on ambiguous reads."""
    outer = _containers(raw) if raw is not result else []
    inner = _containers(result)
    containers = outer + inner
    if len(containers) > 1:
        return containers, "response contains competing task containers"
    if not inner:
        return containers, 'expected a task list or an object with "tasks" or "runs"'
    if raw is not result and isinstance(result, dict) and "result" in result:
        return containers, "response contains an additional nested result"
    return containers, None


def _rows(raw) -> list:
    if not isinstance(raw, list):
        raise TaskReadError('"tasks" must be a list')
    return raw


def _task(raw) -> dict:
    if not isinstance(raw, dict) or not observation.nonblank(raw.get("id")):
        raise TaskReadError("task must have a nonblank id")
    if getattr(raw, "duplicates", None):
        raise TaskReadError(f"task {raw['id']!r} has duplicate keys")
    if any(not isinstance(raw.get(field, ""), str) for field in ("status", "title")):
        raise TaskReadError(f"task {raw['id']!r} must have text status and title")
    return {"status": "", "title": "", **raw}


def parse_tasks(raw) -> list[dict]:
    """Read a task envelope or list, preserving each task's original metadata."""
    containers, problem = _task_containers(raw, _result(raw))
    if problem:
        raise TaskReadError(problem)
    kind, rows, _ = containers[0]
    if kind != "tasks":
        raise TaskReadError('expected a "tasks" list for a single run')
    return [_task(row) for row in _rows(rows)]


def task_key(task: dict) -> tuple[str | None, str]:
    if isinstance(task, RunTask):
        return (task.source_run if task.qualified else None, task["id"])
    run = task.get("run")
    return (run if isinstance(run, str) and run else None, task["id"])


# Task lifecycle states that establish a start for dependency checks.
STARTED = {"dispatched", "running", "in_progress", "active", "working", "started"}


def active(tasks: list[dict]) -> list[dict]:
    """Tasks not finished: running or waiting."""
    return [t for t in tasks if t["status"] not in FINISHED]


def started(tasks: list[dict]) -> list[dict]:
    """Tasks whose lifecycle has reached dispatch or an explicit start."""
    return [t for t in tasks if t["status"] in STARTED]


def cli_command() -> str:
    if command := os.environ.get("ORCA_CLI_COMMAND"):
        return command
    if os.environ.get("ORCA_DEV_REPO_ROOT"):
        return "orca-dev"
    managed = any(os.environ.get(key) for key in ("ORCA_TERMINAL_HANDLE", "ORCA_PANE_KEY", "ORCA_AGENT_PANE"))
    return "orca-ide" if sys.platform.startswith("linux") and not managed else "orca"


def read_run(run: str) -> list[dict]:
    command = cli_command()
    return parse_tasks(_read_run(run, command, shutil.which(command)))


def _read_json(command: str, executable: str | None, argv: list[str], timeout: float):
    if not executable:
        raise RuntimeError(f"executable {command!r} is unavailable")
    try:
        proc = subprocess.run(
            [executable, "orchestration", *argv, "--json"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(str(exc)) from exc
    if proc.returncode != 0:
        lines = (proc.stderr or proc.stdout).strip().splitlines()
        raise RuntimeError(lines[-1] if lines else f"command exited with status {proc.returncode}")
    return json.loads(proc.stdout, object_pairs_hook=_JSONObject)


def _read_run(run: str, command: str, executable: str | None):
    return _read_json(command, executable, ["task-list", "--run", run], 30)


def run_owners(data: dict) -> dict[str, dict]:
    """Return the configured run IDs and the coordinators that use them."""
    runs = {}
    for key, owner in model.coordinators(data).items():
        run = owner.get("run") if isinstance(owner, dict) else None
        if isinstance(run, str) and run.strip():
            runs.setdefault(run, {})[key] = owner
    legacy = data.get("orca")
    run = legacy.get("run") if isinstance(legacy, dict) else None
    if isinstance(run, str) and run.strip():
        runs.setdefault(run, {})
    return runs


def _identifier(raw, fields: tuple[str, ...]) -> str | None:
    values = [raw[field] for field in fields if isinstance(raw, dict) and field in raw]
    if any(not observation.nonblank(value) or value != value.strip() for value in values):
        raise TaskReadError(f"{'/'.join(fields)} must be a nonblank identifier without surrounding whitespace")
    if len(set(values)) > 1:
        raise TaskReadError(f"conflicting identifiers for {'/'.join(fields)}")
    return values[0] if values else None


def _scoped_run(raw, result, recorded: bool) -> str | None:
    fields = ("runId", "run_id", "run") if recorded else ("runId", "run_id")
    outer = _identifier(raw, fields)
    inner = _identifier(result, fields)
    if outer and inner and outer != inner:
        raise TaskReadError(f"conflicting run scope {outer!r} and {inner!r}")
    return outer or inner


def _append_rows(
    tasks: TaskCollection,
    rows: list,
    owners: dict,
    context: str,
    *,
    run: str | None,
    recorded: bool,
    allow_unscoped: bool = True,
) -> set[str | None]:
    qualified = []
    for index, raw in enumerate(rows):
        try:
            row = _task(raw)
            row_run = _scoped_run(row, None, recorded)
            if run and row_run and run != row_run:
                raise TaskReadError(f"task {row['id']!r} identifies a different run {row_run!r}")
            if run or row_run or allow_unscoped:
                qualified.append((run or row_run, row))
        except TaskReadError as exc:
            tasks.unknown(f"{context}, task at index {index}", str(exc))

    scopes = {scope for scope, _ in qualified}
    inferred = None
    if not run and allow_unscoped and len(owners) == 1:
        expected = next(iter(owners))
        if scopes <= {None, expected}:
            inferred = expected
    for explicit_scope, row in qualified:
        scope = explicit_scope or inferred
        tasks.append(RunTask(row, scope, owners.get(scope, {}), qualified=bool(explicit_scope)) if scope else row)
    return {run or inferred} if run or inferred else scopes


def _deduplicate(tasks: TaskCollection) -> None:
    unique = {}
    ambiguous = set()
    for row in tasks:
        scope = getattr(row, "source_run", None)
        key = (scope, row["id"])
        if key in unique:
            tasks.unknown(f"Orca run {scope!r}", f"duplicate task {row['id']!r}")
            if unique[key] != row:
                ambiguous.add(key)
            continue
        unique[key] = row
    tasks[:] = [row for key, row in unique.items() if key not in ambiguous]


def _collect(
    tasks: TaskCollection,
    runs: Iterable[str],
    owners: dict,
    read: Callable[[str], object],
    source: str,
    *,
    recorded: bool = False,
    allow_nested_map: bool = True,
) -> None:
    for run in runs:
        context = f"Orca run {run!r} ({source})"
        try:
            raw = read(run)
            result = _result(raw)
            containers, problem = _task_containers(raw, result)
            # A wrapper without a container of its own scopes everything it encloses.
            if not problem or (raw is not result and not _containers(raw)):
                scope = _scoped_run(raw, result, recorded)
                if scope and scope != run:
                    raise TaskReadError(f"response identifies a different run {scope!r}")
        except (RuntimeError, ValueError) as exc:
            tasks.unknown(context, str(exc))
            continue
        before = len(tasks)
        if problem:
            tasks.unknown(context, problem)
        for kind, container, layer in containers:
            try:
                if problem:
                    scope = _scoped_run(layer, None, recorded)
                    if scope and scope != run:
                        raise TaskReadError(f"task container identifies a different run {scope!r}")
                if kind == "runs":
                    if not (recorded and problem and allow_nested_map):
                        raise TaskReadError('expected a "tasks" list for a single run')
                    if not isinstance(container, dict) or run not in container:
                        raise TaskReadError(f"nested runs map has no entry for {run!r}")
                    if run in getattr(container, "duplicates", ()):
                        raise TaskReadError(f"duplicate run key {run!r} in nested runs map")
                    _collect(
                        tasks,
                        (run,),
                        owners,
                        container.__getitem__,
                        f"{source}, nested runs",
                        recorded=True,
                        allow_nested_map=False,
                    )
                    continue
                _append_rows(tasks, _rows(container), owners, context, run=run, recorded=recorded)
            except TaskReadError as exc:
                tasks.unknown(context, str(exc))
        tasks.notes.append(f"{context}: read {len(tasks) - before} task(s).")


def _recorded_runs(tasks: TaskCollection, recorded, owners: dict, *, require_all: bool) -> None:
    if not isinstance(recorded, dict) or not (recorded or owners):
        raise TaskReadError('"runs" must map run identifiers to task lists or responses')
    invalid = getattr(recorded, "duplicates", set()).copy()
    for run in recorded:
        if run in invalid:
            tasks.unknown(f"Orca run {run!r} (recorded)", "duplicate run key")
        elif not observation.nonblank(run) or run != run.strip():
            tasks.unknown(f"Orca run {run!r} (recorded)", "invalid run identifier")
            invalid.add(run)

    def read(run):
        if run not in recorded:
            raise TaskReadError("missing run in recording")
        return recorded[run]

    runs = owners | recorded if require_all else recorded
    _collect(tasks, (run for run in runs if run not in invalid), owners, read, "recorded", recorded=True)


def _recorded_tasks(path, owners: dict) -> TaskCollection:
    tasks = TaskCollection()
    context = f"Orca recording {str(path)!r}"
    workers = {}
    observed_at = None
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh, object_pairs_hook=_JSONObject)
        result = _result(raw)
        containers, problem = _task_containers(raw, result)
        scope = None
        if problem:
            tasks.unknown(context, problem)
        else:
            scope = _scoped_run(raw, result, recorded=True)
            if scope and containers[0][0] == "runs":
                raise TaskReadError("use either a single run identifier or a runs map")
        for kind, container, layer in containers:
            try:
                if kind == "runs":
                    _recorded_runs(tasks, container, owners, require_all=problem is None)
                    continue
                local_run = _scoped_run(layer, None, recorded=True) if problem else scope
                scopes = _append_rows(
                    tasks,
                    _rows(container),
                    owners,
                    context,
                    run=local_run,
                    recorded=True,
                    allow_unscoped=problem is None,
                )
                if problem is None and owners and (len(owners) > 1 or scopes != set(owners)):
                    tasks.unknown(
                        "Orca run coverage",
                        "flat recording cannot establish coverage of " + ", ".join(repr(run) for run in owners),
                    )
            except TaskReadError as exc:
                tasks.unknown(context, str(exc))
        metadata = (raw if isinstance(raw, dict) else {}) | (result if isinstance(result, dict) else {})
        workers = metadata.get("workers", {})
        observed_at = metadata.get("observed_at")
        if not isinstance(workers, dict):
            tasks.notes.append(f"{context}: worker activity Unknown (expected a workers map).")
            workers = {}
        if observed_at is not None and not observation.is_timestamp(observed_at):
            tasks.notes.append(f"{context}: observation time Unknown (invalid observed_at).")
            observed_at = None
    except (OSError, ValueError) as exc:
        tasks.unknown(context, str(exc))

    def read_worker(dispatch):
        if dispatch in getattr(workers, "duplicates", ()):
            raise TaskReadError("duplicate dispatch in worker recording")
        if dispatch not in workers:
            raise TaskReadError("missing worker in recording")
        entry = workers[dispatch]
        return _worker_result(entry), entry.get("observed_at") if isinstance(entry, dict) else None

    _deduplicate(tasks)
    _observe(tasks, "recorded", read_worker, observed_at=observed_at)
    return tasks


def _observe(tasks: TaskCollection, source: str, read: Callable, *, observed_at: str | None = None) -> None:
    cache = {}
    workers = []
    for task in tasks:
        status = task["status"]
        dispatch = task.get("dispatchId")
        dispatch = dispatch if observation.nonblank(dispatch) else None
        if status not in STARTED and (status.strip() or not dispatch):
            continue
        run = task.source_run if isinstance(task, RunTask) else None
        task_id = task["id"]
        row = {
            "run": run,
            "task": task_id,
            "dispatch": dispatch,
            "activity": "unknown",
            "observed_at": None,
            "owners": {key: owner.get("parent") for key, owner in getattr(task, "run_owners", {}).items()},
        }
        workers.append(row)
        try:
            if not status.strip():
                raise TaskReadError("task has no lifecycle status")
            if not dispatch:
                raise TaskReadError("task has no dispatch identifier")
            if dispatch not in cache:
                try:
                    cache[dispatch] = read(dispatch)
                except (RuntimeError, ValueError) as exc:
                    cache[dispatch] = exc
            entry = cache[dispatch]
            if isinstance(entry, Exception):
                raise TaskReadError(str(entry))
            details, timestamp = entry
            if not isinstance(details, dict) or (
                details.get("dispatchId") != dispatch
                or details.get("taskId") != task_id
                or not observation.nonblank(details.get("runId"))
                or (run and details["runId"] != run)
            ):
                raise TaskReadError("worker response does not match the task, run and dispatch")
            row["run"] = details["runId"]
            if not observation.is_timestamp(timestamp):
                raise TaskReadError("worker has no valid observation time")
            row["observed_at"] = timestamp
            row["activity"] = _worker_activity(details)
        except TaskReadError as exc:
            tasks.notes.append(f"Orca worker {task_id!r} in run {run!r}: Unknown ({exc}).")
    tasks.observation = {
        "source": source,
        "observed_at": observed_at,
        "coverage_complete": tasks.complete,
        "workers": workers,
    }


def _worker_result(raw):
    result = _result(raw)
    if isinstance(raw, dict) and raw is not result:
        for key in ("runId", "taskId", "dispatchId"):
            if key in raw and (not isinstance(result, dict) or raw[key] != result.get(key)):
                raise TaskReadError(f"worker envelope {key} does not match the result")
    return result


def _worker_activity(details: dict) -> str:
    terminal_states = FINISHED | {"closed", "dead", "exited", "settled", "terminated"}
    if any(
        details.get(key) in terminal_states
        for key in ("state", "terminalState", "liveness")
        if isinstance(details.get(key), str)
    ):
        return "stopped"
    activity = details.get("activity")
    return activity if activity in observation.ACTIVITIES else "unknown"


def _observed_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _observe_live(tasks: TaskCollection, command: str, executable: str | None) -> None:
    observed_at = _observed_now()
    deadline = monotonic() + OBSERVATION_BUDGET

    def read_worker(dispatch):
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TaskReadError("worker observation time budget exhausted")
        payload = _read_json(
            command, executable, ["worker-show", "--dispatch", dispatch], min(remaining, WORKER_TIMEOUT)
        )
        return _worker_result(payload), _observed_now()

    _observe(tasks, "live", read_worker, observed_at=observed_at)


def tasks_from_args(data: dict, args) -> list[dict] | str:
    """Collect configured runs, or return the legacy skip message when no check is requested."""
    if getattr(args, "no_orca", False):
        return "Orca not checked (--no-orca)."
    owners = run_owners(data)
    if path := getattr(args, "orca_json", None):
        return _recorded_tasks(path, owners)
    override = getattr(args, "orca_run", None)
    runs = [override] if override else list(owners)
    if not runs:
        return 'Orca not checked: set a coordinator run or "orca": {"run": ...} in roadmap.json or pass --orca-run.'
    command = cli_command()
    executable = shutil.which(command)
    source = f"CLI {command!r}"
    if executable and executable != command:
        source += f" resolved to {executable!r}"
    tasks = TaskCollection()
    _collect(tasks, runs, owners, lambda run: _read_run(run, command, executable), source)
    for run in sorted(owners.keys() - set(runs)):
        tasks.unknown(f"Orca run {run!r}", "outside the selected run", requested=False)
    _deduplicate(tasks)
    _observe_live(tasks, command, executable)
    return tasks


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
