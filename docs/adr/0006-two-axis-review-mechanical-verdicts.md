---
status: accepted, amended by ADR-0007
---

# Review judges along two axes; judgment lives in Findings, aggregation is mechanical

Review is the judgment counterpart of ADR-0003's Checks, mirroring `/code-review`'s two-axis split: **Standards** — format deckbuilding craft, a format-agnostic Smell baseline plus per-Format standards from the profile, where the profile overrides the baseline — and **Brief** — fidelity to the Brief's intent. Judgment happens exactly once, at the Finding level: each Finding carries a severity (blocker or note), names cards, states the problem, and may suggest one swap. Everything above Findings is arithmetic: an axis with any blocker is `rebuild`, with only notes `playable`, clean `ship`; the overall Verdict is the worst axis. Review trusts the green Suite — it never recounts Check territory — but may flag a Check target as mis-set for the Brief, closing the "wrongly set target" loop ADR-0003 left open.

## Considered options

- **A third axis (Table / Feel / Fun)** — rejected: format-specific craft parameterizes Standards through the Format profile, and audience or fun asks are Brief material judged on the Brief axis; a third axis adds a reranking surface without new content.
- **Re-verifying Checks during Review** — rejected: recounting duplicates the Suite and blurs the ADR-0003 boundary. The one legitimate overlap is judging a target itself mis-set for the Brief.
- **Hard violations in Review** — rejected by construction: anything deterministic is a Check; every Review finding is a judgment call.
- **A judged, holistic overall verdict** — rejected: cross-axis reranking is precisely what the two-axis separation exists to prevent; worst-of keeps the merge mechanical.
- **Code-only review skill (no subagent-less path)** — rejected: ADR-0001's portability rule survives ADR-0004, so the skill keeps a sequential two-pass fallback while the plugin command fans out two parallel subagents. _Amended by ADR-0007: chat is retired, so the fallback's rationale is gone; it may stay as robustness, not as a contract._

## Consequences

- The axes are named **Standards** and **Brief**; Review Block sections carry those names.
- Smell baseline v1, names and meanings fixed (wording polished at implementation): synergy island, dead card, win-more, no comeback plan, piloting overload, fragile mana, theme tax, redundancy gap, curve lie, interaction mismatch.
- Per-Format standards live in the Format profile and are authored at implementation. Seeds: Kitchen 20 — Pack-combining quality, teaching pilotability, rare-as-payoff; Commander — politics, functional-copy redundancy, answer spread; the four 60-card Formats share one list.
- Findings are capped at five per axis, worst first, plus a one-line summary of the rest. A suggestion names an owned card as a swap or an unowned card as a Maybeboard candidate; Review never edits the Deck — Build owns edits.
- No Brief present: the review runs Standards-only and the Brief axis reports "no Brief available" — any ManaBox deck export is reviewable, tutor-built or not.
- Closing instructions are Verdict-dependent: `ship` ends with the ManaBox import suggestion; `playable` and `rebuild` offer a Build re-run that consumes the Review Block.
