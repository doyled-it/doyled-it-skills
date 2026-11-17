"""Shared helpers for the roadmap CLI tests (standard library only)."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SKILL = ROOT / "plugins" / "roadmap" / "skills" / "roadmap"
SCRIPTS = SKILL / "scripts"
CLI = SCRIPTS / "roadmap.py"
EXAMPLE = SKILL / "references" / "example-roadmap.json"
SCHEMA = SKILL / "references" / "roadmap.schema.json"
FIXTURES = HERE / "fixtures"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def example() -> dict:
    """A fresh deep copy of the bundled example roadmap."""
    return copy.deepcopy(json.loads(EXAMPLE.read_text()))


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def issue(data: dict, iid: str) -> dict:
    return next(i for i in data["issues"] if i["id"] == iid)
