---
status: accepted
---

# ManaBox is the database: state travels by paste round-trip

Chat conversations share no files, and the owner already keeps the collection and decks in ManaBox. tutor therefore stores nothing: the Collection enters as a pasted Export (or as a claude.ai Project knowledge file), and every stage ends by emitting a Block — Brief, Deck (ManaBox-importable), or Review — that the owner re-pastes into later conversations. Files, git repos, and issue trackers were rejected as artifact stores because the primary runtime (phone chat) cannot reach them.

## Consequences

- ManaBox import/export fidelity is load-bearing; the Deck Block must be a format ManaBox actually imports.
- Upgrading a deck is a fresh conversation seeded with a current Export plus existing Blocks — never a mutation of stored state.
- A claude.ai Project holding the latest Export is a convenience channel, not a requirement; plain paste must always work.
