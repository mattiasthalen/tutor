#!/usr/bin/env python3
"""Report Export/Oracle freshness for the brief's single question (issue #52).

The brief conversation asks about staleness exactly once. This helper gathers
everything that one question folds in, deterministically:

- the Export's newest ``Added`` timestamp (and its row count),
- the Oracle's two staleness signals: the Export newer than the Oracle's
  source-Export watermark, and ``generated_at`` older than ~30 days.

It reports facts; the skill words the question and the human answers it.
Downstream stages trust their input silently.

Usage:
    freshness.py --collection EXPORT_CSV [--oracle ORACLE_JSONL]
                 [--today YYYY-MM-DD]

``--today`` pins the date for deterministic runs; default is today. When the
Oracle is absent or its metadata unreadable, the report degrades gracefully to
the Export alone.

Exit status: 0 when no staleness signal fired, 1 when at least one fired,
2 when the Export is unusable. Stdlib only, no network.
"""

import argparse
import csv
import datetime
import io
import json
import pathlib
import sys

STALE_AFTER_DAYS = 30  # the ~30-day drift nudge from spec #46


def read_export(path):
    """Header-keyed, BOM-tolerant read; returns (row_count, newest_added)."""
    raw = pathlib.Path(path).read_bytes()
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    newest = max((r.get("Added") or "").strip() for r in rows) if rows else ""
    return len(rows), newest


def read_oracle_meta(path):
    """The Oracle's first-line ``oracle_meta`` record, or None when the file
    or its metadata cannot be read — the caller degrades gracefully."""
    try:
        with open(path, encoding="utf-8") as handle:
            first_line = handle.readline()
        meta = json.loads(first_line)["oracle_meta"]
        return meta if isinstance(meta, dict) else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def parse_iso_date(value):
    """The date part of an ISO-8601 timestamp, or None."""
    try:
        return datetime.date.fromisoformat(value[:10])
    except (ValueError, TypeError, IndexError):
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--collection", required=True, help="ManaBox Export CSV")
    parser.add_argument("--oracle", help="Oracle JSONL (omit when absent)")
    parser.add_argument(
        "--today", help="pin the date (YYYY-MM-DD) for deterministic runs"
    )
    args = parser.parse_args(argv)

    try:
        today = (
            datetime.date.fromisoformat(args.today)
            if args.today
            else datetime.date.today()
        )
    except ValueError as exc:
        print(f"unusable — --today: {exc}", file=sys.stderr)
        return 2

    try:
        row_count, newest_added = read_export(args.collection)
    except OSError as exc:
        print(f"unusable — cannot read the Export: {exc}", file=sys.stderr)
        return 2

    print(f"export: {args.collection}")
    print(f"export rows: {row_count}")
    print(
        f"export newest added: {newest_added or 'none (no Added values)'}"
    )

    if not args.oracle:
        print(
            "oracle: absent — no staleness signals to fold in; the freshness "
            "question covers the Export alone, and Build can offer /tutor:oracle"
        )
        return 0

    meta = read_oracle_meta(args.oracle)
    if meta is None:
        print(
            f"oracle: {args.oracle} — metadata unreadable; treating the Oracle "
            "as absent for the freshness question"
        )
        return 0

    print(f"oracle: {args.oracle}")
    generated_at = (meta.get("generated_at") or "").strip()
    watermark = (meta.get("source_export_newest_added") or "").strip()
    print(f"oracle generated_at: {generated_at or 'unrecorded'}")
    print(f"oracle watermark: {watermark or 'unrecorded'}")

    fired = 0

    if newest_added and watermark:
        # Lexicographic compare, deliberately: both sides carry the uniform
        # ManaBox Zulu ISO-8601 shape (YYYY-MM-DDTHH:MM:SS.mmmZ) — the
        # watermark is copied verbatim from an Export's Added value — and
        # that fixed shape sorts chronologically as text. Mixed precision
        # or offsets would break this; neither occurs here.
        newer = newest_added > watermark
        fired += newer
        print(
            f"signal export-newer-than-oracle: {'yes' if newer else 'no'} — "
            f"newest Added {newest_added} vs watermark {watermark}"
        )
    else:
        print(
            "signal export-newer-than-oracle: unavailable — "
            + ("no Added values in the Export" if not newest_added
               else "the Oracle records no watermark")
        )

    generated_date = parse_iso_date(generated_at)
    if generated_date is None:
        print(
            "signal oracle-older-than-30-days: unavailable — "
            "generated_at is missing or not a date"
        )
    else:
        age_days = (today - generated_date).days
        stale = age_days > STALE_AFTER_DAYS
        fired += stale
        print(
            f"signal oracle-older-than-30-days: {'yes' if stale else 'no'} — "
            f"generated {age_days} days before {today.isoformat()}"
        )

    return 1 if fired else 0


if __name__ == "__main__":
    sys.exit(main())
