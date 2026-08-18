---
name: build
description: Starts a Build from a settled Brief — generates the Deck's Suite (every deterministic Check it must pass) from the Brief and its Format profile before any card is picked, runs it on the empty Deck, and writes the honest red report to the Collection home. Use when the user runs /tutor:build, has a settled Brief and wants the deck built, or asks what a deck must pass.
metadata:
  version: 0.1.0
---

# Build: start red

TDD for decks (ADR 0003, amended by ADR 0005): at Build start the Suite — every Check the Deck must pass — is generated from the Brief and the Format profile, before any card is picked, and shown honestly red on the empty Deck. This skill is that front half. Filling the Deck until the Suite is green is the next stage; until it lands, iterate by adding cards to the Deck Block and re-running the Suite through the suite-runner skill.

## Gather the inputs

1. The Collection home is the working directory. The Brief lives at `decks/<slug>.brief.txt` — with several, ask which; with none, hand off to `/tutor:brief` first. A pasted Export or Block always beats the file on conflict: report the diff, write the paste to the file's place (or a temp file), and work from it.
2. The Export is `collection.csv`, the Oracle `oracle.jsonl`. When the Oracle is absent and network allows, offer to generate it on the spot via `/tutor:oracle` — one question, then move on. Declined or offline, generation still works from the Brief's `identity:` line, but the Suite can only be walked as a checklist (`--render-checklist`), every verdict flagged best-effort — say so rather than skipping Checks.

## Pick the Format profile

A Format is a first-class data profile: `${CLAUDE_PLUGIN_ROOT}/skills/build/profiles/<format-slug>.yaml`, slugged from the Brief's `format:` (lowercase, spaces to hyphens). Commander ships as `profiles/commander.yaml`; a Brief whose Format has no profile file yet stops here honestly — name the profiles that exist, never improvise targets.

## Generate the Suite — data, never code

1. Run the generator:

   ```sh
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/build/scripts/generate_suite.py" \
     --brief decks/<slug>.brief.txt \
     --profile "${CLAUDE_PLUGIN_ROOT}/skills/build/profiles/<format-slug>.yaml" \
     --oracle oracle.jsonl \
     --out decks/<slug>.suite.yaml
   ```

   Drop `--oracle` only when none exists. The Suite is declarative data the fixed runner interprets: snapshotted profile targets, the quota table over the global Role vocabulary (ramp, draw, removal, wipe, wincon, land, theme/other), mechanical Brief constraints, an empty `roles:` section (Role tagging is judgment recorded once per card as Build fills the Deck — no card is picked yet), and check ids resolving to the runner's fixed predicates. Targets come from the profile; only the Brief overrides them, each override under a `# brief:` provenance comment.
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
3. Show the human the report Block verbatim and say what it means: the Suite is the Deck's definition of done, red is the work remaining, and the Suite file and report now live in the Collection home beside the Brief. Building fills the Deck until this same runner reports all green — a Suite that cannot green from the Collection ends with an honest red report, never a bent target.
