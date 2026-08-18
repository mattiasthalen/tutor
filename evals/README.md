# tutor Evals

Evals judge tutor itself — does a skill produce a sound Brief, Deck, or
Review — as opposed to Checks, which judge Decks (see `CONTEXT.md`). They are
deterministic, fixture-driven, and **never call the live Scryfall API**.

## Run the offline harness

```sh
python3 evals/run_evals.py
```

Grades every mechanical expectation in `evals.json` against the committed
fixtures and prints a red/green report. Exit 0 means green. Per-case
artifacts land in `evals/results/<case-name>/` (gitignored) as
`eval_metadata.json` and `grading.json` in the skill-creator grading schema.

The harness's own tests, including the proof that a broken fixture turns the
run red:

```sh
python3 -m unittest discover -s tests
```

## How cases are authored

`evals.json` follows the skill-creator eval workflow format: `skill_name`
plus `evals[]` entries of `id`, `prompt`, `expected_output`, `files`, and
`expectations`. The gated `claude plugin eval` is early access today; cases
are authored in this format now and ported when enablement lands — see
`docs/spikes/plugin-eval-enablement.md`.

Expectations come in the spec's two grader tiers:

- **Hard mechanical invariants** — registered in `run_evals.py`'s
  `EXPECTATION_CHECKS`, keyed by the exact expectation text, graded by fixed
  predicates on every run. Any failure is red.
- **Soft LLM judgment** — expectations without a registered predicate. The
  harness reports them as `soft` and leaves them to the dev-time
  skill-creator workflow (run the skill with subagents, grade the outputs).

A later skill ticket adds a case by appending it to `evals.json`, naming it
in `CASE_NAMES`, and registering a fixed predicate for every mechanical
expectation. The smoke case (`harness-smoke`) stays the end-to-end guard for
the fixture tree itself.

## Fixtures

`fixtures/manifest.json` records provenance and registers every planted
flaw; the smoke case cross-checks it.

- `fixtures/collections/` — the realism fixture: the real captured ManaBox
  4.1.12 Export (`real-collection.csv`, 577 rows) with its deck text export
  and `verify_export.py` verification script, byte-identical to the capture
  branch. Beside it, synthetic Collections covering what the real Export
  lacks: etched foil, ja/zhs languages, promo collector numbers, and
  per-Format shaped pools (Kitchen 20, Standard).
- `fixtures/briefs/`, `fixtures/decks/` — fixture Brief Blocks and Deck
  Blocks; the `*-flawed.txt` Decks carry planted flaws for Review evals,
  each registered in the manifest.
- `fixtures/scryfall/` — the pinned Scryfall snapshot (`snapshot.jsonl`)
  covering exactly the fixture cards, and the fixture Oracle
  (`oracle.jsonl`) derived from it byte-reproducibly by `derive_oracle.py`.

## Refreshing the pinned snapshot — deliberate, never automatic

```sh
python3 evals/fixtures/scryfall/refresh_snapshot.py   # the deliberate refresh network path
python3 evals/fixtures/scryfall/derive_oracle.py      # re-derive the Oracle from it
python3 evals/run_evals.py                            # prove the tree still green
```

Run this only when the fixture set changes or a data refresh is wanted, and
commit the resulting diff. Card data © Wizards of the Coast, provided by
Scryfall; see `NOTICE`.
