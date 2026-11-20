#!/usr/bin/env bash
# Runs the roadmap command tests (uv or Python 3.11+, standard library only): validate,
# render, epic sections and preview, publish dry runs and sync drift detection
# against recorded GitLab, GitHub and Forgejo responses. No network access.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT/tests/roadmap"

# As the roadmap launcher does: a Python 3.11+ that uv already has, then the
# first python3 that is 3.11+. Nothing is downloaded.
PY=()
if command -v uv >/dev/null 2>&1 && uv python find --no-project '>=3.11' >/dev/null 2>&1; then
  PY=(uv run --no-project --no-python-downloads --python '>=3.11' python)
else
  for candidate in python3 python3.13 python3.12 python3.11; do
    if command -v "$candidate" >/dev/null 2>&1 &&
      "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
      PY=("$candidate")
      break
    fi
  done
fi
if [ ${#PY[@]} -eq 0 ]; then
  echo "roadmap: FAIL: uv or Python 3.11 or newer is required" >&2
  exit 1
fi

export PYTHONDONTWRITEBYTECODE=1
echo "roadmap: command tests with $("${PY[@]}" --version)"
"${PY[@]}" -m unittest discover -q -s . -p 'test_*.py'
