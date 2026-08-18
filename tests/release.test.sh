#!/usr/bin/env bash
# Behaviour tests for scripts/release (issue #50, ADR 0004).
#
# Seam under test: the release script's command-line interface, observed from
# outside — the files it leaves behind, the git history and tags it creates,
# what lands on the remote, and its exit status. Never its internals.
#
# Each test runs against a fresh fixture: a copy of this repository in a
# temporary directory with its own git history and a local bare "origin"
# remote, pinned to version 0.1.0 with a known CHANGELOG. Everything is real —
# real git, real `claude plugin validate`, real `claude plugin tag` — and
# nothing leaves the temporary directory.

set -uo pipefail

REPO_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

TODAY=$(date +%F)
PASS=0
FAILED=0

ok() { PASS=$((PASS + 1)); printf 'ok   - %s\n' "$1"; }
not_ok() { FAILED=$((FAILED + 1)); printf 'FAIL - %s\n       %s\n' "$1" "$2"; }

# check <description> <command...> — passes when the command exits 0.
check() {
  local desc=$1
  shift
  if "$@" >/dev/null 2>&1; then
    ok "$desc"
  else
    not_ok "$desc" "expected success from: $*"
  fi
}

# check_not <description> <command...> — passes when the command exits nonzero.
check_not() {
  local desc=$1
  shift
  if "$@" >/dev/null 2>&1; then
    not_ok "$desc" "expected failure from: $*"
  else
    ok "$desc"
  fi
}

# Print the body of the CHANGELOG section whose header starts with "## [<name>]".
changelog_section() { # <file> <name>
  awk -v name="$2" '
    $0 ~ "^## \\[" name "\\]" { in_section = 1; next }
    /^## / { in_section = 0 }
    in_section { print }
  ' "$1"
}

section_contains() { # <file> <name> <text>
  changelog_section "$1" "$2" | grep -q "$3"
}

unreleased_remains_empty() { # <file>
  grep -qx '## \[Unreleased\]' "$1" &&
    ! changelog_section "$1" Unreleased | grep -q '[^[:space:]]'
}

# Build a fresh fixture repo at a known state and echo its path.
# Layout: <path> is the working clone, <path>.origin is its bare remote.
# (Runs in a command substitution, so it must not rely on parent-shell state.)
new_fixture() {
  local dir
  dir=$(mktemp -d "$WORK/fixture-XXXXXX")

  # Copy the working tree as it stands (tracked + untracked, no ignored files,
  # no .git) so in-progress work is what gets tested.
  git -C "$REPO_ROOT" ls-files -z --cached --others --exclude-standard |
    (cd "$REPO_ROOT" && tar --null -T - -cf -) | tar -xf - -C "$dir"

  # Pin the fixture to a known version state, independent of the repo's.
  jq --arg v 0.1.0 '.version = $v' "$dir/.claude-plugin/plugin.json" >"$dir/pj.tmp"
  mv "$dir/pj.tmp" "$dir/.claude-plugin/plugin.json"
  local skill
  for skill in "$dir"/skills/*/SKILL.md; do
    sed -E -i 's/^(  version:).*/\1 0.1.0/' "$skill"
  done

  # A second skill, deliberately out of step, to prove lockstep mirroring
  # covers every skill rather than one known file.
  mkdir -p "$dir/skills/probe"
  cat >"$dir/skills/probe/SKILL.md" <<'EOF'
---
name: probe
description: Fixture-only probe skill used by the release-flow tests to prove that every skill is mirrored to the plugin version in lockstep. Never shipped to users.
metadata:
  version: 0.0.1
---

# Probe

Fixture-only content. If you are reading this outside a release-flow test,
something copied the test fixture by mistake.
EOF

  # A known changelog with one entry waiting under Unreleased.
  cat >"$dir/CHANGELOG.md" <<'EOF'
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Probe entry: a change waiting to ship.
EOF

  git -C "$dir" init -q -b main
  git -C "$dir" config user.email release-test@example.invalid
  git -C "$dir" config user.name "release test"
  git -C "$dir" add -A
  git -C "$dir" commit -qm "fixture baseline"

  git init -q --bare "$dir.origin"
  git -C "$dir" remote add origin "$dir.origin"
  git -C "$dir" push -q -u origin main

  printf '%s\n' "$dir"
}

# run_release <fixture> <args...> — runs the fixture's own copy of the script,
# capturing output in <fixture>.out and exit status in RELEASE_STATUS.
run_release() {
  local dir=$1
  shift
  (cd "$dir" && ./scripts/release "$@") >"$dir.out" 2>&1
  RELEASE_STATUS=$?
}

remote_has_tag() { # <fixture> <tag>
  git ls-remote --tags "$1.origin" | grep -q "refs/tags/$2\$"
}

