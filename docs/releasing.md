# Releasing

How a tutor release is cut, per
[ADR 0004](adr/0004-single-channel-pinned-semver-releases.md).

## One channel, one version

The pinned `version` in `.claude-plugin/plugin.json` is the sole version
authority — the marketplace entry never carries one. A release **is** the
deliberate commit that bumps that pin; `scripts/release` performs it.

- **Unbumped merges deliberately ship nothing.** Docs, research, and map churn
  merge to main without a bump, and pinned-version installs stay cached until
  the version string changes. Nothing reaches users by accident.
- **No stable/latest split.** One marketplace, one channel — main is it.
- **GitHub Releases are deferred** until tutor goes public ("me first, the
  world next"). Every release is still tagged `tutor--v{version}`, and
  [CHANGELOG.md](../CHANGELOG.md) — Keep a Changelog shape — is the record
  meanwhile.

## Semver for prompt-ware

- **MAJOR** — existing artifacts break: a Block format change an existing
  Brief/Deck/Review Block cannot survive through Upgrade, or a skill or
  command is removed or renamed.
- **MINOR** — new capability: a new Format profile, skill, or Check class.
- **PATCH** — prompt fixes, wording, docs inside skills.

## Cutting a release

Keep the notes as you go: every ship-worthy change adds a line under
`## [Unreleased]` in `CHANGELOG.md`. The release script refuses to cut a
release while that section is empty — a release ships something deliberate.

From a clean tree on `main`:

```sh
scripts/release minor --dry-run   # demo the whole release, cut nothing
scripts/release minor             # cut it
```

The bump argument is `major`, `minor`, `patch`, or an explicit `X.Y.Z`; the
next version must move strictly forward. The script then performs the whole
release, in order:

1. Sets the new version in `.claude-plugin/plugin.json` — applied to a
   staged temporary copy of the tree, not the real one.
2. Mirrors it into every skill's `metadata.version` — plugin and skills
   version in lockstep, one organism.
3. Drafts the changelog entry: the `[Unreleased]` body moves under a dated
   `[{version}]` heading, leaving an empty `[Unreleased]` on top.
4. Runs the strict plugin validators (`claude plugin validate .`, `skills`,
   `commands` — all `--strict`) against that staged copy. The real tree is
   untouched until they pass.
5. Applies the validated bump to the real tree, commits it, tags
   `tutor--v{version}` via `claude plugin tag` (which validates the tag
   against the manifest), and pushes the commit and the tag together in one
   atomic push — the bump never reaches the remote without its tag.

Any refusal — dirty tree, backward version, empty notes, failed validation —
cuts nothing: no commit, no tag, no push. A failure later in the flow —
committing, tagging, pushing — rolls the release back to that same clean
state, so a retry is never blocked and no untagged bump can land on the
remote (every release is tagged, per ADR 0004).

`--dry-run` prints the plan and performs the same staged rehearsal — bump,
mirror, changelog draft, and validators, all against the temporary copy —
but changes, commits, tags, and pushes nothing.

The whole flow is covered by `tests/release.test.sh`, which releases fixture
repositories against local bare remotes; it runs in CI alongside the
validators.
