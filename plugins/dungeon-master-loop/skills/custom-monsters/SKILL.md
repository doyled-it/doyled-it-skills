---
name: custom-monsters
description: Use when you need a homebrew or reskinned monster, villain, or statblock for D&D 5e (2024) that the Monster Manual does not have, including building to a target challenge rating and re-statting a recurring villain as the party levels.
---

# Custom monsters

## Overview

When the books do not have the creature the fight needs, build or reskin one. This skill produces
a bestiary statblock artifact that `encounter-design` and `improvised-combat` can drop into a
fight. The fastest route is usually to reskin an existing statblock; build from numbers only when
nothing fits.

A warning the research surfaced: the 2024 Dungeon Master's Guide has no monster-creation framework
and no "Monster Statistics by Challenge Rating" table (the 2014 DMG did). So there is no single
official 2024 method, and any number you use comes from a specific, labeled source. The build
math and its provenance are in `references/monster-building-2024.md`.

## Three routes, fastest first

### 1. Reskin (default)

Find an existing statblock at the right challenge rating with the right shape (melee brute, ranged
skirmisher, caster, swarm), and change the fiction: name, description, damage type, one or two
signature abilities. The math is already balanced. Most "custom" monsters should be reskins. Note
the base statblock in the artifact so you can re-run it.

### 2. Quick build (improvised or fast prep)

When you need a monster fast and no reskin fits, use the Forge of Foes quick-monster workflow:
pick a target CR, take base stats from a quick table, adjust armor class against hit points,
improvise one or two attacks to a target damage per round, add one or two signature powers, and
improvise saves at the table. This is 5e-generic, not 2024-specific. The sample numbers are in
the reference, labeled.

### 3. Build to CR from numbers (set-piece bosses)

For a boss or set piece you want precise, build from the community reverse-engineered 2024 Monster
Manual tables (hit points, damage per round, armor class, save DC by CR), then cross-check against
the 2014 DMG CR benchmarks and against the XP of the closest official 2024 monster. Every figure
is labeled by source and edition in the reference. Do not mix editions silently.

## Make a monster interesting

A balanced statblock is still boring if it only swings. Add what `encounter-design`'s
interesting-combat core rewards:

- One signature move that creates a decision for the players (a pull, a zone, a debuff, a summon).
- For a boss, extra actions: villain actions on top of the normal economy (position, escape,
  explode across rounds), or legendary actions and legendary resistance, so it survives the party's
  action economy.
- A clear way it fights and a reason and threshold to flee.

## Recurring villains

When `advancing-the-world` flags a surviving villain for re-stat, bring the villain's statblock
up to remain a threat for the party's new level: raise the defensive numbers and damage to the new
CR band, keep the signature moves and personality, and add a villain action if it did not have
one. Re-stat only when you are prepping that fight, not every time the party levels.

## Output: the bestiary statblock artifact

In Obsidian (the default binding), write it as a bestiary-indexed note: `statblock: inline` plus a
`name` in frontmatter, with the `statblock` block body, per
`../dungeon-master-loop/references/obsidian-ttrpg-formats.md`. That flag is what lets Initiative
Tracker and Encounter Builder find the creature by name; without it the block renders but is
invisible to the trackers.

A statblock with its CR and XP, the base statblock if it is a reskin, the source and edition of any
built numbers, the signature move, and any villain or legendary actions. encounter-design and
improvised-combat reference it by name; printable-minis-and-terrain maps it to a mini.

## Common mistakes

- Building from numbers when a reskin would have been faster and already balanced.
- Mixing 2014 and 2024 or community numbers without labeling which is which.
- A boss with no extra actions, erased by the party's action economy.
- Re-statting a recurring villain every level instead of when the fight is actually coming.
