#!/usr/bin/env python3
"""tutor's offline eval harness (issue #48).

Runs the eval cases in ``evals/evals.json`` — authored in the skill-creator
eval workflow format — and grades their mechanical expectations against the
committed fixtures. Everything here is deterministic and offline: fixtures on
disk are the only input, fixed predicates are the only graders, and the live
Scryfall API is never called (network lives only in the deliberate snapshot
refresh script and the oracle build script's live mode; this harness runs
neither path).

Usage:
    python3 evals/run_evals.py [--case NAME_OR_ID] [--fixture-root DIR] [--out DIR]

Exit status: 0 when every graded mechanical expectation passes, 1 otherwise.

Two grader tiers (from the spec's testing decisions): hard mechanical
invariants are graded here by fixed predicates registered per expectation
text; expectations without a registered predicate are soft LLM judgment,
reported as such and left to the dev-time skill-creator workflow.

Results land in ``evals/results/<case-name>/`` as ``eval_metadata.json`` and
``grading.json`` in the skill-creator grading schema, so the same artifacts
slot into the skill-creator viewer and, later, the gated ``claude plugin
eval`` flow (see docs/spikes/plugin-eval-enablement.md).
"""

import argparse
import csv
import io
import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
EVALS_DIR = pathlib.Path(__file__).resolve().parent

# Descriptive per-case directory names, keyed by eval id (the skill-creator
# evals.json schema itself carries no name field; the workflow names runs).
CASE_NAMES = {
    1: "harness-smoke",
    2: "oracle-smoke",
    3: "brief-smoke",
    4: "build-smoke",
    5: "review-smoke",
    6: "build-deep",
}


class Context:
    """What every fixed predicate gets to look at: the fixture tree."""

    def __init__(self, fixture_root):
        self.fixture_root = pathlib.Path(fixture_root)

    def path(self, relative):
        return self.fixture_root / relative

    def read_manabox_csv(self, relative):
        """Parse a ManaBox export CSV header-keyed; tolerate a UTF-8 BOM."""
        raw = self.path(relative).read_bytes()
        text = raw.decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(text)))


# --- Fixed predicates -------------------------------------------------------
# Each returns (passed: bool, evidence: str).

def check_realism_row_count(ctx):
    rows = ctx.read_manabox_csv("collections/real-collection.csv")
    count = len(rows)
    return (
        count == 577,
        f"collections/real-collection.csv parsed header-keyed: {count} data rows (expected 577)",
    )


MANABOX_HEADER = [
    "Binder Name", "Binder Type", "Name", "Set code", "Set name",
    "Collector number", "Foil", "Rarity", "Quantity", "ManaBox ID",
    "Scryfall ID", "Purchase price", "Misprint", "Altered", "Condition",
    "Language", "Purchase price currency", "Added",
]

SYNTHETIC_COLLECTIONS = [
    "collections/synthetic-edge-cases.csv",
    "collections/synthetic-kitchen20-pool.csv",
    "collections/synthetic-standard-pool.csv",
]


def synthetic_rows(ctx):
    for rel in SYNTHETIC_COLLECTIONS:
        for r in ctx.read_manabox_csv(rel):
            yield rel, r


def real_rows(ctx):
    return ctx.read_manabox_csv("collections/real-collection.csv")


# The three gap predicates below grade both halves of "cover what the real
# Export lacks": the synthetics carry the value AND the real Export still
# lacks it — if the real Export ever gains one, the synthetic's reason to
# exist is gone and the run goes red instead of silently hollow.

def check_etched_foil(ctx):
    hits = [f"{rel}: {r['Name']}" for rel, r in synthetic_rows(ctx) if r["Foil"] == "etched"]
    gained = sorted({r["Name"] for r in real_rows(ctx) if r["Foil"] == "etched"})
    return bool(hits) and not gained, (
        f"etched Foil rows: {hits or 'none'}; "
        + (f"real Export gained etched ({gained[:3]}) — no longer a gap" if gained
           else "real Export still lacks etched")
    )


def check_non_english_languages(ctx):
    langs = {}
    for rel, r in synthetic_rows(ctx):
        if r["Language"] != "en":
            langs.setdefault(r["Language"], f"{rel}: {r['Name']}")
    missing = {"ja", "zhs"} - set(langs)
    gained = sorted(set(langs) & {r["Language"] for r in real_rows(ctx)})
    return not missing and not gained, (
        f"non-English rows: {langs or 'none'}; missing: {sorted(missing) or 'none'}; "
        + (f"real Export gained {gained} — no longer a gap" if gained
           else "real Export still lacks them")
    )


def check_promo_collector_numbers(ctx):
    hits = [
        f"{rel}: {r['Name']} ({r['Set code']}) {r['Collector number']}"
        for rel, r in synthetic_rows(ctx)
        if not r["Collector number"].isdigit()
    ]
    gained = sorted({
        r["Collector number"] for r in real_rows(ctx)
        if not r["Collector number"].isdigit()
    })
    return bool(hits) and not gained, (
        f"promo collector numbers: {hits or 'none'}; "
        + (f"real Export gained non-digit numbers ({gained[:3]}) — no longer a gap" if gained
           else "real Export still lacks them")
    )


def check_per_format_pools(ctx):
    problems, evidence = [], []
    for rel, want in [
        ("collections/synthetic-kitchen20-pool.csv", "Uncharted Haven"),
        ("collections/synthetic-standard-pool.csv", None),
    ]:
        raw = ctx.path(rel).read_bytes().decode("utf-8-sig")
        header = next(csv.reader(io.StringIO(raw)))
        if header != MANABOX_HEADER:
            problems.append(f"{rel}: header differs from the ManaBox 18-column header")
            continue
        rows = list(csv.DictReader(io.StringIO(raw)))
        if len(rows) < 13:
            problems.append(f"{rel}: only {len(rows)} rows — not a shaped pool")
        if want and not any(r["Name"] == want for r in rows):
            problems.append(f"{rel}: missing {want}")
        if want is None and not any(r["Quantity"] == "4" for r in rows):
            problems.append(f"{rel}: no playset (Quantity 4) rows")
        evidence.append(f"{rel}: {len(rows)} rows, exact ManaBox header")
    return not problems, "; ".join(problems or evidence)


# The nine canonical Brief keys (spec #52), in Brief Block order — the one
# copy in this file. skills/brief/scripts/validate_brief.py carries its own
# on purpose: skill assets stay self-contained across the skill/eval boundary.
BRIEF_CANONICAL_KEYS = (
    "name", "format", "centerpiece", "identity", "play variant",
    "power", "constraint", "donor", "notes",
)


def parse_brief_lines(text):
    """The harness's own flat ``key: value`` read of a fixture Brief —
    deliberately independent of the skill's validator, never imported from it.

    Returns (entries, problems): (key, value) pairs in file order, plus one
    problem per line that is not a canonical non-empty ``key: value`` line.
    """
    entries, problems = [], []
    for line in text.splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep or not value.strip() or key not in BRIEF_CANONICAL_KEYS:
            problems.append(f"not a canonical 'key: value' line: {line!r}")
            continue
        entries.append((key, value.strip()))
    return entries, problems


BOARD_HEADERS = {"// Commander", "// Mainboard", "// Sideboard", "// Maybeboard"}
BASIC_NAMES = {"Plains", "Island", "Swamp", "Forest", "Mountain", "Wastes"}

# Deck-line grammar. fixtures/scryfall/refresh_snapshot.py carries a verbatim
# copy of these two regexes (kept in lockstep by hand, not imported), so the
# snapshot coverage check reads the fixtures with the same grammar the refresh
# used. Edit them together.
PINNED_LINE = re.compile(
    r"^(\d+) (.+) \(([A-Z0-9]{2,6})\) (\S+)(?: // (.+))?$"
)
BARE_LINE = re.compile(r"^(\d+) (.+?)(?: // (.+))?$")


def check_fixture_briefs(ctx):
    briefs = sorted(ctx.path("briefs").glob("*.txt"))
    if len(briefs) < 2:
        return False, f"only {len(briefs)} fixture Briefs under briefs/"
    problems = []
    for brief in briefs:
        entries, brief_problems = parse_brief_lines(brief.read_text(encoding="utf-8"))
        problems += [f"{brief.name}: {p}" for p in brief_problems]
        if "format" not in {key for key, _ in entries}:
            problems.append(f"{brief.name}: missing the required format: line")
    return not problems, "; ".join(problems) or f"{len(briefs)} Briefs, all flat key: value with format:"


def parse_deck_block(text):
    """Parse a Deck Block; return (card_lines, problems). card_lines are
    (qty, name, set_code_or_None, number_or_None) tuples."""
    lines = text.splitlines()
    problems, cards, boards = [], [], []
    if not lines or not lines[0].startswith("// "):
        problems.append("first line is not a '// <name>' title comment")
    for line in lines[1:]:
        if not line.strip():
            continue
        if line in BOARD_HEADERS:
            boards.append(line)
            continue
        if line.startswith("//"):
            problems.append(f"unrecognized comment/header line: {line!r}")
            continue
        m = PINNED_LINE.match(line)
        if m:
            cards.append((int(m.group(1)), m.group(2), m.group(3), m.group(4)))
            continue
        m = BARE_LINE.match(line)
        if m:
            cards.append((int(m.group(1)), m.group(2), None, None))
            continue
        problems.append(f"unparseable card line: {line!r}")
    if not boards:
        problems.append("no Board headers")
    if not cards:
        problems.append("no card lines")
    return cards, problems


def check_fixture_decks(ctx):
    decks = sorted(ctx.path("decks").glob("*.txt"))
    if not decks:
        return False, "no fixture Decks under decks/"
    problems, evidence = [], []
    for deck in decks:
        cards, deck_problems = parse_deck_block(deck.read_text(encoding="utf-8"))
        problems += [f"{deck.name}: {p}" for p in deck_problems]
        unpinned_nonbasics = [
            name for _, name, set_code, _ in cards
            if set_code is None and name not in BASIC_NAMES
        ]
        if unpinned_nonbasics:
            problems.append(f"{deck.name}: nonbasics without a printing pin: {unpinned_nonbasics}")
        evidence.append(f"{deck.name}: {sum(q for q, *_ in cards)} cards")
    return not problems, "; ".join(problems or evidence)


