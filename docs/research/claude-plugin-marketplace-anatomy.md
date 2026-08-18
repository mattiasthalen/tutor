# Claude Code plugin and marketplace anatomy for mattiasthalen/tutor

Research for issue #5 (child of the wayfinder map, issue #2). Answers: what must this repo
contain to be simultaneously a Claude Code plugin named `tutor` (shipping MTG deckbuilding
skills) and its own plugin marketplace?

Primary sources are the official Claude Code docs at `code.claude.com/docs`, specifically:

- [Create plugins](https://code.claude.com/docs/en/plugins) — plugin authoring guide
- [Plugins reference](https://code.claude.com/docs/en/plugins-reference) — full manifest schema
- [Create and distribute a plugin marketplace](https://code.claude.com/docs/en/plugin-marketplaces) — marketplace schema and hosting
- [Discover and install prebuilt plugins through marketplaces](https://code.claude.com/docs/en/discover-plugins) — install UX
- [Extend Claude with skills](https://code.claude.com/docs/en/skills) — SKILL.md frontmatter

Every claim below links to the specific page (and section, where the page has anchors) it comes
from. A local installed plugin+marketplace at
`/root/.claude/plugins/cache/mattpocock/mattpocock-skills/1.2.3/` was inspected as a working
example — it is cited only as corroboration, never as the source of a claim.

## Answer in short

Put `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` side by side in the same
`.claude-plugin/` directory at the repo root. The marketplace's single plugin entry points its
`source` back at the marketplace root (`"./"` or simply the containing directory), so the
"catalog" and the "thing being catalogued" are the same repository checked out once. Skills live
in `skills/<name>/SKILL.md` under the repo root (not inside `.claude-plugin/`). Users add the
repo as a marketplace with `/plugin marketplace add mattiasthalen/tutor`, then install the
plugin with `/plugin install tutor@<marketplace-name>`. Updates propagate through git: pushing
new commits to the default branch changes what a marketplace refresh (`/plugin marketplace
update`, or background auto-update) sees, and whether that counts as a new *version* to install
depends on whether `plugin.json` pins an explicit `version` string.

## 1. The plugin manifest — `.claude-plugin/plugin.json`

**Location.** The manifest lives at `.claude-plugin/plugin.json`, inside a `.claude-plugin/`
directory at the plugin's root. Nothing else goes in that directory — commands, agents, skills,
and hooks directories must sit at the plugin root itself, not inside `.claude-plugin/`. The
plugin root is "the individual plugin's own directory: the one you pass to `--plugin-dir` or
that contains `.claude-plugin/plugin.json`. It is never `~/.claude/`." ([Create
plugins](https://code.claude.com/docs/en/plugins#plugin-structure-overview))

**The manifest itself is optional.** "The manifest is optional. If omitted, Claude Code
auto-discovers components in default locations and derives the plugin name from the directory
name. Use a manifest when you need to provide metadata or custom component paths." ([Plugins
reference](https://code.claude.com/docs/en/plugins-reference#plugin-manifest-schema)) Since
`tutor` wants a stable display name, description, and namespace, it should ship one anyway.

**Required field, if a manifest is present.** "If you include a manifest, `name` is the only
required field." `name` is the unique kebab-case identifier used for skill namespacing (e.g.
`/tutor:deck-review`). ([Plugins
reference](https://code.claude.com/docs/en/plugins-reference#required-fields))

**Optional metadata fields:** `displayName` (UI label, falls back to `name`), `version`
(semantic version string — see §5), `description`, `author` (`{name, email, url}`), `homepage`,
`repository`, `license`, `keywords` (array), `metadata` (free-form object Claude Code ignores),
`defaultEnabled` (boolean, requires v2.1.154+). ([Plugins
reference](https://code.claude.com/docs/en/plugins-reference))

**Optional component-path override fields:** `skills`, `commands`, `agents`, `workflows`,
`hooks`, `mcpServers`, `outputStyles`, `lspServers`, `experimental.themes`,
`experimental.monitors`, plus `dependencies`, `userConfig`, and `channels` for more advanced
plugins. These let a plugin point components at non-default locations; `tutor` doesn't need them
if it uses the default `skills/` layout (§3). ([Plugins
reference](https://code.claude.com/docs/en/plugins-reference))

**Minimal example** used in the docs' own quickstart:

```json
{
  "name": "tutor",
  "description": "MTG deckbuilding skills for Claude Code",
  "version": "0.1.0",
  "author": { "name": "mattiasthalen" }
}
```

(Field purposes per the quickstart table: `name` — unique identifier and skill namespace;
`description` — shown in the plugin manager; `version` — optional, gates updates; `author` —
optional, attribution.) ([Create
plugins](https://code.claude.com/docs/en/plugins#create-the-plugin-manifest))

## 2. The marketplace file — `.claude-plugin/marketplace.json`

**Location.** "Create `.claude-plugin/marketplace.json` in your repository root." It sits in the
same `.claude-plugin/` directory as `plugin.json`. ([Create and distribute a plugin
marketplace](https://code.claude.com/docs/en/plugin-marketplaces#create-the-marketplace-file))

**Required top-level fields:**

| Field | Type | Notes |
|---|---|---|
| `name` | string | Kebab-case marketplace identifier. Public-facing — appears in `/plugin install my-tool@your-marketplace`. A fixed list of names is reserved for Anthropic (`claude-code-marketplace`, `claude-plugins-official`, `claude-plugins-community`, `claude-community`, `anthropic-marketplace`, `anthropic-plugins`, `agent-skills`, `anthropic-agent-skills`, `knowledge-work-plugins`, `life-sciences`, `claude-for-legal`, `claude-for-financial-services`, `financial-services-plugins`, `first-party-plugins`, `healthcare`, plus impersonating variants) — `tutor` is not on that list. |
| `owner` | object | `{name}` required, `email`/`url` optional. |
| `plugins` | array | The catalog entries. |

([Create and distribute a plugin
marketplace](https://code.claude.com/docs/en/plugin-marketplaces#marketplace-schema))

**Optional top-level fields:** `$schema`, `description`, `version` (marketplace manifest
version, distinct from any plugin's version), `metadata.pluginRoot` (base directory prepended to
relative plugin sources), `allowCrossMarketplaceDependenciesOn`, `renames` (migrate users when a
plugin entry is renamed or dropped, requires v2.1.193+). ([Create and distribute a plugin
marketplace](https://code.claude.com/docs/en/plugin-marketplaces#marketplace-schema))

**Each plugin entry requires** `name` (kebab-case, public-facing in `/plugin install
name@marketplace`) and `source` (string or object — see below). Entries may also carry any field
from the plugin manifest schema (`description`, `version`, `author`, `homepage`, `repository`,
`license`, `keywords`, `metadata`) plus marketplace-only fields `category`, `tags`, `strict`,
`relevance`, `defaultEnabled`, and component-path overrides (`skills`, `commands`, `agents`,
`hooks`, `mcpServers`, `lspServers`). ([Create and distribute a plugin
marketplace](https://code.claude.com/docs/en/plugin-marketplaces#plugin-entries))

### How one repo serves as both the plugin and the marketplace

This is the crux of the question. The mechanism is the **relative-path plugin source**:

> "For plugins in the same repository, use a path starting with `./`... Paths resolve relative
> to the marketplace root, which is the directory containing `.claude-plugin/`."
> ([Plugin sources → Relative
> paths](https://code.claude.com/docs/en/plugin-marketplaces#relative-paths))

A marketplace entry can point `source` at the marketplace root itself — the docs' own example of
several plugins sharing one `skills/` folder "at the marketplace root (`source: "./"`)" is
exactly a plugin whose source is the repository the marketplace.json lives in. ([Advanced plugin
entries](https://code.claude.com/docs/en/plugin-marketplaces#advanced-plugin-entries)) For
`tutor`, with only one plugin in the catalog, `marketplace.json` becomes:

```json
{
  "name": "tutor",
  "owner": { "name": "mattiasthalen" },
  "plugins": [
    {
      "name": "tutor",
      "source": "./",
      "description": "MTG deckbuilding skills for Claude Code"
    }
  ]
}
```

`source: "./"` resolves to the marketplace root — the same repo checkout — so the plugin's
`skills/`, `.claude-plugin/plugin.json`, etc. are read directly from where the marketplace file
also lives. Because there is exactly one plugin entry here, the "list specific subdirectories"
caveat for shared `skills/` folders (needed when *multiple* plugins share one root) does not
apply — the default `skills/` scan just works. ([Advanced plugin
entries](https://code.claude.com/docs/en/plugin-marketplaces#advanced-plugin-entries))

The local reference plugin `mattpocock-skills` confirms this pattern in practice (corroboration,
not primary source): its `.claude-plugin/marketplace.json` has one entry, `{"name":
"mattpocock-skills", "source": "./", ...}`, sitting next to `.claude-plugin/plugin.json` in the
same directory — `/root/.claude/plugins/cache/mattpocock/mattpocock-skills/1.2.3/.claude-plugin/`.

**`strict` mode** governs authority when both files declare components. Default `true` means
`plugin.json` is authoritative and the marketplace entry can only *add* components; `false`
means the marketplace entry is the entire definition and a `plugin.json` that also declares
components is a conflict that fails to load. ([Strict
mode](https://code.claude.com/docs/en/plugin-marketplaces#strict-mode)) `tutor` should leave
`strict` at its default (`true`) — it has both a proper `plugin.json` and its own components.

**Other plugin source types** (not needed for `tutor` since everything lives in one repo, but
relevant if a future skill or MCP server moves out): `github` (`{repo, ref?, sha?}`), `url` (git,
`{url, ref?, sha?}`), `git-subdir` (`{url, path, ref?, sha?}`), `npm` (`{package, version?,
registry?}`), `archive` (zip over HTTPS, `{url, sha256?}`), `command` (locally generated plugin
directory). ([Plugin sources](https://code.claude.com/docs/en/plugin-marketplaces#plugin-sources))

## 3. Where skills/commands/agents live, and plugin skill frontmatter

**Default plugin directory layout** (all at the plugin root, i.e. the repo root for `tutor`):

| Component | Default location | Purpose |
|---|---|---|
| Manifest | `.claude-plugin/plugin.json` | Metadata (optional) |
| Skills | `skills/<name>/SKILL.md` | Preferred for new plugins |
| Commands | `commands/*.md` | Flat legacy skill files — "use `skills/` for new plugins" |
| Agents | `agents/*.md` | Subagent definitions |
| Hooks | `hooks/hooks.json` | Event handlers |
| MCP servers | `.mcp.json` | MCP server definitions |
| LSP servers | `.lsp.json` | Code-intelligence servers |
| Monitors | `monitors/monitors.json` | Background monitors |
| Executables | `bin/` | Added to Bash tool `$PATH` while plugin is enabled |
| Settings | `settings.json` | Only `agent` and `subagentStatusLine` keys supported |

("Don't put `commands/`, `agents/`, `skills/`, or `hooks/` inside the `.claude-plugin/`
directory. Only `plugin.json` goes inside `.claude-plugin/`. All other directories must be at
the plugin root level." — [Create
plugins](https://code.claude.com/docs/en/plugins#plugin-structure-overview))

**Adding skills.** "Add a `skills/` directory at your plugin root with Skill folders containing
`SKILL.md` files... Each `SKILL.md` contains YAML frontmatter and instructions. Include a
`description` so Claude knows when to use the skill." ([Create
plugins](https://code.claude.com/docs/en/plugins#add-skills-to-your-plugin)) A plugin that ships
exactly one skill may instead place `SKILL.md` directly at the plugin root with no `skills/`
subdirectory — Claude Code auto-loads it as a single skill. `tutor` will ship multiple MTG
deckbuilding skills, so it should use the `skills/<name>/SKILL.md` layout, not the single-file
form.

**Namespacing.** Plugin skills are always namespaced as `/plugin-name:skill-name` (e.g.
`/tutor:deck-review`) to avoid collisions with personal, project, and other plugins' skills. The
namespace prefix comes from `plugin.json`'s `name` field. ([Create
plugins](https://code.claude.com/docs/en/plugins#why-namespacing))

**Skill frontmatter** works identically for plugin-bundled skills as for personal/project
skills — same YAML fields between `---` markers, same rules — with one difference in how the
*command name* is derived. All frontmatter fields are optional; only `description` is
recommended. ([Extend Claude with
skills](https://code.claude.com/docs/en/skills#frontmatter-reference))

Key fields (full table on the skills page): `name` (display name; for a **plugin** skill it
supplies the last segment of the invocation command, e.g. `name: fancy` on
`tutor/skills/review/SKILL.md` yields `/tutor:fancy` instead of `/tutor:review`), `description`
(what/when — used for auto-invocation), `disable-model-invocation` (user-only trigger, good for
side-effecting skills), `user-invocable` (`false` hides it from `/`, Claude-only), `allowed-tools`
/ `disallowed-tools`, `argument-hint`, `arguments`, `context: fork` (run in a subagent), `agent`
(which subagent type for a forked skill), `model`, `effort`, `paths` (glob-restricted
auto-activation), `hooks`, `shell`, `metadata`, `license`, `compatibility`. ([Extend Claude with
skills](https://code.claude.com/docs/en/skills#frontmatter-reference))

**Command-name derivation table** (relevant row): "Plugin `skills/` subdirectory → Frontmatter
`name` or the directory name, namespaced by plugin → `my-plugin/skills/review/SKILL.md` →
`/my-plugin:review`, or `/my-plugin:fancy` with `name: fancy`." ([Extend Claude with
skills](https://code.claude.com/docs/en/skills#how-a-skill-gets-its-command-name))

**Path-override semantics** if `tutor`'s `plugin.json` ever needs non-default paths: the
`skills` field *adds to* the default `skills/` scan (both are loaded), whereas `commands`,
`agents`, `workflows`, `outputStyles`, and the `experimental.*` fields *replace* their defaults
outright. All custom paths must be relative to the plugin root and start with `./` (the `skills`
field alone also accepts `"."`). ([Plugins reference → Path behavior
rules](https://code.claude.com/docs/en/plugins-reference#path-behavior-rules))

**Portability note:** Claude Code accepts every frontmatter field above, but if any `tutor` skill
is ever uploaded outside Claude Code (claude.ai skill upload, Skills API), only six spec fields
survive: `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` — an
unsupported field is a hard packaging error there, not a silent drop. Not a concern for a
Claude Code plugin distributed only via this marketplace, but worth knowing if skills get reused
elsewhere. ([Extend Claude with skills → Using skill frontmatter outside Claude
Code](https://code.claude.com/docs/en/skills#using-skill-frontmatter-outside-claude-code))

## 4. Install UX

Two-step flow: register the marketplace, then install the plugin from it. ([Discover and install
prebuilt plugins](https://code.claude.com/docs/en/discover-plugins#how-marketplaces-work))

**Add the marketplace**, GitHub `owner/repo` shorthand:

```
/plugin marketplace add mattiasthalen/tutor
```

"Add a GitHub repository that contains a `.claude-plugin/marketplace.json` file using the
`owner/repo` format." (`/plugin market` also works as a shortcut for `/plugin marketplace`.)
([Discover and install prebuilt plugins → Add from
GitHub](https://code.claude.com/docs/en/discover-plugins#add-from-github)) This registers the
catalog only — no plugin is installed yet.

**Install the plugin:**

```
/plugin install tutor@<marketplace-name>
```

`<marketplace-name>` is `marketplace.json`'s top-level `name` field (not necessarily the plugin
name, though they can match). Since `tutor` is a single-plugin, self-referencing repo, naming
both the plugin (`plugin.json`'s `name`) and the marketplace (`marketplace.json`'s `name`)
`"tutor"` is reasonable, giving `/plugin install tutor@tutor`. The command "opens that plugin's
details, where you choose an installation scope" — User (all projects), Project (shared via
`.claude/settings.json`), or Local (this repo only, not shared). ([Discover and install prebuilt
plugins → Install plugins](https://code.claude.com/docs/en/discover-plugins#install-plugins))
"In these identifiers, `plugin-name` is the plugin's `name` in the marketplace entry, which can
differ from the `name` in the plugin's own `plugin.json`." ([Discover and install prebuilt
plugins → Manage installed
plugins](https://code.claude.com/docs/en/discover-plugins#manage-installed-plugins))

Non-interactive/CLI equivalents exist for scripting: `claude plugin marketplace add
mattiasthalen/tutor` and `claude plugin install tutor@tutor [--scope project|user|local]`.
([Discover and install prebuilt plugins → Manage marketplaces from the
CLI](https://code.claude.com/docs/en/discover-plugins#manage-marketplaces-from-the-cli))

After install, check the summary line: `Plugin is now active.` means it loaded immediately;
`Run /reload-plugins to activate.` means the user must run that command (or restart) before the
skills appear. ([Discover and install prebuilt plugins → Install
plugins](https://code.claude.com/docs/en/discover-plugins#install-plugins))

## 5. Versioning and how updates propagate

Claude Code resolves a plugin's *current version* — the cache key it compares against what's
installed to decide whether an update exists — from the first of these that is set (all source
types except `command`):

1. `version` in the plugin's own `plugin.json`
2. `version` in the plugin's marketplace entry in `marketplace.json`
3. The git commit SHA of the plugin's source, for `github`, `url`, `git-subdir`, and
   **relative-path sources in a git-hosted marketplace** — this is `tutor`'s case
4. The SHA-256 digest, for `archive` sources
5. `unknown`, for `npm` sources or local directories outside a git repo

([Plugins reference → Version
management](https://code.claude.com/docs/en/plugins-reference#version-management))

**Practical consequence for `tutor`:** because the plugin's `source` is a relative path (`"./"`)
inside a git-hosted marketplace (this same GitHub repo), if `plugin.json` omits `version`
entirely, Claude Code falls back to the repository's current commit SHA as the version. Every
push to the tracked branch is then a "new version" as far as update-checking is concerned. If
`plugin.json` sets an explicit `version` string instead, that string pins the plugin — "users
only receive updates when you bump it" — and pushes that don't bump it are invisible to update
checks, even if the commit SHA changed. Setting `version` in *both* `plugin.json` and the
marketplace entry is discouraged: "Claude Code always uses the `plugin.json` value without
warning, so a stale manifest version can mask a version you set in `marketplace.json`." ([Create
and distribute a plugin marketplace → Version resolution and release
channels](https://code.claude.com/docs/en/plugin-marketplaces#version-resolution-and-release-channels))

**How the update actually reaches a user:**

- Manual refresh: `/plugin marketplace update` (or `/plugin marketplace update tutor` for just
  this one) re-fetches the catalog; a subsequent `/plugin install`/`/plugin update` picks up the
  new version. ([Create and distribute a plugin marketplace →
  Overview](https://code.claude.com/docs/en/plugin-marketplaces#overview): "Once your
  marketplace is live, you can update it by pushing changes to your repository. Users refresh
  their local copy with `/plugin marketplace update`.")
- Background auto-update: "Claude Code checks for marketplace and plugin updates after your
  session starts, with a random delay of up to ten minutes... If any plugins were updated,
  you'll see a notification prompting you to run `/reload-plugins`, or the new versions load on
  your next launch." Auto-update is **off by default for third-party and local development
  marketplaces** (only official Anthropic marketplaces have it on by default), so a `tutor` user
  must explicitly enable it per-marketplace via `/plugin` → Marketplaces → Enable auto-update
  for pushes to reach them automatically. ([Discover and install prebuilt plugins → Configure
  auto-updates](https://code.claude.com/docs/en/discover-plugins#configure-auto-updates))
- Installing with an explicit marketplace name (`tutor@tutor`) always refreshes that marketplace
  first (with minor caching/skip exceptions), so a fresh install picks up the latest commit even
  without auto-update enabled. ([Discover and install prebuilt plugins → Install
  plugins](https://code.claude.com/docs/en/discover-plugins#install-plugins))
- Either way, an already-active plugin needs `/reload-plugins` to pick up changes without a
  restart, and that reload is skipped with a warning if it would invalidate the prompt cache
  (until rerun with `--force`). ([Discover and install prebuilt plugins → Apply plugin changes
  without
  restarting](https://code.claude.com/docs/en/discover-plugins#apply-plugin-changes-without-restarting))

**Recommendation for `tutor`:** set an explicit `version` in `plugin.json` and bump it on
releases (e.g. via a CHANGELOG/tag convention) rather than relying on the bare commit-SHA
fallback — it gives predictable, intentional release points instead of every commit counting as
an update candidate.

## 6. Proposed file tree for mattiasthalen/tutor

```
tutor/                                   # repo root = marketplace root = plugin root
├── .claude-plugin/
│   ├── marketplace.json                 # this repo's own catalog, single entry, source: "./"
│   └── plugin.json                      # plugin manifest, name: "tutor"
├── skills/
│   ├── deck-building/
│   │   └── SKILL.md                     # illustrative — core deckbuilding workflow skill
│   ├── mana-base-analysis/
│   │   └── SKILL.md                     # illustrative — mana curve / color balance
│   └── format-legality-check/
│       └── SKILL.md                     # illustrative — format/banlist validation
├── agents/                              # optional: custom subagents (e.g. a deck-reviewer)
├── commands/                            # optional, legacy flat-file skills — prefer skills/
├── hooks/
│   └── hooks.json                       # optional
├── .mcp.json                            # optional: e.g. a card-database MCP server
├── docs/
│   ├── agents/
│   │   ├── domain.md
│   │   ├── issue-tracker.md
│   │   └── triage-labels.md
│   └── research/
│       └── claude-plugin-marketplace-anatomy.md   # this document
├── CLAUDE.md
├── LICENSE
└── README.md
```

Notes on the tree:

- `.claude-plugin/` holds only the two manifest files — no `skills/`, `commands/`, `agents/`, or
  `hooks/` inside it, per the explicit warning in the plugin-authoring guide.
- `marketplace.json`'s single plugin entry uses `"source": "./"`, so it resolves to the repo
  root — the same place `plugin.json` and `skills/` live. No second repo, no separate hosting.
- Skill names above (`deck-building`, `mana-base-analysis`, `format-legality-check`) are
  illustrative placeholders for future implementation tickets, not a commitment from this
  research ticket.
- `docs/agents/` and `CLAUDE.md` reflect this repo's existing conventions (issue tracker,
  triage labels, domain docs) and are unaffected by the plugin/marketplace layout.

## Sources

- [Create plugins](https://code.claude.com/docs/en/plugins)
- [Plugins reference](https://code.claude.com/docs/en/plugins-reference)
- [Create and distribute a plugin marketplace](https://code.claude.com/docs/en/plugin-marketplaces)
- [Discover and install prebuilt plugins through marketplaces](https://code.claude.com/docs/en/discover-plugins)
- [Extend Claude with skills](https://code.claude.com/docs/en/skills)
- Corroboration only (not cited as source of any claim): local installed plugin+marketplace at
  `/root/.claude/plugins/cache/mattpocock/mattpocock-skills/1.2.3/`
