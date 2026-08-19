---
name: brief
description: Settles a Brief — the statement of intent for a Deck — in a human-in-the-loop conversation before any card is picked, ending with a Brief Block in the Collection home. Use when the user runs /tutor:brief, asks for a new deck, shares a deck idea (a commander, a theme, a format, a table setup), or wants to revise an existing Brief.
metadata:
  version: 0.1.0
---

# Brief

The Brief is the statement of intent for a Deck: Format, identity, Power, constraints — including any play-variant asks — settled with the human before any building. This skill runs that conversation and ends with a Brief Block written to the Collection home, handing off to Build. Intent drives everything downstream; nothing here picks a card.

## Read the Collection first

1. The Collection home is the working directory; the Export lives at `collection.csv`. Read it header-keyed — never positional — UTF-8 with BOM tolerance; skip malformed rows and report a count with an example or two. A pasted Export is always accepted and beats the file on conflict: report the diff (rows added, removed, quantities changed) so drift is visible, then work from the paste.
2. Recognize the existing Decks from the Export's deck rows: a row with `Binder Type` of `deck` belongs to the Deck named by its `Binder Name`. These names are the donor vocabulary; their copies stay committed to those Decks unless this Brief frees them.
3. No Export at all? Say so and carry on — a Brief can still be settled. Donor recognition and the freshness question degrade to what is known, and the closing note recommends dropping `collection.csv` into the Collection home before Build runs.

## Settle intent, key by key

Harvest everything the opening message already gives — never re-ask what was stated. Ask only what is missing or genuinely ambiguous, batched into as few rounds as possible. The conversation pins:

- **`format:`** — required, and the only required key. A Format profile: commander, kitchen 20, casual 60, standard, modern, pioneer — or a named house format. Play variants are never Formats: Archenemy, Two-Headed Giant, and Jumpstart 40 go to `play variant:`, and the Deck is still built to some Format.
- **`centerpiece:`** — only when the Format or the Brief demands one: a Commander deck's commander, an Archenemy villain's planeswalker. Most Decks have none; never invent one.
- **`identity:`** — the color ask, when the Centerpiece does not already imply it.
- **`play variant:`** — the table setup riding on top of the Format, when one is in play: archenemy, two-headed giant, jumpstart 40.
- **`power:`** — the shared 1–5 ladder. Commander reads the number as the official WotC Bracket (1 Exhibition … 5 cEDH); the 60-card Formats read it through their profile (1 jank … 5 competitive). The number is canonical; free text may trail it ("3, battlecruiser feel"). Left unstated it defaults to 2 — omit the key and say that reading applies, rather than inventing a number. Kitchen 20 carries no Power — the Format pins it; do not ask.
- **`constraint:`** — repeatable, one line per mechanical ask: countable, deterministic, checkable — "must include Sol Ring", "nothing above 6 mana", "at least 10 ramp cards". Build turns every `constraint:` into a Check, so phrase each one checkably.
- **`donor:`** — repeatable; Decks whose committed copies this build may poach. Validate every name against the recognized Decks; on a miss, offer the recognized names instead of guessing. "The entire collection is available" is one line: `donor: all`. No donor lines means every deck-row copy stays committed, and Build reports the contention it declines.
- **`notes:`** — the fuzzy asks: feel, theme, taste — "feel like dragon tribal", "no infinite combos". Review judges these; Checks cannot. Route every ask honestly — mechanical to `constraint:`, fuzzy to `notes:` — and say which way a borderline ask went.
- **`name:`** — propose one when the human does not.

Budget asks are declined gently: tutor builds only from the Collection and carries no price semantics — no `budget:` key exists in the grammar. Unowned wishes belong on the Maybeboard at Build time.

## The freshness question — once

Staleness is asked about exactly once, in one question. Gather the facts first:

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/skills/brief/scripts/freshness.py" \
  --collection collection.csv --oracle oracle.jsonl