def check_planted_flaws(ctx):
    manifest = json.loads(ctx.path("manifest.json").read_text(encoding="utf-8"))
    flawed = manifest.get("planted_flaws", {})
    if not flawed:
        return False, "manifest registers no planted flaws"
    collection_names = {r["Name"] for rel in SYNTHETIC_COLLECTIONS + ["collections/real-collection.csv"]
                        for r in ctx.read_manabox_csv(rel)}
    problems = []
    for deck_rel, flaws in flawed.items():
        deck_path = ctx.path(deck_rel)
        if not deck_path.is_file():
            problems.append(f"{deck_rel}: registered but missing")
            continue
        deck_text = deck_path.read_text(encoding="utf-8")
        for flaw in flaws:
            for card in flaw["cards"]:
                if card not in deck_text:
                    problems.append(f"{deck_rel}: flaw {flaw['id']} names {card!r} not in the Deck")
                if flaw["class"] == "availability" and card in collection_names:
                    problems.append(
                        f"{deck_rel}: availability flaw {flaw['id']} card {card!r} is owned"
                    )
    for clean_rel in manifest.get("clean_decks", []):
        if not ctx.path(clean_rel).is_file():
            problems.append(f"clean deck {clean_rel} missing")
        if clean_rel in flawed:
            problems.append(f"{clean_rel} listed both clean and flawed")
    flaw_count = sum(len(f) for f in flawed.values())
    return not problems, "; ".join(problems) or (
        f"{flaw_count} planted flaws across {len(flawed)} Decks, "
        f"{len(manifest.get('clean_decks', []))} clean Decks"
    )


def load_snapshot(ctx):
    """Read snapshot.jsonl; return (meta, cards)."""
    lines = ctx.path("scryfall/snapshot.jsonl").read_text(encoding="utf-8").splitlines()
    meta = json.loads(lines[0])["snapshot_meta"]
    return meta, [json.loads(line) for line in lines[1:]]


def fixture_card_references(ctx):
    """Every card reference the fixtures make, re-read from the fixture files.

    Not an independent parse: this walks the same files with the same
    PINNED_LINE/BARE_LINE grammar refresh_snapshot.py copies, so the coverage
    check is a fixture-vs-snapshot drift tripwire — a shared grammar bug
    would blind both sides.

    Returns (ids, pins, names): Scryfall IDs from Collection CSVs,
    (set, collector number) pins and bare names from Deck texts.
    """
    ids, pins, names = set(), set(), set()
    for csv_path in sorted(ctx.path("collections").glob("*.csv")):
        for row in ctx.read_manabox_csv(f"collections/{csv_path.name}"):
            if row.get("Scryfall ID", "").strip():
                ids.add(row["Scryfall ID"].strip())
    deck_paths = sorted(ctx.path("decks").glob("*.txt"))
    deck_paths.append(ctx.path("collections/real-deck.txt"))
    for deck_path in deck_paths:
        for line in deck_path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("//"):
                continue
            m = PINNED_LINE.match(line)
            if m:
                pins.add((m.group(3).lower(), m.group(4)))
                continue
            m = BARE_LINE.match(line)
            if m:
                names.add(m.group(2))
    return ids, pins, names


def check_snapshot_coverage(ctx):
    meta, cards = load_snapshot(ctx)
    problems = []
    if "captured_at" not in meta:
        problems.append("snapshot metadata line lacks captured_at")
    if meta.get("card_count") != len(cards):
        problems.append(
            f"metadata card_count {meta.get('card_count')} != {len(cards)} card lines"
        )
    snap_ids = {c["id"] for c in cards}
    snap_pins = {(c["set"], c["collector_number"]) for c in cards}
    snap_names = {c["name"] for c in cards}
    snap_names |= {f["name"] for c in cards for f in c.get("card_faces", [])}

    ids, pins, names = fixture_card_references(ctx)
    missing = [i for i in sorted(ids) if i not in snap_ids]
    missing += [f"{s.upper()} {n}" for s, n in sorted(pins) if (s, n) not in snap_pins]
    missing += [n for n in sorted(names) if n not in snap_names]
    if missing:
        problems.append(f"fixture cards absent from the snapshot: {missing[:10]}")

    orphans = [
        f"{c['name']} ({c['set'].upper()}) {c['collector_number']}"
        for c in cards
        if c["id"] not in ids
        and (c["set"], c["collector_number"]) not in pins
        and c["name"] not in names
        and not any(f["name"] in names for f in c.get("card_faces", []))
    ]
    if orphans:
        problems.append(f"snapshot cards no fixture references: {orphans[:10]}")

    return not problems, "; ".join(problems) or (
        f"{len(cards)} snapshot cards captured {meta['captured_at']} cover "
        f"{len(ids)} Collection printings, {len(pins)} Deck pins, "
        f"{len(names)} bare names — exactly"
    )


ORACLE_FIELDS = {
    "name", "mana_value", "colors", "color_identity", "type_line",
    "oracle_text", "legalities", "game_changer",
}
TOKEN_LAYOUTS = {"token", "double_faced_token", "emblem", "art_series"}


def load_oracle(ctx):
    lines = ctx.path("scryfall/oracle.jsonl").read_text(encoding="utf-8").splitlines()
    meta = json.loads(lines[0])["oracle_meta"]
    return meta, [json.loads(line) for line in lines[1:]]


def check_oracle_rederivation(ctx):
    import subprocess
    derived = subprocess.run(
        [sys.executable, str(ctx.path("scryfall/derive_oracle.py")), "--stdout"],
        capture_output=True, text=True, timeout=120,
    )
    if derived.returncode != 0:
        return False, f"derive_oracle.py failed: {derived.stderr.strip()[:200]}"
    committed = ctx.path("scryfall/oracle.jsonl").read_text(encoding="utf-8")
    if derived.stdout != committed:
        return False, "committed oracle.jsonl differs from a fresh derivation of the snapshot"
    return True, f"oracle.jsonl reproduced byte-identical ({len(committed.splitlines()) - 1} cards)"


def check_oracle_shape(ctx):
    meta, records = load_oracle(ctx)
    _, snapshot_cards = load_snapshot(ctx)
    problems = []
    if meta.get("card_count") != len(records):
        problems.append(f"metadata card_count {meta.get('card_count')} != {len(records)} lines")
    names = [r["name"] for r in records]
    if names != sorted(names) or len(names) != len(set(names)):
        problems.append("Oracle lines are not unique name-sorted")
    for r in records:
        if set(r) != ORACLE_FIELDS:
            problems.append(f"{r.get('name', '?')}: fields {sorted(r)} != the Oracle shape")
            break
        if set(r["legalities"]) != {"standard", "pioneer", "modern", "commander"}:
            problems.append(f"{r['name']}: legalities not trimmed to the four sanctioned Formats")
            break
        if not isinstance(r["game_changer"], bool):
            problems.append(f"{r['name']}: game_changer is not a boolean")
            break
    token_names = {c["name"] for c in snapshot_cards if c.get("layout") in TOKEN_LAYOUTS}
    playable_names = {c["name"] for c in snapshot_cards if c.get("layout") not in TOKEN_LAYOUTS}
    leaked = sorted((token_names - playable_names) & set(names))
    if leaked:
        problems.append(f"token rows leaked into the Oracle: {leaked[:5]}")
    if playable_names - set(names):
        problems.append(f"playable snapshot cards missing: {sorted(playable_names - set(names))[:5]}")
    if not any(" // " in n for n in names):
        problems.append("no multi-faced name flattened with //")
    if not {"Plains", "Island", "Swamp", "Forest"} <= set(names):
        problems.append("basic lands missing from the Oracle")
    return not problems, "; ".join(problems) or (
        f"{len(records)} name-keyed lines, four-Format legalities, "
        f"{sum(1 for n in names if ' // ' in n)} flattened multi-faced names, tokens excluded"
    )


def check_oracle_watermark(ctx):
    meta, _ = load_oracle(ctx)
    snap_meta, _ = load_snapshot(ctx)
    problems = []
    if meta.get("generated_at") != snap_meta.get("captured_at"):
        problems.append(
            f"generated_at {meta.get('generated_at')} != snapshot captured_at {snap_meta.get('captured_at')}"
        )
    newest = ""
    for csv_path in sorted(ctx.path("collections").glob("*.csv")):
        for row in ctx.read_manabox_csv(f"collections/{csv_path.name}"):
            newest = max(newest, row.get("Added", "").strip())
    if meta.get("source_export_newest_added") != newest:
        problems.append(
            f"watermark {meta.get('source_export_newest_added')} != newest fixture Added {newest}"
        )
    return not problems, "; ".join(problems) or (
        f"generated_at {meta['generated_at']}, source Export watermark {newest}"
    )


SCRYFALL_HOST = "api." + "scryfall.com"  # the tripwire literal, split so this file stays out of its own scan
NETWORK_ALLOWED = {
    "fixtures/scryfall/refresh_snapshot.py",  # the one deliberate network path
    "fixtures/scryfall/snapshot.jsonl",       # records api_host as provenance
}


def check_offline_guarantee(_ctx):
    """Tripwire, not proof: scan the eval tree's text files for the literal
    host string. A file that reaches Scryfall without spelling the host out
    (or spelling it in pieces, as this one does) would slip past."""
    offenders = []
    for path in sorted(EVALS_DIR.rglob("*")):
        if not path.is_file() or "results" in path.parts:
            continue
        relative = path.relative_to(EVALS_DIR).as_posix()
        if relative in NETWORK_ALLOWED:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if SCRYFALL_HOST in text:
            offenders.append(relative)
    return not offenders, (
        f"files carrying the literal Scryfall host string: {offenders}"
        if offenders
        else f"the literal Scryfall host string appears only in {sorted(NETWORK_ALLOWED)}"
    )


# --- Oracle skill predicates (issue #51) ------------------------------------
# The oracle-smoke case runs the skill's deterministic seam — the
# build_oracle.py CLI — offline, resolution pinned to the committed snapshot.
# Never the live API.

ORACLE_SCRIPT = REPO_ROOT / "skills" / "oracle" / "scripts" / "build_oracle.py"


def run_oracle_script(ctx, csv_text=None, expect_failure=False):
    """Run build_oracle.py in a temp Collection home, offline.

    With csv_text, that text is the Export; otherwise the realism Export is
    copied in. Returns (completed_process, oracle_path, home_path).
    """
    import atexit
    import shutil
    import subprocess
    import tempfile

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="oracle-smoke-"))
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    export = tmp / "collection.csv"
    if csv_text is None:
        shutil.copy(ctx.path("collections/real-collection.csv"), export)
    else:
        export.write_text(csv_text, encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable, str(ORACLE_SCRIPT),
            "--collection", str(export),
            "--snapshot", str(ctx.path("scryfall/snapshot.jsonl")),
        ],
        capture_output=True, text=True, timeout=300,
    )
    if completed.returncode != 0 and not expect_failure:
        raise AssertionError(
            f"build_oracle.py failed: {completed.stderr.strip()[:200]}"
        )
    return completed, tmp / "oracle.jsonl", tmp


def first_snapshot_card(ctx):
    _, cards = load_snapshot(ctx)
    return next(c for c in cards if c.get("layout") == "normal")


