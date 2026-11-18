---
name: writing-software-docs
description: Use when writing software docs grounded in code, specs, or fact sheets: docs pages, README sections, user guides, tutorials, how-to guides, reference, explanations, troubleshooting, changelogs, or release notes. Not for essays (use writing-nonfiction) or code comments and commit messages (follow the repo's conventions).
---

# Writing Software Docs

## Principle

Organize docs by reader need ([Diataxis](https://diataxis.fr)): learning,
doing, looking up, or understanding. Give each page one type.

## Deliverables

1. **Visible placement plan before prose.** Map each reader need to a type and
   destination. A broad "page about X" usually spans all four needs. Inspect
   the docs tree and prefer same-type existing pages; otherwise propose page
   paths. Do not hide the plan in an HTML comment. When the plan covers more
   than the user asked for (several pages from one request), confirm the plan
   with the user before drafting the extra pages; draft only what was asked
   until they agree. When the user named the scope, keep to it and list the
   other types as suggested follow-ups.
2. **One type per page.** Add a section only to a same-type existing page.
   Never combine types on a new page. Exception: READMEs and mixed-type
   landing pages already mix types, so a section may be added to one, labeled
   with its type in the heading or a marker. Follow the recipes below. Mark
   each page's type with a comment placed after any frontmatter (frontmatter
   must stay first), in the site's comment syntax: `{/* diataxis: how-to */}`
   for MDX, `<!-- diataxis: how-to -->` for Markdown and HTML (substitute the
   type). Draft every page in the agreed plan, even when a step needs
   confirmation.
3. **Cross-links.** Link related types for the subject instead of repeating
   them. When drafting without a docs tree, use proposed relative links.
4. **Unconfirmed list.** Only source-stated claims go on pages; arithmetic on
   stated values counts. Prerequisites, expected results, and control actions
   are claims too. List inferences and gaps for confirmation.
5. **Visible gaps.** Replace a needed unconfirmed step or table cell with
   `**TODO(confirm):** <question>` in place and add it to Unconfirmed. Do not
   state a guessed action before its marker. Keep the source's main path
   (such as a plugin UI) rather than replacing it. Hidden comments do not count.

## Page recipes

| Type | Include | Leave out |
| --- | --- | --- |
| Tutorial: learning | One guided path to first success; numbered steps with expected results; what the reader can now do | Options, background |
| How-to: doing | Goal in title; prerequisites; numbered steps; success check | Teaching, exhaustive options |
| Reference: looking up | Product-shaped tables: names, types or ranges, defaults, effects | Steps, advice |
| Explanation: understanding | How parts connect and their tradeoffs | Steps, exhaustive values |

| Changelog or release notes: reference | Version and date; entries grouped by change type (added, changed, fixed, removed); each entry states the reader-visible effect; links to the how-to for any migration | Marketing, background, steps |

Troubleshooting is a how-to keyed by symptom: symptom, cause, then fix. Commit
messages and code comments are out of scope: follow the repo's commit
conventions and write comments in the code, not in the docs tree.

## Check before delivery

- Check claims against sources; list unsupported claims or mark necessary gaps.
- Check each page's type, marker, links, and `TODO(confirm)` entries against
  the placement plan and Unconfirmed list.

Use `writing-human-prose` for sentences. Before publication, run
`reviewing-nonfiction` in its software-docs mode and say so in the handoff:
the reviewer checks one Diataxis type per page, claims against sources,
placement and links, and does not require a lede, nut graf, or essay form.

## Common mistakes

| Mistake | Fix |
| --- | --- |
| One page mixes steps, tables, and background | Split and cross-link |
| Procedure steps enter reference | Move them to a how-to |
| An inferred converse or UI action appears as fact | List it; mark needed gaps visibly |
| A new page duplicates a same-type page | Add a section or row there |
