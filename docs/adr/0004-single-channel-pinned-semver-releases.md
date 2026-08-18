---
status: accepted, amended by ADR-0007
---

# One release channel — the marketplace plugin — with a pinned semver

Claude Code now runs on every surface tutor targets, including the phone (claude.ai/code and the mobile app), so the claude.ai skill-ZIP upload channel is cut: the plugin, installed from this repo's own marketplace, is the sole shipping path. tutor pins an explicit semver in `.claude-plugin/plugin.json` — the sole version authority; the marketplace entry never carries a version — and a release is the deliberate commit that bumps it. This amends ADR-0001, whose "two channels" consequence is dropped; its core (all capability in portable skills, plugin as thin wrapper) stands, ~~and skills must stay free of Claude Code-only dependencies so the ZIP channel can return cheaply if a public audience wants it~~ — amended by ADR-0007: chat is retired as a runtime, so the cheap-return insurance is dropped.

## Considered options

- **No declared version, ride commit SHAs** — rejected: update detection is version-string inequality, so every docs/ADR/map commit on main would ship as a noise update, and a SHA gives users nothing readable to report.
- **Version in the marketplace entry** — rejected: `plugin.json` wins silently when both are set; one authority avoids the stale-mask failure `claude plugin validate` warns about.
- **Per-skill version lines** — rejected: the skills chain brief → build → review over shared Block formats; they version as one organism.
- **Keep the dual channel (skill ZIPs + plugin)** — rejected: Claude Code covers the phone path now; claude.ai upload has no version concept, so the ZIP channel carried manual re-upload toil for no reach.
- **Full CI release automation (release-please style)** — rejected: overkill for a solo prompt-ware repo; a release script gives the same guardrails without the machinery.

## Consequences

- **Release = version-bump commit.** Merges that don't bump (docs, research, map churn) deliberately ship nothing: pinned-version installs stay cached until the string changes.
- **Semver semantics for prompt-ware:** MAJOR = existing artifacts break — a Block format change an existing Brief/Deck/Review Block cannot survive through Upgrade, or a skill/command removed or renamed. MINOR = new capability — a new Format profile, skill, or Check class. PATCH = prompt fixes, wording, docs inside skills.
- **Lockstep version.** The single version is stamped into `plugin.json` and mirrored into each skill's `metadata.version` (the agentskills.io spec has no first-class version field).
- **A release script** (`scripts/release`) performs the bump: set the version, mirror it into skills, draft the `CHANGELOG.md` entry, run `claude plugin validate`, tag `tutor--v{version}` (`claude plugin tag --push` validates the tag against `plugin.json`), push. Manual bumping invites the declared-but-unbumped strand-users failure.
- **Tags every release** (`tutor--v{version}`) — future dependency constraints resolve only through that tag convention. GitHub Releases with notes are deferred until tutor goes public ("me first, the world next"); `CHANGELOG.md` (Keep a Changelog shape) is the record meanwhile.
- **Update path documented in the README:** auto-update is off by default for self-hosted marketplaces — enable it per marketplace in `/plugin`, or run `/plugin marketplace update` then `/plugin update tutor`.
- No stable/latest split: one marketplace, one channel, main is it.