def check_oracle_skill_output(ctx):
    _, oracle_path, _ = run_oracle_script(ctx)
    if not oracle_path.is_file():
        return False, "no oracle.jsonl written beside the Export"
    lines = oracle_path.read_text(encoding="utf-8").splitlines()
    meta = json.loads(lines[0]).get("oracle_meta", {})
    snap_meta, _ = load_snapshot(ctx)
    problems = []
    if meta.get("generated_at") != snap_meta.get("captured_at"):
        problems.append(
            f"generated_at {meta.get('generated_at')} != snapshot captured_at "
            f"{snap_meta.get('captured_at')} (offline runs pin freshness to the snapshot)"
        )
    newest = max(
        (r.get("Added", "").strip() for r in ctx.read_manabox_csv("collections/real-collection.csv")),
        default="",
    )
    if meta.get("source_export_newest_added") != newest:
        problems.append(
            f"watermark {meta.get('source_export_newest_added')} != the Export's newest Added {newest}"
        )
    names = [json.loads(line)["name"] for line in lines[1:]]
    if not names or names != sorted(names) or len(names) != len(set(names)):
        problems.append("body lines are not one sorted line per unique card name")
    return not problems, "; ".join(problems) or (
        f"oracle.jsonl beside the Export: {len(names)} unique names, "
        f"generated_at {meta['generated_at']}, watermark {newest}"
    )


def check_oracle_skill_agreement(ctx):
    _, oracle_path, _ = run_oracle_script(ctx)
    written = oracle_path.read_text(encoding="utf-8").splitlines()[1:]
    fixture_by_name = {}
    for line in ctx.path("scryfall/oracle.jsonl").read_text(encoding="utf-8").splitlines()[1:]:
        fixture_by_name[json.loads(line)["name"]] = line
    problems = []
    names = []
    uuid = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
    for line in written:
        name = json.loads(line)["name"]
        names.append(name)
        if fixture_by_name.get(name) != line:
            problems.append(f"{name}: line differs from the fixture Oracle's")
            break
        if uuid.search(line):
            problems.append(f"{name}: a UUID leaked into the Oracle")
            break
    _, snapshot_cards = load_snapshot(ctx)
    token_only = {c["name"] for c in snapshot_cards if c.get("layout") in TOKEN_LAYOUTS} - {
        c["name"] for c in snapshot_cards if c.get("layout") not in TOKEN_LAYOUTS
    }
    leaked = sorted(token_only & set(names))
    if leaked:
        problems.append(f"token rows leaked: {leaked[:3]}")
    if "Forest" not in names:
        problems.append("basic lands missing")
    if not any(" // " in n for n in names):
        problems.append("no multi-faced name flattened with //")
    return not problems, "; ".join(problems) or (
        f"all {len(written)} written lines byte-identical to the fixture Oracle; "
        "tokens out, basics in, multi-faced names flattened"
    )


def check_oracle_skill_tolerance(ctx):
    card = first_snapshot_card(ctx)
    good = f"\"{card['name']}\",{card['set'].upper()},{card['id']},2026-08-02T09:00:00.000Z\n"
    completed, oracle_path, _ = run_oracle_script(
        ctx,
        csv_text="Name,Set code,Scryfall ID,Added\n" + good + "Orphan,,,\n,,,\n",
    )
    problems = []
    if "2 malformed rows skipped" not in completed.stdout:
        problems.append("malformed rows not reported with a count")
    if "row 3" not in completed.stdout:
        problems.append("skipped-row examples missing from the report")
    if card["name"] not in oracle_path.read_text(encoding="utf-8"):
        problems.append("the well-formed row no longer resolves")

    completed, oracle_path, _ = run_oracle_script(
        ctx, csv_text="Binder Name,Quantity\nB,1\n", expect_failure=True,
    )
    if completed.returncode != 2 or "identity columns" not in completed.stderr:
        problems.append(
            f"a header without identity columns must hard-fail naming them "
            f"(exit {completed.returncode}: {completed.stderr.strip()[:120]})"
        )
    elif oracle_path.exists():
        problems.append("an Oracle was written despite the hard failure")
    return not problems, "; ".join(problems) or (
        "malformed rows skipped and reported with count and examples; "
        "the identity-column header check is the one hard failure"
    )


def check_oracle_skill_fallback(ctx):
    card = first_snapshot_card(ctx)
    completed, oracle_path, _ = run_oracle_script(
        ctx,
        csv_text=(
            "Name,Set code,Scryfall ID,Added\n"
            f"\"{card['name']}\",{card['set'].upper()},"
            "00000000-0000-0000-0000-000000000000,2026-08-02T09:00:00.000Z\n"
        ),
    )
    problems = []
    if "1 by Name + Set code fallback" not in completed.stdout:
        problems.append("the fallback resolution is not reported")
    names = [
        json.loads(line)["name"]
        for line in oracle_path.read_text(encoding="utf-8").splitlines()[1:]
    ]
    if names != [card["name"]]:
        problems.append(f"expected [{card['name']}] via fallback, got {names}")
    return not problems, "; ".join(problems) or (
        f"an unknown Scryfall ID resolved through Name + Set code: {card['name']}"
    )


# --- Brief skill predicates (issue #52) -------------------------------------
# The brief conversation is prompt-ware: its behavioral expectations (fires
# from natural language; scripted answers yield the Brief; a pasted Export
# beats the file) stay soft, dev-time judged. These predicates grade the
# deterministic shadows: wiring, the validator and freshness scripts (wrapped,
# never re-implemented), and the fixture Briefs those scripts must accept —
# where a predicate needs Brief fields rather than a verdict, it reads them
# through parse_brief_lines, the harness's own fixture read.

BRIEF_SKILL_PATH = REPO_ROOT / "skills" / "brief" / "SKILL.md"
BRIEF_COMMAND_PATH = REPO_ROOT / "commands" / "brief.md"
BRIEF_VALIDATOR = REPO_ROOT / "skills" / "brief" / "scripts" / "validate_brief.py"
BRIEF_FRESHNESS = REPO_ROOT / "skills" / "brief" / "scripts" / "freshness.py"
PLUGIN_MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"

PLAY_VARIANTS = {"archenemy", "two-headed giant", "jumpstart 40"}


def run_brief_script(script, *args):
    import subprocess

    return subprocess.run(
        [sys.executable, str(script), *[str(a) for a in args]],
        capture_output=True, text=True, timeout=120,
    )


def check_brief_wiring(_ctx):
    problems = []
    command = BRIEF_COMMAND_PATH.read_text(encoding="utf-8")
    if "skills/brief/SKILL.md" not in command:
        problems.append("commands/brief.md never hands off to skills/brief/SKILL.md")
    skill = BRIEF_SKILL_PATH.read_text(encoding="utf-8")
    pinned = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))["version"]
    m = re.search(r"^metadata:\n[ \t]+version:[ \t]*(\S+)", skill, re.MULTILINE)
    if not m:
        problems.append("skills/brief/SKILL.md carries no metadata.version")
    elif m.group(1) != pinned:
        problems.append(
            f"skill metadata.version {m.group(1)} != pinned plugin version {pinned}"
        )
    return not problems, "; ".join(problems) or (
        f"/tutor:brief wraps skills/brief/SKILL.md, versioned {pinned} in lockstep"
    )


def check_brief_nl_triggers(_ctx):
    """Tripwire, not proof: the structural half of "fires from natural
    language" is a description naming deck intents beyond the command; the
    firing itself is the soft expectation, judged at dev time."""
    skill = BRIEF_SKILL_PATH.read_text(encoding="utf-8")
    m = re.search(r"^description:[ \t]*(.+)$", skill, re.MULTILINE)
    if not m:
        return False, "skills/brief/SKILL.md frontmatter has no description line"
    description = m.group(1)
    missing = [n for n in ("/tutor:brief", "new deck", "deck idea") if n not in description]
    return not missing, (
        f"description lacks {missing}" if missing
        else "the description names /tutor:brief plus natural-language deck intents"
    )


def check_fixture_briefs_validate(ctx):
    manifest = json.loads(ctx.path("manifest.json").read_text(encoding="utf-8"))
    pairings = manifest.get("briefs", {})
    briefs = sorted(ctx.path("briefs").glob("*.txt"))
    if not briefs:
        return False, "no fixture Briefs to validate"
    problems, donor_checked = [], 0
    for brief in briefs:
        args = [brief]
        pool = pairings.get(f"briefs/{brief.name}", {}).get("pool")
        if pool:
            args += ["--collection", ctx.path(pool)]
            donor_checked += 1
        result = run_brief_script(BRIEF_VALIDATOR, *args)
        if result.returncode != 0:
            verdict = result.stdout.strip() or result.stderr.strip()
            problems.append(f"{brief.name}: {verdict[:200]}")
    return not problems, "; ".join(problems) or (
        f"{len(briefs)} fixture Briefs valid, {donor_checked} checked against their paired Export"
    )


def check_power_ladder(_ctx):
    import tempfile

    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        good = pathlib.Path(tmp) / "good.txt"
        good.write_text("format: commander\npower: 4, big villain turns\n", encoding="utf-8")
        bad = pathlib.Path(tmp) / "bad.txt"
        bad.write_text("format: commander\npower: 6\n", encoding="utf-8")
        good_run = run_brief_script(BRIEF_VALIDATOR, good)
        bad_run = run_brief_script(BRIEF_VALIDATOR, bad)
    if good_run.returncode != 0:
        problems.append(
            f"'power: 4, big villain turns' rejected: {good_run.stdout.strip()[:200]}"
        )
    if bad_run.returncode != 1:
        problems.append(f"'power: 6' not rejected (exit {bad_run.returncode})")
    return not problems, "; ".join(problems) or (
        "trailing free text passes, an out-of-ladder number fails — the 1-5 number is canonical"
    )


def check_donor_grammar(ctx):
    import tempfile

    export = ctx.path("collections/real-collection.csv")
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        all_brief = pathlib.Path(tmp) / "all.txt"
        all_brief.write_text("format: commander\ndonor: all\n", encoding="utf-8")
        unknown = pathlib.Path(tmp) / "unknown.txt"
        unknown.write_text("format: commander\ndonor: No Such Deck\n", encoding="utf-8")
        all_run = run_brief_script(BRIEF_VALIDATOR, all_brief, "--collection", export)
        unknown_run = run_brief_script(BRIEF_VALIDATOR, unknown, "--collection", export)
    if all_run.returncode != 0:
        problems.append(f"'donor: all' rejected: {all_run.stdout.strip()[:200]}")
    if unknown_run.returncode != 1:
        problems.append(
            f"an unrecognized donor Deck name passed (exit {unknown_run.returncode})"
        )
    return not problems, "; ".join(problems) or (
        "donor: all frees the whole Collection; an unknown Deck name is rejected "
        "against the Export's deck rows"
    )


