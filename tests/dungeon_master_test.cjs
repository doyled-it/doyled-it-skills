const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');
const read = (f) => fs.readFileSync(path.join(root, f), 'utf8');
const pluginDir = 'plugins/dungeon-master-loop';

const SKILLS = [
  'dungeon-master-loop',
  'worldbuilding-initial-conditions',
  'advancing-the-world',
  'session-zero',
  'party-composition',
  'session-prep',
  'encounter-design',
  'improvised-combat',
  'custom-monsters',
  'printable-minis-and-terrain',
];
const SUBSKILLS = SKILLS.filter((s) => s !== 'dungeon-master-loop');

function walkFiles(dir) {
  const out = [];
  for (const ent of fs.readdirSync(path.join(root, dir), { withFileTypes: true })) {
    const rel = path.join(dir, ent.name);
    if (ent.isDirectory()) out.push(...walkFiles(rel));
    else out.push(rel);
  }
  return out;
}

const plugin = () => JSON.parse(read(`${pluginDir}/.claude-plugin/plugin.json`));
const marketplace = () => JSON.parse(read('.claude-plugin/marketplace.json'));
const frontmatter = (text) => (text.match(/^---\n([\s\S]*?)\n---/u) || [])[1] || '';

test('marketplace entry and plugin metadata are consistent', () => {
  const entry = marketplace().plugins.find((p) => p.name === 'dungeon-master-loop');
  assert.ok(entry, 'dungeon-master-loop missing from marketplace.json');
  assert.equal(entry.source, './plugins/dungeon-master-loop');
  const p = plugin();
  assert.equal(p.name, 'dungeon-master-loop');
  // Version is valid semver, not a hardcoded literal; pair with the marketplace entry only if it carries one.
  assert.match(p.version, /^\d+\.\d+\.\d+$/u, 'plugin version must be semver');
  if (entry.version !== undefined) assert.equal(p.version, entry.version);
  // Plugins defer to the repo LICENSE (Commons Clause plus AGPL-3.0) rather than naming an SPDX id.
  assert.equal(p.license, 'SEE LICENSE IN LICENSE');
  // Description consistent across the two manifests (AGENTS.md requirement).
  assert.equal(p.description, entry.description);
  assert.match(p.description, /Start with the dungeon-master-loop skill\./u);
});

test('every skill exists with its frontmatter name matching the directory and a trigger description', () => {
  for (const name of SKILLS) {
    const fm = frontmatter(read(`${pluginDir}/skills/${name}/SKILL.md`));
    const nameLine = (fm.match(/name:\s*(.+)/u) || [])[1]?.trim();
    assert.equal(nameLine, name, `frontmatter name mismatch for ${name}`);
    assert.match(fm, /description:\s*Use when/u, `${name} description must start with "Use when"`);
    assert.doesNotMatch(fm, /\b(I can|I will|you can use this)\b/iu, `${name} description must be third person`);
  }
});

test('the orchestrator composes every sub-skill by name and stays an overview', () => {
  const text = read(`${pluginDir}/skills/dungeon-master-loop/SKILL.md`);
  for (const name of SUBSKILLS) {
    assert.ok(text.includes(name), `orchestrator missing sub-skill ${name}`);
  }
  assert.ok(text.split('\n').length < 500, 'orchestrator SKILL.md should stay under 500 lines');
});

test('the orchestrator defines the bidirectional artifact contract and the vault binding exists', () => {
  const text = read(`${pluginDir}/skills/dungeon-master-loop/SKILL.md`);
  assert.match(text, /artifact contract/iu);
  assert.match(text, /world to session/iu);
  assert.match(text, /session to world/iu);
  assert.match(text, /write-back/iu);
  assert.ok(
    fs.existsSync(path.join(root, `${pluginDir}/skills/dungeon-master-loop/references/vault-binding.md`)),
    'vault-binding reference should exist'
  );
});

