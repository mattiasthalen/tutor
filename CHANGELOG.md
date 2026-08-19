# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
— see [docs/releasing.md](docs/releasing.md) for what MAJOR, MINOR, and PATCH
mean for prompt-ware.

## [Unreleased]

### Added

- Plugin skeleton: this repository as its own marketplace, the pinned-version
  plugin manifest as sole version authority, the `/tutor:hello` verification
  command, and strict plugin-validator CI. (#47)
- Release flow: `scripts/release` performs the whole release — version bump
  mirrored into every skill in lockstep, changelog entry drafted, validators
  run, `tutor--v{version}` tagged and pushed — with a `--dry-run` demo mode,
  guarded by `tests/release.test.sh` in CI. (#50)
- `/tutor:oracle`: generates the Oracle (`oracle.jsonl`) beside the Export —
  tolerant header-keyed Export parsing, batched and throttled resolution via
  Scryfall's collection endpoint with a Name + Set code fallback for migrated
  IDs, and a first metadata line carrying the two staleness signals. Legality
  data is informational only. (#51)
- Brief skill: `/tutor:brief` settles the Brief — Format, identity, Power,
  constraints, Donor Decks, and play-variant asks — in one human-in-the-loop
  conversation, asks the single Export/Oracle freshness question once, and
  ends with a validated flat `key: value` Brief Block written to the
  Collection home, handing off to Build. Ships stdlib-only helpers for Brief
  validation (donor recognition included) and freshness signals, plus the
  `brief-smoke` offline eval case. (#52)
- Build front half: `/tutor:build` generates the Deck's Suite from the Brief
  and its Format profile before any card is picked — snapshotted targets, the
  quota table over the global Role vocabulary, mechanical Brief constraints
  under `# brief:` provenance comments, an empty Role-tag section — and shows
  it honestly red on the empty Deck through the fixed runner, Suite and report
  written to the Collection home. Commander ships as the first first-class
  Format profile: deck size, singleton copy limit, check targets, per-bracket
  Game Changers limits reading the Oracle's `game_changer` flag, banlist
  parameter, and judgment-flavored Role guidance, all data. The runner now
  runs exactly the Checks a Suite lists and gains the Commander predicates —
  color identity, banlist, Game Changers, must-include — plus the
  `mana_value` Oracle vocabulary; the `build-smoke` offline eval case grades
  the whole seam. (#53)
- Review skill: `/tutor:review` judges a finished Deck — any ManaBox deck,
  tutor-built or not — along the two axes (ADR 0006): two parallel subagents,
  Standards (the locked Smell baseline v1 plus per-Format `review_standards`
  authored into the Commander profile — politics, functional-copy redundancy,
  answer spread — where the profile overrides the baseline) and Brief
  (fidelity to stated intent), with a sequential two-pass fallback. Findings
  are severity + named cards + problem + at most one suggestion; the
  stdlib-only assembler computes every Verdict arithmetically (blocker →
  rebuild, notes → playable, clean → ship, overall = worst axis), caps five
  Findings per axis worst first, and renders the Review Block; closings are
  Verdict-dependent and Review never edits the Deck. A Review-flawed fixture
  Deck plants Smell- and Brief-class flaws the Suite provably cannot see;
  the `review-smoke` offline eval case hard-grades the arithmetic. (#55)
- Build to green: `/tutor:build` now runs the whole loop — adding and
  swapping owned cards until the Suite is green through the fixed runner, or
  ending red with an honest report and the human's options (loosen the
  Brief, accept the Deck as-is, acquire cards) — and ships a
  ManaBox-importable Deck Block to the Collection home's deck library:
  nonbasics pinned to the exact owned printing (the fancier print among the
  copies the Brief's `donor:` lines leave free — a copy committed to another
  Deck is never pinned), basics lumped per name last in each Board, inline category
  comments, the Maybeboard as the unpinned possibly-unowned wishlist, and
  the short-form Fan Content footer. Copies in existing Decks are committed
  by default: the Brief's `donor:` lines land in the Suite as data, the
  runner's availability Check honors them, and declined contention is
  reported out loud ("wanted Rhystic Study; all copies committed to
  Tatyova") via the new stdlib-only availability helper; `ship_deck.py`
  round-trips the shipped Block byte-identically. A Deck card missing from
  the Oracle degrades per-card to flagged model knowledge, never a hard
  failure. The runner also learned to read pinned multi-faced names
  (`Emeritus of Abundance // Regrowth (SOS) 145`) without truncating them as
  comments. The `build-deep` offline eval case grades the finished Build —
  Collection-only drawing, Format legality, the ManaBox-importable Block,
  the round-trip, targets never bent — with the Brief's-intent grader kept
  soft, and a paste-shaped Export case as parser-tolerance smoke. (#54)
- Upgrade path: an Upgrade is an ordinary Build re-run with a fresh Export
  and the existing Deck — no fourth deck verb. The rebuilt Deck's own copies
  are freed automatically at every seam — the availability helper (via the
  Brief's `name:` line and the Deck Block's title), printing pins at ship,
  and the runner's availability Check (the Deck under check is never held
  against itself) — so the Deck never contends with itself and no `donor:`
  line ever names it; every other Deck's contention stays honestly declined.
  The byte-identical Suite re-runs as-is against the fresh Export (only
  cards new to the pool need fresh Role tagging), Build accepts a Review
  Block as input on a `playable`/`rebuild` Verdict — its Findings the
  work list, the revision loop staying manual — and the deck library is a
  growing library whose artifacts an Upgrade reads and updates in place.
  The `upgrade-deep` offline eval case proves it: Suite bytes unchanged,
  the committed all-green report reproduced against a fresh Export derived
  from the Collection fixture, freed-own-copies availability verified, and
  the Upgrade contract pinned in the build skill. (#56)
