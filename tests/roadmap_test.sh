#!/usr/bin/env bash
# Runs the roadmap command tests (Python 3.11+, standard library only): validate,
# render, epic sections and preview, publish dry runs and sync drift detection
# against recorded GitLab, GitHub and Forgejo responses. No network access.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT/tests/roadmap"

PY=""
for candidate in python3 python3.13 python3.12 python3.11; do
  if command -v "$candidate" >/dev/null 2>&1 &&
    "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    PY=$candidate
    break
  fi
done
if [ -z "$PY" ]; then
  echo "roadmap: FAIL: Python 3.11 or newer is required" >&2
  exit 1
fi

export PYTHONDONTWRITEBYTECODE=1
echo "roadmap: command tests with $("$PY" --version)"
"$PY" -m unittest -q test_validate test_render test_epic_block test_markers test_forge_text test_urls test_gates test_http test_apply test_publish test_sync test_sync_errors test_validate_robust test_a11y_members test_hygiene test_check_mr test_drift_issue test_forgejo
