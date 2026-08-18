---
status: accepted, amended by ADR-0004
---

# All capability lives in portable skills; the plugin is a thin wrapper

tutor's primary use is claude.ai chat on a phone, where plugins, slash commands, and subagents do not exist — only uploaded Agent Skills. Everything tutor can do is therefore authored as portable skills (the agentskills.io spec), shipped two ways: skill ZIPs for claude.ai upload, and a Claude Code plugin — this repo, via its own marketplace — whose commands and subagent fan-out merely wrap the same skills.

## Consequences

- Skills must never depend on Claude Code-only features; the chat path, which has no subagents, must remain fully functional on its own.
- Stage chaining is written into each skill's closing instructions (natural-language handoff), since chat has no command chaining.
- ~~Releases have two channels: marketplace version and skill-ZIP bundle.~~ Amended by ADR-0004: the skill-ZIP channel is cut — the marketplace plugin is the sole release channel, and the phone path runs through Claude Code (claude.ai/code and the mobile app). Skills still must not depend on Claude Code-only features, so the ZIP channel can return if a public audience wants it.
