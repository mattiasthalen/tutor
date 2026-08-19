---
name: build
description: Runs a Build from a settled Brief to a shipped Deck — generates the Suite (every deterministic Check the Deck must pass) before any card is picked, shows it honestly red on the empty Deck, then adds and swaps owned cards until the Suite is green (or ends red with an honest report), shipping a ManaBox-importable Deck Block to the Collection home. An Upgrade is this same Build re-run with a fresh Export and the existing Deck. Use when the user runs /tutor:build, has a settled Brief and wants the deck built, wants an existing deck upgraded or rebuilt after a Review, or asks what a deck must pass.
metadata:
  version: 0.1.0
---

# Build: red to green

TDD for decks (ADR 0003, amended by ADR 0005): at Build start the Suite — every Check the Deck must pass — is generated from the Brief and the Format profile, before any card is picked, and shown honestly red on the empty Deck. Then Build loops — adding and swapping owned cards, recording Role judgment — until the same fixed runner reports all green, and the Deck Block ships to the Collection home's deck library. A Suite that cannot green from the Collection ends with an honest red report and the human's options — Build never bends a target.

## Gather the inputs

1. The Collection home is the working directory. The Brief lives at `decks/<slug>.brief.txt` — with several, ask which; with none, hand off to `/tutor:brief` first. A pasted Export or Block always beats the file on conflict: report the diff, write the paste to the file's place (or a temp file), and work from it.
2. The Export is `collection.csv`, the Oracle `oracle.jsonl`. When the Oracle is absent and network allows, offer to generate it on the spot via `/tutor:oracle` — one question, then move on. Declined or offline, generation still works from the Brief's `identity:` line, but the Suite can only be walked as a checklist (`--render-checklist`), every verdict flagged best-effort — say so rather than skipping Checks.
3. An Upgrade — rebuilding an existing Deck against a fresh Export — is an ordinary Build re-run, no fourth deck verb. The Deck's own copies — Export rows committed to the ManaBox deck its import created, named by the Deck Block's title and the Brief's `name:` — are freed automatically by the availability arithmetic, so the rebuilt Deck never contends with itself. The freeing keys on name identity: a renamed Deck — its ManaBox name matching neither the Block title nor the Brief's `name:` — names its ManaBox name as a `donor:` once, the connection only the human can make. `donor:` lines otherwise stay what they were: the Brief naming *other* Decks as fair game. The deck library (`decks/`) is a growing library, never a scratch directory: an Upgrade reads the existing Deck's artifacts — Brief, Suite, Deck Block, report, Review — and updates them in place, same slug, same files.
4. Build accepts a Review Block as input (`decks/<slug>.review.txt`, or pasted), honoring the Verdict-dependent handoff: `playable` and `rebuild` re-runs consume it — its Findings and their suggestions are the loop's work list against the same Brief and Suite — while `ship` leaves nothing to consume. The revision loop is manual: the human reads the Review and re-runs Build; nothing loops back into Review automatically.

## Pick the Format profile

A Format is a first-class data profile: `${CLAUDE_PLUGIN_ROOT}/skills/build/profiles/<format-slug>.yaml`, slugged from the Brief's `format:` (lowercase, spaces to hyphens). Commander ships as `profiles/commander.yaml`; a Brief whose Format has no profile file yet stops here honestly — name the profiles that exist, never improvise targets.

## Generate the Suite — data, never code

On an Upgrade the Suite already exists and re-runs as-is: never regenerate `decks/<slug>.suite.yaml` — the byte-identical Suite runs against the fresh Export, and only cards new to the pool need fresh Role tagging, recorded in `roles:` as they are picked like any Build. Only a changed Brief regenerates the Suite, and re-settling the Brief goes through `/tutor:brief` first. A first Build generates:

1. Run the generator:

   ```sh
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/build/scripts/generate_suite.py" \
     --brief decks/<slug>.brief.txt \
     --profile "${CLAUDE_PLUGIN_ROOT}/skills/build/profiles/<format-slug>.yaml" \
     --oracle oracle.jsonl \
     --out decks/<slug>.suite.yaml
   ```

   Drop `--oracle` only when none exists. The Suite is declarative data the fixed runner interprets: snapshotted profile targets, the quota table over the global Role vocabulary (ramp, draw, removal, wipe, wincon, land, theme/other), mechanical Brief constraints — the `donor:` lines included, so availability is contention-aware — an empty `roles:` section (Role tagging is judgment recorded once per card as Build fills the Deck — no card is picked yet), and check ids resolving to the runner's fixed predicates. Targets come from the profile; only the Brief overrides them, each override under a `# brief:` provenance comment.
2. The generator refuses rather than bends: an untranslatable `constraint:` line, an `identity:` contradicting the Centerpiece's Oracle identity, a missing Centerpiece the Format demands. On a refusal, take the message back to the human and re-settle the Brief (`/tutor:brief`) — never hand-edit the Suite to make a constraint fit, never drop one silently.

