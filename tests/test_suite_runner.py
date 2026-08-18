"""Offline tests for the Suite runner skill asset (issue #49).

The seam under test is the runner's CLI — Suite, Deck, Oracle, and Collection
files in; report Block on stdout and a red/green exit code out — plus the
checklist render of the same Suite data. Expected outputs are the suite-shape
prototype's captured runs (`runs/report-*.txt` on branch
claude/deck-test-artifact-shape-wk1txl), copied byte-exact into
tests/fixtures/expected/: the prototype is the reference implementation, so
these tests never recompute a verdict the way the runner does.

Everything runs offline against committed fixtures; no network, stdlib only.
"""

import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
RUNNER = REPO / "skills" / "suite-runner" / "scripts" / "check_deck.py"
FIXTURES = REPO / "tests" / "fixtures"

# The date the prototype's reference runs were captured on. Passed to the
# runner so reports are byte-comparable regardless of the day tests run.
REFERENCE_DATE = "2026-08-18"


def run_runner(*args):
    """Invoke the runner CLI with the given arguments."""
    return subprocess.run(
        [sys.executable, str(RUNNER), *(str(a) for a in args)],
        capture_output=True,
        text=True,
    )


def run_suite(deck, *extra, oracle=None):
    """Invoke the runner CLI over the fixture Suite and the given deck file."""
    return run_runner(
        "--suite", FIXTURES / "suite.yaml",
        "--deck", FIXTURES / "decks" / deck,
        "--oracle", oracle or FIXTURES / "oracle.json",
        "--collection", FIXTURES / "collection.csv",
        "--date", REFERENCE_DATE,
        *extra,
    )


def expected(name):
    return (FIXTURES / "expected" / name).read_text()


class EmptyDeckRun(unittest.TestCase):
    """Build start: every size, mana-base, curve, and quota Check red;
    constraint-shaped Checks pass vacuously (ADR 0005)."""

    def test_report_matches_prototype_reference(self):
        result = run_suite("empty.txt")
        self.assertEqual(result.stdout, expected("report-empty.txt"))

    def test_exit_code_is_red(self):
        self.assertEqual(run_suite("empty.txt").returncode, 1)


class PlantedViolationsDraftRun(unittest.TestCase):
    """Mid-build draft with nine planted violations — every one caught,
    each red line naming the offending cards as evidence."""

    def test_report_matches_prototype_reference(self):
        result = run_suite("draft.txt")
        self.assertEqual(result.stdout, expected("report-draft.txt"))

    def test_exit_code_is_red(self):
        self.assertEqual(run_suite("draft.txt").returncode, 1)


class GreenFinalRun(unittest.TestCase):
    """The finished Pack: every Check green, exit code 0 — the signal the
    Build loop stops on."""

    def test_report_matches_prototype_reference(self):
        result = run_suite("final.txt")
        self.assertEqual(result.stdout, expected("report-final.txt"))

    def test_exit_code_is_green(self):
        self.assertEqual(run_suite("final.txt").returncode, 0)


class DeterministicReports(unittest.TestCase):
    """Same Deck, same card facts, same verdict: repeated runs produce
    byte-identical reports, so two reports diff cleanly."""

    def test_repeated_runs_are_byte_identical(self):
        for deck in ("empty.txt", "draft.txt", "final.txt"):
            with self.subTest(deck=deck):
                first = run_suite(deck)
                second = run_suite(deck)
                self.assertEqual(first.stdout, second.stdout)
                self.assertEqual(first.returncode, second.returncode)


class JsonlOracle(unittest.TestCase):
    """The Collection-home Oracle is `oracle.jsonl` (ADR 0007): JSON Lines,
    one card-facts object per line, whose first line is a metadata record —
    `generated_at` plus the source-Export watermark — not a card. The runner
    reads it and reaches the same verdicts as the JSON-array Oracle fixture,
    byte for byte."""

    @classmethod
    def setUpClass(cls):
        cards = json.loads((FIXTURES / "oracle.json").read_text())
        meta = {
            "generated_at": "2026-08-18T00:00:00Z",
            "source_export_newest_added": "2026-08-17 21:14:02",
        }
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.jsonl = pathlib.Path(cls.tmpdir.name) / "oracle.jsonl"
        cls.jsonl.write_text("\n".join(json.dumps(r) for r in [meta] + cards) + "\n")

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_same_reports_as_array_oracle(self):
        for deck in ("empty.txt", "draft.txt", "final.txt"):
            with self.subTest(deck=deck):
                from_array = run_suite(deck)
                from_jsonl = run_suite(deck, oracle=self.jsonl)
                self.assertEqual(from_jsonl.stdout, from_array.stdout)
                self.assertEqual(from_jsonl.returncode, from_array.returncode)


class ChecklistRender(unittest.TestCase):
    """The same Suite data renders as a walkable checklist for sandbox-less
    sessions — from the Suite file alone, no Deck, Oracle, or Collection."""

    def test_render_matches_prototype_reference(self):
        result = run_runner("--suite", FIXTURES / "suite.yaml", "--render-checklist")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, expected("checklist.md"))


CHECK_LINE = re.compile(r"^(red|green)\s+(\S+) — (.+)$")


def parse_report(text):
    """Split a report Block into (head keys, verdict line, per-Check verdicts)."""
    lines = text.splitlines()
    head_keys = [line.split(":", 1)[0] for line in lines[:5]]
    verdict_line = lines[5]
    blank = lines[6]
    checks = []
    for line in lines[7:]:
        m = CHECK_LINE.match(line)
        checks.append((m.group(1), m.group(2), m.group(3)) if m else None)
    return head_keys, verdict_line, blank, checks


class ReportBlockShape(unittest.TestCase):
    """The suite report Block holds its shape (flat head, one verdict line,
    one red|green line per Check) and every verdict matches the prototype's
    captured run, check by check."""

    STAGES = {
        "empty.txt": "report-empty.txt",
        "draft.txt": "report-draft.txt",
        "final.txt": "report-final.txt",
    }

    def test_head_verdict_and_check_lines(self):
        for deck in self.STAGES:
            with self.subTest(deck=deck):
                head, verdict, blank, checks = parse_report(run_suite(deck).stdout)
                self.assertEqual(head, ["suite", "deck", "format", "date", "oracle"])
                self.assertRegex(verdict, r"^verdict: (red|green) — \d+ red / \d+ green$")
                self.assertEqual(blank, "")
                self.assertTrue(checks, "no Check lines in report")
                for line in checks:
                    self.assertIsNotNone(line, "malformed Check line in report")

    def test_every_verdict_matches_reference(self):
        for deck, reference in self.STAGES.items():
            with self.subTest(deck=deck):
                _, _, _, actual = parse_report(run_suite(deck).stdout)
                _, _, _, ref = parse_report(expected(reference))
                self.assertEqual(
                    [(cid, color) for color, cid, _ in actual],
                    [(cid, color) for color, cid, _ in ref],
                )


if __name__ == "__main__":
    unittest.main()
