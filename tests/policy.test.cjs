const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const { execFileSync } = require('node:child_process');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const skillPaths = [
  'plugins/codegraph/skills/using-codegraph/SKILL.md',
  'plugins/development-loop/skills/development-loop/SKILL.md',
  'plugins/cross-repo-completeness/skills/cross-repo-completeness/SKILL.md',
];
const block = execFileSync('bash', [path.join(root,
  'plugins/development-loop/skills/development-loop/scripts/install.sh'), '--print-only'],
{ encoding: 'utf8' });

for (const file of [...skillPaths, 'README.md']) {
  test(`${file}: closes cold indexes while honoring user restrictions`, () => {
    const text = read(file);
    assert.match(text, /codegraph init \./u);
    assert.match(text, /codegraph sync \./u);
    assert.match(text, /explicit user\s+(?:no-index|indexing) restriction/iu);
    assert.doesNotMatch(text, /skip it when there is no|indexing is the repo owner's choice/iu);
  });
  test(`${file}: reports unsupported files honestly`, () => {
    const text = read(file);
    assert.match(text, /unsupported/iu);
    assert.match(text, /empty/iu);
    assert.match(text, /direct(?:ly)? (?:reads?|inspect)/iu);
  });
}

for (const [file, load] of [
  ...[...skillPaths, 'README.md', 'AGENTS.md'].map((f) => [f, () => read(f)]),
  ['install.sh managed block', () => block],
]) {
  test(`${file}: creating and syncing the index is mandatory, not a default`, () => {
    const text = load();
    assert.match(text, /\bsync(?:ing)?\b[^.]{0,40}\bmandatory\b|\bmandatory\b[^.]{0,40}\bsync\b/iu);
    assert.match(text, /without\s+asking/iu);
    assert.match(text, /after\s+(?:pulls|pulling)[^.]{0,40}(?:branch\s+switches|switching\s+branches)/iu);
    assert.match(text, /prohibition\s+on\s+all\s+writes/iu);
    assert.match(text, /user's\s+decision[^.]{0,20}(?:text\s+)?(?:is|are)\s+tool\s+guidance/iu);
    assert.doesNotMatch(text,
      /overrides? (?:this|the) default|(?:gaps|indexing)[^.]{0,60}by default|Default policy|for the current task/iu);
  });
  test(`${file}: source-read-only work still indexes; no-behavior edits need no index`, () => {
    const text = load();
    assert.match(text, /source-read-only\s+task\s+still\s+creates\s+and\s+syncs\s+the\s+index/iu);
    assert.doesNotMatch(text, /source-read-only[^.]{0,80}counts\s+as\s+a\s+no-index\s+restriction/iu);
    assert.match(text, /no\s+behavior\s+change\s+does\s+not\s+need\s+an\s+index/iu);
  });
}

test('cold-repo skill is discoverable before an index exists', () => {
  const description = read(skillPaths[0]).split('\n').find((line) => line.startsWith('description:'));
  assert.match(description, /missing|absent|unindexed/u);
});

test('managed block names skills and the complete execution chain', () => {
  for (const name of [
    'development-loop', 'using-codegraph', 'cross-repo-completeness',
    'superpowers:brainstorming', 'superpowers:writing-plans',
    'superpowers:test-driven-development', 'superpowers:subagent-driven-development',
    'superpowers:executing-plans', 'superpowers:requesting-code-review',
    'superpowers:verification-before-completion', 'superpowers:finishing-a-development-branch',
  ]) assert.ok(block.includes('`' + name + '`'), `missing exact skill ${name}`);
  assert.match(block, /codegraph init \./u);
  assert.match(block, /codegraph sync \./u);
  assert.match(block, /explicit user (?:no-index|indexing) restriction/iu);
  assert.match(block, /unsupported/iu);
});

test('development loop explicitly routes bug diagnosis, reviews and inline execution', () => {
  const text = read(skillPaths[1]);
  for (const name of [
    'using-codegraph', 'cross-repo-completeness', 'superpowers:systematic-debugging',
    'superpowers:executing-plans', 'superpowers:requesting-code-review',
    'superpowers:receiving-code-review', 'superpowers:verification-before-completion',
  ]) assert.ok(text.includes('`' + name + '`'), `missing ${name}`);
  assert.match(text, /(?:push|remote writes)[\s\S]{0,70}authoriz/iu);
});

test('changed plugins invalidate known installed caches', () => {
  for (const [name, version] of [
    ['codegraph', '1.2.2'], ['development-loop', '1.3.0'], ['cross-repo-completeness', '1.1.2'],
    ['roadmap', '1.0.0'],
  ]) assert.equal(JSON.parse(read(`plugins/${name}/.claude-plugin/plugin.json`)).version, version);
});

// --- printable-parts plugin ------------------------------------------------

const ppPlugin = () =>
  JSON.parse(read('plugins/printable-parts/.claude-plugin/plugin.json'));
const marketplace = () => JSON.parse(read('.claude-plugin/marketplace.json'));
const ppSkill = () => read('plugins/printable-parts/skills/printable-parts/SKILL.md');

function walkFiles(dir) {
  const out = [];
  for (const ent of fs.readdirSync(path.join(root, dir), { withFileTypes: true })) {
    const rel = path.join(dir, ent.name);
    if (ent.isDirectory()) out.push(...walkFiles(rel));
    else out.push(rel);
  }
  return out;
}

test('printable-parts: marketplace entry and plugin metadata are consistent', () => {
  const entry = marketplace().plugins.find((p) => p.name === 'printable-parts');
  assert.ok(entry, 'printable-parts missing from marketplace.json');
  assert.equal(entry.source, './plugins/printable-parts');
  const plugin = ppPlugin();
  assert.equal(plugin.name, 'printable-parts');
  assert.equal(plugin.version, '1.1.1');
  // Description consistent across the two manifests (AGENTS.md requirement).
  assert.equal(plugin.description, entry.description);
  assert.match(plugin.description, /text-to-cad/u);
  assert.match(plugin.description, /Start with the printable-parts skill\./u);
});

test('printable-parts: SKILL.md description says what it does and when to use it', () => {
  const text = ppSkill();
  const fm = text.split('---')[1] || '';
  const desc = (fm.match(/description:\s*([\s\S]*?)\nlicense:/u) || [])[1] || '';
  // Anthropic's guidance (owner's tie-breaker): what it does AND when to use.
  assert.match(desc, /\bUse when\b/u);
  assert.match(desc, /text-to-cad/u);
  // Trigger nouns the soft layer competes for.
  for (const noun of ['mount', 'bracket', 'clip', 'perch', 'enclosure']) {
    assert.ok(desc.includes(noun), `description missing trigger noun ${noun}`);
  }
  // Third person: no first/second person openers.
  assert.doesNotMatch(desc, /\b(I can|I will|you can use this)\b/iu);
});

test('printable-parts: SKILL.md composes text-to-cad by name and stays an overview', () => {
  const text = ppSkill();
  assert.match(text, /REQUIRED SUB-SKILL:\*\*\s*`?cad`?/u);
  assert.match(text, /`?print3d`?/u);
  assert.match(text, /never\s+(?:vendors?|edits?)\s+it|never vendors or edits it/iu);
  // Under 500 lines (Anthropic's budget).
  assert.ok(text.split('\n').length < 500, 'SKILL.md body should stay under 500 lines');
});

test('printable-parts: the enforcement reference documents the per-runtime limit', () => {
  const text = read(
    'plugins/printable-parts/skills/printable-parts/references/enforcement.md'
  );
  assert.match(text, /PreToolUse/u);
  assert.match(text, /fail(?:s)?\s+open/iu);
  // The hook is Claude Code only; other runtimes get the soft + repo layers.
  assert.match(text, /Claude Code only|Claude Code\b[^.]*hook/iu);
  assert.match(text, /Codex/u);
});

test('printable-parts: SKILL.md carries the prior-art and reference-hardware steps', () => {
  const text = ppSkill();
  // The two addendum steps appear in the checklist.
  assert.match(text, /0\.\s*Prior art searched/u);
  assert.match(text, /1\.5\s*Reference model/u);
  // And link one level deep to their own references.
  assert.match(text, /references\/prior-art\.md/u);
  assert.match(text, /references\/reference-hardware\.md/u);
  for (const ref of ['prior-art.md', 'reference-hardware.md']) {
    const body = read(
      `plugins/printable-parts/skills/printable-parts/references/${ref}`
    );
    assert.ok(body.length > 0, `${ref} should exist and be non-empty`);
  }
  // The intent schema documents the two records the gate enforces.
  const intentRef = read(
    'plugins/printable-parts/skills/printable-parts/references/intent-list.md'
  );
  assert.match(intentRef, /prior_art/u);
  assert.match(intentRef, /reference_tier/u);
});

test('printable-parts: hook manifest gates the Bash tool before it runs', () => {
  const hooks = JSON.parse(
    read('plugins/printable-parts/hooks/hooks.json')
  );
  const pre = hooks.hooks.PreToolUse;
  assert.ok(Array.isArray(pre) && pre.length >= 1);
  assert.equal(pre[0].matcher, 'Bash');
  assert.match(pre[0].hooks[0].command, /guard-printable-mesh\.js/u);
});

test('printable-parts: README documents the plugin, the install, and the hook limit', () => {
  const text = read('README.md');
  assert.match(text, /### printable-parts/u);
  assert.match(text, /\/plugin install printable-parts@doyled-it-skills/u);
  assert.match(text, /hook is Claude Code only/iu);
});

test('printable-parts: no em dashes in the plugin or its tests', () => {
  const files = [
    ...walkFiles('plugins/printable-parts'),
    ...walkFiles('tests/printable-parts'),
  ];
  for (const file of files) {
    if (/\.(md|json|js|py|sh|cjs)$/u.test(file)) {
      assert.ok(!read(file).includes('—'), `em dash in ${file}`);
    }
  }
});

// --- roadmap plugin ----------------------------------------------------------

const rmSkill = () => read('plugins/roadmap/skills/roadmap/SKILL.md');

test('roadmap: marketplace entry and plugin metadata are consistent', () => {
  const entry = marketplace().plugins.find((p) => p.name === 'roadmap');
  assert.ok(entry, 'roadmap missing from marketplace.json');
  assert.equal(entry.source, './plugins/roadmap');
  const plugin = JSON.parse(read('plugins/roadmap/.claude-plugin/plugin.json'));
  assert.equal(plugin.name, 'roadmap');
  assert.equal(plugin.description, entry.description);
  assert.match(plugin.description, /Start with the roadmap skill\./u);
});

test('roadmap: SKILL.md says when to use it and carries the agreed glossary', () => {
  const text = rmSkill();
  const desc = (text.match(/^description:\s*(.*)$/mu) || [])[1] || '';
  assert.match(desc, /^Use when/u);
  for (const word of ['Roadmap', 'Epic', 'Issue', 'Depends on', 'Gate', 'Merge request', 'Status', 'Iteration']) {
    assert.ok(text.includes(`| ${word} |`), `glossary missing ${word}`);
  }
  for (const status of ['To do', 'In progress', 'In review', 'Blocked', 'Done']) {
    assert.ok(text.includes(status), `missing status ${status}`);
  }
  assert.match(text, /Never say "milestone"/u);
  assert.match(text, /No worker starts before this/u);
  assert.match(text, /`superpowers:brainstorming`/u);
  assert.match(text, /`development-loop`/u);
  assert.ok(text.split('\n').length < 500, 'SKILL.md should stay under 500 lines');
});

test('roadmap: lifecycle covers kickoff, each issue, done, new work and handoff', () => {
  const text = rmSkill();
  for (const heading of ['Program kickoff', 'Each issue', 'Issue done', 'New work', 'Handoff']) {
    assert.match(text, new RegExp(`### \\d\\. ${heading}`, 'u'));
  }
  assert.match(text, /short name and\s+link/u);
});

test('roadmap: references are linked one level deep and exist', () => {
  const text = rmSkill();
  for (const ref of ['glossary.md', 'forges.md', 'commands.md', 'evals.md', 'roadmap.schema.json',
    'example-roadmap.json']) {
    assert.ok(text.includes(`references/${ref}`), `SKILL.md does not link ${ref}`);
    assert.ok(read(`plugins/roadmap/skills/roadmap/references/${ref}`).length > 0);
  }
  const forges = read('plugins/roadmap/skills/roadmap/references/forges.md');
  assert.match(forges, /Forgejo/u);
  assert.match(forges, /no endpoint to add an issue to a project/u);
});

test('roadmap: the skill is generic, with no project specifics', () => {
  for (const file of walkFiles('plugins/roadmap')) {
    if (/__pycache__/u.test(file)) continue;
    assert.doesNotMatch(read(file), /\b(?:ep2p|irmbpmn|mdoyle|CDP|gemma)\b/u, `project specific text in ${file}`);
  }
});

test('roadmap: SKILL.md says where the command lives and the docs match the code', () => {
  const text = rmSkill();
  assert.match(text, /in this skill's\s+own directory/u);
  assert.match(text, /-path '\*roadmap\/scripts\/roadmap\.py'/u);
  const desc = (text.match(/^description:\s*(.*)$/mu) || [])[1] || '';
  assert.doesNotMatch(desc, /\. (?:Keeps|Renders|Publishes)\b/u, 'description should name triggers only');
  for (const file of ['SKILL.md', 'references/glossary.md']) {
    assert.doesNotMatch(read(`plugins/roadmap/skills/roadmap/${file}`), /\| Iteration \|[^\n]*sprint/iu,
      `Iteration defined with "sprint" in ${file}`);
  }
  assert.match(read('plugins/roadmap/skills/roadmap/references/forges.md'), /from `--forge` when given, then `forge\.kind`/u);
  assert.ok(!walkFiles('plugins/roadmap').some((f) => /global-instructions/u.test(f)),
    'the personal global-instructions draft does not belong in the public plugin');
});

test('roadmap: orchestrators sync at every update, and the enforcement layers are documented', () => {
  const text = rmSkill();
  assert.match(text, /[Oo]rchestrators run `sync` at every update/u);
  assert.ok(text.includes('references/enforcement.md'), 'SKILL.md does not link enforcement.md');
  const enforcement = read('plugins/roadmap/skills/roadmap/references/enforcement.md');
  for (const word of ['check-mr', 'drift-issue', 'PostToolUse', 'Stop', 'codex-notify', 'Install nothing']) {
    assert.ok(enforcement.includes(word), `enforcement.md does not cover ${word}`);
  }
  assert.match(read(skillPaths[1]), /## 6\. Issue done[\s\S]{0,400}run `roadmap\.py sync`/u);
  assert.match(block, /run `roadmap`\s+sync at every update/u);
  const plugin = JSON.parse(read('plugins/roadmap/.claude-plugin/plugin.json'));
  assert.match(plugin.description, /closes only its own drift issue/u);
});

test('roadmap: no em dashes in the plugin or its tests', () => {
  for (const file of [...walkFiles('plugins/roadmap'), ...walkFiles('tests/roadmap')]) {
    if (/\.(md|json|py|sh)$/u.test(file)) assert.ok(!read(file).includes('—'), `em dash in ${file}`);
  }
});

test('development loop checks the roadmap first and finishes issues on it', () => {
  const text = read(skillPaths[1]);
  assert.match(text, /## 0\. Program check[\s\S]{0,400}`roadmap`[\s\S]{0,300}agreed[\s\S]{0,120}before any worker starts/u);
  assert.match(text, /## 6\. Issue done[\s\S]{0,300}re-render/u);
  assert.match(block, /`roadmap`[\s\S]{0,120}agreed before any worker starts/u);
  assert.ok(read('README.md').includes('### roadmap'));
  assert.ok(read('README.md').includes('/plugin install roadmap@doyled-it-skills'));
});

test('canonical instructions and generated state conventions exist', () => {
  assert.equal(read('CLAUDE.md').trim(), '@AGENTS.md');
  for (const name of ['development-loop', 'using-codegraph', 'cross-repo-completeness']) {
    assert.ok(read('AGENTS.md').includes('`' + name + '`'));
  }
  for (const dir of ['.codegraph/', '.superpowers/', '.worktrees/']) assert.ok(read('.gitignore').includes(dir));
});
