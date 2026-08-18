# tutor

Domain glossary for tutor — a deckbuilder that constructs Magic: The Gathering decks from the owner's physical collection.

## Language

**Collection**:
The owner's physical Magic: The Gathering cards. Every Deck is built only from the Collection.
_Avoid_: inventory, library (an MTG zone)

**Export**:
The CSV file ManaBox produces representing the Collection — its digital form. Whether it also carries deck assignments is under verification.
_Avoid_: dump, backup

**Brief**:
The statement of intent for a Deck: format, identity, budget, power, constraints. Settled with the human before any building.
_Avoid_: spec, requirements

**Deck**:
A playable list of cards drawn from the Collection that satisfies a Brief.
_Avoid_: list, build

**Review**:
The judgment of a finished Deck against the review axes.
_Avoid_: audit, critique

**Block**:
A re-pasteable fenced code block that carries a Brief, Deck, or Review between conversations. The interchange artifact of the paste round-trip.
_Avoid_: snippet, export (that's ManaBox's)

**Upgrade**:
Rebuilding an existing Deck against a fresh Export and a possibly revised Brief.
_Avoid_: respec, refresh
