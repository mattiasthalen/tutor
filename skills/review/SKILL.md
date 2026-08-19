---
name: review
description: Reviews a finished Deck along the two axes — Standards (format deckbuilding craft) and Brief (fidelity to the Brief's stated intent) — ending with a Review Block whose Verdicts are computed, never re-judged. Any ManaBox deck is reviewable, tutor-built or not; a finished Table gets a Table Review judging the sitting as a whole. Use when the user runs /tutor:review, asks for judgment on a finished deck ("review this deck", "is this deck any good"), wants to know whether a Deck is ready to ship, or asks how a finished table night's decks hold up together.
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

Mass land denial, chained extra turns, and early two-card combos are judged in this axis too — table-experience calls over the Deck as played, weighed beside the Smells without joining the locked baseline's names. (Power fit is the Brief axis's, judged against the declared `power:`.)

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

## Table Review: the sitting as a whole

After a Table's last Seat ships, the finished sitting gets one more review — judged whole, not deck by deck (each Deck already gets its own Review above). Gather the Table Brief, every Seat's shipped Deck Block, and the per-Deck Review Blocks where they exist. The declared-Power match is already a mechanical Check (`validate_brief.py --seat-brief`, run at brief time, every Seat's effective Power against the table's) — felt fairness is what is judged here.

Fan out three parallel subagents, one per axis — the same sequential fallback applies — each returning exactly one JSON array of Table Findings and nothing else. A Table Finding is a `severity` (`blocker` or `note`), the `seats` (Seat deck names) and `cards` it names — findings name Seats and cards — the `problem`, and at most one suggestion (`swap` or `maybeboard`):

- **power spread** — does the sitting play like its numbers? A Seat playing above or below its declared Power, a villain the heroes cannot touch, a Pack pair that teaches nothing — felt fairness beside the mechanical match, never a recount of it.
- **play patterns** — do the Decks clash at the table? Two hard-control Seats grinding the night to a halt, a combo Seat ending the game the play variant promised to stretch, piloting loads mismatched to who actually sits down.
- **contention fallout** — what did seat order cost? The wants earlier Seats' finished Decks declined, the cards a later Seat settled for, and whether re-seating copies is worth a re-brief.

Assemble mechanically — the same arithmetic as the Deck Review, never fresh judgment:

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/skills/review/scripts/assemble_table_review.py" \
  --table-name "<table>" \
  --power-spread power-spread.json --play-patterns play-patterns.json \
  --contention contention.json --out decks/<table-slug>.table-review.txt
```

The Table Review Block carries `table:` and `date:` reference lines, one overall `verdict:`, then the three axis sections side by side — power spread, play patterns, contention fallout — each with its own computed verdict and at most five Findings worst first, naming Seats and cards. Close on the Verdict as above, with one table-shaped difference: with `playable` or `rebuild`, the offer is the human re-brief loop — revise the Briefs (`/tutor:brief`), then re-run the affected Seats in seat order through `/tutor:build`; reallocation is never automatic, and no Seat is unbuilt by a review.
