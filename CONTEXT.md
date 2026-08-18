# tutor

Domain glossary for tutor — a deckbuilder that constructs Magic: The Gathering decks from the owner's physical collection.

## Language

**Collection**:
The owner's physical Magic: The Gathering cards. Every Deck is built only from the Collection.
_Avoid_: inventory, library (an MTG zone)

**Export**:
The CSV file ManaBox produces representing the Collection — its digital form. Each card row records where it lives — a binder or one of the owner's ManaBox decks — so an Export carries deck assignments.
_Avoid_: dump, backup

**Brief**:
The statement of intent for a Deck: Format, identity, budget, power, constraints — including any play-variant asks. Settled with the human before any building.
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

**Donor Deck**:
A Deck the Brief names as fair game for poaching — its cards count as available while building. Cards in any Deck not named a Donor Deck stay committed to it.
_Avoid_: source deck

**Format**:
A named set of deck-construction rules that a Deck declares and checks read: deck size, copy limits, color rules, banlist. Formats are first-class — Commander is one Format among others, including house formats.
_Avoid_: game mode

**Play variant**:
A table setup that changes game rules, not deck-construction rules — Archenemy, Two-Headed Giant, and Jumpstart 40 (two Packs shuffled together) are play variants, not Formats. A play variant shapes the Brief; the Deck itself is built to some Format.
_Avoid_: format (for table setups)

**Centerpiece**:
The card a Deck is built around, when its Format or Brief demands one — a Commander deck's commander (legendary creature, sets color identity), an Archenemy villain's planeswalker. Most Decks have none.
_Avoid_: boss, face card

**Kitchen 20**:
House Format mirroring the Foundations Beginner Box packets: themed, mono-color, 20-card Decks for teaching and quick games. Every Kitchen 20 Deck is a Pack.
_Avoid_: beginner deck, starter deck

**Pack**:
A Kitchen 20 Deck seen as a Jumpstart-style half: any two Packs shuffle into a 40-card game. Combining well with other Packs is part of what makes a Kitchen 20 Deck good.
_Avoid_: half-deck, booster, packet

**Check**:
A deterministic pass/fail predicate over a Deck — same Deck, same card facts, same verdict, every run. Checks never judge taste; judgment belongs to Review.
_Avoid_: test (tutor's own software tests), rule

**Suite**:
The full set of Checks generated for one Deck from its Brief and Format at Build start — all red on an empty Deck, all green when the Build is done.
_Avoid_: checklist, test suite

**Role**:
A card's function tag counted by quota Checks: ramp, draw, removal, wipe, wincon, land, theme/other. One card may carry several Roles and counts toward each. Tagging a card is judgment; counting tags is mechanical.
_Avoid_: category, archetype

**Oracle**:
The Scryfall-derived card-facts file covering the Collection — the data Checks run against. Companion artifact to the Export.
_Avoid_: dump, card database

**Eval**:
A test of tutor itself — does a skill produce a sound Brief, Deck, or Review. Evals judge tutor; Checks judge Decks.
_Avoid_: test (unqualified), Check (that judges a Deck, not tutor)
