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
