---
name: printable-minis-and-terrain
description: Use when tying D&D encounter and world prep to 3D printing on an FDM printer (Bambu Lab): deciding when to print versus use a token or proxy, sourcing STLs, scheduling print lead time across upcoming sessions, keeping a mini and terrain inventory, and mapping prepped enemies and terrain to miniatures you own or must print.
---

# Printable minis and terrain

## Overview

Physical minis and terrain make a fight read at the table, but printing takes hours to days, so it
has to be planned against prep, not grabbed the night before. This skill connects encounter and
world prep to the printer: it keeps an inventory of what you own, maps prepped enemies to minis,
and queues prints early enough to finish. Printer-specific settings and times for Michael's Bambu
Lab X2D are in `references/bambu-x2d-settings.md`.

This skill is optional in the loop (a token works), but when you do print, lead time is the whole
game. A boss you decide to print three days out is fine; one you remember the night before is a
token.

## The mini and terrain inventory

Keep one inventory of what you physically own or have printed. It is the thing improvised-combat
and encounter-design check before conjuring enemies. One row per piece:

- ID and name
- Type and size category (Tiny to Gargantuan)
- Tags (humanoid, undead, beast, construct, terrain, and so on)
- Status: owned and printed, queued, or not owned
- STL source and local file path, if any
- "Needs print by" date, for anything queued

Prefer reusing owned minis over printing new ones, and print generic, reusable creatures (guards,
undead, beasts, townsfolk) once so they serve many sessions.

## The print manifest: look ahead, do not just read next session

A print manifest is wrong if it only reads the current session plan, because lead time runs ahead
of a single week. Build it from a multi-session lookahead:

- The current session plan's designed encounters.
- Recurring villains likely to reappear (from hooks and seeds, and advancing-the-world's re-stat
  flags).
- Faction clocks near completion, which will trigger set-piece fights.
- Terrain for upcoming fantastic locations.

For each item, decide print, proxy, or token (below), and give anything to print a "needs print
by" date backed off from the session by its print time plus a day for failures. Batch minis that
share a plate and material.

Because lead time runs days out, the loop invokes this skill at three points, not just before a
session: when the cast is finalized (queue the villains and recurring NPCs immediately), after
advancing the world (queue the likely enemies a near-full clock or a re-statted villain will
bring), and again at physical prep for the current session. Queue early, reconcile late.

## When to print, proxy, or token

- **Print** when the creature is a boss or a set-piece centerpiece, will recur, or is a reusable
  generic you will get many sessions out of. Printing earns its lead time there.
- **Proxy** (an owned mini that stands in) when you lack the exact figure but own something of the
  right size and silhouette. Match size category first, then silhouette, then role. Mark the real
  monster with a labeled base or colored ring and note the "counts as" in the encounter. This is
  the same proxy rule improvised-combat uses.
- **Token** (a disc or scrap) when it is a one-off, a swarm, or you are out of lead time. Do not
  print under deadline pressure; a token now beats a failed print at midnight.

## Mapping prepped enemies to minis

As encounter-design and session-prep produce enemy lists, resolve each enemy to an inventory ID:
owned, queued (with a needs-print-by date), or proxied (with the counts-as note). An enemy with no
plan is a hole; close it with a proxy or a token before the session.

## Printer and materials (Bambu Lab X2D)

Full settings, realistic print times, and optional filament purchases are in
`references/bambu-x2d-settings.md`. The short version: it is a dual-nozzle FDM machine (no resin),
so minis look good at table distance but soften on faces and thin parts. Use a 0.2 mm nozzle and
fine layers for hero, NPC, and boss minis, and a 0.4 mm nozzle for crowds and terrain. The current
PLA, PETG, and TPU stock covers minis, terrain, and flexible pieces; the reference flags optional
purchases (fine-detail matte PLA, soluble support filament, a 0.2 mm hotend, a filament dryer) that
would clearly help, with reasons. Confirm the exact model and firmware against Bambu's own specs
before buying hardware.

## Outputs (artifacts handed forward)

An updated inventory and a dated print manifest. You read the manifest during prep so prints finish
before the session. improvised-combat reads the inventory at the table.

## Common mistakes

- Building the manifest from next session only, so a long print misses its session.
- Printing a one-off boss under deadline instead of proxying it.
- Printing detailed minis on a 0.4 mm nozzle, or crowds on a 0.2 mm nozzle (slow for no gain).
- No inventory, so improvised-combat cannot prefer owned minis and you reprint what you already
  have.
