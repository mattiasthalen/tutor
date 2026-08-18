---
name: hello
description: Confirms the tutor plugin is installed and responding. Use when the user runs /tutor:hello or asks to verify that tutor is installed and working.
metadata:
  version: 0.1.0
---

# Hello from tutor

Confirm to the user that the tutor plugin is installed and its command namespace works, in three short lines:

1. Read the installed plugin manifest at `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json` and report the plugin name and version from it. Do not guess the version from memory — the manifest is the sole version authority.
2. State that the `/tutor:*` command namespace is working end to end (this command reached this skill).
3. Note that `/tutor:oracle` (generate the card-facts file from an Export) is available today, and the deckbuilding loop — brief, build, review — arrives in later releases.

If the manifest cannot be read, say so plainly and report the installation as broken rather than inventing a version.
