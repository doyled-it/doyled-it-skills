# Obsidian TTRPG formats (the default binding)

The artifact contract is tool-agnostic, but Obsidian with its D&D plugin set is the documented
default binding. This file gives the exact, verified syntax each artifact uses so a note the
suite produces is live in the plugins (a creature is in the bestiary, an encounter runs in a
tracker, a map renders, a query lists sessions). Formats were verified against the plugins'
official docs on 2026-11-17; sources are listed at the end. The abstract contract in
`../SKILL.md` still stands for any other tool.

## The one rule that makes creatures work: bestiary indexing

A note renders a statblock in reading view whether or not it is in the bestiary. But Initiative
Tracker, Encounter Builder, and Quick Initiative find a creature BY NAME only if it is registered
in the Fantasy Statblocks bestiary. Registration needs a frontmatter flag plus a setting:

- Add `statblock: inline` and a `name:` to the note's YAML frontmatter. This registers the first
  fenced `statblock` block in the bestiary. This is the method the Fantasy Statblocks docs
  recommend.
- Turn on "Parse Frontmatter for Creatures" (the `autoParse` setting), and make sure the note is
  inside a configured Bestiary folder (the default path is the whole vault). The example vault
  binding ships a Fantasy Statblocks `data.json` with `autoParse: true`.

A statblock block with no `statblock: inline` flag renders but is invisible to the trackers. That
is the single most common integration bug. The alternative flag `statblock: true` puts the whole
creature in frontmatter and needs its own `name:` key; it is more conflict-prone, so prefer
`inline`.

## Monster (custom-monsters output): a bestiary-indexed statblock

````markdown
---
statblock: inline
name: Goblin Boss
---

```statblock
layout: Basic 5e 2025 Layout
name: Goblin Boss
size: Small
type: humanoid
subtype: goblinoid
alignment: neutral evil
ac: 17
hp: 21
hit_dice: 6d6
speed: "30 ft."
stats: [10, 14, 10, 10, 8, 10]
saves:
  - dexterity: 4
skillsaves:
  - stealth: 6
senses: "darkvision 60 ft., passive Perception 9"
languages: "Common, Goblin"
cr: 1
modifier: 2
traits:
  - name: Nimble Escape
    desc: "The goblin can take the Disengage or Hide action as a bonus action."
actions:
  - name: Scimitar
    desc: "Melee Weapon Attack: +4 to hit, reach 5 ft., one target. Hit: 5 (1d6 + 2) slashing."
```
````

- `stats` is `[STR, DEX, CON, INT, WIS, CHA]`. `saves` and `skillsaves` are lists of single-key
  maps. Other list fields: `bonus_actions`, `reactions`, `legendary_actions` (name/desc pairs),
  `spells` (plain strings), and the damage/condition fields as strings.
- `modifier` is the initiative modifier Initiative Tracker reads. With no `modifier` it falls
  back to the DEX modifier from `stats[1]`.
- `layout:` must match a layout installed in Fantasy Statblocks exactly. The example binding
  imports the community 2024 layout, whose name is `Basic 5e 2025 Layout`.

## Combat-capable NPC (worldbuilding and advancing-the-world output)

A villain or recurring NPC that can also fight is one note that is both an NPC and a statblock:
keep the roleplay frontmatter and add the bestiary flag. The `type: npc` tag drives your NPC
Dataview queries; `statblock: inline` puts the same note in the bestiary.

````markdown
---
type: npc
statblock: inline
name: Varro the Chain
status: alive
location: Harbor ward
faction: The Dredge
---

> One or two read-aloud lines: looks, voice, first impression.

- Wants:
- Secret or leverage:

```statblock
layout: Basic 5e 2025 Layout
name: Varro the Chain
size: Medium
type: humanoid
ac: 15
hp: 58
hit_dice: 9d8+18
speed: "30 ft."
stats: [16, 14, 15, 11, 12, 14]
cr: 4
modifier: 2
actions:
  - name: Spiked Chain
    desc: "Melee Weapon Attack: +5 to hit, reach 10 ft. Hit: 8 (1d10 + 3) piercing."
```
````

## PC as an Initiative Tracker party member (party-composition output)

Initiative Tracker reads players two ways: entries added in its settings, or a player note it
syncs from. For the note form, the tracker reads these frontmatter keys (all optional):

```markdown
---
type: pc
hp: 23
ac: 17
modifier: 2
level: 2
---
```

`modifier` is the initiative modifier. Group players into a party in the tracker's settings; a
`party:` line in an encounter block then pulls that whole party in. Record per-character levels
(never an average) so the encounter budget sums correctly.

