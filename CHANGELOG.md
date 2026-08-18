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
