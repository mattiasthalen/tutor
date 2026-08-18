# Research: agentskills.io packaging and claude.ai skill upload constraints

- **Issue:** [#24](https://github.com/mattiasthalen/tutor/issues/24) (part of map issue #22)
- **Date:** 2026-08-18
- **Question:** How are portable skills packaged and versioned under the agentskills.io spec, and what does claude.ai's skill upload actually support? Specifically: whether `SKILL.md` frontmatter carries a version field, what a skill ZIP must contain, what happens when a same-named skill is re-uploaded, any size or count limits, and whether upload works from a phone.

## Summary

1. The agentskills.io spec has **no top-level `version` frontmatter field**. The only sanctioned place for a version is the optional free-form `metadata` map (string keys to string values); the spec's own example shows `metadata: { author: example-org, version: "1.0" }`.
2. A claude.ai skill ZIP must contain **the skill folder as the ZIP root** (not loose files, not a nested subfolder), with `SKILL.md` inside, and the folder name must match the skill's `name`.
3. **Re-upload behavior for a same-named skill on claude.ai is undocumented** in every primary source checked. Only delete-then-re-upload is documented. Treat as unverified until tested empirically.
4. claude.ai documents that a "ZIP file exceeds size limits" error exists but **never states the number**. The nearest documented figures are 30 MB (uncompressed) for Skills API uploads and 30 MB per file for claude.ai code-execution file transfer.
5. **No primary source confirms or denies ZIP skill upload from the phone apps.** The prerequisite capability (code execution and file creation) is documented as available and toggleable on Claude Mobile (iOS/Android); the upload flow itself is only documented for the Settings web UI.
6. Real, first-class versioning exists **only in the Skills API** (`/v1/skills`): custom-skill versions are server-assigned epoch timestamps, referenced exactly or as `latest`, and each new version is a complete snapshot. claude.ai's upload UI exposes no version concept, and skills do **not** sync between claude.ai, the API, and Claude Code.

## Findings

### 1. Packaging under the agentskills.io spec

Source: [agentskills.io Specification](https://agentskills.io/specification) (also mirrored at `https://agentskills.io/specification.md`).

- A skill is a **directory** containing, at minimum, a `SKILL.md` file. Optional conventional subdirectories: `scripts/`, `references/`, `assets/`; any additional files are allowed.
- `SKILL.md` = YAML frontmatter + Markdown body. Frontmatter fields:

  | Field | Required | Constraints |
  |---|---|---|
  | `name` | Yes | 1-64 chars; lowercase `a-z`, `0-9`, hyphens; no leading/trailing hyphen; no consecutive hyphens (`--`); **must match the parent directory name** |
  | `description` | Yes | 1-1024 chars, non-empty |
  | `license` | No | license name or reference to a bundled license file |
  | `compatibility` | No | 1-500 chars; environment requirements only |
  | `metadata` | No | arbitrary map, string keys to string values |
  | `allowed-tools` | No | space-separated pre-approved tools; experimental |

- **There is no `version` field.** The spec's optional-fields example places a version inside `metadata`:

  ```yaml
  metadata:
    author: example-org
    version: "1.0"
  ```

- Guidance: keep `SKILL.md` under 500 lines / under ~5,000 tokens; name + description cost ~100 tokens at startup; keep file references one level deep; move detail into `references/`. Reinforced in [Best practices for skill creators](https://agentskills.io/skill-creation/best-practices).
- Validation: `skills-ref validate ./my-skill` using the [skills-ref reference library](https://github.com/agentskills/agentskills/tree/main/skills-ref).
- The spec defines **no packaging, ZIP, distribution, or publishing layer** — the documentation index ([llms.txt](https://agentskills.io/llms.txt)) has no such page. ZIP is purely the transport claude.ai and the Skills API use, not part of the format.
- The [Anthropic engineering post on Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) confirms the directory model and progressive disclosure and says nothing about versioning.

### 2. What a claude.ai skill ZIP must contain

Sources: [How to create custom skills](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills) (help center); [Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) (platform docs).

- The ZIP must contain **the skill folder as its root** — not the files directly, not a wrapper subfolder:

  ```text
  my-skill.zip
  └── my-skill/
      ├── SKILL.md
      └── resources/
  ```

- The **folder name must match the skill's `name`**.
- Upload flow (help center): Customize > Skills, "+", "+ Create skill", upload the ZIP. The platform docs call the location "Settings > Features"; the [Teach Claude your way of working tutorial](https://claude.com/resources/tutorials/teach-claude-your-way-of-working-using-skills) says "Settings > Capabilities > Skills". The UI naming drifts across Anthropic's own docs; the destination is the same Skills settings surface.
- Prerequisite: the **Code execution and file creation** capability must be enabled ([Use skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude); [Create and edit files with Claude](https://support.claude.com/en/articles/12111783-create-and-edit-files-with-claude)).
- claude.ai-specific frontmatter constraints (platform docs overview): `name` max 64 chars, lowercase letters/numbers/hyphens, **no XML tags, and cannot contain the reserved words "anthropic" or "claude"**; `description` non-empty, max 1024 chars, no XML tags. Note the reserved-word rule when naming tutor skills.

### 3. Versioning

- **Spec level:** no version field (section 1). A version string in `metadata` is spec-legal and ignored by runtimes; it is documentation, not mechanism.
- **Skills API** ([Using Agent Skills with the API](https://platform.claude.com/docs/en/build-with-claude/skills-guide)): the only surface with first-class versions.
  - `POST /v1/skills` creates a skill; `POST /v1/skills/{skill_id}/versions` creates a version.
  - Custom-skill versions are **server-assigned epoch timestamps** (e.g. `1759178010641129`); Anthropic's pre-built skills use date versions (e.g. `20251013`). Either an exact version or `latest` can be referenced.
  - **Each version is a complete snapshot** — files omitted from a version upload are not carried over.
  - Optional `display_title` must be **unique among custom skills in the workspace**.
  - Deleting a skill requires deleting all its versions first.
  - The [launch blog post](https://claude.com/blog/skills) confirms: "the new `/v1/skills` endpoint gives developers programmatic control over custom skill versioning and management."
- **claude.ai upload:** no version concept is documented anywhere in the help center. The documented lifecycle is upload, toggle on/off, delete ("open the skill, toggle it off, click '...', select 'Delete'"), and "If you change your mind, you can add the skill again by re-uploading the file" ([Use skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)).
- **No cross-surface sync** (platform docs overview, "Limitations and constraints"): skills uploaded to claude.ai are not available on the API and vice versa; Claude Code skills are filesystem-based and separate. Each surface is its own release channel.

### 4. Re-upload of a same-named skill (replace, duplicate, error?)

**Unverified — undocumented in primary sources.** Checked: both skills help-center articles, the platform docs overview and skills-guide, the launch blog, the engineering blog, and the agentskills.io spec. None states what claude.ai does when a ZIP with an already-used skill name is uploaded again.

Adjacent documented facts, for orientation only:

- The claude.ai delete flow plus "add the skill again by re-uploading the file" implies delete-and-re-upload is the supported update path ([Use skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)).
- On the Skills API, a duplicate `display_title` among workspace custom skills is rejected (uniqueness requirement), and updates are explicit new versions ([skills-guide](https://platform.claude.com/docs/en/build-with-claude/skills-guide)).
- In Claude Code/Cowork's `.skill` file install flow there is a "Save and Replace" prompt for same-named skills — known there because of a bug report that Replace did not actually overwrite files ([anthropic/claude-code issue #46836](https://github.com/anthropics/claude-code/issues/46836)). This is a different surface from claude.ai chat upload; do not extrapolate.

**Consequence for release flow:** assume the worst case (duplicate or error, manual delete first) until someone runs the experiment on a real account. That experiment is cheap and should precede any automation that depends on overwrite semantics.

### 5. Size and count limits

- **claude.ai ZIP size:** a limit exists but is unnumbered. The troubleshooting list in [Use skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude) names "ZIP file exceeds size limits" as an upload error without stating the value.
- **Nearest documented numbers:**
  - Skills API upload: total size **under 30 MB uncompressed** ([skills-guide](https://platform.claude.com/docs/en/build-with-claude/skills-guide)).
  - claude.ai code execution file transfer: **30 MB per file** for uploads and downloads ([Create and edit files with Claude](https://support.claude.com/en/articles/12111783-create-and-edit-files-with-claude)).
  - It is plausible the claude.ai skill ZIP limit is in the same 30 MB range, but that is inference, not a sourced fact.
- **Skill count:** no documented limit on the number of custom skills per user on claude.ai. (The API documents a runtime cap of 8 skills per request `container`, which does not apply to claude.ai chat.)
- **Context, not storage, is the real budget:** name + description of every enabled skill loads at startup (~100 tokens each); bundled files cost nothing until read ([platform docs overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview); [engineering blog](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills): bundled content is "effectively unbounded").
- Help-center vs spec discrepancy: [How to create custom skills](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills) states description max **200 characters**, while the spec and platform docs say **1024**. Staying at or under 200 satisfies every stated constraint.

### 6. Upload from a phone

**Not verified either way in primary sources.** No Anthropic document states that skill ZIP upload works, or does not work, in the iOS/Android apps.

What is documented:

- The prerequisite capability is mobile-available: "Code execution and file creation is available to all Claude users (Free, Pro, Max, Team, and Enterprise) on the web, Claude Desktop, and Claude Mobile," with a documented mobile settings path (tap initials, "Capabilities," toggle) ([Create and edit files with Claude](https://support.claude.com/en/articles/12111783-create-and-edit-files-with-claude)).
- The skill upload flow is documented only in terms of the Settings/Customize web UI ([Use skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude); [How to create custom skills](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills)).
- claude.ai in a phone's mobile browser serves the same settings surface as desktop web, so browser-based upload from a phone should behave like desktop upload — inference from it being one web app, not a documented guarantee.

**Consequence for release flow:** do not design a release step that requires the native app's skill-management UI. The safe assumption for ADR-0001's phone-primary runtime is: skills are *used* from the phone, and *installed* via the mobile browser's claude.ai settings (or from a desktop, once per release) — and this should be smoke-tested once on a real device.

### 7. Plan availability (affects who can install)

- Help center: "Skills are available for users on Free, Pro, Max, Team, and Enterprise plans" ([What are skills?](https://support.claude.com/en/articles/12512176-what-are-skills)).
- Platform docs: custom skill upload on claude.ai "Available on Pro, Max, Team, and Enterprise plans with code execution enabled" ([overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)); the [launch blog](https://claude.com/blog/skills) likewise said Pro/Max/Team/Enterprise.
- Read: skill *use* has reached Free; custom skill *upload* is documented only for paid plans. Sources disagree at the edges; the paid-plan assumption is the safe one.
- On claude.ai, custom skills are **individual to each user** (platform docs overview). Team/Enterprise owners can additionally provision org-wide skills from Organization settings ([Use skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)).

## What this means for tutor's versioning and release decisions

1. **Version must live in `metadata` (plus the release artifact name), not in a dedicated frontmatter field** — there is none, and inventing one would be off-spec.
2. **The skill folder name is the identity**: it is the required frontmatter `name`, must equal the directory name, must survive zipping as the ZIP root, and on claude.ai it is the only handle a user sees. Renaming a skill is a new skill.
3. **claude.ai has no version mechanism**, so a release is "user deletes old, uploads new ZIP" until re-upload semantics are tested. Release notes/versions must be carried in the artifact (ZIP filename, `metadata.version`), not the platform.
4. **Keep ZIPs small** (well under 30 MB uncompressed; trivially true for text skills) and descriptions at or under 200 characters to satisfy the strictest documented bound.
5. **Avoid "claude"/"anthropic" in skill names** (reserved words on the claude.ai/API surface).
6. **Two channels stay fully independent**: the Claude Code plugin (marketplace versioning) and the skill-ZIP bundle (manual per-user upload); nothing syncs between them.

## Unverified items (needs empirical testing, not more reading)

| Item | Status |
|---|---|
| claude.ai re-upload of same-named skill: replace vs duplicate vs error | Undocumented; test on a real account |
| Exact claude.ai skill-ZIP size limit | Limit exists ("ZIP file exceeds size limits" error) but the number is unpublished; 30 MB figures from adjacent surfaces are the nearest anchors |
| Skill ZIP upload from within the iOS/Android apps | Not stated anywhere; capability toggle exists on mobile; mobile-browser upload expected to work but untested |
| Max number of custom skills per claude.ai user | No documented limit found |

## Sources

- Agent Skills specification: <https://agentskills.io/specification>
- Agent Skills overview: <https://agentskills.io>
- Agent Skills best practices: <https://agentskills.io/skill-creation/best-practices>
- Agent Skills docs index: <https://agentskills.io/llms.txt>
- Claude platform docs, Agent Skills overview: <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview>
- Claude platform docs, Skills API guide: <https://platform.claude.com/docs/en/build-with-claude/skills-guide>
- Help center, What are skills?: <https://support.claude.com/en/articles/12512176-what-are-skills>
- Help center, Use skills in Claude: <https://support.claude.com/en/articles/12512180-use-skills-in-claude>
- Help center, How to create custom skills: <https://support.claude.com/en/articles/12512198-how-to-create-custom-skills>
- Help center, Create and edit files with Claude: <https://support.claude.com/en/articles/12111783-create-and-edit-files-with-claude>
- Anthropic engineering blog, Equipping agents for the real world with Agent Skills: <https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills>
- Anthropic launch blog, Skills: <https://claude.com/blog/skills> (redirect target of anthropic.com/news/skills)
- Claude tutorial, Teach Claude your way of working using Skills: <https://claude.com/resources/tutorials/teach-claude-your-way-of-working-using-skills>
- anthropics/skills repository: <https://github.com/anthropics/skills>
- Claude Code issue on "Save and Replace" for `.skill` files (adjacent surface): <https://github.com/anthropics/claude-code/issues/46836>