```

Drop `--oracle` when no Oracle exists. Then ask the one question, quoting the Export's newest `Added` timestamp — "the Export was last touched then; is it current?" — and folding in whichever staleness signals fired: the Export newer than the Oracle's watermark, or the Oracle generated more than ~30 days ago, each with the offer to regenerate via `/tutor:oracle`. When the Oracle is absent the same single question notes that Build can offer to generate one — never a second question. After the answer, move on for good: downstream stages trust their input silently.

## Close: the Brief Block

1. Assemble the Brief Block: flat `key: value` lines, one per line, no indentation, no sentinels, no version markers — a Block is recognized by shape alone. Canonical keys in canonical order: `name`, `format`, `centerpiece`, `identity`, `play variant`, `power`, `constraint` (repeatable), `donor` (repeatable), `notes`. Only `format` is required; omit every key with nothing to say. For example:

   ```
   name: Tatyova Landfall
   format: commander
   centerpiece: Tatyova, Benthic Druid
   identity: simic
   power: 2
   constraint: nothing above 6 mana
   donor: Baylen, the Haymaker
   notes: lands matter, steady card draw, no infinite combos
   ```

2. Validate before writing, and fix every reported problem until the verdict is `valid`:

   ```sh
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/brief/scripts/validate_brief.py" \
     <brief-file> --collection collection.csv
   ```

3. Write the Block to the Collection home as `decks/<slug>.brief.txt` — the growing deck library, one Brief beside the Deck it will produce. Slug the `name:` (lowercase, hyphens); fall back to the `format:` when unnamed. Show the human the final Block fenced, exactly as written.

4. Hand off: the Brief is settled and where it lives; the next step is `/tutor:build`, which reads this Brief, generates the Suite from it and the Format profile before any card is picked, and builds until the Suite is green. Revising intent later is a re-run of this conversation over the same file.

## Tables: one conversation plans the whole sitting

When the ask is a multi-deck sitting — an Archenemy night, a Commander pod, a Kitchen 20 Pack set built to combine — it is a Table, and this same conversation settles it once: one Table Brief plus one untouched per-Deck Brief per Seat, two Seats minimum. Every table-level decision — `power:`, every `constraint:`, `play variant:`, every `donor:` — is copied verbatim into each Seat's Brief, because every build session reads only its own Brief; the Table Brief is an index that never embeds the per-Deck Briefs.

1. Settle the table keys first, exactly as above: one `format:` per Table (play variants ride on top in `play variant:`, never as the Format); the shared `power:` (Kitchen 20 Tables and Seats carry no Power — the Format pins it); shared `constraint:` and `donor:` lines. A Deck seated at this Table is never a Donor Deck — table donors name outside Decks or `all`, and contention across the Table resolves by seat order, never by poaching a table-mate.
2. Settle the Seats in order, and say that seat order = build order = contention priority — the villain before the heroes, or whichever Deck the owner wants first pick: an earlier Seat's finished Deck keeps the copies it took. One `seat:` line per Deck: `seat: [role —] <deck name>[, power N]` — the role (villain, hero) optional, the trailing `, power N` only where one Seat overrides the table's Power (a villain above the heroes), and every other comma part of the deck name ("Nicol Bolas, God-Pharaoh"). Each seat's deck name joins that Seat's Brief's `name:` line exactly.
3. Then settle each Seat's own Brief in seat order — `name:`, `centerpiece:`, `identity:`, `notes:`, any seat-only constraints — with the table-level lines copied in and the Seat's effective Power declared: its `power:` equals the table's, or its seat line's override. The freshness question still fires exactly once for the whole conversation, never per Seat.
4. Validate the sitting as a whole before writing, and fix every problem until the verdict is `valid`:

   ```sh
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/brief/scripts/validate_brief.py" \
     <table-file> --collection collection.csv \
     --seat-brief <first-seat-brief> --seat-brief <second-seat-brief>
   ```

   That runs the Table Brief grammar, the seat join, the copy-down checks, and the mechanical declared-Power match — every Seat's effective Power equals the table's unless its seat line overrides. Validate each Seat's Brief on its own too, as in the close above — a Seat's Brief is an ordinary Brief.
5. Write the Table Brief to `decks/<table-slug>.table.txt` and each Seat's Brief to `decks/<slug>.brief.txt` as usual, and show every Block fenced. For example:

   ```
   table: Family Archenemy Night
   format: commander
   play variant: archenemy
   power: 3
   seat: villain — Nicol Bolas, God-Pharaoh, power 4
   seat: hero — Meren Reanimator
   ```

6. Hand off: `/tutor:build` runs once per Seat, in seat order, each session reading only that Seat's Brief — every later Seat passing each earlier Seat's finished Deck Block as `--table-mate`, so one physical copy never sits in two decks at the sitting. After the last Seat, `/tutor:review` judges the finished sitting as a whole in a Table Review. Contention a later Seat cannot live with is a human re-brief loop — revise the Briefs here, then re-run the affected Seats in seat order — never an automatic reallocation.
