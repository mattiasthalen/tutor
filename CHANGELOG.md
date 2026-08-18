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
