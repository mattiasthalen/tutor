# Spike: the gated `claude plugin eval` enablement

**Date**: 2026-08-18 · **Ticket**: #48 · **Status**: recorded, not a blocker

## Question

The spec stages the eval harness: the skill-creator eval workflow is the
dev-time behavioral harness now, and the org-gated, publicly undocumented
`claude plugin eval` becomes the CI behavioral gate when enablement lands.
What is actually gated today, and what will the port cost when it opens?

## What the spike observed (Claude Code CLI 2.1.234, 2026-08-18)

- The subcommand **exists and is fully self-documented**: `claude plugin eval
  --help` describes case discovery (`evals/**/case.yaml`, or
  `evals/**/prompt.md` + `graders/*.md`), per-case `runs` (default 3), a
  score `--threshold` (exit 1 below it), `--judge-model` LLM grading
  (default haiku), free graders such as `tool_used: Skill`, an
  `--ablation with-without` no-plugin baseline arm, cost ceilings, and an
  HTML report that publishes to claude.ai by default when the account
  supports it.
- **Execution is gated.** Running `claude plugin eval . --no-publish` in this
  repo prints exactly:

  ```
  `plugin eval` is currently in early access
  ```

  and exits 0 without discovering or running any case. The gate sits in
  front of case discovery, so nothing in-repo can trip it by accident —
  including our `evals/` tree, which it would otherwise scan.
- No public docs cover the enablement path; the gate message names no
  program to apply to. Presumably org-level early access, granted outside
  the CLI.

## Decision recorded

Eval cases are authored **now** in the skill-creator eval workflow format
(`evals/evals.json`, graded offline by `evals/run_evals.py`) and **ported
when enablement lands**. This is not a blocker: the offline harness runs
today, deterministically, with no gate in front of it.

## Porting map (when the gate opens)

The grader vocabulary maps cleanly onto the loop, as the spec expected:

| skill-creator format (now)            | `claude plugin eval` (later)              |
| ------------------------------------- | ----------------------------------------- |
| `evals.json` case (id, prompt, files) | one `evals/<case>/case.yaml` per case     |
| mechanical expectation + fixed predicate in `run_evals.py` | free/programmatic grader |
| soft expectation (dev-time judgment)  | LLM grader under `--judge-model`          |
| with_skill / without_skill runs       | `--ablation with-without` arms            |
| grading.json pass/fail                | case score vs `--threshold`               |

Two local facts already line up: `claude plugin eval` writes results to
`./evals/results/<timestamp>/` by default, which this repo already
gitignores, and its fixture inputs stay ours — cases point at
`evals/fixtures/`, so determinism and the no-live-Scryfall rule carry over
unchanged.

## Re-check trigger

Re-run the probe (`claude plugin eval . --no-publish`) after CLI upgrades or
when Anthropic announces plugin-eval general availability; when the gate
message disappears, open the porting ticket.
