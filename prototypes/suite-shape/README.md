# Prototype: deck-test artifact shape — how a Suite reads and runs

Throwaway prototype for [issue #31](https://github.com/mattiasthalen/tutor/issues/31).
It answers one question: **what artifact form should a Suite take so it reads and runs in
both runtimes** — claude.ai chat (code-execution sandbox, pasted data, no repo) and
Claude Code (files on disk) — and where do Role tags and Format-profile targets live so
an Upgrade re-run stays stable?

Everything runs one real fixture: *Sunlit Flock*, a Kitchen 20 white lifegain Pack.
Card facts are genuine Foundations data pulled from Scryfall (`oracle.json`); the
Collection is a toy Export subset (`collection.csv`); thresholds in the profile are
illustrative, not tuned.

**Premise update:** ADR 0004 (landed while this ticket was open) cut the claude.ai
skill-ZIP channel — Claude Code on every surface is now the sole shipping path — but
requires skills to stay free of Claude Code-only dependencies so the ZIP channel can
return. That demotes the "claude.ai chat" columns below from co-primary runtime to
portability contingency; the comparison itself is unchanged.

## The candidates, made concrete

| File | Candidate | What it is |
| --- | --- | --- |
| `candidate-a-checklist.md` | A — rendered checklist | Markdown the model walks and counts by hand. Here it is *generated from C* (`check_deck.py --render-checklist`), which is the hybrid claim: the checklist is a view, not a source of truth. |
| `candidate-b-bespoke.py` | B — bespoke generated script | Targets, Role tags, and thresholds hardcoded; the Suite *is* code. Regenerating it at Upgrade rewrites ~150 lines. |
| `suite.yaml` + `check_deck.py` | C — declarative Suite + fixed runner | The Suite is data: profile targets snapshotted, quotas, mechanical Brief constraints, Role tags (judgment recorded once), and a check list whose ids map to fixed predicates. The runner is a reusable skill asset, stdlib-only, with a ~50-line YAML-subset parser so the chat sandbox needs no dependencies. |
| `demo.html` | — | Single-file interactive demo. Its JavaScript engine is a second, independent interpreter of the same `suite.yaml` data and produces identical verdicts to the Python runner on all three deck stages (11 / 9 / 0 red) — the portability evidence for C. |

## Run it

```sh
python3 check_deck.py --deck decks/empty.txt    # all quotas red — Build start
python3 check_deck.py --deck decks/draft.txt    # 9 planted violations, all caught
python3 check_deck.py --deck decks/final.txt    # all green, exit 0
python3 check_deck.py --render-checklist        # candidate A from the same Suite
python3 candidate-b-bespoke.py decks/draft.txt  # candidate B, same verdicts
```

Captured output lives in `runs/`. Open `demo.html` by double-click — no server, no
install; click cards, run walkthroughs, flip the sandbox/no-sandbox lens.

## What the prototype showed

- **"All red on an empty Deck" (ADR 0003) is not literally true.** On the empty deck,
  11 of 18 Checks are red but 7 pass vacuously (singleton, evergreen, availability,
  mono-color, nonbasic list, cmc cap, color coverage — no cards, no violation). Either
  the ADR's sentence gets softened ("nothing green that matters — every quota and
  size/land Check red") or constraint-class Checks gain a "not yet meaningful" guard.
  Decision needed, small.
- **The report Block reads well flat**: `suite:`/`deck:`/`format:`/`date:`/`oracle:`
  head, one `verdict:` line, then one `red|green <check-id> — evidence` line per Check,
  findings naming cards. Matches the Review Block's flat style and is stable enough to
  diff between runs.
- **Role tags and targets belong in the Suite artifact** (`roles:`, `profile:`,
  `quotas:`), not in code and not re-derived per run. The Upgrade walkthrough in the
  demo shows a re-run against a changed Collection with the Suite file byte-identical;
  only cards new to the pool need fresh tagging.
- **The evergreen-keyword list is profile data, and that placement earns its keep**:
  Vanguard Seraph (Surveil) flags red under the classic list — whether Surveil counts
  as evergreen is a profile judgment, changed by editing one line of data, never the
  runner.
- **Sizes** (context-budget signal for chat): `suite.yaml` ~3.9 KB, checklist render
  ~2.3 KB, report ~1.5 KB per run; the fixed runner ~12 KB loaded as a skill asset,
  paid once per skill rather than per Deck. The bespoke script is ~6 KB *per Deck*.

## Recommendation (for the ticket discussion)

C with A as its render — one declarative Suite Block (YAML-ish flat data) per Deck;
a fixed stdlib-only runner shipped as a skill asset executes it wherever a sandbox
exists (both runtimes today), and the same data renders as a walkable checklist when
no sandbox is available, flagged best-effort. B loses on Upgrade stability and on
readability in degraded mode.

## Not modeled here (on purpose)

Donor-Deck contention and committed copies (settled by the collection-ingestion
decision, orthogonal to artifact shape); set-specific availability matching (name-level
only); the Fan Content footer on generated artifacts; knowledge-backed fallback
execution (the demo's no-sandbox lens shows its *shape* only).
