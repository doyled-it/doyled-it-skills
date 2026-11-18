# Example vault binding: the artifact contract in an Obsidian vault

The dungeon-master-loop artifact contract is abstract on purpose, so the method works at any
table or in any tool. This file is a worked example of binding it to an Obsidian vault: it maps
each artifact 1:1 to a folder or note in a typical D&D vault layout. It names no specific owner or
repository. Swap this one file to bind the method to your own vault or tool. Nothing else in the
suite names a vault path.

The example layout splits player-safe canon (`world-building/`) from GM-only material
(`gm-only/`), keeps per-note templates in `_templates/`, and keeps play-facing notes flat at the
top level (`sessions/`, `npcs/`, `pcs/`, `bestiary/`, `encounters/`, `maps/`). Prefer existing
templates over inventing new structure.

## Player-safe versus GM-only

The golden rule: anything that would spoil a surprise lives in `gm-only/`, never in
`world-building/`. The Front's portents and villain plan, the secrets and clues tracker, and the
faction clocks (which encode what happens off screen if nobody intervenes) are all GM-only. The
public face of a region, settlement, faction, or god is player-safe canon.

| Artifact | Vault location | Notes |
| --- | --- | --- |
| Setting canon (player-safe) | `world-building/` (`regions/`, `settlements/`, `factions/`, `pantheon/`, `lore/`) | The public face only. Templates: `_templates/location.md`, `_templates/faction.md`. |
| The Front (portents, villain plan) | `gm-only/fronts/` (one note per Front) | GM-only: it is the central surprise. Never in `world-building/`. |
| Faction clocks | `gm-only/faction-clocks.md` | GM-only tracker. Each clock's goal is what the faction achieves off screen. One clock per faction. |
| Secrets and clues | `gm-only/secrets-and-clues.md` | GM-only tracker, with a rolled-forward section. |
| Hooks and seeds (iceberg) | `gm-only/hooks-and-seeds/` | Named-but-unbuilt people, places, and threads. GM-only until surfaced in play. |
| Table safety (lines, veils, tone) | `world-building/session-zero/` (or a pinned safety note) | Produced at session zero. A hard constraint that every prep and combat skill reads. |
| Party roster | `pcs/` (one note per PC, `_templates/pc.md`) plus a party summary note | party-composition writes the derived drivers (per-character levels, roles, gaps, spotlight) into the summary note. |
| Canon NPCs | `npcs/` (one note per NPC, `_templates/npc.md`) | Promoted here from prep or play by advancing-the-world. Name, want, lever, location. |
| Session plan | `sessions/<date> Session NN - Title.md` (`_templates/session.md`) | Holds the scenes, secrets in play, rewards, and a "Prep inventions" list (see below). |
| Encounter | `encounters/` | Uses the Initiative Tracker `encounter` code block; creatures resolve against `bestiary/`. |
| Bestiary statblock | `bestiary/` (`_templates/statblock.md`) | custom-monsters writes here; encounters reference by name. |
| Mini and terrain inventory | `gm-only/mini-inventory.md` | One row per owned or printable mini and terrain piece. printable-minis-and-terrain defines the columns. |
| Print manifest | `gm-only/print-queue.md` | A dated queue of what to print before upcoming sessions. |
| Session recap | the session note's `## Recap` section (the template titles it `## Recap (fill after the session)`, so match on the `## Recap` prefix) and its `## Faction clocks to tick` section, including an "inventions made at the table" list under Recap | advancing-the-world fills these as its first step. Add the inventions list if the template lacks it. |

## The "Prep inventions" field (prep-time write-back)

When session-prep invents an NPC, location, secret, or monster, it records it in a "Prep
inventions" list in the session plan note. advancing-the-world Step 2 reads both that list and the
recap's "inventions made at the table" field, and promotes or parks each entry. The "Prep
inventions" list is how a prep-time invention reaches that step instead of dying in the session
note.

## Conventions the example vault expects

- Link by note title with Obsidian wikilinks, for example `[[faction-clocks]]`.
- Put queryable facts in frontmatter (`type`, `status`, `date`, `pcs`, `giver`) so Dataview and
  Bases can index them.
- Keep player-safe notes out of `gm-only/`, and keep surprises out of `world-building/`.
- If the vault runs the Initiative Tracker and Encounter Builder plugins, encounters use their
  block format so a prepped encounter becomes a live tracker at the table.

## Notes to add if your vault lacks them

Create `gm-only/mini-inventory.md` (one row per owned or printable piece) and
`gm-only/print-queue.md` (a dated manifest with a "needs print by" date per item) the first time
you run printable-minis-and-terrain. Both are GM-only prep logistics.
