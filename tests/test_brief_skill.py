"""Tests for the brief skill's deterministic seams (issue #52).

The brief conversation itself is prompt-ware, judged at dev time through the
skill-creator workflow and by humans. What is tested here are the skill's
deterministic public seams only:

- ``skills/brief/scripts/validate_brief.py`` — the one authority on whether
  a Brief Block is valid (grammar, Power ladder, donor recognition),
- ``skills/brief/scripts/freshness.py`` — the Export/Oracle staleness report
  behind the brief's single freshness question, and
- the ``brief-smoke`` eval case in the offline harness.

Everything runs through the CLIs — exit codes and stdout — never internals.
"""

import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
VALIDATOR = REPO / "skills" / "brief" / "scripts" / "validate_brief.py"
FRESHNESS = REPO / "skills" / "brief" / "scripts" / "freshness.py"
FIXTURES = REPO / "evals" / "fixtures"


def run_script(script, *args):
    return subprocess.run(
        [sys.executable, str(script), *[str(a) for a in args]],
        capture_output=True,
        text=True,
        timeout=60,
    )


def run_validator(*args):
    return run_script(VALIDATOR, *args)


class BriefValidatorAcceptsCanonicalBriefs(unittest.TestCase):
    """Acceptance: scripted answers yield a valid Brief Block — the committed
    fixture Briefs are the valid shapes, and the validator passes every one."""

    def test_every_fixture_brief_is_valid(self):
        briefs = sorted((FIXTURES / "briefs").glob("*.txt"))
        self.assertGreaterEqual(len(briefs), 2, "fixture Briefs missing")
        for brief in briefs:
            result = run_validator(brief)
            self.assertEqual(
                result.returncode, 0,
                f"{brief.name} judged invalid:\n{result.stdout}{result.stderr}",
            )
            self.assertIn("valid", result.stdout)


VALID_BRIEF = """\
name: Tatyova Landfall
format: commander
centerpiece: Tatyova, Benthic Druid
identity: simic
power: 2
constraint: nothing above 6 mana
donor: Baylen, the Haymaker
notes: lands matter, steady card draw, no infinite combos
"""