## Start red: run the empty Deck

1. Write the empty Deck Block — `decks/<slug>.deck.txt`, a `// <name>` title plus the Boards the Format uses (`// Commander`, `// Mainboard`), no cards.
2. Run the Suite through the fixed runner and write the report:

   ```sh
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/suite-runner/scripts/check_deck.py" \
     --suite decks/<slug>.suite.yaml --deck decks/<slug>.deck.txt \
     --oracle oracle.jsonl --collection collection.csv \
     > decks/<slug>.suite-report.txt
   ```

   Exit 1 is the point: every size, mana-base, curve, and quota Check starts red, while constraint-shaped Checks (singleton, legality lists, availability) may pass vacuously — vacuous green is honest, and no artificial red is added (ADR 0005).

## Loop: fill the Deck until the Suite is green

1. Pick owned cards toward the reddest Checks first — quotas, curve, lands — honoring the Brief's `notes:` (fuzzy intent is built toward here even though only Review judges it). The Deck draws only from the Collection: copies in existing Decks are committed by default; the Brief's `donor:` lines free them, and the Deck being built frees its own committed copies automatically (an Upgrade never contends with itself). Before adding a card, confirm a copy is free:

   ```sh
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/build/scripts/availability.py" \
     --collection collection.csv --brief decks/<slug>.brief.txt \
     --want "<card name>"
   ```

   (`--deck decks/<slug>.deck.txt` checks the whole working Deck at once.) A declined want is reported out loud in the closing report — "wanted Rhystic Study; all copies committed to Tatyova" — never silently swallowed and never taken anyway.
2. Add each picked card as a `<qty> <name>` line under its Board, and record its Role judgment at the same time: one `  <name>: [tag, tag]` line in the Suite's `roles:` section, tags from the global vocabulary, guided by the profile's `role_guidance`. Tagging is judgment recorded once; the runner counts tags mechanically and never re-judges. Roles are the only lines Build ever adds to the Suite — targets are never touched.
3. Re-run the runner (same command as above) after each batch of adds and swaps; the report diff shows exactly which Checks moved. Keep looping — add, swap, retag — until exit 0. A red Check is answered by changing the Deck or re-settling the Brief, never by editing a target: Build must never bend the Suite to the Deck.
4. A Deck card missing from the Oracle degrades per-card to flagged model knowledge — the runner names it in the report head and verdicts the rest. Never treat the gap as a hard failure: list the uncovered cards in the closing report, flag every verdict that touches them as best-effort, and recommend regenerating the Oracle (`/tutor:oracle`).

## Ship the Deck Block

1. When the Suite is green (or the human accepts a red end), ship the working Deck through:

   ```sh
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/build/scripts/ship_deck.py" \
     --deck decks/<slug>.deck.txt --collection collection.csv \
     --brief decks/<slug>.brief.txt \
     --oracle oracle.jsonl --out decks/<slug>.deck.txt
   ```

   The shipped Block is text ManaBox actually imports: first line `// <name>`; Board headers only for the Boards the Format uses; every nonbasic pinned to the exact owned printing — set code and collector number, the fancier owned print chosen when several exist, drawn only from the copies the contention arithmetic leaves free — the Brief's `donor:` lines plus the Deck's own automatically freed copies (the same arithmetic the loop consulted: a copy committed to another Deck is never pinned, so physical assembly never raids one); optional inline `// category` comments; basics lumped per name, last in each Board after a blank line; and the short-form Fan Content footer line. Unowned upgrade ideas worth a future slot go on the Maybeboard — the wishlist Board, unpinned and allowed to be unowned, the one place the collection-only rule bends.
2. Re-run the runner once over the shipped file and write the final report to `decks/<slug>.suite-report.txt` — the Suite re-runs through the fixed runner, byte-stable, so the report proves the shipped bytes.

## Close: green or honestly red

1. Show the final report Block verbatim and the shipped Deck Block fenced, exactly as written. Where legality or price surfaces in the summary, say the Scryfall data behind it is informational only, never a guarantee.
2. Green: say the Deck, Suite, and report live in the Collection home's deck library, and hand off to `/tutor:review` — Review needs the Deck Block and the Brief Block (it trusts the green Suite and never recounts). Blocks are recognized by shape alone and never embed one another: name the files rather than pasting one Block inside another.
3. Red end: deliver the honest red report with every declined contention sentence and the uncovered cards, and lay out the human's options — loosen the Brief (re-run `/tutor:brief`, then regenerate the Suite), accept the Deck as-is (ship it red-reported), or acquire cards (name what is missing; recommending purchases is not tutor's job). The choice is theirs; the targets stay unbent either way.
