---
status: accepted
---

# Claude Code is the only runtime; state lives in the Collection home

ADR-0004 cut the skill-ZIP release channel but kept claude.ai chat viable as a runtime: skills stayed free of Claude Code-only dependencies, and state travelled by paste round-trip per ADR-0002. Resolving Oracle generation (issue #32) forced the issue — producing the card-facts file needs network access and a writable file beside the Export, neither of which chat's sandbox has — and the owner no longer uses the chat path at all. So chat is retired as a target runtime entirely: tutor runs in Claude Code sessions only, and skills may rely on session affordances — files in the working directory, network access, subagents where they help.

State moves from paste round-trip to the **Collection home**: the working directory holding `collection.csv` (the Export), `oracle.jsonl` (the Oracle), and built Blocks (convention: a `decks/` folder). For the owner that folder is a private git repo — a durable deck library reachable from the phone through the Claude Code mobile app — but tutor sees only well-known filenames in a working directory; git-ness is invisible to skills. A pasted Export or Block remains a legal input and beats the file on conflict.

## Consequences

- Supersedes ADR-0002's storage model ("tutor stores nothing", state by paste). Still standing from it: ManaBox is the Collection's source of truth, and the Deck Block stays ManaBox-importable.
- Amends ADR-0001: the "skills must never depend on Claude Code-only features" consequence is dropped. Portable-skill authoring survives as a style discipline, not a runtime contract.
- Amends ADR-0004: the "ZIP channel can return cheaply" insurance clause is dropped — reviving chat would now cost real work (an Oracle upload path, paste-only ingestion).
- Amends ADR-0005: the Suite's paste-round-trip carriage is retired — the Suite lives as a file in the Collection home; a pasted Suite Block stays legal input. The checklist render survives as a human-facing view, not a chat fallback.
- Amends ADR-0006: the sequential no-subagent Review fallback loses its chat rationale — fan-out is always available; keeping the fallback is robustness, not a runtime contract.
- Evals lose the chat-simulation input mode: file-on-disk is primary; one pasted-Export case remains as parser-tolerance smoke; the manual claude.ai smoke checklist is dropped.
