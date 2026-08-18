---
name: oracle
description: Generates the Oracle — the Scryfall-derived card-facts file covering the Collection — from the ManaBox Export in a Collection home. Use when the user runs /tutor:oracle, asks to generate or refresh the Oracle or card facts, when Build offers Oracle generation because oracle.jsonl is absent, or when the brief's freshness question ends in a regenerate.
metadata:
  version: 0.1.0
---

# Oracle

The Oracle is the card-facts file Checks run against, so Checks judge real
card data instead of model memory (see CONTEXT.md). This skill reads the
Export, resolves every unique card through Scryfall's collection endpoint,
and writes `oracle.jsonl` beside the Export — one JSON line per unique card
name, first line a metadata record carrying the two staleness signals. The
script does all the work; never assemble or hand-edit an Oracle from card
knowledge — a card the script cannot resolve stays out and degrades honestly
at Build.

## Run it

1. Locate the Export: `collection.csv` in the working directory (the
   Collection home, ADR 0007). A pasted Export is always legal input and
   beats the file on conflict — write the paste to a temporary file and pass
   that path.
2. Run (network required; the script batches 75 identifiers per call,
   throttles under Scryfall's 2 calls/second, and identifies itself with the
   required headers — do not work around a network failure by inventing
   card facts):

   ```sh
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/oracle/scripts/build_oracle.py" \
     --collection collection.csv
   ```

   Exit 0: `oracle.jsonl` written beside the Export. Exit 2: hard failure —
   an Export header missing the identity columns (no Scryfall ID column and
   no Name + Set code columns) or an unreachable endpoint; report it plainly
   and stop. Offline runs (evals, fixture-pinned tests) add
   `--snapshot <snapshot.jsonl>` and never touch the live API.
3. Report from the script's output, keeping its numbers exactly:
   - rows read and malformed rows skipped, with the count and examples;
   - cards resolved, how many needed the Name + Set code fallback, and any
     cards left unresolved (these degrade per-card to flagged model
     knowledge at Build — recommend a ManaBox re-export if they matter);
   - the two staleness signals from line one: `generated_at` and the source
     Export's newest `Added` watermark — the brief's freshness question
     reads both;
   - the compliance line: card data provided by Scryfall (tutor is not
     endorsed by or affiliated with Scryfall), and legality data is
     informational only, never a guarantee.

Regenerate — rerun this skill on a fresh Export — whenever the Export is
newer than the Oracle's watermark or `generated_at` is older than about 30
days; the brief conversation folds both signals into its one freshness
question.
