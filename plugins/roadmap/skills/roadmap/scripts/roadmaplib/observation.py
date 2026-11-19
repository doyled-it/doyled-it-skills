"""Contract for timestamped Orca worker observations."""

from __future__ import annotations

import re
from datetime import datetime

ACTIVITIES = ("working", "waiting", "idle", "queued", "stopped", "unknown")
SOURCES = ("live", "recorded")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])")


def nonblank(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_timestamp(value) -> bool:
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def problems(snapshot):
    """Yield field locations and errors for a snapshot stored in roadmap.json."""
    if not isinstance(snapshot, dict):
        yield "", "must be an object"
        return
    if snapshot.get("source") not in SOURCES:
        yield ".source", 'must be "live" or "recorded"'
    if "observed_at" not in snapshot or (
        snapshot["observed_at"] is not None and not is_timestamp(snapshot["observed_at"])
    ):
        yield ".observed_at", "must be a date and time with a timezone, or null"
    if not isinstance(snapshot.get("coverage_complete"), bool):
        yield ".coverage_complete", "must be true or false"
    workers = snapshot.get("workers")
    if not isinstance(workers, list):
        yield ".workers", "must be a list of worker observations"
        return
    for index, row in enumerate(workers):
        where = f".workers[{index}]"
        if not isinstance(row, dict):
            yield where, "must be an object"
            continue
        activity = row.get("activity")
        if activity not in ACTIVITIES:
            yield f"{where}.activity", "must be working, waiting, idle, queued, stopped or unknown"
        if not nonblank(row.get("task")):
            yield f"{where}.task", "must be a nonblank task identifier"
        for key in ("run", "dispatch"):
            if not nonblank(row.get(key)) and not (activity == "unknown" and key in row and row[key] is None):
                yield f"{where}.{key}", "must be a nonblank identifier, or null for Unknown activity"
        if not is_timestamp(row.get("observed_at")) and not (
            activity == "unknown" and "observed_at" in row and row["observed_at"] is None
        ):
            yield f"{where}.observed_at", "must be a date and time with a timezone, or null for Unknown activity"
        owners = row.get("owners")
        if not isinstance(owners, dict) or any(
            not nonblank(key) or (parent is not None and not nonblank(parent)) for key, parent in owners.items()
        ):
            yield f"{where}.owners", "must map owner keys to their parent keys or null"


def summary(snapshot: dict) -> str:
    workers = snapshot["workers"]
    working = {row["dispatch"] for row in workers if row["activity"] == "working"}
    unknown = sum(row["activity"] == "unknown" for row in workers)
    text = f"{len(working)} confirmed working, {unknown} Unknown"
    if not snapshot["coverage_complete"]:
        text += ". Coverage of all roadmap runs is Unknown"
    return text
