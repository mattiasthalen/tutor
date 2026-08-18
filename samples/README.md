# ManaBox export samples

Landing spot for real ManaBox export files, captured for
[issue #16](https://github.com/mattiasthalen/tutor/issues/16) — verifying the parser
assumptions the ManaBox research (issue #3) left at low confidence.

## What goes here

- `collection*.csv` — a whole-collection CSV export (ManaBox: collection tab → top-right
  menu → export CSV). Ideally the collection holds at least one non-English card (a Chinese
  printing is the disputed case), one non-Near-Mint card, one foil and one etched card, and
  one card whose name contains a comma.
- `deck*.txt` — one deck exported as a plain text file (the re-importable Export, not the
  custom/grouped Share).
- Note the ManaBox app version and device locale in the issue when attaching — both affect
  the open questions (format drift, decimal separator).

## Verifying

```sh
python3 samples/verify_export.py samples/collection.csv samples/deck.txt
```

Prints a Markdown report of the literal facts the ingestion decision needs: encoding/BOM,
delimiter, exact header row, distinct values for every enum-ish column (Condition, Language,
Foil, …), decimal-separator usage, comma-in-name quoting, blank-line quirks, and deck-file
line shapes. Paste the report into issue #16 as the resolution evidence.

The open points this settles are listed in the research findings:
[docs/research/manabox-export-formats.md on the research branch](https://github.com/mattiasthalen/tutor/blob/research/manabox-export-formats/docs/research/manabox-export-formats.md)
(§1.3 header, §1.6 Condition casing, §1.7 Chinese language codes, §5 encoding/BOM/locale).