def check_play_variants_never_formats(ctx):
    problems, archenemy_fixture = [], None
    for brief in sorted(ctx.path("briefs").glob("*.txt")):
        entries, _ = parse_brief_lines(brief.read_text(encoding="utf-8"))
        fields = {}
        for key, value in entries:
            fields.setdefault(key, value)
        if fields.get("format", "").lower() in PLAY_VARIANTS:
            problems.append(
                f"{brief.name}: format: {fields['format']!r} is a play variant, never a Format"
            )
        if fields.get("play variant", "").lower() == "archenemy":
            archenemy_fixture = brief.name
            if not fields.get("centerpiece"):
                problems.append(f"{brief.name}: the Archenemy Brief names no villain Centerpiece")
            if not fields.get("format"):
                problems.append(f"{brief.name}: the Archenemy Brief is still built to some Format")
    if archenemy_fixture is None:
        problems.append("no fixture Brief expresses Archenemy through play variant:")
    return not problems, "; ".join(problems) or (
        f"{archenemy_fixture} rides play variant: archenemy on a Format with the villain "
        "as Centerpiece; no Brief misfiles a variant as its Format"
    )


def check_freshness_helper(ctx):
    import datetime

    export = ctx.path("collections/real-collection.csv")
    oracle = ctx.path("scryfall/oracle.jsonl")
    with open(oracle, encoding="utf-8") as handle:
        meta = json.loads(handle.readline())["oracle_meta"]
    base = datetime.date.fromisoformat(meta["generated_at"][:10])
    fresh_today = (base + datetime.timedelta(days=2)).isoformat()
    stale_today = (base + datetime.timedelta(days=40)).isoformat()

    problems = []
    fresh = run_brief_script(
        BRIEF_FRESHNESS, "--collection", export, "--oracle", oracle, "--today", fresh_today
    )
    if (
        fresh.returncode != 0
        or "export newest added:" not in fresh.stdout
        or "signal export-newer-than-oracle: no" not in fresh.stdout
    ):
        problems.append(
            f"fresh Export/Oracle pair misreported (exit {fresh.returncode}): "
            f"{(fresh.stdout or fresh.stderr).strip()[:200]}"
        )
    stale = run_brief_script(
        BRIEF_FRESHNESS, "--collection", export, "--oracle", oracle, "--today", stale_today
    )
    if stale.returncode != 1 or "signal oracle-older-than-30-days: yes" not in stale.stdout:
        problems.append(
            f"a 40-day-old Oracle raised no staleness signal (exit {stale.returncode})"
        )
    absent = run_brief_script(BRIEF_FRESHNESS, "--collection", export, "--today", fresh_today)
    if absent.returncode != 0 or "oracle: absent" not in absent.stdout:
        problems.append(f"an absent Oracle did not degrade gracefully (exit {absent.returncode})")
    return not problems, "; ".join(problems) or (
        "newest Added surfaced, the 30-day signal fires on cue, and an absent Oracle degrades gracefully"
    )


def check_brief_skill_content(_ctx):
    """Tripwire, not proof: the skill is prompt-ware judged by its artifacts;
    these needles keep the load-bearing grammar sentences from silently
    vanishing in an edit."""
    text = BRIEF_SKILL_PATH.read_text(encoding="utf-8")
    needles = [f"{key}:" for key in BRIEF_CANONICAL_KEYS] + [
        "Only `format` is required",
        "no `budget:` key",
        "defaults to 2",
        "freshness question",
        "recognized by shape alone",
        "/tutor:build",
    ]
    missing = [n for n in needles if n not in text]
    return not missing, (
        f"skills/brief/SKILL.md lacks {missing}" if missing
        else "all nine canonical keys, the format-only requirement, the budget ban, "
             "the Power default, the single freshness question, and the Build handoff are pinned"
    )


# --- Build skill predicates (issue #53) -------------------------------------
# The build-smoke case runs the deterministic seams of Build's front half —
# the Suite generator CLI and the fixed runner over the committed build
# fixtures — offline. The live /tutor:build walk stays soft, dev-time judged.

BUILD_SKILL_PATH = REPO_ROOT / "skills" / "build" / "SKILL.md"
BUILD_COMMAND_PATH = REPO_ROOT / "commands" / "build.md"
BUILD_GENERATOR = REPO_ROOT / "skills" / "build" / "scripts" / "generate_suite.py"
COMMANDER_PROFILE = REPO_ROOT / "skills" / "build" / "profiles" / "commander.yaml"
SUITE_RUNNER = REPO_ROOT / "skills" / "suite-runner" / "scripts" / "check_deck.py"

# The date pinned into the committed build fixtures (Suite generated: line and
# report date: line), so re-runs are byte-comparable.
BUILD_REFERENCE_DATE = "2026-08-18"

ROLE_VOCABULARY = {"ramp", "draw", "removal", "wipe", "wincon", "land", "theme", "other"}


def run_build_cli(script, *args):
    import subprocess

    return subprocess.run(
        [sys.executable, str(script), *[str(a) for a in args]],
        capture_output=True, text=True, timeout=120,
    )


def section_lines(text, section):
    """The stripped non-comment lines of one top-level section of a
    YAML-subset file — the harness's own flat read, deliberately independent
    of the runner's parser."""
    lines, inside = [], False
    for line in text.splitlines():
        if not line.strip():
            continue
        if not line.startswith(" "):
            inside = line.rstrip() == f"{section}:"
            continue
        if inside and not line.strip().startswith("#"):
            lines.append(line.strip())
    return lines


def report_colors(stdout):
    """A runner report's check lines as {check-id: "red"|"green"}. The suite
    tests carry their own copies of this regex (grader independence, never
    imported), kept in lockstep by hand — edit them together."""
    return dict(
        (m.group(2), m.group(1))
        for m in (re.match(r"^(red|green)\s+(\S+) — ", line)
                  for line in stdout.splitlines())
        if m
    )


def check_commander_profile(_ctx):
    text = COMMANDER_PROFILE.read_text(encoding="utf-8")
    problems = []
    profile = section_lines(text, "profile")
    for needle in ("deck_size: 100", "copy_limit_nonland: 1", "banlist_key: commander"):
        if needle not in profile:
            problems.append(f"profile lacks {needle!r}")
    for target in ("lands_min", "lands_max", "curve_avg_max",
                   "early_nonland_cmc2_min", "p_2plus_lands_in_7_min"):
        if not any(l.startswith(f"{target}:") for l in profile):
            problems.append(f"no {target} check target")
    brackets = section_lines(text, "game_changers_max_by_power")
    if brackets != ["1: 0", "2: 0", "3: 3", "4: unlimited", "5: unlimited"]:
        problems.append(f"Game Changers bracket table is {brackets}")
    guidance = section_lines(text, "role_guidance")
    guided = {l.split(":", 1)[0] for l in guidance}
    if not {"ramp", "draw", "removal", "wipe", "wincon"} <= guided:
        problems.append(f"role guidance covers only {sorted(guided)}")
    return not problems, "; ".join(problems) or (
        "deck size 100, singleton, five check targets, brackets 0/0/3/unlimited/unlimited, "
        "banlist key, Role guidance — all data"
    )


def check_suite_generation_reproducible(ctx):
    generated = run_build_cli(
        BUILD_GENERATOR,
        "--brief", ctx.path("briefs/commander-tatyova-landfall.txt"),
        "--profile", COMMANDER_PROFILE,
        "--oracle", ctx.path("scryfall/oracle.jsonl"),
        "--date", BUILD_REFERENCE_DATE,
    )
    if generated.returncode != 0:
        return False, f"generate_suite.py failed: {generated.stderr.strip()[:200]}"
    committed = ctx.path("build/tatyova-landfall.suite.yaml").read_text(encoding="utf-8")
    if generated.stdout != committed:
        return False, "committed fixture Suite differs from a fresh generation"
    return True, (
        f"fixture Suite reproduced byte-identical "
        f"({len(committed.splitlines())} lines of declarative data)"
    )


def check_suite_shape(ctx):
    text = ctx.path("build/tatyova-landfall.suite.yaml").read_text(encoding="utf-8")
    problems = []
    ids = re.findall(r"^  - id: (\S+)$", text, re.MULTILINE)
    classes = {cid.split(".", 1)[0] for cid in ids}
    expected = {"legality", "availability", "manabase", "curve", "quota", "brief", "consistency"}
    if classes != expected:
        problems.append(f"Check classes {sorted(classes)} != {sorted(expected)}")
    if any("budget" in cid for cid in ids) or "budget" in text:
        problems.append("a budget class leaked into the Suite")
    quota_tags = {cid.split(".", 1)[1] for cid in ids if cid.startswith("quota.")}
    if not quota_tags <= ROLE_VOCABULARY:
        problems.append(f"quota tags outside the Role vocabulary: {sorted(quota_tags - ROLE_VOCABULARY)}")
    profile_snapshot = [
        line for line in section_lines(COMMANDER_PROFILE.read_text(encoding="utf-8"), "profile")
    ]
    suite_profile = section_lines(text, "profile")
    missing = [line for line in profile_snapshot if line not in suite_profile]
    if missing:
        problems.append(f"profile targets not snapshotted verbatim: {missing}")
    for derived in ("color_identity:", "game_changers_max:", "cmc_max:"):
        lines = text.splitlines()
        hits = [i for i, l in enumerate(lines) if l.strip().startswith(derived)]
        if not hits:
            problems.append(f"no Brief-derived {derived} value")
        elif not all(lines[i - 1].strip().startswith("# brief:") for i in hits):
            problems.append(f"{derived} carries no brief: provenance comment")
    if "# brief: constraint: nothing above 6 mana" not in text:
        problems.append("cmc_max does not trace to the Brief's constraint line")
    if section_lines(text, "roles"):
        problems.append("roles: is not empty — a card was picked before Build start?")
    return not problems, "; ".join(problems) or (
        f"{len(ids)} Checks across all seven classes, no budget, targets snapshotted, "
        "overrides under brief: provenance, roles empty"
    )


def check_empty_deck_red(ctx):
    result = run_build_cli(
        SUITE_RUNNER,
        "--suite", ctx.path("build/tatyova-landfall.suite.yaml"),
        "--deck", ctx.path("build/tatyova-empty-deck.txt"),
        "--oracle", ctx.path("scryfall/oracle.jsonl"),
        "--collection", ctx.path("collections/real-collection.csv"),
        "--date", BUILD_REFERENCE_DATE,
    )
    problems = []
    if result.returncode != 1:
        problems.append(f"exit code {result.returncode}, red is 1")
    committed = ctx.path("build/tatyova-empty-report.txt").read_text(encoding="utf-8")
    if result.stdout != committed:
        problems.append("report differs from the committed reference")
    colors = report_colors(result.stdout)
    must_be_red = (
        "legality.size", "legality.land_count", "curve.average", "curve.early_plays",
        "quota.ramp", "quota.draw", "quota.removal", "quota.wipe", "quota.wincon",
        "consistency.opening_lands", "brief.includes",
    )
    vacuous_green = (
        "legality.singleton", "legality.color_identity", "legality.banlist",
        "legality.game_changers", "availability.in_collection",
    )
    problems += [f"{cid} is {colors.get(cid)}, not red" for cid in must_be_red
                 if colors.get(cid) != "red"]
    problems += [f"{cid} is {colors.get(cid)}, not vacuously green" for cid in vacuous_green
                 if colors.get(cid) != "green"]
    return not problems, "; ".join(problems) or (
        f"{sum(1 for c in colors.values() if c == 'red')} red / "
        f"{sum(1 for c in colors.values() if c == 'green')} green, byte-identical "
        "to the reference — Build starts honestly red"
    )


