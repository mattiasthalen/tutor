#!/usr/bin/env python3
"""tutor Suite generator — the mechanical half of Build start (issue #53).

At Build start the Suite — every deterministic Check the Deck must pass — is
generated from the Brief and its Format profile, before any card is picked
(ADR 0003 as amended by ADR 0005). This script does the judgment-free part:
it snapshots the profile's targets, applies the only overrides allowed — the
Brief's — translates mechanical Brief constraints into Check parameters, and
emits the declarative Suite the fixed runner
(skills/suite-runner/scripts/check_deck.py) interprets. Data, never code.

What is deterministic lives here; what is judgment stays out. Role tags are
judgment recorded once per card *as Build tags it* — the emitted `roles:`
section is empty because no card is picked yet. Every value the Brief sets or
overrides carries a full-line `# brief:` provenance comment: targets come
from the Format profile and are never silently bent.

Constraint grammar (a `constraint:` line must match one of these, or the run
refuses — re-phrase the Brief rather than let a constraint be dropped):

  nothing above N mana        -> constraints.cmc_max: N   (also "no cards
                                 above N mana"; "mv" / "mana value" for "mana")
  at least N lands            -> profile.lands_min: N (lands_max raised to N
                                 when the range would invert)
  at most N lands             -> profile.lands_max: N (lands_min lowered to N
                                 when the range would invert)
  at least N <role> cards     -> quotas.<role>: N, where <role> is in the
                                 global Role vocabulary (ramp, draw, removal,
                                 wipe, wincon, theme, other; trailing "s" ok)
  must include <card name>    -> constraints.must_include entry

Usage:
    generate_suite.py --brief BRIEF --profile PROFILE [--oracle ORACLE]
                      [--date YYYY-MM-DD] [--out FILE]

The Suite goes to stdout (or --out); everything else goes to stderr.
Exit status: 0 generated, 1 refused (the Brief and profile cannot honestly
yield a Suite — the message says why), 2 unusable input. Stdlib only.
"""

import argparse
import json
import re
import sys
from datetime import date

# ---------- tiny YAML-subset parser ----------
# A deliberate copy of the runner's (check_deck.py) parser: 2-space indents,
# dicts, lists, inline [a, b]. Kept in lockstep by hand, not imported — skill
# assets stay self-contained. What this emits, that parser must re-read; a
# test pins the two sources byte-identical (test_build_skill.py).

def parse_scalar(s):
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [parse_scalar(x) for x in inner.split(",")] if inner else []
    if s in ("true", "false"):
        return s == "true"
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s

def parse_yaml(text):
    lines = [l.rstrip() for l in text.splitlines()
             if l.strip() and not l.strip().startswith("#")]

    def indent_of(l):
        return len(l) - len(l.lstrip())

    def parse_block(i, ind):
        if lines[i].lstrip().startswith("- "):
            items = []
            while i < len(lines) and indent_of(lines[i]) == ind and lines[i].lstrip().startswith("- "):
                head = lines[i].lstrip()[2:]
                if ":" in head:  # list of dicts: "- key: value" + deeper keys
                    item = {}
                    k, _, v = head.partition(":")
                    item[k.strip()] = parse_scalar(v)
                    i += 1
                    while i < len(lines) and indent_of(lines[i]) == ind + 2 and not lines[i].lstrip().startswith("- "):
                        k, _, v = lines[i].lstrip().partition(":")
                        item[k.strip()] = parse_scalar(v)
                        i += 1
                    items.append(item)
                else:
                    items.append(parse_scalar(head))
                    i += 1
            return items, i
        out = {}
        while i < len(lines) and indent_of(lines[i]) == ind:
            l = lines[i].lstrip()
            k, _, v = l.partition(":")
            if v.strip():
                out[k.strip()] = parse_scalar(v)
                i += 1
            else:
                sub, i2 = parse_block(i + 1, indent_of(lines[i + 1])) if i + 1 < len(lines) and indent_of(lines[i + 1]) > ind else ({}, i + 1)
                out[k.strip()] = sub
                i = i2
        return out, i

    val, _ = parse_block(0, 0)
    return val

# ---------- inputs ----------

BRIEF_KEYS = (
    "name", "format", "centerpiece", "identity", "play variant",
    "power", "constraint", "donor", "notes",
)
# Mirrors validate_brief.py's REPEATABLE_KEYS — the one authority on the
# Brief grammar; every other key may appear at most once.
REPEATABLE_KEYS = ("constraint", "donor")

def refuse(message):
    print(message, file=sys.stderr)
    sys.exit(1)

def unusable(message):
    print(message, file=sys.stderr)
    sys.exit(2)

