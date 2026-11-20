#!/bin/sh
# Run a roadmap Python script on an installed Python 3.11 or newer.
#
#   sh python.sh SCRIPT [ARG...]          the roadmap command
#   sh python.sh --hook SCRIPT [ARG...]   a Claude Code hook or Codex notify program
#
# Order: a Python 3.11+ that uv already has (uv python find), run with
# `uv run --no-project --no-python-downloads --python '>=3.11' python`; then
# python3 when it is 3.11 or newer (macOS ships 3.9). Nothing is downloaded:
# with neither, the command says what to install and exits 1. uv is looked up
# on PATH, then in ROADMAP_UV_DIRS (colon-separated; default ~/.local/bin,
# ~/.cargo/bin, /opt/homebrew/bin, /usr/local/bin), because hosts started from
# a desktop often run hooks with a short PATH.
#
# --hook fails open: it always exits 0, so a hook never blocks a turn (uv exits
# 2 when it cannot run, and 2 blocks a Claude Code turn). When the script cannot
# run it prints one systemMessage, and only when a roadmap is present
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

# Text safe to put inside a JSON string.
plain() {
  printf '%s' "$1" | tr -cd 'A-Za-z0-9 ._+/:,;()-'
}

skip() {
  if roadmap_present; then
    printf '{"systemMessage": "roadmap check skipped: %s"}\n' "$(plain "$1")"
  fi
  exit 0
}

run() {
  if [ "$hook" = 0 ]; then
    exec "$@"
  fi
  "$@"
  status=$?
  [ "$status" = 0 ] || skip "the hook did not run under $1 (exit $status). Run the roadmap command by hand to see why"
  exit 0
}

find_uv() {
  if command -v uv >/dev/null 2>&1; then
    command -v uv
    return 0
  fi
  dirs=${ROADMAP_UV_DIRS-$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin}
  old_ifs=$IFS
  IFS=:
  set -f
  for dir in $dirs; do
    if [ -n "$dir" ] && [ -x "$dir/uv" ]; then
      IFS=$old_ifs
      set +f
      printf '%s\n' "$dir/uv"
      return 0
    fi
  done
  IFS=$old_ifs
  set +f
  return 1
}

uv=$(find_uv) || uv=""
if [ -n "$uv" ] && "$uv" python find --no-project '>=3.11' >/dev/null 2>&1; then
  run "$uv" run --no-project --no-python-downloads --python '>=3.11' python "$@"
fi
if command -v python3 >/dev/null 2>&1 &&
  python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
  run python3 "$@"
fi

if command -v python3 >/dev/null 2>&1; then
  found=$(python3 --version 2>&1)
else
  found="no python3"
fi
if [ -n "$uv" ]; then
  why="uv at $uv has no Python 3.11 or newer installed and python3 is $found"
  fix="Run: $uv python install 3.12"
else
  why="no uv was found and python3 is $found"
  fix="Install uv (https://docs.astral.sh/uv/) and run: uv python install 3.12"
fi
if [ "$hook" = 1 ]; then
  skip "it needs Python 3.11 or newer; $why. $fix"
fi
echo "roadmap: needs Python 3.11 or newer; $why." >&2
echo "$fix, or install Python 3.11 or newer, then run the command again." >&2
exit 1