remote_main() { # <fixture>
  git ls-remote "$1.origin" refs/heads/main | cut -f1
}

# --- Test: a release run performs the whole release (AC 1) -------------------

test_release_run_performs_whole_release() {
  printf '\n# a release run performs the whole release, in lockstep\n'
  local F
  F=$(new_fixture)
  local baseline
  baseline=$(git -C "$F" rev-parse HEAD)

  run_release "$F" minor

  check "exits 0" test "$RELEASE_STATUS" -eq 0
  check "plugin.json pins 0.2.0" \
    test "$(jq -r .version "$F/.claude-plugin/plugin.json")" = 0.2.0
  local skill
  for skill in "$F"/skills/*/SKILL.md; do
    check "mirrors 0.2.0 into ${skill#"$F"/}" grep -qx '  version: 0.2.0' "$skill"
  done
  check "changelog gains a [0.2.0] section dated today" \
    grep -qx "## \[0.2.0\] - $TODAY" "$F/CHANGELOG.md"
  check "the unreleased entry moved into the [0.2.0] section" \
    section_contains "$F/CHANGELOG.md" 0.2.0 "Probe entry"
  check "an [Unreleased] section remains, emptied" \
    unreleased_remains_empty "$F/CHANGELOG.md"
  check "the bump is committed (clean tree)" \
    test -z "$(git -C "$F" status --porcelain)"
  check "a bump commit exists on top of the baseline" \
    test "$(git -C "$F" rev-parse HEAD)" != "$baseline"
  check "the bump commit is pushed to origin main" \
    test "$(remote_main "$F")" = "$(git -C "$F" rev-parse HEAD)"
  check "tag tutor--v0.2.0 exists on the remote" \
    remote_has_tag "$F" tutor--v0.2.0
}

# --- Test: dry run demoes the release without cutting one (AC 1) -------------

test_dry_run_cuts_nothing() {
  printf '\n# --dry-run demoes the whole release without cutting one\n'
  local F
  F=$(new_fixture)
  local baseline
  baseline=$(git -C "$F" rev-parse HEAD)

  run_release "$F" minor --dry-run

  check "exits 0" test "$RELEASE_STATUS" -eq 0
  check "prints the planned version 0.2.0" grep -q '0\.2\.0' "$F.out"
  check "prints the planned tag tutor--v0.2.0" grep -q 'tutor--v0\.2\.0' "$F.out"
  check "shows the validators passing as part of the demo" \
    grep -q 'Validation passed' "$F.out"
  check "leaves every file untouched" \
    test -z "$(git -C "$F" status --porcelain)"
  check "plugin.json still pins 0.1.0" \
    test "$(jq -r .version "$F/.claude-plugin/plugin.json")" = 0.1.0
  check "creates no commit" test "$(git -C "$F" rev-parse HEAD)" = "$baseline"
  check "creates no local tag" test -z "$(git -C "$F" tag)"
  check "pushes no tag" test -z "$(git ls-remote --tags "$F.origin")"
  check "pushes no commit" test "$(remote_main "$F")" = "$baseline"
}

# --- Test: the plugin validator gates the release (AC 1) ---------------------

test_validator_gates_the_release() {
  printf '\n# the plugin validator gates the release\n'
  local F
  F=$(new_fixture)

  # Break the plugin in a way only the validator notices: the marketplace
  # manifest loses its required owner. The release must refuse to cut.
  jq 'del(.owner)' "$F/.claude-plugin/marketplace.json" >"$F/m.tmp"
  mv "$F/m.tmp" "$F/.claude-plugin/marketplace.json"
  git -C "$F" commit -qam "break the marketplace manifest"
  git -C "$F" push -q origin main
  local baseline
  baseline=$(git -C "$F" rev-parse HEAD)

  run_release "$F" minor

  check "refuses to cut the release (nonzero exit)" \
    test "$RELEASE_STATUS" -ne 0
  check "creates no bump commit" \
    test "$(git -C "$F" rev-parse HEAD)" = "$baseline"
  check "creates no tag" test -z "$(git -C "$F" tag)"
  check "pushes no tag" test -z "$(git ls-remote --tags "$F.origin")"
  check "pushes no commit" test "$(remote_main "$F")" = "$baseline"

  run_release "$F" minor --dry-run
  check "the dry-run preflight reports the same failure" \
    test "$RELEASE_STATUS" -ne 0
}

# --- Test: successive releases stack in the changelog (AC 1, AC 2) -----------

test_successive_releases_stack() {
  printf '\n# successive releases stack: newest on top, older sections kept\n'
  local F
  F=$(new_fixture)

  run_release "$F" minor
  check "first release cuts 0.2.0" test "$RELEASE_STATUS" -eq 0

  # Queue the next change under the emptied [Unreleased] and release again.
  sed -i 's/^## \[Unreleased\]$/## [Unreleased]\n\n### Fixed\n\n- Second probe entry./' \
    "$F/CHANGELOG.md"
  git -C "$F" commit -qam "queue the next change"
  git -C "$F" push -q origin main
  run_release "$F" patch

  check "second release cuts 0.2.1" test "$RELEASE_STATUS" -eq 0
  check "plugin.json pins 0.2.1" \
    test "$(jq -r .version "$F/.claude-plugin/plugin.json")" = 0.2.1
  check "sections stack newest-first under [Unreleased]" \
    test "$(grep -o '^## \[[^]]*\]' "$F/CHANGELOG.md" | tr '\n' ' ')" = \
      "## [Unreleased] ## [0.2.1] ## [0.2.0] "
  check "the new entry lives in [0.2.1]" \
    section_contains "$F/CHANGELOG.md" 0.2.1 "Second probe entry"
  check "the first release's entry still lives in [0.2.0]" \
    section_contains "$F/CHANGELOG.md" 0.2.0 "Probe entry"
  check "tag tutor--v0.2.1 joins tutor--v0.2.0 on the remote" \
    remote_has_tag "$F" tutor--v0.2.1
}

# --- Test: bump keywords compute the next version (AC 1) ---------------------

test_bump_arithmetic() {
  printf '\n# bump keywords compute the next version\n'
  local F
  F=$(new_fixture)

  run_release "$F" major --dry-run
  check "major: 0.1.0 -> 1.0.0" grep -q 'tutor--v1\.0\.0' "$F.out"
  run_release "$F" patch --dry-run
  check "patch: 0.1.0 -> 0.1.1" grep -q 'tutor--v0\.1\.1' "$F.out"
  run_release "$F" 2.0.1 --dry-run
  check "an explicit X.Y.Z version is honoured" grep -q 'tutor--v2\.0\.1' "$F.out"
}

# --- Test: guardrails keep the release deliberate (AC 1, AC 4) ---------------

test_guardrails_keep_the_release_deliberate() {
  printf '\n# guardrails: a release is deliberate, or it is refused\n'
  local F baseline

  # A dirty working tree is not a deliberate release.
  F=$(new_fixture)
  baseline=$(git -C "$F" rev-parse HEAD)
  echo scratch >"$F/scratch.txt"
  run_release "$F" minor
  check "refuses a dirty working tree" test "$RELEASE_STATUS" -ne 0
  check "dirty tree: plugin.json still pins 0.1.0" \
    test "$(jq -r .version "$F/.claude-plugin/plugin.json")" = 0.1.0
  check "dirty tree: pushes no commit" test "$(remote_main "$F")" = "$baseline"
  check "dirty tree: pushes no tag" test -z "$(git ls-remote --tags "$F.origin")"

  # The bump must move the version forward.
  F=$(new_fixture)
  run_release "$F" 0.1.0
  check "refuses re-releasing the current version" test "$RELEASE_STATUS" -ne 0
  run_release "$F" 0.0.9
  check "refuses a downgrade" test "$RELEASE_STATUS" -ne 0
  check "downgrade: leaves every file untouched" \
    test -z "$(git -C "$F" status --porcelain)"
  run_release "$F" banana
  check "refuses a malformed version argument" test "$RELEASE_STATUS" -ne 0
  run_release "$F"
  check "refuses to run without a bump argument" test "$RELEASE_STATUS" -ne 0
  check "bad arguments: pushes no tag" test -z "$(git ls-remote --tags "$F.origin")"

  # An empty [Unreleased] means there is nothing deliberate to ship.
  F=$(new_fixture)
  baseline=$(git -C "$F" rev-parse HEAD)
  awk '/^### Added/ { exit } { print }' "$F/CHANGELOG.md" >"$F/cl.tmp"
  mv "$F/cl.tmp" "$F/CHANGELOG.md"
  git -C "$F" commit -qam "empty the unreleased section"
  git -C "$F" push -q origin main
  baseline=$(git -C "$F" rev-parse HEAD)
  run_release "$F" minor
  check "refuses to release an empty [Unreleased]" test "$RELEASE_STATUS" -ne 0
  check "empty notes: creates no bump commit" \
    test "$(git -C "$F" rev-parse HEAD)" = "$baseline"
  check "empty notes: pushes no tag" test -z "$(git ls-remote --tags "$F.origin")"
}

# --- Runner ------------------------------------------------------------------

test_release_run_performs_whole_release
test_dry_run_cuts_nothing
test_validator_gates_the_release
test_successive_releases_stack
test_bump_arithmetic
test_guardrails_keep_the_release_deliberate

printf '\n%d passed, %d failed\n' "$PASS" "$FAILED"
test "$FAILED" -eq 0
