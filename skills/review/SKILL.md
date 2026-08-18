---
name: review
description: Reviews a finished Deck along the two axes — Standards (format deckbuilding craft) and Brief (fidelity to the Brief's stated intent) — ending with a Review Block whose Verdicts are computed, never re-judged. Any ManaBox deck is reviewable, tutor-built or not. Use when the user runs /tutor:review, asks for judgment on a finished deck ("review this deck", "is this deck any good"), or wants to know whether a Deck is ready to ship.
metadata:
  version: 0.1.0
---

# Review: two axes, one mechanical Verdict

Review is the judgment counterpart of the Suite's Checks (ADR 0006), mirroring the code-review split: two parallel subagents, one per axis — **Standards** judges format deckbuilding craft, **Brief** judges fidelity to the Brief's stated intent — their Findings aggregated side by side, never merged or reranked. Judgment happens exactly once, at the Finding level; everything above it is arithmetic the assembler script computes. Review trusts the green Suite and never recounts Check territory, but may flag a Check target as mis-set for the Brief ("24 lands passed, but this curve wants 26"). Power fit, mass land denial, chained extra turns, and early two-card combos are Review judgment, not Checks. Review never edits the Deck — Build owns edits; a Finding suggests at most one line, and the human decides.

## Gather the inputs

1. The Collection home is the working directory. The Deck is `decks/<slug>.deck.txt` — with several, ask which — or any pasted ManaBox deck Block, tutor-built or not; a paste always beats the file on conflict.
2. The Brief is `decks/<slug>.brief.txt`. With no Brief (a non-tutor deck, a bare paste), the review runs Standards-only and the Brief axis reports "no Brief available" — the assembler writes that line; ask for intent only if the human volunteers to settle a Brief first.
3. When a Suite exists beside the Deck (`decks/<slug>.suite.yaml`), run it once through the fixed runner and keep the report — seeing green is how trust is earned, re-litigating targets is not:

   ```sh
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/suite-runner/scripts/check_deck.py" \
     --suite decks/<slug>.suite.yaml --deck decks/<slug>.deck.txt \
     --oracle oracle.jsonl --collection collection.csv
   ```

   A red report is Build territory: show it, offer `/tutor:build`, and review anyway only on an explicit ask, saying Check territory stands unverified. No Suite at all: same caveat, judgment-only review.
4. The Export (`collection.csv`) and the Oracle (`oracle.jsonl`) feed suggestions: an owned card may be suggested as a swap, an unowned card only as a Maybeboard candidate.

## Fan out the axis passes

Launch two parallel subagents, one per axis, in a single message so they run side by side (with no Brief, launch Standards alone). Each gets its charter below plus the Deck Block, the Brief (when present), the Suite report, and — Standards only — the Format profile. Each returns exactly one JSON array of Findings and nothing else:

```json
[
  {"severity": "blocker", "cards": ["Card A", "Card B"],
   "problem": "what is wrong, named plainly", "swap": "Owned Card"},
  {"severity": "note", "cards": ["Card C"],
   "problem": "works, but a better line exists", "maybeboard": "Unowned Card"}
]
```

A Finding is a `severity` — `blocker` (would not play as-is) or `note` (works, but a better line exists) — the `cards` it names, the `problem`, and at most one suggestion: `swap` (a card the Collection owns) or `maybeboard` (an unowned candidate). Emit every Finding found: the assembler shows the worst five per axis and folds the rest into one line, so completeness costs nothing.

When subagents are unavailable, run the same two charters yourself as the sequential two-pass fallback — Standards pass, then Brief pass, each still ending in its own Findings array before any assembly. The fallback is robustness, not a second contract (ADR 0006 as amended by ADR 0007).

### Standards charter

Judge format deckbuilding craft against the Smell baseline v1 — each Smell a judgment call over the Deck as played, never a recount of what the Suite already counted:

- **synergy island** — a card or package that rewards only itself, plugged into nothing else the Deck does.
- **dead card** — no realistic draw of it is welcome here: it keys on something this Deck never presents.
- **win-more** — shines only once the game is already won, and does nothing to get there.
- **no comeback plan** — behind on board, the Deck has no road back: no sweeper, no reset, no catch-up engine.
- **piloting overload** — more triggers, modes, and bookkeeping than its pilot can track at a real table.
- **fragile mana** — the plan wants colors or counts on turns the mana base cannot promise in play, beyond the counts the Checks own.
- **theme tax** — on-theme filler holding slots honest playables need: rent paid to the theme, not to the game.
- **redundancy gap** — a load-bearing effect the Deck carries exactly once, one answer away from no plan.
- **curve lie** — the curve's numbers pass while the early plays do nothing that matters; the real game starts turns late.
- **interaction mismatch** — answers that cannot touch what this Format's tables actually present: wrong shapes, wrong speeds.

Then read the `review_standards:` section of the Format profile (`${CLAUDE_PLUGIN_ROOT}/skills/build/profiles/<format-slug>.yaml`, the same file Build generated the Suite from) and apply each entry on top of the baseline; an entry sharing a baseline Smell's name replaces that Smell's reading — the profile overrides the baseline. With no profile for the Format, or none carrying `review_standards:`, the baseline stands alone.

### Brief charter

Judge fidelity to the Brief's stated intent, line by line: the fuzzy asks (`notes:` — feel, theme, taste) land here, as do Power fit against the declared `power:`, the play variant's table promise, and whether the Deck a green Suite produced is the Deck the human asked for. Judge the targets too: a Check target the Suite honoured but the intent outgrew is a Finding here, flagged as mis-set for the Brief — name the target and the cards it touches, and leave the recount to the runner. Silence on a Brief line the Deck honours is correct; only deviations become Findings.

## Assemble — arithmetic, never fresh judgment

1. Write each axis's Findings array verbatim to a file (a temp path is fine) — reorder nothing, merge nothing, soften nothing.
2. Assemble the Review Block:

   ```sh
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/review/scripts/assemble_review.py" \
     --deck-name "<name>" \
     --standards standards-findings.json --brief brief-findings.json \
     --out decks/<slug>.review.txt
   ```

   Pass `--no-brief` in place of `--brief` when no Brief exists. The script computes every Verdict — any blocker makes an axis `rebuild`, only notes `playable`, clean `ship`, the overall Verdict is the worst axis — and renders each axis's Findings worst first, capped at five with a one-line summary of the rest. An exit-2 refusal names a malformed Finding: re-emit that axis's Findings and rerun; the Block is never hand-patched.
3. Show the human the Review Block verbatim, beside where it now lives in the Collection home.

## Close on the Verdict

- `ship` — the Deck is done as asked: suggest the ManaBox import (the Deck Block imports as-is).
- `playable` or `rebuild` — offer a Build re-run that consumes the Review Block: `/tutor:build` reads the Findings and their suggestions as its work list against the same Brief and Suite. The Deck file stands untouched either way — Review judges, Build edits.