test('the required review fixes are covered in the skills', () => {
  const advancing = read(`${pluginDir}/skills/advancing-the-world/SKILL.md`);
  assert.match(advancing, /recap capture/iu);
  const prep = read(`${pluginDir}/skills/session-prep/SKILL.md`);
  assert.match(prep, /non-combat/iu);
  assert.match(prep, /write-back/iu);
  const printing = read(`${pluginDir}/skills/printable-minis-and-terrain/SKILL.md`);
  assert.match(printing, /lookahead/iu);
  assert.match(printing, /inventory/iu);
  assert.match(printing, /Bambu Lab X2D/u);
  const math = read(`${pluginDir}/skills/encounter-design/references/encounter-math-2024.md`);
  assert.match(math, /per character/iu);
  assert.match(math, /removed|dropped/iu);
  const monster = read(`${pluginDir}/skills/custom-monsters/references/monster-building-2024.md`);
  assert.match(monster, /no monster-creation framework/iu);
});

test('the code-review fixes are present', () => {
  const orch = read(`${pluginDir}/skills/dungeon-master-loop/SKILL.md`);
  assert.match(orch, /Table safety \(lines, veils, tone\)/u);
  assert.match(orch, /every faction has a clock/iu);
  const advancing = read(`${pluginDir}/skills/advancing-the-world/SKILL.md`);
  assert.match(advancing, /Prep inventions/u);
  assert.match(advancing, /inventions made at the table/iu);
  assert.match(advancing, /0, 1, or 2/u);
  assert.match(advancing, /Clock sizes \(the canonical definition/u);
  assert.match(advancing, /Ticking a clock down \(the canonical definition/u);
  assert.match(advancing, /Blades in the Dark/u);
  assert.match(advancing, /setback is 1 by default/iu);
  assert.match(advancing, /exactly one clock/iu);
  assert.match(advancing, /net change once/iu);
  assert.match(advancing, /cannot be ticked down/iu);
  assert.match(advancing, /printable-minis-and-terrain/u);
  assert.match(advancing, /roll20\.net\/compendium\/BITD/u);
  const challenges = read(`${pluginDir}/skills/session-prep/references/non-combat-challenges.md`);
  assert.match(challenges, /advancing-the-world/u);
  assert.match(challenges, /Ticking a clock down/u);
  const math = read(`${pluginDir}/skills/encounter-design/references/encounter-math-2024.md`);
  assert.match(math, /sum of each character's own per-level budget/u);
  assert.match(math, /375 \+ 375 \+ 750 \+ 750/u);
  const binding = read(`${pluginDir}/skills/dungeon-master-loop/references/vault-binding.md`);
  assert.match(binding, /gm-only\/fronts\//u);
  assert.match(binding, /gm-only\/secrets-and-clues\.md/u);
  assert.match(binding, /Canon NPCs/u);
});

test('no owner or private-repo identifiers leak into the public plugin', () => {
  const banned = [/michael/iu, /mdoyle/iu, /the-dungeon-games/u];
  for (const file of walkFiles(pluginDir)) {
    if (/\.(md|json)$/u.test(file)) {
      const text = read(file);
      for (const re of banned) assert.doesNotMatch(text, re, `personal detail matching ${re} in ${file}`);
    }
  }
});

test('README documents the plugin and the project-scoped install', () => {
  const text = read('README.md');
  assert.match(text, /### dungeon-master-loop/u);
  assert.match(text, /dungeon-master-loop@doyled-it-skills --scope project/u);
});

test('the Obsidian formats reference exists and every consuming skill links it', () => {
  const ref = `${pluginDir}/skills/dungeon-master-loop/references/obsidian-ttrpg-formats.md`;
  assert.ok(fs.existsSync(path.join(root, ref)), 'obsidian-ttrpg-formats.md should exist');
  const refText = read(ref);
  assert.match(refText, /statblock: inline/u);
  assert.match(refText, /```encounter/u);
  const consumers = [
    'custom-monsters', 'encounter-design', 'improvised-combat',
    'worldbuilding-initial-conditions', 'advancing-the-world', 'party-composition',
    'session-prep', 'session-zero',
  ];
  for (const sk of consumers) {
    const text = read(`${pluginDir}/skills/${sk}/SKILL.md`);
    assert.match(text, /obsidian-ttrpg-formats\.md/u, `${sk} must link the Obsidian formats reference`);
  }
});

test('no em dashes anywhere in the plugin', () => {
  const emDash = String.fromCharCode(0x2014);
  for (const file of walkFiles(pluginDir)) {
    if (/\.(md|json)$/u.test(file)) {
      assert.ok(!read(file).includes(emDash), `em dash in ${file}`);
    }
  }
});