def check_build_wiring(_ctx):
    problems = []
    command = BUILD_COMMAND_PATH.read_text(encoding="utf-8")
    if "skills/build/SKILL.md" not in command:
        problems.append("commands/build.md never hands off to skills/build/SKILL.md")
    skill = BUILD_SKILL_PATH.read_text(encoding="utf-8")
    pinned = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))["version"]
    m = re.search(r"^metadata:\n[ \t]+version:[ \t]*(\S+)", skill, re.MULTILINE)
    if not m:
        problems.append("skills/build/SKILL.md carries no metadata.version")
    elif m.group(1) != pinned:
        problems.append(
            f"skill metadata.version {m.group(1)} != pinned plugin version {pinned}"
        )
    return not problems, "; ".join(problems) or (
        f"/tutor:build wraps skills/build/SKILL.md, versioned {pinned} in lockstep"
    )


def check_build_skill_content(_ctx):
    """Tripwire, not proof: the skill is prompt-ware judged by its artifacts;
    these needles keep the load-bearing sentences from silently vanishing."""
    text = BUILD_SKILL_PATH.read_text(encoding="utf-8")
    needles = [
        "before any card is picked",
        "decks/<slug>.suite.yaml",
        "suite-report.txt",
        "/tutor:oracle",
        "beats the file",
        "re-settle the Brief",
        "vacuous",
    ]
    missing = [n for n in needles if n not in text]
    return not missing, (
        f"skills/build/SKILL.md lacks {missing}" if missing
        else "Collection-home writes, the Oracle offer, paste-beats-file, the refusal "
             "path, and the no-card-yet contract are pinned"
    )


# --- Review skill predicates (issue #55) ------------------------------------
# The review-smoke case grades Review's deterministic shadows — the assembler
# CLI (verdict arithmetic, the Review Block shape, the Finding shape), the
# wiring, the locked Smell baseline, the Commander review standards, and the
# Review-flawed fixture registration. Judgment quality (whether a live Review
# catches the planted flaws) stays soft, dev-time judged.

REVIEW_SKILL_PATH = REPO_ROOT / "skills" / "review" / "SKILL.md"
REVIEW_COMMAND_PATH = REPO_ROOT / "commands" / "review.md"
REVIEW_ASSEMBLER = REPO_ROOT / "skills" / "review" / "scripts" / "assemble_review.py"

SMELL_BASELINE_V1 = (
    "synergy island", "dead card", "win-more", "no comeback plan",
    "piloting overload", "fragile mana", "theme tax", "redundancy gap",
    "curve lie", "interaction mismatch",
)

COMMANDER_REVIEW_SEEDS = ("politics", "functional-copy redundancy", "answer spread")


def run_assembler(standards, brief):
    """Run assemble_review.py over in-memory Findings; brief None means
    --no-brief. Returns the CompletedProcess."""
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        args = [
            sys.executable, str(REVIEW_ASSEMBLER),
            "--deck-name", "Probe Deck", "--date", "2026-08-18",
            "--standards", str(root / "standards.json"),
        ]
        (root / "standards.json").write_text(json.dumps(standards), encoding="utf-8")
        if brief is None:
            args.append("--no-brief")
        else:
            (root / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
            args += ["--brief", str(root / "brief.json")]
        return subprocess.run(args, capture_output=True, text=True, timeout=120)


def probe_finding(severity="note", cards=("Probe Card",), problem="a probe problem",
                  **suggestion):
    entry = {"severity": severity, "cards": list(cards), "problem": problem}
    entry.update(suggestion)
    return entry


def block_lines(stdout, prefix):
    return [l for l in stdout.splitlines() if l.startswith(prefix)]


def check_review_verdict_arithmetic(_ctx):
    problems = []
    cases = [
        # (standards findings, brief findings, axis verdicts, overall)
        ([], [], ("standards: ship", "brief: ship"), "verdict: ship"),
        ([probe_finding()], [], ("standards: playable", "brief: ship"),
         "verdict: playable"),
        ([probe_finding(), probe_finding("blocker")], [probe_finding()],
         ("standards: rebuild", "brief: playable"), "verdict: rebuild"),
        ([], [probe_finding("blocker")], ("standards: ship", "brief: rebuild"),
         "verdict: rebuild"),
        # A blocker past the display cap still rebuilds the axis.
        ([probe_finding(cards=(f"Note {n}",)) for n in range(5)]
         + [probe_finding("blocker", ("Buried Blocker",))], [],
         ("standards: rebuild", "brief: ship"), "verdict: rebuild"),
    ]
    for standards, brief, axes, overall in cases:
        run = run_assembler(standards, brief)
        if run.returncode != 0:
            problems.append(f"assembler failed: {run.stderr.strip()[:120]}")
            continue
        lines = run.stdout.splitlines()
        for want in (*axes, overall):
            if want not in lines:
                problems.append(
                    f"{len(standards)} standards / {len(brief)} brief findings: "
                    f"missing {want!r}")
    twice = [run_assembler([probe_finding("blocker")], [probe_finding()]).stdout
             for _ in range(2)]
    if twice[0] != twice[1]:
        problems.append("the same Findings assembled to different bytes")
    return not problems, "; ".join(problems) or (
        "blocker->rebuild, notes->playable, clean->ship, overall = worst axis, "
        "capped blockers still count, byte-deterministic"
    )


def check_review_block_shape(_ctx):
    run = run_assembler(
        [probe_finding("blocker", ("Corsair Captain", "Pirate's Cutlass"),
                       "a two-card island")],
        [probe_finding("note", ("Vaporkin",), "off the stated intent")],
    )
    if run.returncode != 0:
        return False, f"assembler failed: {run.stderr.strip()[:120]}"
    lines = run.stdout.splitlines()
    problems = []
    if lines[:3] != ["deck: Probe Deck", "date: 2026-08-18", "verdict: rebuild"]:
        problems.append(f"reference lines are {lines[:3]}")
    if len(block_lines(run.stdout, "verdict: ")) != 1:
        problems.append("not exactly one overall verdict: line")
    try:
        s, b = lines.index("standards: rebuild"), lines.index("brief: playable")
        if not s < b:
            problems.append("axis sections out of order")
        if "Corsair Captain; Pirate's Cutlass" not in lines[s + 1]:
            problems.append("the standards Finding does not name its cards")
        if "Vaporkin" not in lines[b + 1]:
            problems.append("the brief Finding does not name its card")
    except ValueError as exc:
        problems.append(f"missing axis section: {exc}")
    return not problems, "; ".join(problems) or (
        "deck:/date: reference lines, one verdict: line, standards then brief "
        "side by side, Findings naming cards"
    )


def check_review_findings_cap(_ctx):
    run = run_assembler(
        [probe_finding(cards=(f"Card {n}",)) for n in range(1, 8)], [])
    if run.returncode != 0:
        return False, f"assembler failed: {run.stderr.strip()[:120]}"
    shown = block_lines(run.stdout, "note — ")
    rest = block_lines(run.stdout, "rest: ")
    problems = []
    if len(shown) != 5:
        problems.append(f"{len(shown)} Findings shown, cap is 5")
    if rest != ["rest: 2 more notes — Card 6; Card 7"]:
        problems.append(f"rest summary is {rest}")
    ordered = run_assembler(
        [probe_finding("note", ("A Note",)), probe_finding("blocker", ("A Blocker",))],
        [])
    lines = ordered.stdout.splitlines()
    if not lines.index("blocker — A Blocker — a probe problem") < lines.index(
            "note — A Note — a probe problem"):
        problems.append("blockers do not rise above notes (worst first)")
    return not problems, "; ".join(problems) or (
        "five shown worst first, the rest folded into a one-line summary naming cards"
    )


def check_review_finding_shape(_ctx):
    problems = []
    good = run_assembler(
        [probe_finding(swap="Voyaging Satyr"),
         probe_finding(maybeboard="Rhystic Study")], [])
    if good.returncode != 0:
        problems.append(f"one-suggestion Findings refused: {good.stderr.strip()[:120]}")
    elif (" — swap: Voyaging Satyr" not in good.stdout
          or " — maybeboard: Rhystic Study" not in good.stdout):
        problems.append("suggestions do not render as swap:/maybeboard:")
    for label, bad in (
        ("two suggestions", probe_finding(swap="A", maybeboard="B")),
        ("no cards", probe_finding(cards=())),
        ("unknown severity", probe_finding(severity="fatal")),
        ("unknown key", probe_finding(fix="edit the deck")),
    ):
        run = run_assembler([bad], [])
        if run.returncode != 2 or run.stdout != "":
            problems.append(
                f"{label}: exit {run.returncode} with "
                f"{'output' if run.stdout else 'no output'}, want a clean refusal")
    return not problems, "; ".join(problems) or (
        "severity + cards + problem + at most one suggestion enforced; "
        "malformed Findings refused with exit 2 and no partial Block"
    )


def check_review_no_brief(_ctx):
    run = run_assembler([probe_finding()], None)
    if run.returncode != 0:
        return False, f"assembler failed: {run.stderr.strip()[:120]}"
    lines = run.stdout.splitlines()
    problems = []
    if "brief: no Brief available" not in lines:
        problems.append("the Brief axis does not report 'no Brief available'")
    if "verdict: playable" not in lines:
        problems.append("the overall Verdict is not the Standards axis alone")
    return not problems, "; ".join(problems) or (
        "Standards-only review: brief axis reports no Brief available, "
        "overall = the Standards verdict"
    )


def check_review_wiring(_ctx):
    problems = []
    command = REVIEW_COMMAND_PATH.read_text(encoding="utf-8")
    if "skills/review/SKILL.md" not in command:
        problems.append("commands/review.md never hands off to skills/review/SKILL.md")
    skill = REVIEW_SKILL_PATH.read_text(encoding="utf-8")
    pinned = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))["version"]
    m = re.search(r"^metadata:\n[ \t]+version:[ \t]*(\S+)", skill, re.MULTILINE)
    if not m:
        problems.append("skills/review/SKILL.md carries no metadata.version")
    elif m.group(1) != pinned:
        problems.append(
            f"skill metadata.version {m.group(1)} != pinned plugin version {pinned}"
        )
    return not problems, "; ".join(problems) or (
        f"/tutor:review wraps skills/review/SKILL.md, versioned {pinned} in lockstep"
    )


