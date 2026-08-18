# tutor

Domain glossary for tutor — a deckbuilder that constructs Magic: The Gathering decks from the owner's physical collection.

## Language

**Collection**:
The owner's physical Magic: The Gathering cards. Every Deck is built only from the Collection.
_Avoid_: inventory, library (an MTG zone)

**Export**:
The CSV file ManaBox produces representing the Collection — its digital form. Each card row records where it lives — a binder or one of the owner's ManaBox decks — so an Export carries deck assignments.
_Avoid_: dump, backup

**Collection home**:
The folder where the Export, the Oracle, and built Blocks live — the working directory a tutor session runs in. The owner's is a private git repo doubling as a deck library, reachable from the phone; tutor sees only a folder.
_Avoid_: workspace, vault

**Brief**:
The statement of intent for a Deck: Format, identity, Power, constraints — including any play-variant asks. Settled with the human before any building.
_Avoid_: spec, requirements

**Deck**:
A playable list of cards drawn from the Collection that satisfies a Brief.
_Avoid_: list, build

**Review**:
The judgment of a finished Deck along the two review axes: Standards (format deckbuilding craft) and Brief (fidelity to the Brief's intent).
_Avoid_: audit, critique

**Finding**:
A single Review judgment on one axis: a severity — blocker (would not play as-is) or note (works, but a better line exists) — the card or cards it names, the problem, and at most one suggestion: an owned swap or an unowned Maybeboard candidate. Findings judge; they never edit the Deck.
_Avoid_: issue (a tracker term), comment

**Verdict**:
The computed outcome of a Review: ship, playable, or rebuild. Each axis gets one — any blocker means rebuild, only notes mean playable, clean means ship — and the overall Verdict is the worst axis. Verdicts are arithmetic over Findings, never fresh judgment.
_Avoid_: score, grade

**Smell**:
A named heuristic on the Standards axis — the format-agnostic baseline every Review applies unless the Format profile overrides it. A Smell is always a judgment call, never a hard violation; deterministic failures belong to Checks.
_Avoid_: violation, error

**Block**:
A fenced code block that carries a Brief, Deck, Review, Suite (with its red/green Report), Table Brief, or Table Review between sessions. Lives as a file in the Collection home; a pasted Block is always accepted and beats the file on conflict.
_Avoid_: snippet, export (that's ManaBox's)

**Board**:
A named section of a Deck Block — Commander, Mainboard, Sideboard, or Maybeboard. A Deck Block carries only the Boards its Format uses.
_Avoid_: zone (an MTG term), section

**Maybeboard**:
The wishlist Board: upgrade candidates worth a future slot, possibly outside the Collection. Not part of the playable Deck — the one place unowned cards may appear.
_Avoid_: wishlist, sideboard

**Upgrade**:
Rebuilding an existing Deck against a fresh Export and a possibly revised Brief.
_Avoid_: respec, refresh

**Donor Deck**:
A Deck the Brief names as fair game for poaching — its cards count as available while building. Cards in any Deck not named a Donor Deck stay committed to it. The Brief may name every Deck at once ("the entire collection is available"). Decks seated at the same Table are never Donor Decks for each other.
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
The full set of Checks generated for one Deck from its Brief and Format at Build start — red on an empty Deck (bar vacuously passing constraint Checks), all green when the Build is done. Declarative data interpreted by a fixed runner, never code (ADR-0005).
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

**Table**:
A set of Decks built together for one sitting — an Archenemy villain versus three heroes, or three Commander decks for a pod — matched in Power and drawn from one Collection. Every Table plays one Format; its Decks fill Seats.
_Avoid_: pod (one specific table shape), match

**Power**:
How strong a Deck aims to be — a 1–5 ladder declared in the Brief. Commander reads the number as its official Bracket (1 Exhibition to 5 cEDH); other Formats read it through their own profile. Kitchen 20 Decks carry no Power: the Format pins it.
_Avoid_: tier, power level

**Seat**:
A slot in a Table: an optional role (villain, hero) plus the Deck that fills it. Seat order in the Table Brief is build order and contention priority — an earlier Seat's Deck keeps the copies it took.
_Avoid_: player (a Seat names a Deck, not a person), slot

**Table Brief**:
The statement of intent for a Table: Format, play variant, shared Power and constraints, and one Seat line per Deck. An index — it names each Seat's Deck and rides alongside the per-Deck Briefs, never embedding them.
_Avoid_: pod spec, event brief

**Table Review**:
The judgment of a finished Table as one sitting — Power spread, clashing play patterns, contention fallout — once every Seat is built. Judges the sitting; per-Deck Reviews judge the Decks.
_Avoid_: audit, group review
