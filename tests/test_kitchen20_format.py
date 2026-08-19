"""Tests for the Kitchen 20 Format vertical (issue #57).

Kitchen 20 proves spec #46 story 49: a new Format is a data profile, not
engine work. The seams under test are the ticket's acceptance criteria,
never internals:

- the Oracle seam — the Collection-home Oracle carries the card facts the
  runner's packet predicates read (``rarity``, ``keywords``), so the packet
  Legality Checks verdict on data, not model memory,
- the profile seam — ``skills/build/profiles/kitchen-20.yaml`` is pure data
  pinned by the Foundations Beginner Box research, read by the existing
  generator CLI (whose one Kitchen 20 accommodation is the parameter-driven
  ``power: none`` profile key) into the committed fixture Suite
  byte-identically,
- the no-Power seam — the Format pins Power off as profile data and the
  Brief flow (validator, skill text, generator) respects it,
- the runner seam — the unmodified runner reports the clean fixture Pack
  green over the Kitchen 20 pool and each planted packet violation red,
- the ``kitchen20-vertical`` eval case in the offline harness.

Everything runs through the CLIs — exit codes and stdout/files — offline,
against committed fixtures or temp files written per test.
"""

import json
import re
import pathlib
import subprocess
import sys
import tempfile
import unittest

from test_eval_harness import SmokeGradingMixin

REPO = pathlib.Path(__file__).resolve().parents[1]
RUNNER = REPO / "skills" / "suite-runner" / "scripts" / "check_deck.py"
GENERATOR = REPO / "skills" / "build" / "scripts" / "generate_suite.py"
PROFILE = REPO / "skills" / "build" / "profiles" / "kitchen-20.yaml"
FIXTURES = REPO / "evals" / "fixtures"

KITCHEN_BRIEF = FIXTURES / "briefs" / "kitchen20-sunlit-whiskers.txt"
KITCHEN_POOL = FIXTURES / "collections" / "synthetic-kitchen20-pool.csv"
ORACLE = FIXTURES / "scryfall" / "oracle.jsonl"

# The date pinned into the committed build fixtures, so reports and Suites
# are byte-comparable regardless of the day tests run.
REFERENCE_DATE = "2026-08-18"


def run_cli(script, *args):
    return subprocess.run(
        [sys.executable, str(script), *[str(a) for a in args]],
        capture_output=True,
        text=True,
        timeout=120,
    )


def suite_check_ids(suite_text):
    return [line.split("- id:", 1)[1].strip()
            for line in suite_text.splitlines() if "- id:" in line]


class ProfileGeneratesThePacketSuite(unittest.TestCase):
    """Acceptance: the Kitchen 20 profile ships as pure data pinned by the
    Foundations Beginner Box research, and the packet Legality Checks
    generate from it through the existing engine — the generator CLI is the
    seam, its emitted Suite the observable."""

    @classmethod
    def setUpClass(cls):
        cls.result = run_cli(
            GENERATOR,
            "--brief", KITCHEN_BRIEF,
            "--profile", PROFILE,
            "--oracle", ORACLE,
            "--date", REFERENCE_DATE,
        )

    def test_generation_succeeds(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr)

    def test_packet_targets_snapshot_from_the_profile(self):
        suite = self.result.stdout
        for target in (
            "deck_size: 20",
            "copy_limit_nonland: 1",
            "colors_max: 1",
            "multicolor_cards: 0",
            "rares_exact: 1",
            "rarity_ceiling: rare",
            "lands_min: 8",
            "lands_max: 9",
            "nonbasic_allowed: [Uncharted Haven]",
        ):
            self.assertIn(f"  {target}\n", suite)

    def test_evergreen_keyword_list_is_profile_data(self):
        # The keyword list is profile data (issue #57), snapshotted into the
        # Suite for the legality.evergreen predicate; every keyword the
        # fixture pool's cards carry is on it.
        m = re.search(r"^  evergreen_keywords: \[(.+)\]$", self.result.stdout,
                      re.MULTILINE)
        self.assertIsNotNone(m, "no evergreen_keywords line in the Suite")
        keywords = {k.strip() for k in m.group(1).split(",")}
        self.assertLessEqual(
            {"Flying", "Vigilance", "Lifelink", "Flash", "Enchant"}, keywords)
        self.assertNotIn("Scry", keywords)

    def test_packet_checks_generate_and_off_format_checks_do_not(self):
        ids = suite_check_ids(self.result.stdout)
        for cid in (
            "legality.size", "legality.singleton", "legality.mono_color",
            "legality.rare_count", "legality.land_count",
            "legality.nonbasic_lands", "legality.evergreen",
            "availability.in_collection", "manabase.color_coverage",
            "curve.average", "curve.early_plays", "consistency.opening_lands",
        ):
            self.assertIn(cid, ids)
        for cid in ("legality.banlist", "legality.game_changers",
                    "legality.color_identity"):
            self.assertNotIn(cid, ids)

    def test_identity_lands_with_brief_provenance(self):
        self.assertIn("# brief: identity: white\n  color_identity: [W]",
                      self.result.stdout)

    def test_roles_start_empty(self):
        self.assertIn("roles:", self.result.stdout)

    def test_committed_fixture_suite_reproduces_byte_identical(self):
        committed = (FIXTURES / "build" / "sunlit-whiskers.suite.yaml")
        self.assertEqual(self.result.stdout,
                         committed.read_text(encoding="utf-8"))


