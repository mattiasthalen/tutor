# Research: How Claude Code plugin marketplaces version and update plugins

- **Ticket**: [#23](https://github.com/mattiasthalen/tutor/issues/23)
- **Date**: 2026-08-18
- **Question**: What are the versioning and update mechanics for Claude Code plugins distributed via a self-hosted marketplace? Where is a plugin's version declared, what does the version field accept, how does Claude Code discover and apply updates from a marketplace, do git tags/refs participate in version resolution, and can a marketplace pin or serve multiple versions of one plugin?

All claims below come from the official Claude Code documentation at code.claude.com, retrieved 2026-08-18. Primary sources:

- [Create and distribute a plugin marketplace](https://code.claude.com/docs/en/plugin-marketplaces) ("marketplaces doc")
- [Plugins reference](https://code.claude.com/docs/en/plugins-reference) ("reference doc")
- [Discover and install prebuilt plugins](https://code.claude.com/docs/en/discover-plugins) ("discover doc")
- [Constrain plugin dependency versions](https://code.claude.com/docs/en/plugin-dependencies) ("dependencies doc")

## Summary of the facts that constrain versioning decisions

1. A plugin's version can be declared in the plugin's `.claude-plugin/plugin.json` (`version` field) or in its entry in the marketplace's `.claude-plugin/marketplace.json`; if both are set, `plugin.json` wins silently, so the docs advise setting it in only one place.
2. The `version` field is a plain string. The docs describe it as a "Semantic version" but update detection is string equality, not semver ordering: the resolved version is a cache key, and an update happens exactly when the string changes. Semver only becomes load-bearing for dependency constraints, which use npm-style semver ranges.
3. If no `version` is declared anywhere, the version falls back down a documented resolution order: git commit SHA for git-backed sources, `sha256` digest for archive sources, `unknown` for npm and non-git local sources. Omitting `version` on a git-backed source means every pushed commit is an update signal, which the docs call "the simplest setup for internal or actively developed plugins".
4. Updates flow through the marketplace catalog: Claude Code keeps a local clone of the marketplace, refreshes it via `/plugin marketplace update` or background auto-update, then re-resolves each installed plugin's version and skips any plugin whose resolved version matches what is installed. Auto-update is off by default for third-party (self-hosted) marketplaces and on for official Anthropic ones.
5. Git refs participate at two levels: a marketplace can be added pinned to a branch or tag (`owner/repo@ref`, `url#ref`; refs only, no SHA), and each plugin source inside `marketplace.json` can pin `ref` (branch/tag) and `sha` (exact 40-char commit, which wins over `ref`). Git tags additionally drive dependency version resolution via the `{plugin-name}--v{version}` tag convention.
6. One marketplace serves exactly one resolved version per plugin name (duplicate names are a validation error, and there is no version selector on `/plugin install`). Multiple concurrent versions are done with the documented "release channels" pattern: separate marketplaces pointing at different refs or SHAs of the same repo. Pinning a single version is fully supported via the `version` string, `ref`/`sha`, npm `version`, or archive `sha256`.

## 1. Where a plugin's version is declared

Two declaration sites exist, with a defined precedence:

- **`.claude-plugin/plugin.json`** (the plugin manifest). The reference doc's manifest schema lists `version` as an optional string field: "Semantic version. Setting this pins the plugin to that version string, so users only receive updates when you bump it ... If also set in the marketplace entry, `plugin.json` wins." ([reference doc, plugin manifest schema](https://code.claude.com/docs/en/plugins-reference#plugin-manifest-schema))
- **The plugin's entry in `.claude-plugin/marketplace.json`**. Plugin entries accept a `version` field with the same pinning semantics: "If set (here or in `plugin.json`), the plugin is pinned to this string and users only receive updates when it changes." ([marketplaces doc, plugin entries](https://code.claude.com/docs/en/plugin-marketplaces#plugin-entries))

The marketplaces doc explicitly warns against setting both: "Avoid setting `version` in both `plugin.json` and the marketplace entry. Claude Code always uses the `plugin.json` value without warning, so a stale manifest version can mask a version you set in `marketplace.json`." ([marketplaces doc, version resolution](https://code.claude.com/docs/en/plugin-marketplaces#version-resolution-and-release-channels))

`claude plugin validate .` run against a marketplace directory checks entries with local-path sources and "warns when the entry's `version` doesn't match the one in `plugin.json`". ([marketplaces doc, validation errors](https://code.claude.com/docs/en/plugin-marketplaces#marketplace-validation-errors))

There is also a top-level `version` field on `marketplace.json` itself ("Marketplace manifest version"), which versions the catalog document, not any plugin. ([marketplaces doc, optional fields](https://code.claude.com/docs/en/plugin-marketplaces#optional-fields))

## 2. What the version field accepts — is semver required?

- The field's type is `string`. The schema describes it as "Semantic version" with examples like `"1.0.0"` and `"2.1.0"`, but no doc states that installation fails on a non-semver string; semver is the documented convention. ([reference doc, plugin manifest schema](https://code.claude.com/docs/en/plugins-reference#plugin-manifest-schema))
- Update mechanics treat the version as an opaque string compared for equality: "Plugin versions determine cache paths and update detection: if the resolved version matches what a user already has, `/plugin update` and auto-update skip the plugin." There is no semver ordering comparison — a changed string (including a lowered one) is simply a different version. ([marketplaces doc, version resolution](https://code.claude.com/docs/en/plugin-marketplaces#version-resolution-and-release-channels))
- The fallback versions are not semver at all: a git commit SHA, or the first 12 characters of an archive's SHA-256 digest, serve directly as the version. ([reference doc, version management](https://code.claude.com/docs/en/plugins-reference#version-management))
- Semver becomes strict only for **dependency constraints**: a dependency's `version` is "a [semver range](https://github.com/npm/node-semver#ranges) such as `~2.1.0`, `^2.0`, `>=1.4`, or `=2.1.0`", pre-releases are excluded unless the range opts in (e.g. `^2.0.0-0`), and an invalid semver range produces a `range-conflict` error. For tagged releases, the tag's `{version}` component must satisfy those ranges, so a plugin that wants to be constrainable must use real semver. ([dependencies doc](https://code.claude.com/docs/en/plugin-dependencies#declare-a-dependency-with-a-version-constraint))

### The full version resolution order

For every source type except `command`, Claude Code resolves a plugin's version from the first of these that is set ([reference doc, version management](https://code.claude.com/docs/en/plugins-reference#version-management)):

1. `version` in the plugin's `plugin.json`
2. `version` in the plugin's marketplace entry
3. The git commit SHA of the plugin's source — for `github`, `url`, `git-subdir`, and relative-path sources in a git-hosted marketplace
4. The SHA-256 digest for `archive` sources (the `sha256` pin, or the digest of the downloaded file), shortened to 12 characters
5. `unknown`, for `npm` sources or local directories not inside a git repository

A `command` source is never pinned by a declared version: its version always includes a hash of the directory the command produced (copy mode), or is derived from the printed path and top-level entries (link mode). ([marketplaces doc, command sources](https://code.claude.com/docs/en/plugin-marketplaces#command-sources))

Consequence spelled out in the docs: if you declare `"version": "1.0.0"` and push new commits without bumping it, existing users keep the cached copy, because Claude Code sees the same version. "Bump the field on every release, or omit it to fall back to the resolved version." Omitting `version` on git-backed sources means users get an update whenever the resolved commit changes — "the simplest setup for internal or actively developed plugins". ([marketplaces doc, version resolution](https://code.claude.com/docs/en/plugin-marketplaces#version-resolution-and-release-channels))

## 3. How Claude Code discovers and applies updates from a marketplace

**Discovery model.** A marketplace is registered per user (state in `~/.claude/plugins/known_marketplaces.json`) and Claude Code keeps a local copy of it — a git clone for git-based sources. Installed plugins are copied into a versioned cache at `~/.claude/plugins/cache`, laid out as `cache/<marketplace>/<plugin>/<version>/`, with each installed version a separate directory named for the resolved version. ([marketplaces doc, plugin sources](https://code.claude.com/docs/en/plugin-marketplaces#plugin-sources) and [seed directory layout](https://code.claude.com/docs/en/plugin-marketplaces#pre-populate-plugins-for-containers); [reference doc, plugin caching](https://code.claude.com/docs/en/plugins-reference#plugin-caching-and-file-resolution))

**Publishing an update** is just pushing to the marketplace repo: "Once your marketplace is live, you can update it by pushing changes to your repository. Users refresh their local copy with `/plugin marketplace update`." ([marketplaces doc, overview](https://code.claude.com/docs/en/plugin-marketplaces#overview))

**Manual refresh and update.**

- `/plugin marketplace update [name]` (or `claude plugin marketplace update`) refreshes the catalog "to retrieve new plugins and version changes". A marketplace added with a branch or tag `ref` "updates to the latest commit of that ref, not the repository's default branch". ([marketplaces doc, CLI](https://code.claude.com/docs/en/plugin-marketplaces#plugin-marketplace-update))
- `/plugin update` / `claude plugin update <plugin>@<marketplace>` re-resolves the plugin's version and skips it when the resolved version matches the installed one. ([marketplaces doc, version resolution](https://code.claude.com/docs/en/plugin-marketplaces#version-resolution-and-release-channels); [reference doc, version management](https://code.claude.com/docs/en/plugins-reference#version-management))
- Installing by full name (`/plugin install name@marketplace`) refreshes that marketplace before the lookup (Claude Code v2.1.232+), even when auto-update is off, with documented skip conditions (local-path marketplaces, seed-managed marketplaces, refreshed within the last 30 seconds, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, blocking managed settings). ([discover doc, install plugins](https://code.claude.com/docs/en/discover-plugins#install-plugins))

**Background auto-update.** "Claude Code checks for marketplace and plugin updates after your session starts, with a random delay of up to ten minutes, so the running session keeps using the versions it loaded at launch. If any plugins were updated, you'll see a notification prompting you to run `/reload-plugins`, or the new versions load on your next launch." ([discover doc, configure auto-updates](https://code.claude.com/docs/en/discover-plugins#configure-auto-updates))

Auto-update defaults and controls (all from the [discover doc](https://code.claude.com/docs/en/discover-plugins#configure-auto-updates)):

- Official Anthropic marketplaces: auto-update **on** by default. Third-party and local development marketplaces (which includes any self-hosted marketplace): auto-update **off** by default.
- Per-marketplace toggle in the `/plugin` &rarr; Marketplaces UI ("Enable auto-update" / "Disable auto-update").
- Administrators can set `"autoUpdate": true` on an `extraKnownMarketplaces` entry in managed settings.
- `DISABLE_AUTOUPDATER` disables Claude Code and plugin auto-updates; `FORCE_AUTOUPDATE_PLUGINS=1` alongside it keeps plugin auto-updates on.
- `command`-sourced plugins update on their own cadence (re-run once per session, new version installed when the output hash changes) regardless of the marketplace auto-update setting.

**Self-hosted / private-repo caveat.** The background refresh disables git credential helpers for its `git pull`, so private HTTPS marketplaces fail the pull and fall back to a re-clone (which does use stored credentials but can time out). Mitigations documented: `CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE=1`, a configured credential helper, or a global git URL rewrite embedding a read-only token; SSH remotes with a key in `ssh-agent` work in the background as-is. ([marketplaces doc, private repositories](https://code.claude.com/docs/en/plugin-marketplaces#private-repositories))

**Applying updates in a session.** Updates land on disk in the background; the running session switches only via `/reload-plugins` (with a prompt-cache warning and `--force` where relevant) or on next launch. ([discover doc, apply plugin changes](https://code.claude.com/docs/en/discover-plugins#apply-plugin-changes-without-restarting))

## 4. Whether git tags/refs participate in version resolution

Yes, at three distinct levels:

**a) Marketplace source refs.** Users can add a marketplace pinned to a branch or tag: `claude plugin marketplace add owner/repo@ref` or a git URL with `#ref`. "Git-based marketplace sources support `ref` (branch/tag) but not `sha`." A ref-pinned marketplace updates along that ref. ([marketplaces doc, marketplace add](https://code.claude.com/docs/en/plugin-marketplaces#plugin-marketplace-add) and [sources note](https://code.claude.com/docs/en/plugin-marketplaces#plugin-sources))

**b) Plugin source refs and SHAs.** The git-backed plugin source types (`github`, `url`, `git-subdir`) each accept optional `ref` ("Git branch or tag; defaults to repository default branch") and `sha` ("Full 40-character git commit SHA to pin to an exact version"). "When both `ref` and `sha` are set on any of them, the `sha` is the effective pin" — Claude Code fetches the pinned commit directly, and on most hosts install succeeds even if the ref was deleted, as long as the commit is reachable (exception: hosts that cannot fetch by SHA, e.g. AWS CodeCommit). When no explicit `version` is declared, the resolved commit SHA of this source *is* the plugin's version (resolution step 3 above). ([marketplaces doc, plugin sources](https://code.claude.com/docs/en/plugin-marketplaces#plugin-sources))

**c) Release tags for dependency version resolution.** For plugins that other plugins depend on with a semver range, Claude Code "resolves version constraints against git tags on the repository that hosts the dependency". Releases must be tagged `{plugin-name}--v{version}`, where `{version}` matches that commit's `plugin.json` version; `claude plugin tag --push` creates and pushes the tag with validation (or `git tag` manually). At install, Claude Code lists tags, filters on the `{plugin-name}--v` prefix, and fetches the highest version satisfying the range; no matching tag fails with `no-matching-tag` / "has no git tag satisfying" (relative-path dependencies fall back to the marketplace's current copy, checked at load). The name prefix "lets one marketplace repository host multiple plugins with independent version lines". A tag-resolved install's cache directory carries a 12-character commit-SHA suffix, so a force-moved tag produces a fresh cache directory. Tag-based resolution applies only to git-backed sources; for `npm`, `archive`, and `command` sources the constraint is checked at load time only. ([dependencies doc, tag plugin releases](https://code.claude.com/docs/en/plugin-dependencies#tag-plugin-releases-for-version-resolution))

Important boundary: tags drive resolution **only for dependencies with constraints**. A direct `/plugin install` of a catalog entry does not pick among tags; it takes whatever the entry's `source` resolves to (pinned `sha`, `ref`, or the default branch tip). No doc describes a user-facing way to install a specific version by tag.

## 5. Whether a marketplace can pin or serve multiple versions of one plugin

**Pinning: yes, several mechanisms.**

- Declare `version` in `plugin.json` or the marketplace entry — users stay on that string until it changes ([marketplaces doc, version resolution](https://code.claude.com/docs/en/plugin-marketplaces#version-resolution-and-release-channels)).
- Pin the source: `ref`/`sha` for git-backed sources, `version` (exact `2.1.0` or range `^2.0.0`/`~1.5.0`) for `npm` sources, `sha256` for `archive` sources ([marketplaces doc, plugin sources](https://code.claude.com/docs/en/plugin-marketplaces#plugin-sources)).
- Real-world example: Anthropic's community marketplace pins every plugin "to a specific commit SHA in the catalog" ([discover doc, community marketplace](https://code.claude.com/docs/en/discover-plugins#community-marketplace)).

**Multiple concurrent versions in one marketplace: no.** One catalog resolves each plugin name to exactly one version at a time:

- "Duplicate plugin name \"x\" found in marketplace" is a validation error — the same name cannot appear twice with different sources/versions ([marketplaces doc, validation errors](https://code.claude.com/docs/en/plugin-marketplaces#marketplace-validation-errors)).
- The install commands (`/plugin install name@marketplace`, `claude plugin install`) take no version argument in any documented form ([discover doc, install plugins](https://code.claude.com/docs/en/discover-plugins#install-plugins)).

**The documented pattern for multiple versions is release channels: one marketplace per channel.** "To support \"stable\" and \"latest\" release channels for your plugins, you can set up two marketplaces that point to different refs or SHAs of the same repo", assigned to user groups via managed settings (`extraKnownMarketplaces`). Constraint: "Each channel must resolve to a different version. ... If two refs resolve to the same version string, Claude Code treats them as identical and skips the update." ([marketplaces doc, set up release channels](https://code.claude.com/docs/en/plugin-marketplaces#set-up-release-channels))

Two adjacent facts that soften the one-version-per-catalog rule:

- The local cache does hold multiple versions of a plugin side by side (`cache/<marketplace>/<plugin>/<version>/`), but that is storage, not catalog choice ([reference doc, plugin caching](https://code.claude.com/docs/en/plugins-reference#plugin-caching-and-file-resolution)).
- Dependency constraints can effectively hold users on an older version line: `=2.1.0` keeps the dependency at 2.1.0 and "auto-update skips newer versions while plugin A is installed"; auto-update otherwise fetches a constrained dependency "at the highest git tag that satisfies every installed plugin's range, rather than at the marketplace's latest version" ([dependencies doc, how constraints interact](https://code.claude.com/docs/en/plugin-dependencies#how-constraints-interact)).

## Practical implications for a self-hosted marketplace

- Pick one version authority. Either declare `version` in each plugin's `plugin.json` (and bump it on every release, ideally enforced with `claude plugin validate` in CI), or omit it entirely on git-backed sources and let commit SHAs drive updates. Do not set it in both places.
- Use real semver in `plugin.json` and tag releases `{plugin-name}--v{version}` if any plugin will ever be a dependency of another; otherwise ranges cannot resolve.
- Auto-update is off by default for a self-hosted marketplace; either instruct users to enable it per marketplace, or (Team/Enterprise) set `"autoUpdate": true` on the managed `extraKnownMarketplaces` entry.
- For a private marketplace over HTTPS, plan for the background pull's credential limitation (`CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE=1`, credential helper, or scoped URL rewrite).
- To offer stable vs. latest, publish two marketplaces pinned to different refs of the same repo, and make sure the two refs resolve to different version strings.