## Encounter (encounter-design and improvised-combat output)

Initiative Tracker encounter block. Creature names resolve against the bestiary, so the monsters
above drop in by name:

````markdown
```encounter
name: Ambush at the Culvert
rollHP: true
players: true
creatures:
  - 3: Goblin
  - Goblin Boss
  - 2: Goblin, 7, 15, 2
```
````

- A creature entry is `name` or `[name, hp, ac, initiative modifier, xp]`. `X: name` adds X
  copies. `players: true` pulls the whole party; `party: <name>` picks one party. Trailing flags
  `, ally` `, friendly` `, hidden`.
- Keep the prepped objective, terrain, and tactics (from encounter-design) as prose headings
  beside the block. The block runs the fight; the headings tell you how to run it.

### Build-and-run handoff (optional plugins)

Encounter Builder balances a fight to the 2024 budget in an `encounter-builder` block, then its
Start fight button writes an `initiative` block for Quick Initiative:

````markdown
```encounter-builder
party 4x level 3
3x Goblin
Goblin Boss cr 1
```
````

Encounter Builder reads a linked creature's `cr` from frontmatter, so bestiary-only creatures
need `cr` on the line. Quick Initiative reads hp, ac, and the initiative modifier from the same
Fantasy Statblocks notes.

## Dice and random tables (session-prep and session-zero output)

Randomness (which absorbed Dice Roller, so the `dice:` syntax still works):

```markdown
The trap deals `dice: 2d6+3` damage. Advantage: `dice: 2d20kh`.
```

A roll table is a Markdown table with an anchor, rolled with `rdm:`:

```markdown
| Tavern |
| ------ |
| The Prancing Pony |
| The Drunken Goblin |

^taverns

Tonight you drink at `rdm:[@taverns]`.
```

Locking a result writes it into the note: `` `rdm:[@taverns]` `` becomes `` `rdm:[@taverns]Result` `` once rolled.

## Maps (worldbuilding and session-prep output)

Leaflet renders an image as a pannable map with note-linked pins:

````markdown
```leaflet
id: region-map
image: [[region.jpg]]
height: 500px
lat: 50
long: 50
minZoom: 1
maxZoom: 10
defaultZoom: 5
marker: default, 42, -71, [[Home Settlement]]
```
````

`marker:` is `type, lat, long, link` (lat and long are percentages from the top-left on an image
map; `link` is a wikilink). For a built battle map with fog of war, Windrose MapDesigner inserts
a `windrose-map` block (keys `id`, `name`, `type: grid` or `hex`) via its "Insert map" command.

## Dataview queries (the dashboards the loop relies on)

A session log and an open-quest list, as used on a vault home note:

````markdown
```dataview
TABLE WITHOUT ID file.link AS Session, date AS Date, status AS Status
FROM "sessions"
WHERE type = "session"
SORT date DESC
```
````

````markdown
```dataview
TABLE WITHOUT ID file.link AS NPC, location AS Where, faction AS Faction
WHERE type = "npc"
SORT file.name ASC
```
````

Headers with spaces need double quotes. Inline fields are written `field:: value`.

## Player-facing output (session-zero handout)

To mark a note (or part of one) as safe to show players with the Player Facing Notes plugin, add
`pfn` to the note's frontmatter (a checkbox set true), or wrap a region in `::pf` and `::/pf`
lines. "Sync all player copies" then writes filtered copies to a `_player/` folder.

## Sources

- Fantasy Statblocks (bestiary indexing, fields, layouts): https://github.com/javalent/Javalents-Plugins (Fantasy Statblocks/The Bestiary.md, Codeblock Creatures.md, Plugin Settings.md, Integrated Layouts/Basic 5e Layout.md)
- 2024 layout: https://github.com/matthttam/fantasy-statblocks-layout-2025
- Initiative Tracker (encounter block, players): https://github.com/javalent/Javalents-Plugins (Initiative Tracker/Encounter Parameters.md, Creatures and Encounters.md, Settings.md)
- Encounter Builder and Quick Initiative: https://github.com/walkertbrown/encounter-builder , https://github.com/walkertbrown/quick-initiative
- Randomness: https://community.obsidian.md/plugins/randomness
- Leaflet: https://github.com/javalent/obsidian-leaflet
- Windrose MapDesigner: https://community.obsidian.md/plugins/windrose-md
- Dataview: https://blacksmithgu.github.io/obsidian-dataview/queries/query-types/
- Player Facing Notes: https://github.com/Obsidian-TTRPG-Community/player-facing-notes
