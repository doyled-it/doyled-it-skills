---
name: encounter-design
description: Use when designing a planned D&D 5e (2024) combat encounter: tuning difficulty to party size and makeup with the 2024 XP budget, and making the fight interesting with an objective, terrain, enemy tactics, and pacing, not just balanced. Holds the shared interesting-combat core that improvised-combat reuses.
---

# Encounter design

## Overview

A balanced fight is not the same as a good fight. This skill does both: it tunes difficulty with
the 2024 encounter budget, and it makes the fight interesting with an objective, terrain,
tactics, and pacing. It owns the shared "interesting combat" core, which `improvised-combat`
reuses at the table. Use this skill for fights you design ahead of time.

Design the fight, not just the monsters. A pile of statblocks at the right XP is where a boring
fight starts.

## Design order

Do these in order. Difficulty is a constraint, not the design.

### 0. Check table safety

Before generating any content, read the table safety artifact (the lines and veils agreed at
session-zero). Do not stage a fight on a line, and keep veiled content off screen. Safety is a
hard constraint on the monsters, the objective, and the fiction, not an afterthought.

### 1. Objective first

Decide what the fight is about, beyond "kill everything". Options: escort or protect an NPC,
hold a position, assault one, retrieve an item, escape, survive a timer, disrupt a ritual. Tell
the players the objective in the fiction. A fight with a win condition other than zero enemy hit
points is more interesting and lets you plan failure outcomes short of a total party kill.

### 2. Budget to party size and makeup

Set a target difficulty (Low, Moderate, High) and compute the XP budget as the sum of each
character's own per-level budget (not an average level times a head count; a mixed-level party is
summed level by level). The 2024 method drops the old count-based multipliers. Then adjust
qualitatively for the party's makeup (area damage, control, action economy, saves, nova, sustain).
The per-level table, the mixed-level worked example, and the adjustments are all in
`references/encounter-math-2024.md`. Pull the precomputed budgets from the party roster
(party-composition) when you have them.

### 3. Pick or build the monsters

Choose monsters that fit the location and the objective. Favor a mix of roles with synergy
(brutes in front, ranged or controllers behind, a few lightning rods that show off the party).
Spend complex statblocks on bosses and lieutenants; run minor foes simply. A single big monster
dies fast to an action-economy advantage, so give a solo boss extra actions (villain or
legendary actions) or support minions. For a monster the books lack, or to re-stat a recurring
villain, invoke `custom-monsters`.

### 4. Terrain, tactics, pacing

Make the battlefield and the enemies do work. The full checklist is in
`references/interesting-combat.md`. The headline levers:

- **Terrain:** one or two meaningful features, not many. Difficult terrain, usable cover,
  chokepoints, height, interactive objects, and hazards that come with clues so players can play
  around them.
- **Tactics:** plan how the enemies open, press, and retreat before play. Scale their smarts to
  their Intelligence and their nerve to their Wisdom. Prefer ambush, focus fire, and withdrawal
  when the statblock supports it.
- **Pacing:** aim for a short, decisive fight. Change the situation mid-combat (a reinforcement
  wave, a collapsing floor, the villain speaks). End the fight when the outcome is settled rather
  than grinding to the last hit point.

## Output: the encounter artifact

In Obsidian (the default binding), the runnable form is an Initiative Tracker `encounter` block,
with the objective, terrain, and tactics as prose headings beside it, per
`../dungeon-master-loop/references/obsidian-ttrpg-formats.md`. Creature names in the block resolve
against the bestiary, so a `custom-monsters` statblock drops in by name.

Record the encounter so it is runnable and so printing can read it: the objective, the enemy
list with statblock references, the map and its terrain features, the enemy tactics and any
retreat threshold, and the pacing beats or reinforcement triggers. Hand the enemy list and
terrain to `printable-minis-and-terrain`.

## Common mistakes

- Designing by XP alone: the budget is the floor of the work, not the work.
- "Kill everything" as the only objective.
- Too many terrain features, which slows the fight more than it enriches it.
- A solo boss with no extra actions, deleted by the party's action economy in two rounds.
- Monsters that fight to the death with no tactics or morale, when the fiction says they would
  flee.
