---
name: improvised-combat
description: Use when a D&D 5e fight is needed on the fly at the table, with no prepped encounter: conjure an encounter, a quick map, and enemies in minutes, reusing the difficulty budget and interesting-combat core and preferring miniatures you already own.
---

# Improvised combat

## Overview

Sometimes the party starts a fight you did not prep. This is the fast path: an encounter plus a
map plus enemies, conjured in a couple of minutes, that is still interesting and still roughly
tuned. It does not reinvent the rules. It reuses the difficulty budget and the interesting-combat
core from `encounter-design` (read `../encounter-design/references/encounter-math-2024.md` and
`../encounter-design/references/interesting-combat.md`), and it leans on what you physically own
so you are not caught without a mini.

The trick to improvising a good fight is the same as a prepped one, just faster: decide the
question, grab enemies, give the space one feature, and know how the enemies fight.

## The two-minute procedure

1. **Question and objective.** One line: what is this fight about, and when does it end? Even
   improvised, give it a win condition other than "kill everything" when the fiction offers one
   (they are fleeing, there is a hostage, the alarm is ringing).
2. **Budget from the roster.** Pull the party's precomputed Low, Moderate, High budgets from the
   party roster. Pick a band for the moment and grab monsters that fit the XP. No recomputation
   at the table.
3. **Enemies from what you own.** Check the mini and terrain inventory first and prefer creatures
   you have a mini for. Reskin freely: a bandit statblock becomes a cultist, a wolf becomes a
   hound of the Front. When you lack the exact mini, follow the canonical proxy rule in
   `../printable-minis-and-terrain/SKILL.md` (match size, then silhouette, then role; mark the
   real monster and note the "counts as"). Do not restate it here.
4. **One terrain feature.** Give the space a single meaningful feature: a chokepoint, high
   ground, difficult terrain, or an interactive object. One is enough to make positioning matter.
5. **How they fight.** Decide in a sentence how the enemies open, press, and break. Scale smarts
   to Intelligence and nerve to Wisdom. Set a rough retreat threshold so the fight can end before
   the last hit point.

## Keep it tuned by feel

You will not have exact XP. Use the party roster's tactical notes: if they have strong area
damage, use fewer, tougher enemies; if they lack a healer, do not grind them. Change the
situation if the fight sags (a wave arrives, the enemy flees, something collapses). End it when
the question is answered.

## Output in Obsidian

Write the conjured fight as an Initiative Tracker `encounter` block (see
`../dungeon-master-loop/references/obsidian-ttrpg-formats.md`). Owned bestiary creatures drop in by
name, so you can start the fight in seconds without statting anything.

## After the fight: flag for write-back

Improvised enemies, NPCs, and places that the party engaged with are inventions. Note them so
`advancing-the-world` can promote the ones that could recur into canon (and send a reskinned or
homebrewed statblock worth keeping to `custom-monsters`). Add any creature you wished you had a
mini for to the print queue.

## Common mistakes

- Recomputing the full XP budget at the table. Precompute it in party-composition and pick a band.
- Grabbing a monster you have no mini or proxy for when an owned one would have worked.
- Flat enemies with no tactics or terrain, which is the slog you were trying to avoid.
- Letting the improvised fight run to the last hit point instead of ending on the question.