class BriefValidatorRejectsInvalidBriefs(unittest.TestCase):
    """Acceptance: the canonical grammar is enforced — only the nine keys,
    only format required, no budget key, Power a 1-5 number."""

    def validate_text(self, text, *args):
        with tempfile.TemporaryDirectory() as tmp:
            brief = pathlib.Path(tmp) / "brief.txt"
            brief.write_text(text, encoding="utf-8")
            return run_validator(brief, *args)

    def assert_invalid(self, text, needle):
        result = self.validate_text(text)
        self.assertEqual(result.returncode, 1, f"accepted:\n{text}\n{result.stdout}")
        self.assertIn("invalid", result.stdout)
        self.assertIn(needle, result.stdout, f"no {needle!r} in:\n{result.stdout}")

    def test_budget_key_is_rejected_by_name(self):
        self.assert_invalid(
            "format: commander\nbudget: 50 euro\n", "no budget: key"
        )

    def test_unknown_key_is_rejected(self):
        self.assert_invalid("format: commander\nsleeves: dragon shield\n", "sleeves")

    def test_missing_format_is_rejected(self):
        self.assert_invalid("name: Fun Deck\npower: 2\n", "format")

    def test_power_above_ladder_is_rejected(self):
        self.assert_invalid("format: commander\npower: 6\n", "1-5")

    def test_power_zero_is_rejected(self):
        self.assert_invalid("format: commander\npower: 0\n", "1-5")

    def test_power_fraction_is_rejected(self):
        self.assert_invalid("format: commander\npower: 3.5\n", "1-5")

    def test_power_without_leading_number_is_rejected(self):
        self.assert_invalid("format: commander\npower: battlecruiser\n", "1-5")

    def test_duplicate_scalar_key_is_rejected(self):
        self.assert_invalid(
            "name: One\nname: Two\nformat: commander\n", "repeat"
        )

    def test_indented_line_is_rejected(self):
        self.assert_invalid("format: commander\n  notes: indented\n", "canonical")

    def test_power_with_trailing_free_text_is_valid(self):
        result = self.validate_text(
            "format: commander\npower: 3, battlecruiser feel\n"
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_repeated_constraint_and_donor_are_valid(self):
        result = self.validate_text(
            "format: commander\n"
            "constraint: nothing above 6 mana\n"
            "constraint: must include Sol Ring\n"
            "donor: Baylen, the Haymaker\n"
            "donor: Tatyova, Benthic Druid\n"
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_canonical_brief_text_is_valid(self):
        result = self.validate_text(VALID_BRIEF)
        self.assertEqual(result.returncode, 0, result.stdout)


class BriefValidatorRecognizesDonorDecks(unittest.TestCase):
    """Acceptance: donor: values name existing Decks recognized from the
    Export's deck rows; donor: all frees the whole Collection."""

    REAL_EXPORT = FIXTURES / "collections" / "real-collection.csv"

    def validate_text(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            brief = pathlib.Path(tmp) / "brief.txt"
            brief.write_text(text, encoding="utf-8")
            return run_validator(brief, "--collection", self.REAL_EXPORT)

    def test_recognized_donor_deck_is_valid(self):
        result = self.validate_text(VALID_BRIEF)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_donor_all_frees_the_whole_collection(self):
        result = self.validate_text("format: commander\ndonor: all\n")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_unrecognized_donor_deck_is_rejected_naming_the_decks(self):
        result = self.validate_text(
            "format: commander\ndonor: Deck That Does Not Exist\n"
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Deck That Does Not Exist", result.stdout)
        # The evidence offers the recognized Deck names so the human can
        # correct the Brief without opening ManaBox.
        self.assertIn("Tatyova, Benthic Druid", result.stdout)

    def test_donor_lines_pass_unchecked_without_a_collection(self):
        with tempfile.TemporaryDirectory() as tmp:
            brief = pathlib.Path(tmp) / "brief.txt"
            brief.write_text(
                "format: commander\ndonor: Deck That Does Not Exist\n",
                encoding="utf-8",
            )
            result = run_validator(brief)
        self.assertEqual(result.returncode, 0, result.stdout)


class FreshnessReportsExportAndOracle(unittest.TestCase):
    """Acceptance: one freshness question, asked once — the helper surfaces
    the Export's newest Added and the Oracle's two staleness signals."""

    REAL_EXPORT = FIXTURES / "collections" / "real-collection.csv"
    ORACLE = FIXTURES / "scryfall" / "oracle.jsonl"

    def test_fresh_fixture_pair_raises_no_signal(self):
        # Fixture facts: newest Added 2026-08-15T21:10:47.241Z across the
        # whole fixture tree; oracle generated_at 2026-08-18T17:56:23Z.
        result = run_script(
            FRESHNESS,
            "--collection", self.REAL_EXPORT,
            "--oracle", self.ORACLE,
            "--today", "2026-08-20",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("export newest added: 2026-08-15T21:10:47.241Z", result.stdout)
        self.assertIn("export rows: 577", result.stdout)
        self.assertIn("signal export-newer-than-oracle: no", result.stdout)
        self.assertIn("signal oracle-older-than-30-days: no", result.stdout)

    def test_export_newer_than_oracle_watermark_fires(self):
        header = "Binder Name,Binder Type,Name,Set code,Quantity,Added\n"
        row = "Binder,binder,Sol Ring,C21,1,2026-09-01T09:00:00.000Z\n"
        with tempfile.TemporaryDirectory() as tmp:
            export = pathlib.Path(tmp) / "collection.csv"
            export.write_text(header + row, encoding="utf-8")
            result = run_script(
                FRESHNESS,
                "--collection", export,
                "--oracle", self.ORACLE,
                "--today", "2026-09-02",
            )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("signal export-newer-than-oracle: yes", result.stdout)

    def test_oracle_older_than_30_days_fires(self):
        result = run_script(
            FRESHNESS,
            "--collection", self.REAL_EXPORT,
            "--oracle", self.ORACLE,
            "--today", "2026-10-01",
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("signal oracle-older-than-30-days: yes", result.stdout)


class FreshnessDegradesGracefullyWithoutOracle(unittest.TestCase):
    """Acceptance: the freshness question degrades gracefully when the
    Oracle is absent."""

    REAL_EXPORT = FIXTURES / "collections" / "real-collection.csv"

    def test_absent_oracle_reports_export_alone(self):
        result = run_script(
            FRESHNESS, "--collection", self.REAL_EXPORT, "--today", "2026-08-20"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("export newest added: 2026-08-15T21:10:47.241Z", result.stdout)
        self.assertIn("oracle: absent", result.stdout)
        self.assertNotIn("signal export-newer-than-oracle:", result.stdout)
        self.assertNotIn("signal oracle-older-than-30-days:", result.stdout)

    def test_unreadable_oracle_metadata_degrades_not_crashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            oracle = pathlib.Path(tmp) / "oracle.jsonl"
            oracle.write_text("not json at all\n", encoding="utf-8")
            result = run_script(
                FRESHNESS,
                "--collection", self.REAL_EXPORT,
                "--oracle", oracle,
                "--today", "2026-08-20",
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("metadata unreadable", result.stdout)
        self.assertNotIn("Traceback", result.stderr)


def run_harness(*args):
    return subprocess.run(
        [sys.executable, str(REPO / "evals" / "run_evals.py"), *[str(a) for a in args]],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=300,
    )


class BriefSmokeEvalCase(unittest.TestCase):
    """Acceptance: a smoke eval covers the brief skill — mechanical
    invariants graded offline, the two behavioral halves (fires from natural
    language; scripted answers yield a valid Brief Block) reported soft for
    the dev-time skill-creator workflow. Conversation quality stays
    human-judged and is no expectation at all."""

    @classmethod
    def setUpClass(cls):
        cls.result = run_harness("--case", "brief-smoke")
        cls.grading_path = REPO / "evals" / "results" / "brief-smoke" / "grading.json"

    def test_brief_smoke_runs_green(self):
        self.assertEqual(
            self.result.returncode, 0,
            f"brief-smoke not green.\nstdout:\n{self.result.stdout}"
            f"\nstderr:\n{self.result.stderr}",
        )
        self.assertTrue(self.grading_path.is_file(), "no grading.json for brief-smoke")
        import json

        grading = json.loads(self.grading_path.read_text(encoding="utf-8"))
        self.assertEqual(grading["summary"]["failed"], 0)
        self.assertGreater(grading["summary"]["passed"], 0)

    def test_behavioral_halves_are_soft_expectations(self):
        import json

        grading = json.loads(self.grading_path.read_text(encoding="utf-8"))
        soft = " ".join(grading["soft_expectations"])
        self.assertIn("natural language", soft)
        self.assertIn("scripted answers", soft)

    def test_command_wraps_skill_with_version_in_lockstep(self):
        import json

        command = (REPO / "commands" / "brief.md").read_text(encoding="utf-8")
        self.assertIn("skills/brief/SKILL.md", command)
        skill = (REPO / "skills" / "brief" / "SKILL.md").read_text(encoding="utf-8")
        pinned = json.loads(
            (REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )["version"]
        self.assertIn(f"version: {pinned}", skill)


class BriefSmokeCanGoRed(unittest.TestCase):
    """Green is only trustworthy if a broken Brief fixture turns the case
    red: plant the banned budget: key and watch the validator catch it."""

    def test_budget_key_in_a_fixture_brief_turns_the_case_red(self):
        import json
        import shutil

        with tempfile.TemporaryDirectory() as tmp:
            tampered_root = pathlib.Path(tmp) / "fixtures"
            shutil.copytree(FIXTURES, tampered_root)
            brief = tampered_root / "briefs" / "commander-tatyova-landfall.txt"
            brief.write_text(
                brief.read_text(encoding="utf-8") + "budget: 50 euro\n",
                encoding="utf-8",
            )
            out = pathlib.Path(tmp) / "results"
            result = run_harness(
                "--case", "brief-smoke",
                "--fixture-root", tampered_root,
                "--out", out,
            )
            self.assertEqual(
                result.returncode, 1,
                f"brief-smoke stayed green on a budget: line.\nstdout:\n{result.stdout}",
            )
            grading = json.loads(
                (out / "brief-smoke" / "grading.json").read_text(encoding="utf-8")
            )
            failed = [e for e in grading["expectations"] if not e["passed"]]
            self.assertTrue(
                any("validator" in e["text"] for e in failed),
                f"no validator expectation went red: {[e['text'] for e in failed]}",
            )


if __name__ == "__main__":
    unittest.main()
