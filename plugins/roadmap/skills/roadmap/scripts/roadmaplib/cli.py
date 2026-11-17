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


def cmd_epic_preview(args) -> int:
    from . import preview

    data = _load(args.roadmap)
    if args.epic not in {e.get("id") for e in data.get("epics", [])}:
        print(f'error: no epic "{args.epic}" in {args.roadmap}')
        return 1
    try:
        page = render.render_page(data)
    except render.RenderError as exc:
        print(exc)
        return 1
    src = Path(args.roadmap)
    out = Path(args.out) if args.out else src.with_name(f"{src.stem}-epic-{args.epic}.html")
    # The full page goes beside the preview under the preview's own name, so it
    # never replaces a page of the same name the user keeps there.
    full = out.with_name(f"{out.stem}-full.html")
    for path in (out, full):
        if path.exists() and 'name="generator" content="roadmap' not in path.read_text(errors="replace")[:2000]:
            print(f"error: {path} exists and was not written by roadmap; choose another -o")
            return 1
    full.write_text(page)
    kind = (data.get("forge") or {}).get("kind")
    out.write_text(preview.preview_page(data, args.epic, full.name, task_list=kind in ("forgejo", "gitea")))
    print(f"wrote {out} (preview of epic {args.epic}, nothing written to the forge) and the full page {full}")
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
    return 2 if report.failed else 0


def cmd_sync(args) -> int:
    from . import forge, orca, sync

    if args.update_epics and not args.write:
        print("error: --update-epics needs --write, so the epics on the forge and roadmap.json show the same status")
        return 2
    data = _load(args.roadmap)
    try:
        fg = forge.from_args(data, args)
    except forge.ForgeError as exc:
        print(f"error: {exc}")
        return 2
    tasks = orca.tasks_from_args(data, args)
    try:
        report = sync.sync(data, fg, orca_tasks=tasks, stale_days=args.stale_days, now=args.now,
                           update_epics=args.update_epics)
    except (sync.SyncRefused, forge.ForgeError) as exc:
        print(f"error: {exc}")
        return 2
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(report.text())
    if report.errors:
        return 1
    if args.write and report.changed:
        model.save(args.roadmap, report.roadmap)
        print(f"updated status and gates in {args.roadmap}; re-render the page next")
    return 0


def _iso_date(value: str) -> str:
    from . import sync

    try:
        sync.parse_now(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f'"{value}" is not an ISO date such as 2026-11-17') from None
    return value


def _forge_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--forge", choices=("gitlab", "github", "forgejo"),
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

    ep = sub.add_parser("epic-preview",
                        help="write a local page showing an epic's generated section beside the full roadmap")
    ep.add_argument("roadmap")
    ep.add_argument("--epic", required=True, help="epic id")
    ep.add_argument("-o", "--out", help="output HTML path (default: <roadmap>-epic-<id>.html)")
    ep.set_defaults(func=cmd_epic_preview)

    pb = sub.add_parser("publish", help="create or update forge epics and issues (dry run by default)")
    pb.add_argument("roadmap")
    pb.add_argument("--apply", action="store_true", help="make the changes; without it nothing is written")
    _forge_args(pb)
    pb.set_defaults(func=cmd_publish)

    s = sub.add_parser("sync", help="read status, merge requests, pipelines and Orca tasks; report drift")
    s.add_argument("roadmap")
    s.add_argument("--write", action="store_true",
                   help="update status and gate ticks in roadmap.json (never writes to the forge or Orca)")
    s.add_argument("--update-epics", action="store_true",
                   help="rewrite the generated roadmap section in each epic (the only forge write sync makes)")
    s.add_argument("--json", action="store_true", help="print the report as JSON")
    s.add_argument("--stale-days", type=int, default=14, help="no activity for this many days is drift")
    s.add_argument("--now", type=_iso_date, help="ISO date to measure staleness from (default: today)")
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
