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

- **Size.** The number of player characters who actually show up to fights. This scales the
  encounter budget linearly.
- **Levels.** Each character's level (and the average or spread if they differ).
- **Classes and subclasses.**
- **Roles.** Tag each character: striker (damage), controller (area and battlefield control),
  defender (tank, sticky, soaks hits), face (social), skirmisher or scout, healer or support,
  utility or caster. Most characters are two roles.

## Derive the drivers

From the roster, write down the three things the downstream skills need:

### 1. Encounter budget baseline

The 2024 encounter budget is an XP amount per character, by level, times the number of
characters. Compute and record the party's Low, Moderate, and High budgets now, so
`encounter-design` and `improvised-combat` start from a number, not a lookup. The per-character
XP table and the party-makeup adjustments live in
`../encounter-design/references/encounter-math-2024.md`.

### 2. Tactical gaps and strengths

Makeup changes real difficulty at the same XP. Note the party's levers and holes, because these
are qualitative adjustments the budget does not capture:

- Strong area damage or control: single big monsters die fast, swarms get deleted. Lean on
  resilient mid-sized groups and spread threats out.
- No healer or thin sustain: attrition and multi-encounter days bite harder.
- Low mobility or no ranged: terrain, fliers, and kiters punish them.
- Weak in a save (often Wisdom or Constitution): charm, fear, and stun land hard. Use sparingly
  unless you mean it.
- High nova, low endurance: they win short fights fast and fade over a long day. Pace stakes
  across the day, not one big fight.

### 3. Spotlight needs

List what each character is built to be good at and has not had a chance to shine at recently.
This is the checklist session-prep uses to make sure every player gets a scene that is theirs:
a lock for the rogue, a negotiation for the face, a lore puzzle for the wizard, a terrain fight
for the melee.

## Outputs (artifacts handed forward)

A party roster artifact with size, levels, roles, the three computed budgets, the tactical gaps
and strengths, and the spotlight checklist. encounter-design, improvised-combat, and session-prep
all read it.

## Common mistakes

- Budgeting for the party on the sheet instead of the party that shows up. A five-person party
  that is often four is a four-person budget.
- Treating makeup adjustments as math. They are judgment calls layered on the XP budget, not a
  formula.
- Recording roles and never using the spotlight checklist, so the same two players drive every
  scene.