def parse_brief(text):
    """A Brief Block: flat key: value lines, constraint/donor repeatable.
    Grammar problems are the validator's job (validate_brief.py) — run it
    first; here any line the validator would reject — non-canonical, or a
    repeat of a non-repeatable key — is unusable input, its rule mirrored."""
    fields, constraints = {}, []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep or key not in BRIEF_KEYS or not value.strip():
            unusable(f"brief line {number} is not a canonical 'key: value' line: "
                     f"{line!r} — validate the Brief first (validate_brief.py)")
        if key == "constraint":
            constraints.append(value.strip())
        elif key in REPEATABLE_KEYS:
            fields.setdefault(key, value.strip())
        elif key in fields:
            unusable(f"brief line {number} repeats {key!r} — only "
                     f"{', '.join(REPEATABLE_KEYS)} are repeatable; validate the "
                     "Brief first (validate_brief.py)")
        else:
            fields[key] = value.strip()
    if "format" not in fields:
        unusable("the Brief has no format: line — validate the Brief first")
    return fields, constraints

def load_oracle(path):
    """Card facts by name: oracle.jsonl (first line metadata, ADR 0007) or a
    JSON array."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        unusable(f"cannot read the Oracle: {exc}")
    records = (json.loads(text) if text.lstrip().startswith("[")
               else [json.loads(line) for line in text.splitlines() if line.strip()])
    return {c["name"]: c for c in records if "name" in c}

# ---------- the Brief's voice: identity, Power, constraints ----------

NAMED_IDENTITIES = {
    "white": "W", "blue": "U", "black": "B", "red": "R", "green": "G",
    "colorless": "",
    "azorius": "WU", "dimir": "UB", "rakdos": "BR", "gruul": "RG",
    "selesnya": "GW", "orzhov": "WB", "izzet": "UR", "golgari": "BG",
    "boros": "RW", "simic": "GU",
    "bant": "GWU", "esper": "WUB", "grixis": "UBR", "jund": "BRG", "naya": "RGW",
    "abzan": "WBG", "jeskai": "URW", "sultai": "BGU", "mardu": "RWB", "temur": "GUR",
    "five-color": "WUBRG", "five color": "WUBRG", "wubrg": "WUBRG",
}

def identity_colors(value):
    """A Brief identity: value as a set of color letters, or None when the
    word is not a named identity."""
    word = value.strip().lower()
    if word in NAMED_IDENTITIES:
        return set(NAMED_IDENTITIES[word])
    letters = re.sub(r"[^a-z]", "", word)
    if letters and set(letters) <= set("wubrg"):
        return set(letters.upper())
    return None

ROLE_VOCABULARY = ("ramp", "draw", "removal", "wipe", "wincon", "land", "theme", "other")

CMC_MAX = re.compile(r"^(?:nothing|no cards?) above (\d+) (?:mana|mv|mana value)$", re.I)
LANDS_MIN = re.compile(r"^at least (\d+) lands$", re.I)
LANDS_MAX = re.compile(r"^at most (\d+) lands$", re.I)
MUST_INCLUDE = re.compile(r"^must include (.+)$", re.I)
QUOTA = re.compile(r"^at least (\d+) (.+?)(?: cards?)?$", re.I)

GRAMMAR_HINT = (
    "the constraint grammar is: 'nothing above N mana', 'at least N lands', "
    "'at most N lands', 'at least N <role> cards' (role one of "
    f"{', '.join(r for r in ROLE_VOCABULARY if r != 'land')}), "
    "'must include <card name>'"
)

def apply_constraints(lines, profile, quotas, comments):
    """Translate every Brief constraint: line into Check parameters. Returns
    (constraints dict, per-key comment lines, must-include pairs — each a
    (provenance comment, card name)). An untranslatable line refuses the
    whole run: a target is never silently bent, a constraint never silently
    dropped."""
    cons, cons_comments = {}, {}
    must = []
    for line in lines:
        m = CMC_MAX.match(line)
        if m:
            value = int(m.group(1))
            if "cmc_max" in cons and cons["cmc_max"] != value:
                refuse(f"conflicting constraints: cmc_max {cons['cmc_max']} vs {value}")
            cons["cmc_max"] = value
            cons_comments["cmc_max"] = [f"# brief: constraint: {line}"]
            continue
        m = LANDS_MIN.match(line)
        if m:
            profile["lands_min"] = int(m.group(1))
            profile["lands_max"] = max(profile.get("lands_max", 0), profile["lands_min"])
            comments["lands_min"] = [f"# brief: constraint: {line}"]
            continue
        m = LANDS_MAX.match(line)
        if m:
            profile["lands_max"] = int(m.group(1))
            profile["lands_min"] = min(profile.get("lands_min", 0), profile["lands_max"])
            comments["lands_max"] = [f"# brief: constraint: {line}"]
            continue
        m = MUST_INCLUDE.match(line)
        if m:
            must.append((f"# brief: constraint: {line}", m.group(1).strip()))
            continue
        m = QUOTA.match(line)
        if m:
            role = m.group(2).strip().lower()
            if role not in ROLE_VOCABULARY and role.rstrip("s") in ROLE_VOCABULARY:
                role = role.rstrip("s")
            if role not in ROLE_VOCABULARY or role == "land":
                refuse(f"constraint asks a quota for {role!r}, which is not in the "
                       f"global Role vocabulary ({', '.join(ROLE_VOCABULARY)}) — "
                       "re-phrase the Brief (a named archetype is usually 'theme')")
            quotas[role] = int(m.group(1))
            comments[f"quota.{role}"] = [f"# brief: constraint: {line}"]
            continue
        refuse(f"constraint not translatable to a fixed Check: {line!r} — {GRAMMAR_HINT}. "
               "Re-phrase the Brief; a Suite never silently drops a constraint.")
    return cons, cons_comments, must

# ---------- emission ----------

def fmt(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(fmt(v) for v in value) + "]"
    return str(value)

HEAD_COMMENT = """\
# Suite Block — generated at Build start from the Brief and the Format profile,
# before any card is picked (ADR 0005). Data only: targets are snapshotted,
# judgment lands as data, the fixed runner interprets. Re-running the Suite
# (including at Upgrade) reuses this file as-is; only a changed Brief
# regenerates it.
"""

def emit(suite_name, display_format, generated, brief_line, profile, comments,
         quotas, cons, cons_comments, must, checks):
    out = [HEAD_COMMENT]
    out.append(f"suite: {suite_name}")
    out.append(f"format: {display_format}")
    out.append(f"generated: {generated}")
    out.append(f"brief: {brief_line}")
    out.append("")
    out.append("profile:")
    out.append('  # Format-profile targets snapshotted at generation. Lines under a "brief:"')
    out.append("  # comment were set or overridden by the Brief — the only voice allowed to.")
    for key, value in profile.items():
        for comment in comments.get(key, []):
            out.append(f"  {comment}")
        out.append(f"  {key}: {fmt(value)}")
    out.append("")
    out.append("quotas:")
    out.append("  # Role quotas over the global Role vocabulary. One Check per line.")
    for key, value in quotas.items():
        for comment in comments.get(f"quota.{key}", []):
            out.append(f"  {comment}")
        out.append(f"  {key}: {fmt(value)}")
    out.append("")
    out.append("constraints:")
    out.append("  # Mechanical Brief constraints (judgment-free), one Check each.")
    for key, value in cons.items():
        for comment in cons_comments.get(key, []):
            out.append(f"  {comment}")
        out.append(f"  {key}: {fmt(value)}")
    if must:
        out.append("  must_include:")
        for comment, name in must:
            out.append(f"    {comment}")
            out.append(f"    - {name}")
    out.append("")
    out.append("roles:")
    out.append("  # Card -> Role tags: judgment recorded once per card as Build tags it.")
    out.append("  # Empty at Build start — no card is picked yet.")
    out.append("")
    out.append("checks:")
    out.append("  # The Suite: every id resolves to a fixed predicate in the runner (or a")
    out.append("  # walkable sentence when no sandbox exists); every parameter lives above.")
    for check in checks:
        out.append(f"  - id: {check['id']}")
        out.append(f"    text: {check['text']}")
    return "\n".join(out) + "\n"

# ---------- assembly ----------

def build_suite(brief_text, profile_text, oracle, run_date):
    fields, constraint_lines = parse_brief(brief_text)
    prof = parse_yaml(profile_text)
    for section in ("format", "profile", "checks"):
        if section not in prof:
            unusable(f"the Format profile has no {section}: section")

    if fields["format"].strip().lower() != str(prof["format"]).strip().lower():
        refuse(f"the Brief is format: {fields['format']} but the profile is "
               f"{prof['format']} — pick the matching Format profile")

    profile = dict(prof["profile"])
    quotas = dict(prof.get("quotas", {}))
    comments = {}

    # The Centerpiece sets the color identity; the Oracle is its authority,
    # with the Brief's identity: word as fallback and cross-check.
    centerpiece = fields.get("centerpiece")
    if prof.get("centerpiece") == "required" and not centerpiece:
        refuse(f"{prof.get('display_name', prof['format'])} demands a centerpiece: "
               "line in the Brief, and this Brief has none")
    claimed = identity_colors(fields["identity"]) if "identity" in fields else None
    if "identity" in fields and claimed is None:
        refuse(f"identity: {fields['identity']!r} is not a named identity or a set "
               "of color letters")
    identity, identity_comment = None, None
    if centerpiece and oracle is not None:
        card = oracle.get(centerpiece)
        if card is None:
            refuse(f"centerpiece {centerpiece!r} is not in the Oracle — check the "
                   "name, or regenerate the Oracle (/tutor:oracle)")
        identity = set(card.get("color_identity", []))
        identity_comment = (f"# brief: centerpiece: {centerpiece} — color identity "
                            "from the Oracle")
        if claimed is not None and claimed != identity:
            refuse(f"the Brief says identity: {fields['identity']} "
                   f"({sorted(claimed)}) but the Oracle gives {centerpiece} the "
                   f"identity {sorted(identity)} — settle the Brief before building")
    elif claimed is not None:
        identity = claimed
        identity_comment = f"# brief: identity: {fields['identity']}"
    elif centerpiece:
        refuse(f"no Oracle to resolve the color identity of {centerpiece!r} — "
               "generate one (/tutor:oracle) or add an identity: line to the Brief")

    # Power reads through the profile: Commander reads it as the official
    # Bracket, whose Game Changers limit becomes a snapshotted target. An
    # unstated Power defaults to 2 — labelled "default:", never worn as the
    # Brief's voice.
    power_voice = "brief" if "power" in fields else "default"
    power_value = fields.get("power", "2").strip()
    m = re.match(r"^([1-5])(?:[\s,].*)?$", power_value)
    if not m:
        unusable(f"power: {power_value!r} is not on the 1-5 ladder — validate the "
                 "Brief first")
    power = int(m.group(1))
    gc_table = prof.get("game_changers_max_by_power", {})
    gc_limit = gc_table.get(str(power), "unlimited") if gc_table else None

    cons, cons_comments, must = apply_constraints(
        constraint_lines, profile, quotas, comments)

    if identity is not None:
        profile["color_identity"] = sorted(identity)
        if identity_comment:
            comments["color_identity"] = [identity_comment]
    if gc_limit is not None and gc_limit != "unlimited":
        profile["game_changers_max"] = gc_limit
        comments["game_changers_max"] = [
            f"# {power_voice}: power: {power} — bracket allows {gc_limit} Game Changers"]
    if centerpiece and centerpiece not in (name for _, name in must):
        must.insert(0, (f"# brief: centerpiece: {centerpiece}", centerpiece))

    # The check list: profile templates in order, minus checks whose parameter
    # is unset, with quota and Brief Checks inserted before the consistency
    # Check (the report order the Kitchen 20 fixture Suite established).
    checks = []
    for check in prof["checks"]:
        if check["id"] == "legality.game_changers" and "game_changers_max" not in profile:
            continue
        if check["id"] == "legality.color_identity" and "color_identity" not in profile:
            continue
        checks.append(check)
    tail = [c for c in checks if str(c["id"]).startswith("consistency.")]
    body = [c for c in checks if not str(c["id"]).startswith("consistency.")]
    for tag in quotas:
        body.append({"id": f"quota.{tag}",
                     "text": f"At least {{quotas.{tag}}} cards tagged {tag}."})
    if "cmc_max" in cons:
        body.append({"id": "brief.cmc_max", "text": "No card above mana value {cmc_max}."})
    if must:
        body.append({"id": "brief.includes",
                     "text": "The Deck contains every must-include card ({must_include})."})
    checks = body + tail

    display = str(prof.get("display_name", prof["format"]))
    suite_name = fields.get("name") or centerpiece or display
    brief_line = " — ".join(
        [fields["format"]] + ([centerpiece] if centerpiece else []) + [f"power {power}"])
    return emit(suite_name, display, run_date, brief_line, profile, comments,
                quotas, cons, cons_comments, must, checks)

# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(
        description="Generate a declarative tutor Suite from a Brief and a Format profile.")
    ap.add_argument("--brief", required=True, help="Brief Block file")
    ap.add_argument("--profile", required=True, help="Format profile file (YAML-subset)")
    ap.add_argument("--oracle", help="Oracle card-facts file (oracle.jsonl or JSON array)")
    ap.add_argument("--date", default=None, metavar="YYYY-MM-DD",
                    help="date for the generated: line (default: today), for byte-stable output")
    ap.add_argument("--out", help="write the Suite here instead of stdout")
    args = ap.parse_args()

    try:
        brief_text = open(args.brief, encoding="utf-8").read()
    except OSError as exc:
        unusable(f"cannot read the Brief: {exc}")
    try:
        profile_text = open(args.profile, encoding="utf-8").read()
    except OSError as exc:
        unusable(f"cannot read the Format profile: {exc}")
    oracle = load_oracle(args.oracle) if args.oracle else None
    run_date = date.fromisoformat(args.date) if args.date else date.today()

    suite = build_suite(brief_text, profile_text, oracle, run_date.isoformat())
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(suite)
        print(f"Suite written to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(suite)

if __name__ == "__main__":
    main()
