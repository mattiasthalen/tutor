---
status: accepted
---

# The Suite is declarative data interpreted by a fixed runner

At Build start the Suite is generated as one declarative artifact: snapshotted Format-profile targets, the quota table, mechanical Brief constraints, Role tags (judgment recorded once per card), and a list of check ids resolving to fixed predicates. Everything that runs it is generic — a stdlib-only runner shipped as a skill asset interprets any Suite wherever a code sandbox exists, and the same data renders as a walkable checklist, flagged best-effort, where none does. The Suite is the runner's input, never code: an Upgrade re-runs the byte-identical artifact against a fresh Export, and only cards new to the pool need fresh tagging.

## Considered options

- A rendered checklist as the source of truth — rejected: every re-run trusts model arithmetic and drift is invisible. It survives as the *render* of the declarative artifact for sandbox-less walks.
- A bespoke script generated per Deck — rejected: the Suite becomes ~150 lines of code that Upgrade must regenerate byte-stably; targets and Role tags end up buried in code and unreadable when walked.
- A hybrid of checklist plus script — folded into the chosen shape: the checklist is the data's render, the runner its interpreter; nothing is authored twice.

## Consequences

- The Suite artifact carries `profile:` (targets snapshot), `quotas:`, `constraints:`, and `roles:` sections plus the check list: parameters live in data, predicates live in the runner. Judgment-flavored lists (e.g. which keywords count as evergreen) are profile data, changed by editing a line of data, never runner logic.
- The runner is a portable skill asset: stdlib-only, with its own small YAML-subset parser, and free of Claude Code-only dependencies (per ADR-0004). The prototype ran the same Suite through two independent interpreters (Python and JavaScript) with identical verdicts as the portability check.
- The red/green report is a Block: a flat `suite:`/`deck:`/`format:`/`date:`/`oracle:` head, one `verdict:` line, then one `red|green <check-id> — evidence` line per Check, findings naming cards. It reads like the Review Block and diffs cleanly between runs.
- In Claude Code the Suite lives as a file beside the Deck; where no file persistence exists it travels the paste round-trip as a Block — one format, two carriages. The Block glossary entry widens accordingly.
- Amends ADR-0003: "an empty Deck starts all red" is softened — every size, mana-base, curve, and quota Check starts red, while constraint-shaped Checks (singleton, legality lists, availability) may pass vacuously at zero cards. Vacuous green is honest; no artificial red-until-meaningful guard is added.
- Evidence: `prototypes/suite-shape/` — the fixture Suite, both interpreters, the three-stage runs (empty / planted-violations draft / green final), and the interactive demo.