class FormatPinsPowerOff(unittest.TestCase):
    """Acceptance: Kitchen 20 carries no Power — the Format pins it as
    profile data and the Brief flow respects it. The validator side is
    pinned by tests/test_brief_skill.py; this seam is the generator CLI and
    the Suite it emits."""

    def test_suite_brief_line_carries_no_power(self):
        result = run_cli(
            GENERATOR,
            "--brief", KITCHEN_BRIEF,
            "--profile", PROFILE,
            "--oracle", ORACLE,
            "--date", REFERENCE_DATE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        brief_lines = [l for l in result.stdout.splitlines()
                       if l.startswith("brief: ")]
        self.assertEqual(brief_lines, ["brief: kitchen 20"])
        self.assertNotIn("power", result.stdout.lower())

    def test_generator_mirrors_the_validators_no_power_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            brief = pathlib.Path(tmp) / "powered.txt"
            brief.write_text(
                "name: Sunlit Whiskers\nformat: kitchen 20\n"
                "identity: white\npower: 3\n",
                encoding="utf-8",
            )
            result = run_cli(
                GENERATOR,
                "--brief", brief,
                "--profile", PROFILE,
                "--oracle", ORACLE,
                "--date", REFERENCE_DATE,
            )
        self.assertEqual(result.returncode, 2,
                         f"stdout: {result.stdout!r} stderr: {result.stderr!r}")
        self.assertIn("no Power", result.stderr)


SUITE_FIXTURE = FIXTURES / "build" / "sunlit-whiskers.suite.yaml"
CLEAN_PACK = FIXTURES / "decks" / "sunlit-whiskers-pack.txt"
FLAWED_PACK = FIXTURES / "decks" / "sunlit-whiskers-pack-flawed.txt"


def run_pack(deck):
    return run_cli(
        RUNNER,
        "--suite", SUITE_FIXTURE,
        "--deck", deck,
        "--oracle", ORACLE,
        "--collection", KITCHEN_POOL,
        "--date", REFERENCE_DATE,
    )


def report_colors(stdout):
    """A runner report's check lines as {check-id: "red"|"green"}. A
    deliberate copy of the eval harness's regex (grader independence, never
    imported), kept in lockstep by hand — edit the two together."""
    return dict(
        (m.group(2), m.group(1))
        for m in (re.match(r"^(red|green)\s+(\S+) — ", line)
                  for line in stdout.splitlines())
        if m
    )


class CleanPackReportsGreen(unittest.TestCase):
    """Acceptance: the fixture Pack, drawn from the Kitchen 20 pool, passes
    every packet Check through the unmodified runner — exit green,
    byte-identical to the committed reference report."""

    @classmethod
    def setUpClass(cls):
        cls.result = run_pack(CLEAN_PACK)

    def test_exit_green(self):
        self.assertEqual(self.result.returncode, 0, self.result.stdout)

    def test_every_check_green(self):
        colors = report_colors(self.result.stdout)
        self.assertEqual(len(colors), 12, self.result.stdout)
        self.assertEqual({c for c in colors.values()}, {"green"},
                         self.result.stdout)

    def test_report_matches_committed_reference(self):
        committed = FIXTURES / "build" / "sunlit-whiskers-pack-report.txt"
        self.assertEqual(self.result.stdout,
                         committed.read_text(encoding="utf-8"))


class PlantedPacketViolationsReportRed(unittest.TestCase):
    """Acceptance: each planted packet violation — second rare, multicolor
    card, off-profile nonbasic — goes red on its own packet Check through
    the unmodified runner, naming the planted card, and every planted flaw
    is registered in the fixture manifest."""

    @classmethod
    def setUpClass(cls):
        cls.result = run_pack(FLAWED_PACK)
        cls.colors = report_colors(cls.result.stdout)
        cls.reds = {line.split()[1]: line for line in cls.result.stdout.splitlines()
                    if line.startswith("red")}

    def test_exit_red(self):
        self.assertEqual(self.result.returncode, 1, self.result.stdout)

    def test_second_rare_goes_red(self):
        self.assertEqual(self.colors.get("legality.rare_count"), "red")
        self.assertIn("Charming Prince", self.reds["legality.rare_count"])

    def test_multicolor_card_goes_red(self):
        self.assertEqual(self.colors.get("legality.mono_color"), "red")
        self.assertIn("Zoraline, Cosmos Caller", self.reds["legality.mono_color"])

    def test_off_profile_nonbasic_goes_red(self):
        self.assertEqual(self.colors.get("legality.nonbasic_lands"), "red")
        self.assertIn("Tranquil Cove", self.reds["legality.nonbasic_lands"])

    def test_oversized_pack_goes_red(self):
        self.assertEqual(self.colors.get("legality.size"), "red")

    def test_non_evergreen_keyword_goes_red(self):
        # Charming Prince plants a second packet violation: Scry is not on
        # the profile's evergreen list.
        self.assertEqual(self.colors.get("legality.evergreen"), "red")
        self.assertIn("Charming Prince (Scry)", self.reds["legality.evergreen"])

    def test_report_matches_committed_reference(self):
        committed = FIXTURES / "build" / "sunlit-whiskers-pack-flawed-report.txt"
        self.assertEqual(self.result.stdout,
                         committed.read_text(encoding="utf-8"))

    def test_every_planted_flaw_is_registered(self):
        manifest = json.loads(
            (FIXTURES / "manifest.json").read_text(encoding="utf-8"))
        flaws = manifest["planted_flaws"]["decks/sunlit-whiskers-pack-flawed.txt"]
        named = {card for flaw in flaws for card in flaw["cards"]}
        self.assertEqual(
            named, {"Charming Prince", "Zoraline, Cosmos Caller", "Tranquil Cove"})
        self.assertEqual({flaw["class"] for flaw in flaws}, {"legality"})


class OracleCarriesThePacketFacts(unittest.TestCase):
    """The packet Legality Checks read ``rarity`` and ``keywords`` from the
    Oracle through the unmodified runner — so the Collection-home Oracle
    (issue #48 shape, extended here) must carry both. Expected values are
    known-good Scryfall facts for the pinned FDN printings."""

    @classmethod
    def setUpClass(cls):
        lines = ORACLE.read_text(encoding="utf-8").splitlines()
        cls.records = {r["name"]: r for r in map(json.loads, lines[1:]) if "name" in r}

    def test_rarity_is_the_deduped_printings(self):
        self.assertEqual(self.records["Giada, Font of Hope"]["rarity"], "rare")
        self.assertEqual(self.records["Healer's Hawk"]["rarity"], "common")
        self.assertEqual(self.records["Plains"]["rarity"], "common")

    def test_keywords_are_the_cards_keyword_list(self):
        self.assertEqual(self.records["Giada, Font of Hope"]["keywords"],
                         ["Flying", "Vigilance"])
        self.assertEqual(self.records["Pacifism"]["keywords"], ["Enchant"])
        self.assertEqual(self.records["Plains"]["keywords"], [])


class Kitchen20VerticalEvalGradesGreen(SmokeGradingMixin, unittest.TestCase):
    """Acceptance: the offline harness carries a kitchen20-vertical eval case
    and grades it green — the fixture Pack pool builds green, the planted
    packet violations go red, no Power and the review-standard seeds ride as
    profile data."""

    CASE = "kitchen20-vertical"

    def test_profile_graded_green(self):
        self.graded_green("pure data")

    def test_no_power_graded_green(self):
        self.graded_green("no Power")

    def test_suite_reproduction_graded_green(self):
        self.graded_green("reproduces the committed fixture Suite")

    def test_clean_pack_graded_green(self):
        self.graded_green("clean fixture Pack")

    def test_packet_violations_graded_green(self):
        self.graded_green("planted packet violation")

    def test_review_standards_graded_green(self):
        self.graded_green("review standards")

    def test_no_expectation_red(self):
        self.assertEqual(self.grading["summary"]["failed"], 0)


if __name__ == "__main__":
    unittest.main()
