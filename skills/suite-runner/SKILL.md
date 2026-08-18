---
name: suite-runner
description: Runs a declarative Suite over a Deck for a deterministic red/green report. Use when a Deck needs its Suite's verdicts — during Build iterations, at an Upgrade re-run, or when the user asks whether a deck passes its Checks — or when no code can execute and the Suite must be walked as a checklist instead.
metadata:
  version: 0.1.0
---

# Suite runner

A Suite is declarative data — snapshotted profile targets, quotas, mechanical constraints, Role tags, and check ids resolving to fixed predicates (ADR 0005). This skill runs one: same Deck, same card facts, same verdict, every run. The Suite is the runner's input, never code — a red Check is answered by changing the Deck or re-briefing, and the Suite file and runner script stay untouched.

## Run it

1. Gather the four inputs: the Suite file, the Deck Block file, the Oracle, and the Export (`collection.csv`). In a Collection home they sit in the working directory, the Oracle as `oracle.jsonl` — JSON Lines, one card-facts object per line, first line a metadata record (ADR 0007); a plain JSON-array Oracle is also accepted. A pasted Block beats the file on conflict — write the paste to a temporary file and pass that path.
2. Run:

   ```sh
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/suite-runner/scripts/check_deck.py" \
     --suite <suite-file> --deck <deck-file> \
     --oracle <oracle-file> --collection <export-file>
   ```

   Exit 0: every Check green. Exit 1: at least one red. Exit 2: the Suite lists a check id resolving to no fixed predicate — a wrong Suite or an old runner, never a verdict. Add `--date YYYY-MM-DD` when the report must be byte-comparable to an earlier run; two runs over the same inputs then diff clean.
3. Deliver the report Block verbatim — the flat `suite:`/`deck:`/`format:`/`date:`/`oracle:` head, the `verdict:` line, then one `red|green <check-id> — evidence` line per Check. The report is the artifact: quote it whole, with every verdict line exactly as printed.

## Walk it (no sandbox)

Where nothing can execute, the same Suite data is walked as a checklist:

1. Read the Suite file. Its `checks:` list is the checklist; every parameter lives in `profile:`, `quotas:`, and `constraints:`; `roles:` holds Role tags already judged at Build — count them, never re-judge.
2. Walk every check: count against the Oracle where present; with no Oracle, use card knowledge and flag it. Mark each line red or green with the counted evidence — never a bare tick.
3. Emit the same report Block shape, with every verdict flagged best-effort.

`--render-checklist` (with `--suite` alone) prints this walkable form, for handing the Suite to a session that cannot execute.
