"""Tests for the offline eval harness (issue #48).

Every test exercises the harness through its public seams only:

- the CLI: ``python3 evals/run_evals.py`` (exit code, stdout report), and
- the files it emits: ``grading.json`` in the skill-creator grading schema.

Fixture validity is asserted through the smoke case's graded expectations —
the harness is the public interface to the fixtures — plus a red-path test
proving the harness can actually fail, so green means something.
"""

import json
import pathlib
import subprocess
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
RUNNER = REPO / "evals" / "run_evals.py"


def run_harness(*args, cwd=REPO):
    """Run the eval harness CLI and return the CompletedProcess."""
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=300,
    )


class SmokeEvalRunsGreen(unittest.TestCase):
    """Acceptance: one smoke eval runs green, proving the harness end to end."""

    def test_smoke_eval_runs_green(self):
        result = run_harness()
        self.assertEqual(
            result.returncode, 0,
            f"harness not green.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        grading_path = REPO / "evals" / "results" / "harness-smoke" / "grading.json"
        self.assertTrue(grading_path.is_file(), "no grading.json emitted for smoke case")
        grading = json.loads(grading_path.read_text(encoding="utf-8"))
        self.assertEqual(grading["summary"]["failed"], 0)
        self.assertGreater(grading["summary"]["passed"], 0)
        texts = [e["text"] for e in grading["expectations"]]
        self.assertTrue(
            any("577" in t for t in texts),
            f"smoke case never grades the 577-row realism fixture; expectations: {texts}",
        )


class SyntheticCollectionsCoverRealExportGaps(unittest.TestCase):
    """Acceptance: synthetic Collections cover what the real Export lacks —
    etched foil, non-English languages, promo collector numbers, per-Format
    shaped pools."""

    @classmethod
    def setUpClass(cls):
        cls.result = run_harness("--case", "harness-smoke")
        grading_path = REPO / "evals" / "results" / "harness-smoke" / "grading.json"
        cls.grading = json.loads(grading_path.read_text(encoding="utf-8"))

    def graded_green(self, needle):
        matches = [e for e in self.grading["expectations"] if needle in e["text"]]
        self.assertTrue(matches, f"no smoke expectation mentions {needle!r}")
        for e in matches:
            self.assertTrue(e["passed"], f"expectation red: {e['text']}\n{e['evidence']}")

    def test_etched_foil_graded_green(self):
        self.graded_green("etched")
        edge = (REPO / "evals" / "fixtures" / "collections" / "synthetic-edge-cases.csv")
        self.assertIn("etched", edge.read_text(encoding="utf-8-sig"))

    def test_non_english_languages_graded_green(self):
        self.graded_green("non-English")

    def test_promo_collector_numbers_graded_green(self):
        self.graded_green("promo")

    def test_per_format_pools_graded_green(self):
        self.graded_green("Per-Format")


class FixtureBriefsAndDecksExist(unittest.TestCase):
    """Acceptance: fixture Briefs and Decks exist, some with planted flaws
    for Review evals."""

    @classmethod
    def setUpClass(cls):
        cls.result = run_harness("--case", "harness-smoke")
        grading_path = REPO / "evals" / "results" / "harness-smoke" / "grading.json"
        cls.grading = json.loads(grading_path.read_text(encoding="utf-8"))

    def graded_green(self, needle):
        matches = [e for e in self.grading["expectations"] if needle in e["text"]]
        self.assertTrue(matches, f"no smoke expectation mentions {needle!r}")
        for e in matches:
            self.assertTrue(e["passed"], f"expectation red: {e['text']}\n{e['evidence']}")

    def test_briefs_graded_green(self):
        self.graded_green("Brief")
        briefs = list((REPO / "evals" / "fixtures" / "briefs").glob("*.txt"))
        self.assertGreaterEqual(len(briefs), 2, "fewer than two fixture Briefs")

    def test_decks_graded_green(self):
        self.graded_green("ManaBox-importable")

    def test_planted_flaws_graded_green(self):
        self.graded_green("planted flaws")
        manifest = json.loads(
            (REPO / "evals" / "fixtures" / "manifest.json").read_text(encoding="utf-8")
        )
        flawed = manifest["planted_flaws"]
        self.assertTrue(flawed, "no Deck registers planted flaws")
        classes = {f["class"] for flaws in flawed.values() for f in flaws}
        self.assertIn("availability", classes, "no availability flaw planted")


class HarnessCanGoRed(unittest.TestCase):
    """Green is only trustworthy if a broken fixture actually turns the run red."""

    def test_tampered_fixture_turns_run_red(self):
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tampered_root = pathlib.Path(tmp) / "fixtures"
            shutil.copytree(REPO / "evals" / "fixtures", tampered_root)
            collection = tampered_root / "collections" / "real-collection.csv"
            lines = collection.read_bytes().splitlines(keepends=True)
            collection.write_bytes(b"".join(lines[:-10]))  # drop 10 rows

            out = pathlib.Path(tmp) / "results"
            result = run_harness("--fixture-root", str(tampered_root), "--out", str(out))
            self.assertEqual(
                result.returncode, 1,
                f"harness stayed green on a tampered fixture.\nstdout:\n{result.stdout}",
            )
            grading = json.loads(
                (out / "harness-smoke" / "grading.json").read_text(encoding="utf-8")
            )
            self.assertGreater(grading["summary"]["failed"], 0)
            failed = [e for e in grading["expectations"] if not e["passed"]]
            self.assertTrue(any("577" in e["text"] for e in failed))


if __name__ == "__main__":
    unittest.main()
