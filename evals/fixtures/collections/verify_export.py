#!/usr/bin/env python3
"""Report the literal facts of a real ManaBox export (issue #16).

Usage:
    python3 samples/verify_export.py <collection.csv> [<deck.txt>]

Reads the files as bytes first, then prints a Markdown report answering the
open questions from the ManaBox export research (issue #3): encoding/BOM,
delimiter, the exact header row, distinct values per enum-ish column,
decimal-separator usage in prices, comma-in-name quoting, blank-line quirks,
and the line shapes of the deck text export. The report is the resolution
evidence — paste it into the ticket. Stdlib only; no third-party deps.
"""

import csv
import io
import re
import sys
from collections import Counter

# Header two secondary sources agreed on; the report diffs reality against it.
EXPECTED_HEADER = [
    "Name", "Set code", "Set name", "Collector number", "Foil", "Rarity",
    "Quantity", "ManaBox ID", "Scryfall ID", "Purchase price", "Misprint",
    "Altered", "Condition", "Language", "Purchase price currency",
]

# Columns whose value vocabulary is in question; reported as distinct values.
ENUMISH = [
    "Foil", "Rarity", "Misprint", "Altered", "Condition", "Language",
    "Purchase price currency",
]

BOMS = [
    (b"\xef\xbb\xbf", "UTF-8 BOM"),
    (b"\xff\xfe", "UTF-16 LE BOM"),
    (b"\xfe\xff", "UTF-16 BE BOM"),
]


def sniff_bytes(raw):
    """Return (bom_name, decoded_text, encoding_used)."""
    for bom, name in BOMS:
        if raw.startswith(bom):
            enc = "utf-8-sig" if name == "UTF-8 BOM" else "utf-16"
            return name, raw.decode(enc), enc
    try:
        return "none", raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return "none", raw.decode("latin-1"), "latin-1 (utf-8 failed!)"


def line_endings(raw):
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    cr = raw.count(b"\r") - crlf
    return f"CRLF={crlf} LF={lf} CR={cr}"


def classify_price(value):
    v = value.strip()
    if not v:
        return "empty"
    if re.fullmatch(r"\d+", v):
        return "integer (no separator)"
    if re.fullmatch(r"\d+\.\d+", v):
        return "dot decimal (1.84)"
    if re.fullmatch(r"\d+,\d+", v):
        return "comma decimal (1,84)"
    return f"other: {v!r}"


def report_collection(path):
    raw = open(path, "rb").read()
    bom, text, enc = sniff_bytes(raw)
    print(f"## Collection CSV: `{path}`\n")
    print(f"- Size: {len(raw)} bytes; BOM: **{bom}**; decoded as: **{enc}**")
    print(f"- Line endings: {line_endings(raw)}")

    lines = text.splitlines()
    blanks = [i + 1 for i, l in enumerate(lines) if not l.strip()]
    print(f"- Physical lines: {len(lines)}; blank lines: "
          f"{len(blanks)}{' at ' + str(blanks[:10]) if blanks else ''}")

    sample = "\n".join(lines[:20])
    try:
        dialect = csv.Sniffer().sniff(sample)
        delim = dialect.delimiter
    except csv.Error:
        delim = ","
    print(f"- Delimiter (sniffed): `{delim!r}`")

    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    rows = [r for r in rows if any(cell.strip() for cell in r)]
    header, data = rows[0], rows[1:]
    print(f"- Data rows: {len(data)}")
    # An unquoted comma decimal (e.g. 12,50) shifts every later column; a
    # ragged row is the loudest symptom of the open decimal-separator question.
    ragged = [(i + 2, len(r)) for i, r in enumerate(data) if len(r) != len(header)]
    note = (f"; first at line {ragged[0][0]} with {ragged[0][1]} fields"
            if ragged else "")
    print(f"- Rows whose field count != header's {len(header)}: {len(ragged)}{note}\n")

    print("### Literal header\n")
    print("```")
    print(delim.join(header))
    print("```\n")
    if header == EXPECTED_HEADER:
        print("Matches the 15-column header from the research (§1.3) exactly.\n")
    else:
        missing = [c for c in EXPECTED_HEADER if c not in header]
        extra = [c for c in header if c not in EXPECTED_HEADER]
        print(f"- Differs from research §1.3. Missing: {missing or 'none'}; "
              f"extra: {extra or 'none'} (binder/list-name column? see §5.2)\n")

    idx = {name: i for i, name in enumerate(header)}

    print("### Distinct values (the disputed vocabularies)\n")
    for col in ENUMISH:
        if col not in idx:
            print(f"- **{col}**: column not present")
            continue
        counts = Counter(r[idx[col]] for r in data if len(r) > idx[col])
        vals = ", ".join(f"`{v!r}`×{n}" for v, n in counts.most_common())
        print(f"- **{col}**: {vals}")

    if "Purchase price" in idx:
        kinds = Counter(classify_price(r[idx["Purchase price"]])
                        for r in data if len(r) > idx["Purchase price"])
        print("- **Purchase price shapes**: "
              + ", ".join(f"{k}×{n}" for k, n in kinds.most_common()))

    if "Name" in idx:
        commas = [r[idx["Name"]] for r in data
                  if len(r) > idx["Name"] and "," in r[idx["Name"]]]
        example = f" (e.g. `{commas[0]}`)" if commas else ""
        print(f"- **Names containing commas**: {len(commas)}{example}")
        non_ascii = [r[idx["Name"]] for r in data
                     if len(r) > idx["Name"]
                     and any(ord(ch) > 127 for ch in r[idx["Name"]])]
        example = f" (e.g. `{non_ascii[0]}`)" if non_ascii else ""
        print(f"- **Names with non-ASCII characters**: {len(non_ascii)}{example}")
    print()


DECK_LINE = re.compile(
    r"^(?P<qty>\d+)\s+(?P<name>.+?)"
    r"(?:\s+\((?P<set>[A-Za-z0-9]+)\)\s+(?P<num>\S+))?\s*$"
)


def report_deck(path):
    raw = open(path, "rb").read()
    bom, text, enc = sniff_bytes(raw)
    print(f"## Deck text: `{path}`\n")
    print(f"- Size: {len(raw)} bytes; BOM: **{bom}**; decoded as: **{enc}**")
    print(f"- Line endings: {line_endings(raw)}")

    lines = text.splitlines()
    shapes = Counter()
    oddballs = []
    for line in lines:
        if not line.strip():
            shapes["blank"] += 1
            continue
        m = DECK_LINE.match(line)
        if m and m.group("set"):
            shapes["qty name (SET) number"] += 1
        elif m:
            shapes["qty name"] += 1
        else:
            shapes["other"] += 1
            oddballs.append(line)
    print(f"- Lines: {len(lines)}; shapes: "
          + ", ".join(f"{k}×{n}" for k, n in shapes.most_common()))
    for line in oddballs[:10]:
        print(f"  - unmatched line: `{line}`")
    print("\n### First 10 lines verbatim\n")
    print("```")
    for line in lines[:10]:
        print(line)
    print("```\n")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    print("# ManaBox export verification report\n")
    report_collection(argv[1])
    if len(argv) > 2:
        report_deck(argv[2])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
