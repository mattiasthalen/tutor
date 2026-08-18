---
status: accepted
---

# A deck test is a Suite of deterministic Checks, generated test-first

"TDD for decks" means: at Build start the Suite — every Check the Deck must pass — is generated from the Brief and the Format profile, before any card is picked; an empty Deck starts all red, and Build adds and swaps cards until the Suite is green. A Check is a deterministic, binary pass/fail predicate over the Deck and its card facts (the Oracle) — anything requiring judgment or taste belongs to Review, never to a Check.

## Considered options

- Judgment-flavored checks ("enough synergy") — rejected: they blur the Check/Review boundary and make red/green unrepeatable.
- Test-after validation (build the whole deck, then run the checks as a gate) — rejected: red drives card choice; a gate at the end is not TDD.
- A third "warn" verdict — rejected: a warning is either a Review axis in disguise or a wrongly set target.
- Goldfishing/turn simulation as checks — rejected: non-deterministic and expensive. Only closed-form opening-hand math (hypergeometric) qualifies as a Check, and only where a Format profile defines a threshold.

## Consequences

- Check classes in v1: Legality (Format-parameterized, including Kitchen 20's packet rules), Availability (against the Collection), Mana base, Curve, Quotas (counts over Role tags), mechanical Brief constraints, and hypergeometric consistency where the profile sets a threshold. No budget class.
- Targets come from the Format profile, overridden only by the Brief — Build never bends a target silently, and may end red with an honest report when the Collection cannot green a Check.
- Checks run data-backed against the Oracle (chat: Project knowledge beside the Export; Claude Code: Scryfall bulk/API). With no Oracle present, Build falls back to model knowledge and must flag affected classes as best-effort.
