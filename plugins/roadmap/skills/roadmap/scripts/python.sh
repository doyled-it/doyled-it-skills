#!/bin/sh
# Run a roadmap Python script on Python 3.11 or newer.
#
#   sh python.sh SCRIPT [ARG...]          the roadmap command
#   sh python.sh --hook SCRIPT [ARG...]   a Claude Code hook or Codex notify program
#
# Uses `uv run --no-project --python 3.12 python` when uv is on PATH, otherwise
# python3 only when it is 3.11 or newer (macOS ships 3.9). With neither, the
# command explains what to install and exits 1.
#
# --hook fails open: it always exits 0, so a hook never blocks a turn (uv exits
# 2 when it cannot get Python, and 2 blocks a Claude Code turn). When the script
# cannot run it prints one systemMessage, and only when a roadmap is present
# (ROADMAP_FILE, else roadmap.json in the working directory or at its git root),
# so a session without a roadmap hears nothing.

hook=0
if [ "${1:-}" = "--hook" ]; then
  hook=1
  shift
fi

# A roadmap of this tool's shape names "epics" and "issues"; another tool's
# roadmap.json stays silent, as the hook itself does.
ours() {
  [ -f "$1" ] && grep -q '"epics"' "$1" 2>/dev/null && grep -q '"issues"' "$1" 2>/dev/null
}

roadmap_present() {
  if [ -n "${ROADMAP_FILE:-}" ]; then
    ours "$ROADMAP_FILE"
    return
  fi
  if [ -f roadmap.json ]; then
    ours roadmap.json
    return
  fi
  top=$(git rev-parse --show-toplevel 2>/dev/null) || return 1
  [ -n "$top" ] && ours "$top/roadmap.json"
}

skip() {
  if roadmap_present; then
    printf '{"systemMessage": "roadmap check skipped: %s"}\n' "$1"
  fi
  exit 0
}

run() {
  if [ "$hook" = 0 ]; then
    exec "$@"
  fi
  "$@"
  status=$?
  [ "$status" = 0 ] || skip "the hook did not run (exit $status); run the roadmap command by hand to see why"
  exit 0
}

if command -v uv >/dev/null 2>&1; then
  run uv run --no-project --python 3.12 python "$@"
fi
if command -v python3 >/dev/null 2>&1 &&
  python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
  run python3 "$@"
fi

if command -v python3 >/dev/null 2>&1; then
  found=$(python3 --version 2>&1 | tr -cd 'A-Za-z0-9 ._+-')
else
  found="no python3"
fi
if [ "$hook" = 1 ]; then
  skip "it needs uv or Python 3.11 or newer (found $found)"
fi
echo "roadmap: needs Python 3.11 or newer, run through uv when it is installed (found $found)." >&2
echo "Install uv (https://docs.astral.sh/uv/) or Python 3.11 or newer, then run the command again." >&2
exit 1
