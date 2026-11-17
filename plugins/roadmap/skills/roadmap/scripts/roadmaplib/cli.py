"""Command-line interface for the roadmap tool."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import model, render, validate


def _load(path: str) -> dict:
    try:
        return model.load(path)
    except model.RoadmapError as exc:
        print(f"error: {exc}")
        raise SystemExit(1) from exc


def cmd_validate(args) -> int:
    findings = validate.check(_load(args.roadmap))
    for f in findings:
        print(f)
    n_err = len(validate.errors(findings))
    print(f"{n_err} errors, {len(findings) - n_err} warnings")
    return 1 if n_err else 0


def cmd_render(args) -> int:
    data = _load(args.roadmap)
    try:
        page = render.render_page(data)
    except render.RenderError as exc:
        print(exc)
        return 1
    out = Path(args.out) if args.out else Path(args.roadmap).with_suffix(".html")
    out.write_text(page)
    print(f"wrote {out} ({len(data['issues'])} issues, {len(data['epics'])} epics)")
    for f in validate.errors(validate.check(data)):
        print(f"note: {f}")
    return 0


def cmd_publish(args) -> int:
    from . import forge, publish

    data = _load(args.roadmap)
    try:
        fg = forge.from_args(data, args)
        report = publish.publish(data, fg, apply=args.apply, allow_draft=False)
    except (publish.PublishRefused, forge.ForgeError) as exc:
        print(f"error: {exc}")
        return 2
    print(report.text())
    if args.apply and report.changed:
        model.save(args.roadmap, report.roadmap)
        print(f"wrote forge links back into {args.roadmap}")
    return 0


def cmd_sync(args) -> int:
    from . import forge, orca, sync

    data = _load(args.roadmap)
    try:
        fg = forge.from_args(data, args)
    except forge.ForgeError as exc:
        print(f"error: {exc}")
        return 2
    tasks = orca.tasks_from_args(data, args)
    report = sync.sync(data, fg, orca_tasks=tasks, stale_days=args.stale_days, now=args.now)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(report.text())
    if args.write and report.changed:
        model.save(args.roadmap, report.roadmap)
        print(f"updated status and gates in {args.roadmap}; re-render the page next")
    return 0


def _forge_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--forge", choices=("gitlab", "github"),
                   help="override the forge kind (default: roadmap forge.kind, then the git remote)")
    p.add_argument("--repo", default=".", help="checkout whose origin remote picks the forge (default: .)")
    p.add_argument("--recorded", metavar="FILE",
                   help="answer forge reads from a recorded JSON file instead of the network (tests, demos)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="roadmap", description="Keep one agreed roadmap and work only from it.")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="check schema, cycles, dangling dependencies, glossary")
    v.add_argument("roadmap")
    v.set_defaults(func=cmd_validate)

    r = sub.add_parser("render", help="write the one-page HTML roadmap")
    r.add_argument("roadmap")
    r.add_argument("-o", "--out", help="output HTML path (default: roadmap path with .html)")
    r.set_defaults(func=cmd_render)

    pb = sub.add_parser("publish", help="create or update forge epics and issues (dry run by default)")
    pb.add_argument("roadmap")
    pb.add_argument("--apply", action="store_true", help="make the changes; without it nothing is written")
    _forge_args(pb)
    pb.set_defaults(func=cmd_publish)

    s = sub.add_parser("sync", help="read status, merge requests, pipelines and Orca tasks; report drift")
    s.add_argument("roadmap")
    s.add_argument("--write", action="store_true",
                   help="update status and gate ticks in roadmap.json (never writes to the forge or Orca)")
    s.add_argument("--json", action="store_true", help="print the report as JSON")
    s.add_argument("--stale-days", type=int, default=14, help="no activity for this many days is drift")
    s.add_argument("--now", help="ISO date to measure staleness from (default: today)")
    s.add_argument("--orca-run", help="Orca run id to read tasks from (default: roadmap orca.run)")
    s.add_argument("--orca-json", help="read Orca tasks from this JSON file instead of the orca CLI")
    s.add_argument("--no-orca", action="store_true", help="skip the Orca check")
    _forge_args(s)
    s.set_defaults(func=cmd_sync)
    return p


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 11):
        print("error: roadmap needs Python 3.11 or newer")
        return 2
    args = build_parser().parse_args(argv)
    return args.func(args)