def check_smell_baseline(_ctx):
    text = REVIEW_SKILL_PATH.read_text(encoding="utf-8")
    missing = [name for name in SMELL_BASELINE_V1 if name not in text]
    return not missing, (
        f"skills/review/SKILL.md lacks the locked Smells {missing}" if missing
        else "all ten Smell baseline v1 names are pinned in the skill"
    )


def check_commander_review_standards(_ctx):
    text = COMMANDER_PROFILE.read_text(encoding="utf-8")
    standards = section_lines(text, "review_standards")
    named = {l.split(":", 1)[0] for l in standards}
    problems = []
    missing = [seed for seed in COMMANDER_REVIEW_SEEDS if seed not in named]
    if missing:
        problems.append(f"the Commander profile lacks review standards {missing}")
    if any(not l.partition(":")[2].strip() for l in standards):
        problems.append("a review standard carries no guidance text")
    skill = REVIEW_SKILL_PATH.read_text(encoding="utf-8")
    if "overrides the baseline" not in skill:
        problems.append("the skill never pins that the profile overrides the baseline")
    if "review_standards" not in skill:
        problems.append("the skill never reads the profile's review_standards")
    return not problems, "; ".join(problems) or (
        "politics, functional-copy redundancy, answer spread authored as data; "
        "the skill reads them and pins profile-overrides-baseline"
    )


def check_review_skill_content(_ctx):
    """Tripwire, not proof: the review flow is prompt-ware judged by its
    artifacts; these needles keep the load-bearing contract sentences from
    silently vanishing in an edit."""
    text = REVIEW_SKILL_PATH.read_text(encoding="utf-8")
    needles = [
        "two parallel subagents",
        "one per axis",
        "side by side",
        "sequential two-pass fallback",
        "trusts the green Suite",
        "never recounts",
        "mis-set for the Brief",
        "never edits the Deck",
        "ManaBox import",
        "consumes the Review Block",
        "no Brief available",
        "worst first",
        "Power fit, mass land denial, chained extra turns, and early two-card combos",
    ]
    missing = [n for n in needles if n not in text]
    return not missing, (
        f"skills/review/SKILL.md lacks {missing}" if missing
        else "fan-out and fallback, Suite trust, the mis-set flag, the no-edit rule, "
             "Verdict-dependent closings, and the judgment-not-Checks list are pinned"
    )


def check_review_flaw_registration(ctx):
    manifest = json.loads(ctx.path("manifest.json").read_text(encoding="utf-8"))
    deck_rel = "decks/tatyova-landfall-review-flawed.txt"
    flaws = manifest.get("planted_flaws", {}).get(deck_rel, [])
    problems = []
    if not flaws:
        problems.append(f"{deck_rel} registers no planted flaws")
    axes = {f.get("class") for f in flaws}
    if axes - {"standards", "brief"}:
        problems.append(f"Review-flawed flaw classes {sorted(axes)} are not review axes")
    if not any("smell" in f for f in flaws):
        problems.append("no flaw names the Smell it plants")
    unknown_smells = sorted(f["smell"] for f in flaws
                            if "smell" in f and f["smell"] not in SMELL_BASELINE_V1)
    if unknown_smells:
        problems.append(f"planted Smells {unknown_smells} are not locked "
                        "baseline v1 names")
    deck_text = ctx.path(deck_rel).read_text(encoding="utf-8")
    owned = {r["Name"] for r in ctx.read_manabox_csv("collections/real-collection.csv")}
    for flaw in flaws:
        for card in flaw.get("cards", []):
            if card not in deck_text:
                problems.append(f"{flaw['id']} names {card!r} not in the Deck")
            if card not in owned:
                problems.append(f"{flaw['id']} card {card!r} is not owned — "
                                "a Review flaw must not smuggle in a Check flaw")

    def run_suite(deck):
        return run_build_cli(
            SUITE_RUNNER,
            "--suite", ctx.path("build/tatyova-landfall.suite.yaml"),
            "--deck", ctx.path(deck),
            "--oracle", ctx.path("scryfall/oracle.jsonl"),
            "--collection", ctx.path("collections/real-collection.csv"),
            "--date", BUILD_REFERENCE_DATE,
        )

    clean = report_colors(run_suite("decks/tatyova-landfall.txt").stdout)
    flawed = report_colors(run_suite(deck_rel).stdout)
    if not clean:
        problems.append("no check lines parsed from the clean fixture run")
    leaked = [cid for cid, color in clean.items()
              if color == "green" and flawed.get(cid) != "green"]
    if leaked:
        problems.append(f"planted flaws leaked into Check territory: {leaked}")
    return not problems, "; ".join(problems) or (
        f"{len(flaws)} Review-territory flaws registered on owned, present cards, "
        "Smells from the locked baseline; every Check green on the clean Deck "
        "stays green on the Review-flawed one"
    )


# --- Build-to-green predicates (issue #54) ----------------------------------
# The build-deep case grades the finished Build offline: the committed built
# fixtures (Upgrade Brief, built Suite, shipped Deck Block, all-green report)
# through the deterministic seams — the availability and ship CLIs, the
# generator, and the unmodified fixed runner. Card choice and Role tagging
# are the judgment those fixtures record; the graders never re-judge.

BUILD_AVAILABILITY = REPO_ROOT / "skills" / "build" / "scripts" / "availability.py"
BUILD_SHIP = REPO_ROOT / "skills" / "build" / "scripts" / "ship_deck.py"

# A deliberate copy of ship_deck.py's FOOTER (kept in lockstep by hand, never
# imported — the harness grades the skill from outside). Edit them together.
FAN_CONTENT_FOOTER = (
    "// tutor is unofficial Fan Content permitted under the Fan Content "
    "Policy. Not approved/endorsed by Wizards. Portions of the materials "
    "used are property of Wizards of the Coast. ©Wizards of the Coast LLC."
)

UPGRADE_BRIEF_REL = "build/tatyova-upgrade.brief.txt"
BUILT_SUITE_REL = "build/tatyova-landfall.built.suite.yaml"
BUILT_DECK_REL = "build/tatyova-built-deck.txt"
BUILT_REPORT_REL = "build/tatyova-built-report.txt"


def check_upgrade_brief(ctx):
    brief = ctx.path(UPGRADE_BRIEF_REL)
    result = run_brief_script(BRIEF_VALIDATOR, brief,
                              "--collection", ctx.path("collections/real-collection.csv"))
    problems = []
    if result.returncode != 0:
        problems.append(f"the Upgrade Brief is invalid: {result.stdout.strip()[:200]}")
    text = brief.read_text(encoding="utf-8")
    if "donor: Tatyova, Benthic Druid" not in text:
        problems.append("the Upgrade never frees the target Deck's own rows via donor:")
    return not problems, "; ".join(problems) or (
        "valid against the Export; donor: lines free Baylen and the rebuilt "
        "Tatyova deck's own rows"
    )


def check_built_deck_collection_only(ctx):
    result = run_build_cli(
        BUILD_AVAILABILITY,
        "--collection", ctx.path("collections/real-collection.csv"),
        "--brief", ctx.path(UPGRADE_BRIEF_REL),
        "--deck", ctx.path(BUILT_DECK_REL),
    )
    if result.returncode != 0:
        declined = [l for l in result.stdout.splitlines() if l.startswith("wanted ")]
        return False, f"copies not free under the donor: lines: {declined[:5]}"
    return True, (
        f"{len(result.stdout.splitlines())} names checked at count — every copy "
        "free under the Brief's donor: lines"
    )


def check_contention_declined_sentence(ctx):
    # Exsanguinate: every owned copy committed to the Zoraline deck; the
    # original fixture Brief frees only Baylen — the want must be declined.
    result = run_build_cli(
        BUILD_AVAILABILITY,
        "--collection", ctx.path("collections/real-collection.csv"),
        "--brief", ctx.path("briefs/commander-tatyova-landfall.txt"),
        "--want", "Exsanguinate",
    )
    wanted = "wanted Exsanguinate; all copies committed to Zoraline, Cosmos Caller"
    problems = []
    if result.returncode != 1:
        problems.append(f"exit {result.returncode}, a declined want is 1")
    if wanted not in result.stdout:
        problems.append(f"sentence missing; stdout: {result.stdout.strip()[:200]}")
    return not problems, "; ".join(problems) or wanted


def run_built_suite(ctx, oracle=None):
    return run_build_cli(
        SUITE_RUNNER,
        "--suite", ctx.path(BUILT_SUITE_REL),
        "--deck", ctx.path(BUILT_DECK_REL),
        "--oracle", oracle or ctx.path("scryfall/oracle.jsonl"),
        "--collection", ctx.path("collections/real-collection.csv"),
        "--date", BUILD_REFERENCE_DATE,
    )


def check_built_report_green(ctx):
    result = run_built_suite(ctx)
    problems = []
    if result.returncode != 0:
        problems.append(f"exit {result.returncode}, green is 0")
    committed = ctx.path(BUILT_REPORT_REL).read_text(encoding="utf-8")
    if result.stdout != committed:
        problems.append("report differs from the committed all-green reference")
    if "verdict: green — 0 red /" not in result.stdout:
        problems.append("no all-green verdict line")
    return not problems, "; ".join(problems) or (
        "the built Suite re-ran byte-identical to the committed all-green "
        "report through the unmodified runner"
    )


def check_built_suite_roles_only(ctx):
    regenerated = run_build_cli(
        BUILD_GENERATOR,
        "--brief", ctx.path(UPGRADE_BRIEF_REL),
        "--profile", COMMANDER_PROFILE,
        "--oracle", ctx.path("scryfall/oracle.jsonl"),
        "--date", BUILD_REFERENCE_DATE,
    )
    if regenerated.returncode != 0:
        return False, f"generate_suite.py failed: {regenerated.stderr.strip()[:200]}"
    without_roles, role_lines, in_roles = [], [], False
    for line in ctx.path(BUILT_SUITE_REL).read_text(encoding="utf-8").splitlines(True):
        if not line.startswith(" ") and line.strip():
            in_roles = line.rstrip() == "roles:"
        if in_roles and line.startswith("  ") and not line.lstrip().startswith("#"):
            role_lines.append(line)
            continue
        without_roles.append(line)
    problems = []
    if "".join(without_roles) != regenerated.stdout:
        problems.append("the built Suite differs beyond its roles: section — a target was bent")
    if not role_lines:
        problems.append("no Role judgment recorded in the roles: section")
    tags = {t.strip() for l in role_lines for t in l.split("[", 1)[1].rstrip("]\n").split(",")}
    if not tags <= ROLE_VOCABULARY:
        problems.append(f"Role tags outside the vocabulary: {sorted(tags - ROLE_VOCABULARY)}")
    return not problems, "; ".join(problems) or (
        f"built Suite = generated Suite + {len(role_lines)} recorded Role "
        "lines, every tag in the global vocabulary"
    )


