---
name: advancing-the-world
description: Use when a D&D session has just ended and you need to turn what happened into world changes: capture the recap, write inventions from prep and play into canon, tick faction clocks, roll unfound secrets forward, convert loose ends and surviving villains into hooks, re-stat recurring enemies, and advance the Front before the next prep.
---

# Advancing the world

## Overview

This is the session-to-world half of the loop. Play changed the world. This skill records that
change so the next prep starts from a true state, not a stale one. It is the simulation step
that updates state between runs. Skip it and your world quietly drifts out of sync with what
actually happened at the table.

It both produces and consumes the recap: it captures the recap first, then acts on it. Run it
soon after the session, while memory is fresh.

## Step 1: Guided recap capture

Nothing else produces the recap, so start by capturing it. Walk these prompts and write the
answers into the session's recap note:

- What did the party actually do, in three to six beats?
- What did they resolve, and what did they leave open?
- Which villains or threats survived, and in what state?
- Which secrets or clues did they find? Which did they miss?
- What did they learn about the Front or a faction?
- What did they change in the world that NPCs would react to?
- What did you invent at the table that was not in the prep (NPCs, locations, secrets, monsters)?

Write that last answer into the recap's "inventions made at the table" field. It is the named
home for Phase 7's running list of inventions, and Step 2 reads it to decide what becomes canon.

Gate: the recap exists before you touch any world artifact.

## Step 2: Write inventions into canon (the write-back)

A session invents things, both while prepping and at the table, that must not be lost in the
session note. This is the step most loops miss. Read both sources of inventions:

- The recap's "inventions made at the table" field (what you improvised during play).
- The session plan's "Prep inventions" list (the NPCs, locations, secrets, and monsters you
  invented while prepping, flagged there by session-prep).

Walk every entry in both lists and resolve each one. Nothing stays only in the session note:

- An NPC you named, who the party engaged with, becomes a canon NPC (name, want, lever, location)
  in the NPC folder.
- A location the party will return to becomes a canon location.
- A fact you treated as true becomes a secret or a line of canon.
- A monster or statblock that may recur goes to the bestiary via `custom-monsters`.

Prep inventions the party never reached are not discarded. Park each one as a hook or an iceberg
seed in hooks and seeds, so it is still available even though it went unengaged. Pure color the
party walked past that will never matter can be dropped, but drop it on purpose rather than
leaving it stranded.

Rule: every invention, prep-time or table-time, ends this step as canon, a parked hook, or a
deliberate drop. None survives only in the session note.

## Step 3: Advance the clocks

Clocks are the living world between sessions. A clock is a circle of 4, 6, or 8 segments (or 12
for a slow, long arc; see Clock sizes below) that fills as an off-screen goal advances.

Go faction by faction and tick each clock by 0, 1, or 2 segments, based on what that faction
plausibly achieved given the players' action or inaction. Note why for each. A faction the
players left untouched may still advance if the fiction says its plan moved on its own, or hold
at zero when nothing changed its situation. Do not tick a clock just because a session happened.

- Advance a Front portent here, not mid-scene.
- A filled clock is a consequence: the faction achieves its goal. That is a new hook, a changed
  region, or a campaign turn. Record it.

### Clock sizes (the canonical definition, referenced elsewhere)

Use 4 segments for a fast scheme, 6 or 8 for a slow burn, and 12 only for a slow, long campaign
arc. worldbuilding-initial-conditions and the story-model reference point here; this is the one
place clock sizes are defined.

## Step 4: Roll secrets forward

Move unfound but still-relevant secrets to the next session's list, so they are not lost. Retire
secrets the session made irrelevant. Park far-future ones in hooks and seeds. (This carry-forward
is what lets a one-shot become a campaign without re-prep.)

## Step 5: Convert loose ends to hooks

For every surviving villain, dangling clue, unresolved faction move, and promise the party made,
write one hook. The three most useful to carry forward are a surviving or escalating antagonist,
a clue pointing at an unbuilt location, and the leftover secrets. Those plus the Front are the
campaign.

## Step 6: Re-stat recurring villains

If a villain survived and the party has grown, note that the villain must be re-statted to stay a
threat next time. Hand this to `custom-monsters` (the recurring-villain re-stat). Do not re-stat
now unless you are prepping that fight.

## Step 7: Grow the Front

Given the recap, update the Front: did the players slow it, speed it, or redirect it? Add or
revise a portent. If a Front is fully resolved, retire it and promote a hook into a new one, up
to three active Fronts.

## Outputs (artifacts handed forward)

In Obsidian (the default binding), a promoted NPC or a re-statted villain is written as a
bestiary-indexed statblock (`statblock: inline`), per
`../dungeon-master-loop/references/obsidian-ttrpg-formats.md`, so it stays live in the trackers.

Updated setting canon, ticked faction clocks, a rolled-forward secrets list, new hooks and
seeds, a re-stat flag on recurring villains, and an updated Front. session-prep reads all of
these for the next session. The loop closes.

## Common mistakes

- Acting on the session before capturing the recap, then misremembering a week later.
- Leaving a prep-time or improvised invention in the session note, so canon and play diverge.
- Ticking every clock every session out of habit, instead of from what the players did.
- Re-statting a surviving villain immediately, before you know you are prepping that fight.
