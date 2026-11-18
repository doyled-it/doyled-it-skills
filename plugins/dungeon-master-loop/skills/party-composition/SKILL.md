---
name: party-composition
description: Use when the party roster is set or changes (a new player, a death, a level up) in D&D 5e and you need to capture party size, classes, roles, and levels and derive what they drive downstream: the encounter budget baseline, tactical gaps and strengths, and each player's spotlight needs.
---

# Party composition

## Overview

The party is the one input that drives everything downstream. Encounter budgets, which fights are
fun, which challenges land, and whose spotlight is owed all read from the roster. This skill
captures the roster once and derives the drivers the combat and prep skills consume, so you do
not re-derive them every session. Re-run it whenever the roster changes.

## Capture the roster

Record, for the party as a whole and per character:

- **Size.** The number of player characters who actually show up to fights.
- **Levels.** Each character's own level, recorded separately. Never average the levels: the
  budget is the sum of each character's per-level budget, not an average level times a head count
  (see `../encounter-design/references/encounter-math-2024.md`).
- **Classes and subclasses.**
- **Roles.** Tag each character: striker (damage), controller (area and battlefield control),
  defender (tank, sticky, soaks hits), face (social), skirmisher or scout, healer or support,
  utility or caster. Most characters are two roles.

## Derive the drivers

From the roster, write down the three things the downstream skills need:

### 1. Encounter budget baseline

The 2024 encounter budget is the sum of each character's per-level XP budget, not an average level
times a count. Compute and record the party's Low, Moderate, and High budgets now (summing the
real levels), so `encounter-design` and `improvised-combat` start from a number, not a lookup. The
per-level XP table, the mixed-level worked example, and the canonical party-makeup adjustments all
live in `../encounter-design/references/encounter-math-2024.md`.

### 2. Tactical gaps and strengths

Makeup changes real difficulty at the same XP. The canonical list of makeup factors, and how each
shifts difficulty, lives in `../encounter-design/references/encounter-math-2024.md` (the "Party
makeup" section). Do not restate it here. Instead, record where this specific party sits on each
factor: area damage and control, action economy, healer and sustain, mobility and range, weak
saves, and nova versus endurance. Flag the one or two that matter most, so session-prep and
encounter-design can lean into or around them.

### 3. Spotlight needs

List what each character is built to be good at and has not had a chance to shine at recently.
This is the checklist session-prep uses to make sure every player gets a scene that is theirs:
a lock for the rogue, a negotiation for the face, a lore puzzle for the wizard, a terrain fight
for the melee.

## Outputs (artifacts handed forward)

In Obsidian (the default binding), each PC is also an Initiative Tracker party member (a note with
`hp`, `ac`, `modifier`, and `level` frontmatter, grouped into a party), per
`../dungeon-master-loop/references/obsidian-ttrpg-formats.md`, so `players: true` pulls the whole
party into any encounter.

A party roster artifact with size, per-character levels, roles, the three computed budgets, the
tactical gaps and strengths, and the spotlight checklist. encounter-design, improvised-combat, and
session-prep all read it.

## Common mistakes

- Budgeting for the party on the sheet instead of the party that shows up. A five-person party
  that is often four is a four-person budget.
- Averaging the party's levels instead of summing each character's own budget. Mixed-level parties
  must be summed level by level, or the budget is wrong.
- Treating makeup adjustments as math. They are judgment calls layered on the XP budget, not a
  formula.
- Recording roles and never using the spotlight checklist, so the same two players drive every
  scene.
