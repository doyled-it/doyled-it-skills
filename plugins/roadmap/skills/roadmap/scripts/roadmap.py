#!/usr/bin/env python3
"""roadmap: keep one agreed roadmap and work only from it.

Commands:
  validate ROADMAP            check schema, dependency cycles, dangling dependencies, glossary
  render ROADMAP [-o PAGE]    write the one-page HTML roadmap (default: next to the JSON)
  publish ROADMAP [--apply]   create or update epics, issues, blocked-by links and gate
                              checklists on GitLab or GitHub (dry run unless --apply)
  sync ROADMAP [--write]      read issue status, merge requests, pipelines and Orca tasks;
                              report drift (read-only on the forge and Orca)

Standard library only; Python 3.11 or newer.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from roadmaplib.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