def parse_shipped_block(text):
    """The shipped Deck Block, read board by board: returns (title, boards)
    where boards maps a Board name to its raw card lines in order."""
    lines = text.splitlines()
    title = lines[0] if lines else ""
    boards, board = {}, None
    for line in lines[1:]:
        if line in ("// Commander", "// Mainboard", "// Sideboard", "// Maybeboard"):
            board = line[3:]
            boards[board] = []
        elif line.strip() and not line.startswith("//") and board:
            boards[board].append(line)
    return title, boards


def check_shipped_block_shape(ctx):
    text = ctx.path(BUILT_DECK_REL).read_text(encoding="utf-8")
    owned_pins = {}
    for row in ctx.read_manabox_csv("collections/real-collection.csv"):
        owned_pins.setdefault(row["Name"], set()).add(
            (row["Set code"], row["Collector number"]))
    title, boards = parse_shipped_block(text)
    problems = []
    if title != "// Tatyova Landfall":
        problems.append(f"first line is {title!r}, not the '// <name>' title")
    if set(boards) != {"Commander", "Mainboard", "Maybeboard"}:
        problems.append(f"Boards in use are {sorted(boards)}")
    categories = 0
    for board in ("Commander", "Mainboard"):
        basic_seen = False
        for line in boards.get(board, []):
            bare = re.match(r"^(\d+) ([^(]+?)$", line)
            if bare and bare.group(2).strip() in BASIC_NAMES:
                basic_seen = True
                continue
            if basic_seen:
                problems.append(f"{board}: card line after the lumped basics: {line!r}")
                break
            # PINNED_LINE is the harness's one pinned-line grammar — group 5
            # is the inline comment (None when absent).
            m = PINNED_LINE.match(line)
            if not m:
                problems.append(f"{board}: nonbasic without a printing pin: {line!r}")
                break
            if (m.group(3), m.group(4)) not in owned_pins.get(m.group(2), set()):
                problems.append(f"{board}: pin not an owned printing: {line!r}")
                break
            if m.group(5):
                categories += 1
    mainboard = boards.get("Mainboard", [])
    basics = [l for l in mainboard if re.match(r"^\d+ [^(]+$", l)
              and l.split(" ", 1)[1] in BASIC_NAMES]
    if not basics:
        problems.append("no lumped basics in the Mainboard")
    else:
        if mainboard[-len(basics):] != basics:
            problems.append("basics are not last in the Mainboard")
        if f"\n\n{basics[0]}\n" not in text:
            problems.append("no blank line before the lumped basics")
    if not categories:
        problems.append("no inline // category comment survived the ship")
    if text.count(FAN_CONTENT_FOOTER) != 1:
        problems.append(f"Fan Content footer appears {text.count(FAN_CONTENT_FOOTER)} times")
    return not problems, "; ".join(problems) or (
        f"title, three Boards, every nonbasic pinned to an owned printing, "
        f"{categories} category comments, basics lumped last after a blank "
        "line, one Fan Content footer"
    )


def check_maybeboard_wishlist(ctx):
    text = ctx.path(BUILT_DECK_REL).read_text(encoding="utf-8")
    owned = {row["Name"] for row in ctx.read_manabox_csv("collections/real-collection.csv")}
    _, boards = parse_shipped_block(text)
    entries = boards.get("Maybeboard", [])
    problems = []
    if not entries:
        problems.append("no Maybeboard entries to grade")
    unowned = 0
    for line in entries:
        if re.search(r"\([A-Z0-9]{2,5}\) \S+", line.split(" // ")[0]):
            problems.append(f"a Maybeboard entry carries a printing pin: {line!r}")
        name = re.match(r"^\d+ (.+?)(?: // .*)?$", line).group(1)
        if name not in owned:
            unowned += 1
    if not unowned:
        problems.append("no unowned Maybeboard entry — the wishlist bend goes ungraded")
    return not problems, "; ".join(problems) or (
        f"{len(entries)} unpinned wishlist entries, {unowned} unowned — the "
        "one place the collection-only rule bends"
    )


def check_block_round_trip(ctx):
    committed = ctx.path(BUILT_DECK_REL).read_text(encoding="utf-8")
    reshipped = run_build_cli(
        BUILD_SHIP,
        "--deck", ctx.path(BUILT_DECK_REL),
        "--collection", ctx.path("collections/real-collection.csv"),
        "--brief", ctx.path(UPGRADE_BRIEF_REL),
        "--oracle", ctx.path("scryfall/oracle.jsonl"),
    )
    problems = []
    if reshipped.returncode != 0:
        problems.append(f"re-ship failed: {reshipped.stderr.strip()[:200]}")
    elif reshipped.stdout != committed:
        problems.append("re-shipping the shipped Block changed its bytes")
    report = ctx.path(BUILT_REPORT_REL).read_text(encoding="utf-8")
    if "green legality.size — 100 cards, need exactly 100" not in report:
        problems.append("the committed report does not read 100 cards from the Block")
    return not problems, "; ".join(problems) or (
        "re-ship byte-identical; the runner reads the full 100 cards"
    )


def check_oracle_gap_degrades(ctx):
    import tempfile

    lines = [l for l in ctx.path("scryfall/oracle.jsonl").read_text(
        encoding="utf-8").splitlines() if '"Divination"' not in l]
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        gapped = pathlib.Path(tmp) / "oracle.jsonl"
        gapped.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = run_built_suite(ctx, oracle=gapped)
    if result.returncode not in (0, 1):
        problems.append(f"exit {result.returncode} — a gap must never be the "
                        "wrong-Suite refusal or a crash")
    if "unknown to Oracle: Divination" not in result.stdout:
        problems.append("the uncovered card is not named in the report head")
    if "verdict:" not in result.stdout:
        problems.append("no verdict line — the report was withheld")
    return not problems, "; ".join(problems) or (
        "Divination dropped from the Oracle: the runner still reports, names "
        "it in the head, and verdicts the rest"
    )


