# Research: testing Claude Code plugins — `claude plugin eval`, `/skill-doctor`, and skill-creator's eval workflow

Ticket: [#6](https://github.com/mattiasthalen/tutor/issues/6) (child of map [#2](https://github.com/mattiasthalen/tutor/issues/2)). Researched 2026-08-18 against Claude Code v2.1.234.

## TL;DR

- **`claude plugin eval` is real, works, and is documented in its own `--help` output — but it is in early access, gated per-organization, and has zero public documentation page as of 2026-08-18.** `code.claude.com/docs` (plugins reference, skills, commands, CLI reference) and the public `CHANGELOG.md` do not mention it at all. Anthropic's own CLI ships an offline reference document specifically because of this gap (see [Methodology](#methodology-and-source-tiers)).
- It evaluates **agent behavior with a plugin active vs. not** — an eval "case" is a prompt run through Claude Code (with the plugin loaded) and graded; there's a `--ablation with-without` mode that also runs the same prompt with the plugin absent and reports the score delta. It is not a unit-test framework for a skill's internal logic.
- **`/skill-doctor` is not a correctness/linting tool.** It is a **skill usage and context-cost report** (which skills exist, what they cost in context, how often they've been invoked, which are dead weight) — the in-session equivalent of `/plugin stats`. It asserts nothing about whether a skill behaves correctly.
- **Structural validation** (does `SKILL.md`/`plugin.json`/`marketplace.json` parse and conform to schema) is `claude plugin validate <path>`, which **is** documented and generally available today, with a `--strict` flag built for CI.
- **Behavioral/qualitative iteration on a skill** without the gated eval command is `skill-creator`'s manual eval workflow (`evals/evals.json`, subagent A/B runs, `grading.json`, `aggregate_benchmark.py`, an HTML review viewer) — first-party (Anthropic-authored), generally available today, but it is a conversational/subagent-driven workflow, not a scriptable CI command.
- For tutor specifically: nothing about `claude plugin eval` needs to be decided today for CI, because it's gated and the tutor plugin doesn't exist yet. The two pieces usable right now are `claude plugin validate --strict` (schema/structure gate) and the skill-creator workflow (behavioral iteration during authoring). See [Applying this to tutor](#applying-this-to-tutor).

## Methodology and source tiers

The question asks to cite official primary sources. Here, "official" splits into three tiers of decreasing public visibility, and I've kept the tiers explicit throughout so gated/undocumented material is never presented as if it had a public doc behind it:

1. **Tier 1 — published docs** (`code.claude.com/docs/en/*`) and the public `CHANGELOG.md` at `github.com/anthropics/claude-code`. Fetched directly via `curl` (raw Markdown, not summarized) on 2026-08-18: `plugins-reference.md`, `plugins.md`, `skills.md`, `commands.md`, `cli-reference.md`, and the full `CHANGELOG.md` (5,588 lines). **None of these mention `claude plugin eval`, `case.yaml`, `graders/`, or `/skill-doctor`.** `skills.md` and `commands.md` do document `/doctor` (the general setup-health checkup) in full.
2. **Tier 2 — running the installed CLI directly**, as the task brief explicitly sanctions. Ran locally: `claude --version`, `claude plugin --help`, `claude plugin eval --help`, `claude plugin eval init --help`, `claude plugin validate --help`. Installed build: **v2.1.234**, built `2026-08-17T01:20:38Z`, commit `7215ba60b06dff03b3e75825084c7038a013d0b0`, binary at `/opt/claude-code/bin/claude`. This is what the eval suite format, CLI flags, and exit-code summary below are sourced from, and it's authoritative for "what the shipped CLI does" even though the concepts don't have a public docs page yet.
3. **Tier 3 — strings extracted from the shipped CLI binary** (`strings -n 6 /opt/claude-code/bin/claude`, same build as above). The compiled binary embeds a first-party offline reference document — the CLI's own built-in `claude-code-guide` agent uses it to answer questions about features "newer than most training data" that have no public docs page yet, `claude plugin eval` and `/skill-doctor` being the named examples. This is Anthropic's own text about its own shipped feature, not my inference or a third party's guess — but it is *not* a public, stable doc: it's an internal reference embedded for the assistant's own use, extracted via reverse-engineering rather than published for users, and it says explicitly that its own wording may change. I quote it verbatim and mark it **[Binary]** throughout so its evidentiary weight is clear. Anyone can reproduce this by running the two commands above against the same build.

Everything below is tagged **[Docs]**, **[CLI]**, or **[Binary]** per its tier. Where I found nothing (a real gap rather than a fact), I say so rather than filling in from memory or a third-party blog — several web searches surfaced third-party "eval" plugins/tools with similar names (`eval-runner`, `PluginEval`, `cc-plugin-eval`, `skill-doctor` forks by `JoaquinCampo` and `amaljithkuttamath`); none of those are Anthropic's own `claude plugin eval` or `/skill-doctor`, and they're excluded from the findings below except where noted as "third-party, not this."

## `claude plugin eval`

### Status: early access, gated per organization — no public docs page

**[Binary]** The embedded reference is explicit: *"Early access. The commands are compiled into current builds and listed in `claude plugin --help`, but running them is gated per organization. When the gate is closed both commands print `` `plugin eval` is currently in early access `` in red and exit 1."* And on documentation: *"This file is the offline floor for questions about Claude Code's plugin evaluation harness... and there is no public documentation page for them yet."*

**[Docs]** Corroborating the "no public docs page" claim from the negative side: `code.claude.com/docs/en/plugins-reference` (1,316 lines fetched raw) contains the string `eval` exactly once, in an unrelated hooks context (`` `prompt`: evaluate a prompt with an LLM ``) — nothing about an eval subcommand, `case.yaml`, or graders. `cli-reference.md` and `skills.md` contain zero matches for `eval`. The public `CHANGELOG.md` (every released version, 5,588 lines) contains zero matches for "plugin eval" — every "eval" hit is unrelated (hook evaluation, feature-flag evaluation, `/goal` evaluation).

**[Binary]** Internally the feature is gated behind a flag named `pluginEval` (found as `earlyAccess:"pluginEval"` attached to both the `eval` and `evalInit` command definitions in the CLI's command table).

**[CLI]** `claude plugin --help` lists `eval` as a normal subcommand with no visible "beta" marker in the help text itself — the gating is enforced at runtime (org entitlement), not hidden from `--help`:
```
eval [options] [target]              Run eval cases (evals/**/case.yaml or
                                       evals/**/prompt.md + graders/*.md)
                                       against a plugin and report scored
                                       results. Target is a path, a plugin name,
                                       or a `plugin@marketplace` id — installed
                                       and skills-dir plugins both resolve (and
                                       add a no-plugin baseline arm)
```

### How enablement works

**[Binary]**
- **Default path:** *"During early access an organization is enabled server-side; enabled first-party (claude.ai / Claude API direct) clients pick this up automatically after `claude update` and a fresh session. No setting is needed on those machines."*
- **Clients that never receive the server-side flag** — Bedrock, Vertex, Foundry deployments; traffic routed through an LLM gateway or custom `ANTHROPIC_BASE_URL`; and any client with `DISABLE_TELEMETRY`, `DO_NOT_TRACK`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, or `DISABLE_GROWTHBOOK` set (these disable the feature-flag fetch entirely) — **need an enablement environment variable instead: `CLAUDE_CODE_WALNUT_SPIRE=1`**, set in the shell, `~/.claude/settings.json` under `env`, or managed/enterprise settings `env`. The reference explicitly warns *not* to rely on a repository-committed `.claude/settings.json` (or `.settings.local.json`) `env` for it, because project-level `env` isn't pre-trusted for this. **CI runners fall into this category by default** and are named explicitly: *"Enablement in CI usually needs the environment variable... set as a secret/env in the job."*
- This is genuinely undocumented publicly — I'm reporting the exact string found in the shipped binary, not a guess, but flagging plainly that (a) there is no public page confirming this variable name and (b) the binary's own reference says its wording "may change to a generic 'unavailable' message when the feature becomes generally available." Verify against a fresh `claude plugin eval --help` / error message before depending on it in CI.

### What it's for (its own mission statement)

**[Binary]** *"It is for plugin and skill authors (does my skill fire on natural prompts? does it produce the right artifact?), for teams gating plugin changes in CI, and for organizations comparing plugin versions. It measures Claude Code's behavior with a plugin active; it is not a harness for evaluating your own Claude API application, and it is unrelated to the `evals/evals.json` format some skill-authoring tools use."* — that last clause is Anthropic's own confirmation that this is a **separate, unrelated system** from skill-creator's `evals/evals.json` (see [skill-creator](#skill-creator-evalbenchmarking-workflow-generally-available-not-gated) below).

### Eval suite file format

**[CLI]** Directly from `--help`: cases live under `evals/**/case.yaml` or `evals/**/prompt.md` + `graders/*.md`, relative to the plugin root (default `evals/`, overridable — **[Binary]**: via `--eval-dir` or an `experimental.evals` setting).

**[Binary]** Discovery rules: *"A suite is every case under the plugin's eval directory... A case is a directory containing `prompt.md` and/or `case.yaml`; discovery only recognizes case directories beneath the eval directory (so a stray `case.yaml` in `tests/fixtures/` is never run with API spend), skips `node_modules`, `.git`, `.claude`, and `results`, and does not recurse into a case directory (its `graders/`, `resources/`, fixtures are not cases)... Cases run in lexicographic directory order."*

**[CLI]** Authoring a suite: `claude plugin eval init` runs an interactive interview (reads the plugin, sources realistic inputs, designs graders, pilots the suite) and writes `evals/<case>/prompt.md` + `graders/*.md`; `claude plugin eval init <name> --bare` skips the interview and writes a blank single-case template instead. Requires a TTY unless `--bare` is used.

**[Binary]** Quick-start, quoted verbatim from the embedded reference:
```
cd my-plugin                       # a directory with plugin.json or .claude-plugin/plugin.json
claude plugin eval init            # interview: writes evals/<case>/prompt.md + graders/*.md
claude plugin eval init smoke --bare   # or: a blank single-case template, no interview
claude plugin eval .               # run every case under ./evals/
claude plugin eval . --runs 1 --ablation with-without --no-scaffold   # cheap pilot with a baseline arm
```

### What a test case looks like

A case can be authored either as a `prompt.md` (freeform, interview-generated) or as a structured `case.yaml`. **[Binary]** — the CLI's own Zod schema for `case.yaml` (extracted from the binary; field names and defaults are exact):

```yaml
schema_version: string          # required
name: string                    # required, min length 1
description: string             # optional
tags: [string]                  # default: []
plugins: [string]               # optional — which plugin(s) this case targets
context:
  scaffold_script: string       # optional — bash run before the case (author-supplied; off unless --scaffold)
  history_file: string          # optional
  add_dirs: [string]            # default: []
execution:
  prompt: string                # optional
  max_turns: integer            # default 10, max 200
  timeout_seconds: integer      # default 300, max 3600
  model: string                 # optional
  allowed_tools: [string]       # default: []
  artifact_publish: boolean     # optional
  growthbook_overrides: ...     # (present in the schema; exact shape not confirmed — see Gaps)
graders: [Grader]               # discriminated union on `type`, six kinds — see below
```

### Graders — what it can assert

**[Binary]** Every grader has `type`, `name`, `weight` (positive number, default 1 — there's no `weight: 0`; remove the grader or set `arm` instead), and an optional `arm` (`"with-only"` or `"both"` — `with-only` graders, e.g. a `tool_used: Skill` check, score only the with-plugin arm and under `--ablation with-without` become a "did the plugin fire" indicator rather than part of the comparable score). All are `.strict()` — unknown fields are rejected, not ignored.

The six grader types, from the CLI's own schema:

| `type` | Fields | Checks |
|---|---|---|
| `regex` | `target` (see below), `pattern`, `flags` (JS RegExp flags: `d g i m s u v y`), `match` (`contains` \| `not_contains` \| `count:N`, default `contains`) | A JS regex against the target text |
| `tool_used` | `tool`, `input_match?`, `min?`, `max?` (nonnegative ints) | How many times a tool was called, optionally matching its input. `tool: Skill` with `min: 0, max: 0, arm: both` is the documented way to assert a skill *never* fires |
| `tool_order` | `before`, `after` (each a tool name or `{tool, input_match}`) | One tool call happened before another |
| `file_exists` | `path` | A file was produced at that path |
| `llm` | `criteria`, `focus` (same target enum, default `last_message`) | An LLM judge model scores free-text criteria against the target |
| `baseline` | `baseline_file`, `criteria` | An LLM judge compares the run's output against a reference file |

**[Binary]** `target`/`focus` options for `regex` and `llm` graders:

| Value | Content |
|---|---|
| `last_message` (default) | The agent's final assistant text |
| `trace` | The whole session as JSON, one message per line (regex sees all of it; the judge sees only the first and last 12 messages) |
| `files` | The list of file paths the agent *created* during the run (not pre-existing files, not contents) |
| `{source: file, path: ...}` | A produced file's contents — an image (PNG/JPEG/GIF/WebP) is shown to the `llm` judge as an image; other binaries are refused with a render-to-image-or-text hint |

There are **no custom-code graders by design** — structural graders (`regex`, `tool_used`, `tool_order`, `file_exists`) are free to run; `llm` and `baseline` call a judge model (`--judge-model`, default haiku) and cost money. A grader that throws reports `` grader threw: … `` and fails.

### Ablation (the "no-plugin baseline arm")

**[CLI]**
```
--ablation <mode>   Run a no-plugin baseline arm and report the score
                     delta (none | with-without; default: with-without
                     whenever a plugin resolves — by name, or from the
                     target path — and none when nothing does; under
                     with-without, graders marked with-only, incl.
                     `tool_used: Skill`, are a plugin-fired indicator
                     rather than part of the score)
```
**[Binary]** Under `with-without`, the harness runs each case twice (with the plugin active, then without) and reports Δ = with − without; a case whose plugin set resolves empty fails up front rather than silently comparing nothing to nothing.

### Running it: every CLI option

**[CLI]** Verbatim, `claude plugin eval --help` (v2.1.234):

```
Usage: claude plugin eval [options] [command] [target]

Options:
  --ablation <mode>         (see above)
  --allow-tools <tools...>  Operator grant for gated tools (Bash, Write, Edit,
                             WebFetch, mcp__*). Supports Tool(pattern:*) syntax
  --case <glob>             Filter cases by name glob
  -h, --help                Display help for command
  --json [path]              Print the full run result (prompts, graders, per-run
                             scores) as JSON to stdout, or write it to this .json
                             file
  --judge-model <model>     Override LLM-grader model (default: haiku)
  --keep-temp               Preserve scaffold dirs for debugging
  --max-cost-usd <usd>      Optional hard cost ceiling; abort and report partial
                             results if hit (exit 2). Overrun is bounded to one
                             agent run — paid graders (llm/baseline) are skipped
                             while free graders still score it
  --model <model>           Override model for all cases
  --no-publish              Keep the HTML report local only; skip publishing it
                             to claude.ai
  --no-scaffold             Explicitly skip scaffold_script
  --output-dir <dir>        Directory for aggregate-result.json (default:
                             ./evals/results/<timestamp>/)
  --publish-report          Also require publishing the report to claude.ai
                             (already default when the account supports it)
  --report <path>           Write the self-contained HTML report to <path>
                             instead of the results dir
  --runs <n>                Override per-case runs (default: case.runs ?? 3)
  --scaffold                Run each case's scaffold_script (author-supplied
                             bash, run as you — off by default, only for case
                             files you authored)
  --tag <tag...>             Filter cases by tag (repeatable)
  --threshold <0..1>        Exit 1 if any case score is below this threshold
                             (default: 1.0)
  --verbose                 Log per-message trace events to the debug log

Commands:
  init [options] [name]     Author an eval suite under evals/ via interview
                             (--bare for a blank template)
```

`claude plugin eval [target]` — target is a path, a plugin name, or `plugin@marketplace`; pointing at the plugin's root directory runs every case under its `evals/` (or filter with `--case`); pointing at a single `prompt.md`/`case.yaml` runs just that case (the enclosing plugin is still resolved for the baseline arm).

**[Binary]** A same-named `/plugin eval [path]` also exists as an **in-session slash command** (e.g. `/plugin eval ./my-skill`), distinct from the CLI invocation but running the same harness.

### Sandboxing

**[Binary]**, quoted directly because this is the exact clarification the ticket asked for and it corrects an easy assumption: *"Each run gets a throwaway directory and a pinned child environment; the 'sandbox' is isolation by relocation plus a narrow tool allowlist. **It is not an OS-level sandbox and it does not block the network** — anything a granted tool, a plugin hook, or a plugin's MCP server executes runs as you with normal network access."*

Per run, the harness creates `<tmp>/claude-eval-XXXXXX/` containing at least a `home/` directory that becomes the child process's `HOME` (with a throwaway git identity and an empty `.git` so upward git-root walks stop at the sandbox boundary) and a `home/cwd/` working directory. `--keep-temp` preserves every run's sandbox directory (workspace + `out/trace.jsonl`, with credentials already stripped) for debugging; without it, only errored runs' sandboxes are kept.

**Practical read:** this is filesystem/identity isolation to keep eval runs from polluting your real home directory or git state, not a security boundary — a compromised or malicious plugin under test still has real network and tool access equal to whatever `--allow-tools` and the plugin's own permission grants allow.

### Results, JSON output, and the HTML report

**[CLI]** `--json [path]` prints (or writes) "the full run result (prompts, graders, per-run scores)" as JSON.

**[Binary]**
- Every run writes `evals/results/<timestamp>/aggregate-result.json` (or a custom `--output-dir`) and a self-contained `report.html` (or `--report <path>`) — "self-contained" meaning it renders from the JSON document with no external fetches.
- On stdout: progress lines on stderr, then a summary table (`CASE SCORE PASS% RUNS COST NOTES`, or `CASE WITH W/OUT Δ …` under ablation).
- The JSON result has a `schemaVersion` field (currently `1`); a warning is printed if a result doesn't match the CLI's own `resultSchema.ts`. A shape excerpt found in the binary (illustrative of the `arms.with[]` per-run records): each run entry carries `score`, `passed`, `turns`, `costUsd`, `judgeCostUsd`, per-grader chips with `passed`/`weight` and (for `llm`/`baseline`) judge explanations.
- **CI note:** `--json` requires CLI **≥ 2.1.210** (≥ 2.1.224 for "current defaults"); parse `schemaVersion: 1` and tolerate unknown fields, since the format is still early-access and may evolve.
- The HTML report includes the ablation verdict, each case's prompt, grader definitions/rubrics, per-arm × per-run grader chips with explanations, judge votes, and an evidence excerpt (full text lives in the JSON). Scores are explicitly **not comparable across different suites**.
- **Publishing:** when the account can publish claude.ai artifacts (signed in with a Pro/Max/Team/Enterprise claude.ai subscription on the first-party API, artifacts not disabled for the org, not in essential-traffic-only privacy mode), the report is also published as a **private** claude.ai artifact and a `Published: <url>` line is printed; `--no-publish` keeps it local-only, `--publish-report` forces the attempt.

### Exit codes

**[Binary]**

| Code | Meaning |
|---|---|
| 0 | Every case scored ≥ `--threshold` and no case file failed to load |
| 1 | Any case below threshold; a case file failed to load/parse; no cases found; invalid option values; the early-access gate is closed; an unexpected error |
| 2 | Partial run — `--max-cost-usd` ceiling hit (partial results still written, `partialReason: "cost_ceiling"`), or the credential was rejected (`partialReason: "auth_failed"`) |
| 130 | Interrupted (Ctrl-C) — partial results written |
| 143 | Terminated (SIGTERM) |

### CI usage

**[Binary]** The embedded reference's own CI guidance, quoted directly:

> Require a build ≥ 2.1.210 for `--json` (≥ 2.1.224 for the current defaults); parse `schemaVersion: 1` and tolerate unknown fields.
> `claude plugin eval . --json results.json --threshold 0.8 --model <pinned> --judge-model <pinned> --no-publish [--max-cost-usd 20]`; or bare `--json | jq`. `--json` runs are quiet (no progress or per-case diagnostics on stderr — only load errors and `Note:`/`⚠` notices) — everything you need is in the document; to see why a case scored low, re-run it locally without `--json`. Exit 0/1/2/130/143 as in § Exit codes.
> Enablement in CI usually needs the environment variable (§ Availability), set as a secret/env in the job.
> Cost ≈ cases × runs × …

(That last line was truncated by my extraction method — see [Gaps](#gaps--what-i-could-not-confirm).) Pin `--model` and `--judge-model` explicitly in CI, since the harness's own defaults can drift across releases.

## `/skill-doctor`

**[Binary]** — this is the load-bearing correction for the ticket's framing, quoted directly: *"`/skill-doctor` is an in-session command that shows the **skill usage and context-cost report** — in an interactive terminal it opens the plugin manager's **Stats** tab (the same screen as `/plugin stats`); in non-interactive (`-p`), Remote Control, and background sessions it prints the same report as text: a table of every skill with its source, how much context its listing costs, tokens and [uses over 7 days], never-invoked warnings, unused plugins. No arguments; **not a linter** (`claude plugin validate <path>` validates structure; `claude plugin eval` tests behavior). Early access like plugin eval — only suggest it if it is in the build's command list."*

So, precisely:
- **What it asserts:** nothing about correctness. It's an inventory/cost report — which skills are installed, what each costs in context tokens, how often each has actually been invoked in the last 7 days, and which skills/plugins look unused. It's the diagnostic surface for "is my context bloated with dead skills," not "does this skill work."
- **Status:** early access, same gating posture as `claude plugin eval` — **[Docs]** confirmed absent from `commands.md`'s full command table (checked all 100+ entries; `/doctor` is documented in detail, `/skill-doctor` does not appear at all) and from `skills.md`'s bundled-skills list.
- **Relationship to other tools:** structural validation is `claude plugin validate`; behavioral testing is `claude plugin eval`; `/skill-doctor` is neither — it's cost/usage telemetry.
- Third-party community plugins named `skill-doctor` exist (e.g. `JoaquinCampo/skill-doctor`, `amaljithkuttamath/skill-doctor` on GitHub) and do act as skill linters/auditors using the `claude-code-guide` agent — but they are **not** Anthropic's own `/skill-doctor` and aren't installed or referenced anywhere in this repo. Worth flagging in case the ticket's phrasing was influenced by one of these.

## Other first-party mechanisms

### `claude plugin validate` — structural validation, generally available today

**[CLI]** Documented in its own `--help`, no gating observed:
```
Usage: claude plugin validate [options] <path>

Validate a plugin or marketplace manifest, or the skills, agents, and commands
in a directory

Options:
  -h, --help  Display help for command
  --strict    Treat warnings as errors (exit 1). Use in CI to fail on
              unrecognized fields, missing metadata, and other issues that the
              runtime tolerates.
```
**[Docs]** Referenced in `plugins.md` (fetched raw) as the standard local dev-loop tool: *"Test your plugins locally... run `/reload-plugins` to pick up the updates... Test your plugin components"* and *"Test components individually: Check each skill, agent, and hook separately."* This checks schema/shape (does `SKILL.md` frontmatter parse, does `plugin.json`/`marketplace.json` conform), not behavior.

### `/doctor` — installation and context-cost health, not skill correctness

**[Docs]** Fully documented at `code.claude.com/docs/en/commands`. Verbatim: *"Run a setup checkup that diagnoses issues and can fix them. Checks installation health, including duplicate or leftover installs, `PATH` problems, and unparseable settings files. Finds unused skills, MCP servers, and plugins versus their context cost, flags slow hooks, and checks for a newer version... Reports findings first and asks for confirmation before changing anything. From the terminal, `claude doctor` prints read-only installation diagnostics without starting a session."* This is a bundled skill (`disableBundledSkills` turns off every bundled skill except this one), generally available, no gating. It overlaps with `/skill-doctor`'s "unused skills vs. context cost" angle but is about the whole install, not a per-skill correctness or usage report, and asserts nothing about whether a skill's output is right.

### skill-creator eval/benchmarking workflow — generally available, not gated

**[First-party skill, read directly from the installed copy]** `~/.claude/skills/synced/skill-creator/SKILL.md` (Anthropic-authored; synced into this environment, present under `skills/synced/`, the location reserved for skills enabled on a claude.ai account). This is a **skill**, not a CLI command — it's a conversational workflow that has Claude itself orchestrate the evaluation, entirely separate from and (per the binary's own text above) explicitly *unrelated to* `claude plugin eval`'s `case.yaml` format. Summarized from the full file (available in full at that path):

- Test prompts and expectations go in `evals/evals.json`:
  ```json
  {
    "skill_name": "example-skill",
    "evals": [
      { "id": 1, "prompt": "User's task prompt", "expected_output": "Description of expected result", "files": [], "assertions": [] }
    ]
  }
  ```
- For each test case, Claude spawns **two subagents in the same turn**: one with the skill available, one without (or the previous version, when iterating) — an A/B comparison, conceptually parallel to `claude plugin eval`'s ablation arm but run manually via subagents rather than the CLI harness.
- A grader subagent (`agents/grader.md`) evaluates each assertion against the outputs and writes `grading.json` per run, with required fields `text`, `passed`, `evidence` (the viewer depends on these exact names).
- `python -m scripts.aggregate_benchmark <workspace>/iteration-N --skill-name <name>` rolls per-run grades into `benchmark.json`/`benchmark.md`: pass rate, time, and tokens per configuration, mean ± stddev, and the with/without delta.
- `eval-viewer/generate_review.py` launches (or writes, with `--static`, for headless environments) an HTML viewer with an "Outputs" tab (prompt, output, prior iteration, formal grades, a feedback textbox) and a "Benchmark" tab (the quantitative comparison), and collects human feedback into `feedback.json` for the next iteration.
- Separately, a **description-optimization loop** (`scripts/run_loop.py`) tests **triggering accuracy** — does the skill's `description` cause Claude to invoke it on the right prompts and correctly *not* invoke it on near-miss prompts — via a 60/40 train/test split over 20 hand-reviewed eval queries, run through `claude -p`, iterating up to 5 times and selecting the best description by held-out test score. (`claude plugin eval` covers a version of this too, via `tool_used: Skill` graders under ablation, but skill-creator's loop is purpose-built for description tuning specifically.)
- Explicitly qualitative-friendly: "subjective skills (writing style, design quality) are better evaluated qualitatively — don't force assertions onto things that need human judgment," and the whole loop is designed to run interactively with a human reviewing outputs each iteration, not headlessly in CI.

## Applying this to tutor

Grounded in the map's decisions so far ([issue #2](https://github.com/mattiasthalen/tutor/issues/2), [issue #5](https://github.com/mattiasthalen/tutor/issues/5)): tutor is both the plugin and its own marketplace — `.claude-plugin/plugin.json` + `marketplace.json` at the repo root, skills at `skills/<name>/SKILL.md`, namespaced `/tutor:<skill>`. No plugin code exists in the repo yet (this repo currently holds only `README.md` at the committed root, plus uncommitted local scaffolding), so everything below is about what becomes available once skills exist, not what to run today.

**What's usable now, ungated:**
- `claude plugin validate . --strict` in CI once `plugin.json`/`marketplace.json`/`skills/*/SKILL.md` exist — cheap, fast, catches schema drift and malformed frontmatter before anything agentic runs.
- The skill-creator workflow for iterating on each skill's behavior during authoring (the "TDD-style deck build loop" the map describes mirrors `/implement` + `/code-review`, i.e. red-green-refactor with a review pass — skill-creator's with/without subagent comparison plus human review in the HTML viewer is a reasonable fit for developing that loop's skills interactively, prompt by prompt).

**What's blocked on the early-access gate:**
- `claude plugin eval` as a CI gate for tutor's skills — mechanically it fits well (see below), but it requires org enablement, and per the binary's own CI guidance, in a CI runner that almost certainly needs the `CLAUDE_CODE_WALNUT_SPIRE=1` env var set as a secret (unverified against a public doc — confirm the exact requirement against a live `claude plugin eval --help`/error message at implementation time, since the reference itself says the wording may change before general availability).

**How the deck-build TDD loop maps onto `claude plugin eval`'s grader vocabulary, if/when it's enabled for this org:**
- `tool_used` (`tool: Skill`, matching the deck-build skill's name) — does the relevant skill actually fire on a natural deckbuilding prompt (and, with `min: 0, max: 0`, that an unrelated skill does *not* fire on an out-of-scope prompt).
- `tool_order` — does the loop run in the right sequence (e.g. collection check before decklist finalization, a validation step before a "done" claim) — a direct analogue to asserting red-then-green-then-refactor ordering.
- `file_exists` / `regex` on a `{source: file, path: ...}` target — did the run produce a decklist artifact, and does it contain (or not contain) specific cards/counts.
- `llm` — subjective judgments a structural grader can't make: is the deck coherent, on-curve, legal for the stated format.
- `baseline` — regression-test a known-good decklist for a fixed collection + brief against a reference file, to catch behavior drift across skill edits.
- `--ablation with-without` directly answers "does the tutor plugin's skill change the outcome at all" for each scenario — useful evidence for a spec's Testing Decisions section.

This eval-harness research doesn't need to block the tutor spec: `claude plugin validate` plus the skill-creator workflow cover schema and behavioral iteration today; `claude plugin eval` is a strong CI-gate candidate to adopt once (a) tutor has skills to test and (b) the org's early-access enablement is confirmed — worth a short spike at implementation time rather than a blocking dependency now.

## Gaps — what I could not confirm

Said plainly, per the brief, rather than guessed:

- **No public docs page exists for `claude plugin eval` or `/skill-doctor` as of 2026-08-18.** Confirmed by direct absence across four fetched doc pages and the full public changelog, and independently confirmed by the CLI's own embedded text ("no public documentation page for them yet"). This will presumably change when the feature leaves early access — re-check `code.claude.com/docs` at implementation time.
- **The `CLAUDE_CODE_WALNUT_SPIRE` enablement variable** is reported exactly as found in the binary, but is inherently unstable early-access surface — the same embedded text warns its own messaging may change before GA. Do not wire it into CI without first confirming behavior against a live `claude plugin eval --help`/error message on the build in use at the time.
- **`growthbook_overrides` field** in the `case.yaml` `execution` schema — present in the extracted schema, exact shape not confirmed (extraction was cut off before its definition).
- **The tail end of the CI-usage guidance** ("Cost ≈ cases × runs × …") was truncated by my extraction method before completion; the cost model (which multiplier — turns? judge calls?) is not confirmed.
- **Per-version availability table** — the embedded reference explicitly promises "the per-version table" at "§ Availability and enablement" beyond what's quoted here (which build introduced which flag/default); I did not extract the full table, only the qualitative enablement mechanism above.
- I did not have access to an org where the gate is open, so I could not run an actual `claude plugin eval` case end-to-end and observe real output — everything about behavior at runtime (report contents, JSON shape, exit codes) is sourced from the CLI's own help text and embedded reference text, not from an executed run.

## Sources consulted

- `code.claude.com/docs/en/plugins-reference` (fetched raw, 1,316 lines) — no eval coverage
- `code.claude.com/docs/en/plugins` — dev-loop / `--plugin-dir` / `/reload-plugins` guidance
- `code.claude.com/docs/en/skills` (fetched raw, ~750+ lines read) — bundled skills, `/doctor`, no eval/skill-doctor coverage
- `code.claude.com/docs/en/commands` (fetched raw, full command table) — `/doctor` documented in full; `/skill-doctor` absent
- `code.claude.com/docs/en/cli-reference` (fetched raw) — no eval coverage
- `code.claude.com/docs/llms.txt` — doc index, used to enumerate candidate pages
- `github.com/anthropics/claude-code/blob/main/CHANGELOG.md` (fetched raw, full 5,588 lines) — no "plugin eval" entries at any version, including the installed 2.1.234
- Local: `claude --version`, `claude plugin --help`, `claude plugin eval --help`, `claude plugin eval init --help`, `claude plugin validate --help` (installed CLI v2.1.234)
- Local: `strings -n 6` on the installed CLI binary (`/opt/claude-code/bin/claude`, v2.1.234, build `2026-08-17T01:20:38Z`, commit `7215ba60b06dff03b3e75825084c7038a013d0b0`) — embedded first-party reference text for `claude plugin eval` / `/skill-doctor`
- Local: `~/.claude/skills/synced/skill-creator/SKILL.md` (Anthropic-authored skill, full file read)
- `github.com/mattiasthalen/tutor` issues [#2](https://github.com/mattiasthalen/tutor/issues/2) (map, read-only) and [#5](https://github.com/mattiasthalen/tutor/issues/5) (plugin/marketplace anatomy) — repo layout context
- Web search, for completeness/negative-result confirmation only (not cited as fact sources above): third-party tools sharing similar names (`eval-runner`, `PluginEval`, `cc-plugin-eval`, `coder-eval`, `JoaquinCampo/skill-doctor`, `amaljithkuttamath/skill-doctor`) — none are Anthropic's `claude plugin eval` or `/skill-doctor`
