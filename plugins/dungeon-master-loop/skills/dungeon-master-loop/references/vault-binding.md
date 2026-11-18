# Vault binding: artifact contract mapped to the-dungeon-games

The dungeon-master-loop artifact contract is abstract on purpose, so the method works at any
table or in any tool. This file is the thin binding that maps each artifact 1:1 to a folder or
note in Michael's the-dungeon-games Obsidian vault (private repo doyled-it/the-dungeon-games).
Swap this one file to bind the method to a different vault. Nothing else in the suite names a
vault path.

The vault already ships templates in `_templates/` and research notes in `world-building/` and
`resources/`. Prefer those over inventing new structure.

| Artifact | Vault location | Notes |
| --- | --- | --- |
| Setting canon | `world-building/` (`regions/`, `settlements/`, `factions/`, `pantheon/`, `lore/`) | Templates: `_templates/location.md`, `_templates/faction.md`. |
| The Front (central pressure) | `world-building/` front note, plus the "one big pressure" line in `world-building/world-building-framework.md` | One note per Front. See worldbuilding-initial-conditions. |
| Faction clocks | `world-building/faction-clocks.md` | Existing tracker. One clock per faction. |
| Secrets and clues | `world-building/secrets-and-clues.md` | Existing tracker, with a rolled-forward section. |
| Hooks and seeds (iceberg) | `world-building/hooks-and-seeds/` | Park named-but-unbuilt people, places, threads here. |
| Party roster | `pcs/` (one note per PC, `_templates/pc.md`) plus a party summary note | party-composition writes the derived drivers into the summary note. |
| Session plan | `sessions/<date> Session NN - Title.md` (`_templates/session.md`) | Has Strong start, Potential scenes, Secrets in play, NPCs/monsters/locations, Rewards, Recap, Faction clocks to tick. |
| Encounter | `encounters/` | Uses the Initiative Tracker `encounter` code block; creatures resolve against `bestiary/`. |
| Bestiary statblock | `bestiary/` (`_templates/statblock.md`) | custom-monsters writes here; encounters reference by name. |
| Mini and terrain inventory | suggested new note `gm-only/mini-inventory.md` | Not yet in the vault. printable-minis-and-terrain defines the columns. |
| Print manifest | suggested new note `gm-only/print-queue.md` | Not yet in the vault. A dated queue of what to print before upcoming sessions. |
| Session recap | the `## Recap` and `## Faction clocks to tick` sections of the session note | advancing-the-world fills these as its first step. |

## Conventions the vault expects

- Link by note title with Obsidian wikilinks, for example `[[faction-clocks]]`.
- Put queryable facts in frontmatter (`type`, `status`, `date`, `pcs`, `giver`) so Dataview and
  Bases can index them. The Home dashboard queries `type: session` and `type: quest`.
- Keep player-safe notes out of `gm-only/`. Secrets, the Front's true nature, and villain plans
  live in `gm-only/` or in frontmatter the players do not read.
- The vault runs the Initiative Tracker and Encounter Builder plugins. Encounters use their
  block format so a prepped encounter becomes a live tracker at the table.

## Two notes to add

The inventory and print-queue artifacts have no home in the current vault. When you first run
printable-minis-and-terrain against the vault, create:

- `gm-only/mini-inventory.md`: one row per owned or printable mini and terrain piece.
- `gm-only/print-queue.md`: a dated print manifest with a "needs print by" date per item.

Both are gm-only because they are prep logistics, not player-facing canon.