def check_pasted_export_tolerance(ctx):
    import tempfile

    raw = ctx.path("collections/real-collection.csv").read_bytes()
    text = raw.decode("utf-8-sig")
    rows = [r for r in csv.reader(io.StringIO(text))]
    pasted_io = io.StringIO()
    csv.writer(pasted_io, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(rows)
    pasted_bytes = b"\xef\xbb\xbf" + pasted_io.getvalue().encode("utf-8")

    def availability_over(export_path):
        return run_build_cli(
            BUILD_AVAILABILITY,
            "--collection", export_path,
            "--brief", ctx.path(UPGRADE_BRIEF_REL),
            "--deck", ctx.path(BUILT_DECK_REL),
        )

    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        pasted = pathlib.Path(tmp) / "pasted-collection.csv"
        pasted.write_bytes(pasted_bytes)
        from_paste = availability_over(pasted)
    from_file = availability_over(ctx.path("collections/real-collection.csv"))
    if from_paste.returncode != from_file.returncode:
        problems.append(f"exit codes diverge: paste {from_paste.returncode}, "
                        f"file {from_file.returncode}")
    if from_paste.stdout != from_file.stdout:
        problems.append("verdicts diverge between the paste-shaped and file Exports")
    return not problems, "; ".join(problems) or (
        "BOM + CRLF + full quoting: byte-identical availability verdicts"
    )


def check_build_loop_content(_ctx):
    """Tripwire, not proof: the loop is prompt-ware judged by its artifacts;
    these needles keep the back half's load-bearing sentences from silently
    vanishing."""
    text = BUILD_SKILL_PATH.read_text(encoding="utf-8")
    needles = [
        "until the Suite is green",
        "never bend",
        "availability.py",
        "declined contention",
        "loosen the Brief",
        "accept the Deck as-is",
        "acquire cards",
        "ship_deck.py",
        "Fan Content",
        "informational only",
        "Maybeboard",
        "uncovered cards",
        "/tutor:review",
        "Deck Block and the Brief",
    ]
    missing = [n for n in needles if n not in text]
    return not missing, (
        f"skills/build/SKILL.md lacks {missing}" if missing
        else "the loop, contention, the three red-ending options, the shipped "
             "Block with footer and caveat, the wishlist, and the Review "
             "handoff are pinned"
    )


# --- Registry: exact expectation text -> fixed predicate --------------------
# Keys are pinned verbatim to the strings in evals.json; editing a wording
# means editing both, deliberately. Unregistered expectations are soft.

EXPECTATION_CHECKS = {
    "The realism fixture collections/real-collection.csv parses header-keyed as CSV with exactly 577 data rows.":
        check_realism_row_count,
    "A synthetic Collection row carries the etched Foil value the real Export lacks.":
        check_etched_foil,
    "Synthetic Collection rows carry non-English Language codes the real Export lacks, including the disputed zhs.":
        check_non_english_languages,
    "A synthetic Collection row carries a promo collector number (letter-suffixed or starred) the real Export lacks.":
        check_promo_collector_numbers,
    "Per-Format shaped pool Collections cover Kitchen 20 (Uncharted Haven beside mono-white candidates) and Standard (playset quantities), parsing with the full ManaBox header.":
        check_per_format_pools,
    "Fixture Briefs parse as flat key: value Blocks with the required format: line and only canonical Brief keys.":
        check_fixture_briefs,
    "Fixture Decks parse as ManaBox-importable Deck Blocks: title comment, Board headers, quantity lines with set-and-number pins on nonbasics.":
        check_fixture_decks,
    "Some fixture Decks carry planted flaws for Review evals, each registered in the manifest and naming cards present in its Deck (or absent from every Collection for availability flaws).":
        check_planted_flaws,
    "The pinned Scryfall snapshot covers every card the fixtures reference and nothing else, with its capture metadata on line one.":
        check_snapshot_coverage,
    "The fixture Oracle scryfall/oracle.jsonl is byte-identical to a fresh offline derivation from the pinned snapshot.":
        check_oracle_rederivation,
    "Every Oracle line is name-keyed with mana value, colors, color identity, type line, oracle text, the four sanctioned legalities, and the game_changer flag — no UUIDs, tokens excluded, basics included, multi-faced names flattened with //.":
        check_oracle_shape,
    "The Oracle's first line records generated_at and the source Export's newest Added watermark.":
        check_oracle_watermark,
    "Evals never touch the network: a tripwire scan finds the literal live Scryfall API host string in no eval or fixture file except the deliberate refresh script and the snapshot's provenance metadata.":
        check_offline_guarantee,
    "Run offline against the pinned snapshot, the oracle script writes the Oracle beside the realism Export: line one records generated_at plus the source Export's newest Added watermark, then one line per unique card name.":
        check_oracle_skill_output,
    "Every Oracle line the script writes is byte-identical to the fixture Oracle's line for the same card — the shape-exact record with four-Format legalities, the game_changer boolean, tokens excluded, basics included, multi-faced names flattened with //, and no UUIDs.":
        check_oracle_skill_agreement,
    "Malformed Export rows are skipped and reported with a count and examples, and a header missing the identity columns is the only hard failure.":
        check_oracle_skill_tolerance,
    "An Export row whose Scryfall ID the snapshot no longer knows still resolves through its Name + Set code.":
        check_oracle_skill_fallback,
    "The /tutor:brief command is a thin wrapper handing off to the brief skill, whose metadata.version matches the plugin manifest's pinned version.":
        check_brief_wiring,
    "The brief skill's description fires from natural language: it names deck-intent triggers beyond the /tutor:brief command itself.":
        check_brief_nl_triggers,
    "Every fixture Brief validates against the brief skill's validator, donors recognized from its manifest-paired Export's deck rows.":
        check_fixture_briefs_validate,
    "The validator holds the Power ladder: a 1-5 number with trailing free text passes and an out-of-ladder number fails.":
        check_power_ladder,
    "The validator holds donor grammar: donor: all passes and an unrecognized donor Deck name fails against the Export's deck rows.":
        check_donor_grammar,
    "No fixture Brief declares a play variant as its format:, and the Archenemy fixture expresses the variant in play variant: with the Centerpiece naming the villain.":
        check_play_variants_never_formats,
    "The freshness helper surfaces the fixture Export's newest Added and both Oracle staleness signals deterministically, and degrades gracefully when the Oracle is absent.":
        check_freshness_helper,
    "The brief skill's text pins the grammar it must emit: all nine canonical keys, only format required, no budget key, Power defaulting to 2, one freshness question, and a closing handoff to Build.":
        check_brief_skill_content,
    "The Commander Format profile is first-class declarative data: deck size 100, singleton copy limit, lands, curve, and consistency check targets, per-bracket Game Changers limits 0 / 0 / 3 / unlimited / unlimited for Power 1-5, a banlist parameter, and judgment-flavored Role guidance.":
        check_commander_profile,
    "Run over the fixture Tatyova Brief, the Commander profile, and the fixture Oracle, the Suite generator reproduces the committed fixture Suite byte-identical — declarative data, never code.":
        check_suite_generation_reproducible,
    "The fixture Suite carries every generated Check class — Legality, Availability, Mana base, Curve, Quotas over the global Role vocabulary, mechanical Brief constraints, hypergeometric Consistency — with no budget class, targets snapshotted from the profile, Brief-set values under brief: provenance comments, and an empty roles: section because no card is picked yet.":
        check_suite_shape,
    "Through the unmodified runner, the empty fixture Deck reports byte-identical to the committed reference: every size, mana-base-count, curve, and quota Check red, the singleton, color identity, banlist, Game Changers, and availability Checks vacuously green, exit code red.":
        check_empty_deck_red,
    "The /tutor:build command is a thin wrapper handing off to the build skill, whose metadata.version matches the plugin manifest's pinned version.":
        check_build_wiring,
    "The build skill's text pins the front half: the Suite and its report written to the Collection home, the offer to generate an absent Oracle via /tutor:oracle when network allows, a pasted Export or Block beating the file, a refused constraint going back to the Brief, and no card picked before the Suite exists.":
        check_build_skill_content,
    "Verdicts are arithmetic over Findings, hard-graded through the assembler: any blocker makes an axis rebuild, only notes playable, clean ship, the overall Verdict is the worst axis, a blocker past the display cap still rebuilds, and the same Findings assemble to the same bytes — no fresh judgment in aggregation.":
        check_review_verdict_arithmetic,
    "The assembled Review Block carries deck: and date: reference lines, one overall verdict: line, then one section per axis — standards: first, brief: second, side by side, never merged or reranked — each with its own verdict and Findings naming cards.":
        check_review_block_shape,
    "Each axis shows at most five Findings, worst first, with a one-line summary of the rest naming its cards.":
        check_review_findings_cap,
    "A Finding is a severity (blocker or note), named cards, the problem, and at most one suggestion — an owned swap or an unowned Maybeboard candidate; the assembler refuses a malformed Finding with exit 2 and no partial Block.":
        check_review_finding_shape,
    "With no Brief the review runs Standards-only: the Brief axis reports no Brief available and the overall Verdict is the Standards axis alone.":
        check_review_no_brief,
    "The /tutor:review command is a thin wrapper handing off to the review skill, whose metadata.version matches the plugin manifest's pinned version.":
        check_review_wiring,
    "The review skill pins the locked Smell baseline v1 by name: synergy island, dead card, win-more, no comeback plan, piloting overload, fragile mana, theme tax, redundancy gap, curve lie, interaction mismatch.":
        check_smell_baseline,
    "The Commander profile authors the per-Format review standards from the recorded seeds — politics, functional-copy redundancy, answer spread — as data the Standards axis reads, and the review skill pins that the profile overrides the baseline.":
        check_commander_review_standards,
    "The review skill's text pins the contract: two parallel subagents, one per axis, aggregated side by side with the sequential two-pass fallback as robustness; Review trusts the green Suite and never recounts Check territory but may flag a Check target as mis-set for the Brief; Review never edits the Deck; ship closes with the ManaBox import suggestion while playable and rebuild offer a Build re-run consuming the Review Block; Power fit, mass land denial, chained extra turns, and early two-card combos are Review judgment, not Checks.":
        check_review_skill_content,
    "The Review-flawed fixture Deck plants only Review-territory flaws: every Check green on the clean fixture Deck stays green on it through the unmodified runner, and each registered standards/brief flaw names owned cards present in the Deck.":
        check_review_flaw_registration,
    "The Upgrade Brief validates against the Export and frees the target Deck's own rows through donor: lines — an Upgrade is an ordinary Build re-run with the existing Deck's copies freed.":
        check_upgrade_brief,
    "Every card in the built Deck is drawn from the Collection fixture: contention-aware availability over the Export's deck rows reports every copy free under the Brief's donor: lines.":
        check_built_deck_collection_only,
    "Declined contention is reported in the honest sentence shape: a want whose copies are all committed to a Deck the Brief never freed comes back as 'wanted <card>; all copies committed to <deck>'.":
        check_contention_declined_sentence,
    "Format legality holds and the Suite re-runs through the fixed runner: the built Suite over the shipped Deck Block reproduces the committed all-green report byte-identical, exit green.":
        check_built_report_green,
    "Build never bends targets: the built Suite differs from a fresh generation over the Upgrade Brief only by the Role tags recorded in its roles: section.":
        check_built_suite_roles_only,
    "The shipped Deck Block parses as ManaBox-importable text: '// <name>' first, reserved Board headers only for Boards in use, every nonbasic outside the Maybeboard pinned to an owned printing with set code and collector number, inline '// category' comments, basics lumped per name last in their Board after a blank line, and the short-form Fan Content footer line exactly once.":
        check_shipped_block_shape,
    "The Maybeboard is the wishlist Board: its entries carry no printing pin and may be unowned — the one place the collection-only rule bends.":
        check_maybeboard_wishlist,
    "Blocks survive the round-trip: re-shipping the shipped Deck Block reproduces it byte-identical, and the committed report reads the full 100 cards from it.":
        check_block_round_trip,
    "A Deck card missing from the Oracle degrades per-card to flagged model knowledge, never a hard failure: the runner still reports with the uncovered card named in the report head.":
        check_oracle_gap_degrades,
    "The pasted-Export case holds as parser-tolerance smoke: the same availability verdicts from a paste-shaped Export — BOM, CRLF line endings, extra quoting — as from the file on disk.":
        check_pasted_export_tolerance,
    "The build skill's text pins the back half: the loop through the fixed runner with targets never bent, contention consulted and declined contention reported out loud, the honest red ending with the human's three options, the shipped Deck Block with the Fan Content footer and the informational-only legality caveat, the Maybeboard wishlist, and closing instructions naming the Blocks Review needs.":
        check_build_loop_content,
}


# --- Runner -----------------------------------------------------------------

def load_cases():
    data = json.loads((EVALS_DIR / "evals.json").read_text(encoding="utf-8"))
    return data["skill_name"], data["evals"]


def case_name(case):
    return CASE_NAMES.get(case["id"], f"eval-{case['id']}")


def grade_case(case, ctx, out_dir):
    """Grade one case's mechanical expectations; return (all_passed, lines)."""
    name = case_name(case)
    graded, soft, lines = [], [], [f"## {name} (eval id {case['id']})"]
    for text in case["expectations"]:
        checker = EXPECTATION_CHECKS.get(text)
        if checker is None:
            soft.append(text)
            lines.append(f"soft   — {text}")
            continue
        try:
            passed, evidence = checker(ctx)
        except Exception as exc:  # a crashed predicate is a red, with evidence
            passed, evidence = False, f"predicate raised {type(exc).__name__}: {exc}"
        graded.append({"text": text, "passed": passed, "evidence": evidence})
        lines.append(f"{'green' if passed else 'RED  '}  — {text}")
        if not passed:
            lines.append(f"         evidence: {evidence}")

    passed_n = sum(1 for e in graded if e["passed"])
    failed_n = len(graded) - passed_n
    case_dir = out_dir / name
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "eval_metadata.json").write_text(
        json.dumps(
            {
                "eval_id": case["id"],
                "eval_name": name,
                "prompt": case["prompt"],
                "assertions": list(case["expectations"]),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (case_dir / "grading.json").write_text(
        json.dumps(
            {
                "expectations": graded,
                "summary": {
                    "passed": passed_n,
                    "failed": failed_n,
                    "total": len(graded),
                    "pass_rate": round(passed_n / len(graded), 4) if graded else 0.0,
                },
                "soft_expectations": soft,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    lines.append(
        f"{passed_n}/{len(graded)} mechanical expectations green"
        + (f"; {len(soft)} soft (dev-time judgment)" if soft else "")
    )
    return failed_n == 0, lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", help="run only the case with this name or id")
    parser.add_argument(
        "--fixture-root",
        default=str(EVALS_DIR / "fixtures"),
        help="fixture tree to grade (default: evals/fixtures)",
    )
    parser.add_argument(
        "--out",
        default=str(EVALS_DIR / "results"),
        help="where per-case results land (default: evals/results)",
    )
    args = parser.parse_args(argv)

    skill_name, cases = load_cases()
    if args.case:
        cases = [
            c for c in cases
            if args.case in (str(c["id"]), case_name(c))
        ]
        if not cases:
            print(f"no eval case named {args.case!r}", file=sys.stderr)
            return 2

    ctx = Context(args.fixture_root)
    out_dir = pathlib.Path(args.out)
    print(f"# {skill_name} offline eval run")
    all_green = True
    for case in cases:
        ok, lines = grade_case(case, ctx, out_dir)
        all_green = all_green and ok
        print()
        print("\n".join(lines))

    print()
    print("GREEN — offline eval run passed" if all_green else "RED — offline eval run failed")
    return 0 if all_green else 1


if __name__ == "__main__":
    sys.exit(main())
