"""Tests for the Review skill — /tutor:review (issue #55).

The seams under test are the ticket's acceptance criteria, never internals:

- the assembler CLI (``skills/review/scripts/assemble_review.py``) — per-axis
  Findings in, the Review Block out: Verdicts are arithmetic (ADR 0006), the
  Finding shape is enforced, at most five Findings per axis worst first, the
  no-Brief path reports "no Brief available", and aggregation adds no fresh
  judgment (same input, same bytes),
- the Commander Format profile carrying per-Format review standards as data,
- the Review-flawed fixture Deck: its planted flaws are Review territory —
  the fixture Suite finds nothing new red on it (Checks cannot see them), and
- the ``review-smoke`` eval case in the offline harness.

Everything runs through CLIs — exit codes and stdout — offline, against
committed fixtures or temp files written per test.
"""

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from test_eval_harness import SmokeGradingMixin

REPO = pathlib.Path(__file__).resolve().parents[1]
ASSEMBLER = REPO / "skills" / "review" / "scripts" / "assemble_review.py"
RUNNER = REPO / "skills" / "suite-runner" / "scripts" / "check_deck.py"
PROFILE = REPO / "skills" / "build" / "profiles" / "commander.yaml"
FIXTURES = REPO / "evals" / "fixtures"

# The date pinned into review fixtures and tests, so Blocks are byte-stable.
REFERENCE_DATE = "2026-08-18"


def run_cli(script, *args):
    return subprocess.run(
        [sys.executable, str(script), *[str(a) for a in args]],
        capture_output=True,
        text=True,
        timeout=120,
    )


def finding(severity="note", cards=("Llanowar Elves",), problem="a probe problem",
            **suggestion):
    entry = {"severity": severity, "cards": list(cards), "problem": problem}
    entry.update(suggestion)
    return entry


class TempFindings:
    """Per-axis Findings files in a temp directory, the assembler's input."""

    def __init__(self):
        self._dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._dir.name)

    def cleanup(self):
        self._dir.cleanup()

    def write(self, name, findings):
        path = self.root / name
        path.write_text(json.dumps(findings), encoding="utf-8")
        return path


def assemble(home, standards, brief=None, *extra):
    args = [
        "--deck-name", "Probe Deck",
        "--date", REFERENCE_DATE,
        "--standards", home.write("standards.json", standards),
    ]
    if brief is None:
        args.append("--no-brief")
    else:
        args += ["--brief", home.write("brief.json", brief)]
    return run_cli(ASSEMBLER, *args, *extra)


class VerdictsAreArithmetic(unittest.TestCase):
    """Verdicts are arithmetic over Findings, never fresh judgment: any
    blocker makes the axis `rebuild`, only notes `playable`, clean `ship`,
    and the overall Verdict is the worst axis (ADR 0006)."""

    def verdict_lines(self, stdout):
        lines = stdout.splitlines()
        overall = next(l for l in lines if l.startswith("verdict: "))
        standards = next(l for l in lines if l.startswith("standards: "))
        brief = next(l for l in lines if l.startswith("brief: "))
        return overall, standards, brief

    def test_any_blocker_makes_the_axis_rebuild(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        result = assemble(home, [finding(), finding("blocker")], [])
        self.assertEqual(result.returncode, 0, result.stderr)
        overall, standards, brief = self.verdict_lines(result.stdout)
        self.assertEqual(standards, "standards: rebuild")
        self.assertEqual(brief, "brief: ship")
        self.assertEqual(overall, "verdict: rebuild")

    def test_only_notes_make_the_axis_playable(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        result = assemble(home, [finding(), finding()], [])
        self.assertEqual(result.returncode, 0, result.stderr)
        overall, standards, brief = self.verdict_lines(result.stdout)
        self.assertEqual(standards, "standards: playable")
        self.assertEqual(overall, "verdict: playable")

    def test_clean_axes_ship(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        result = assemble(home, [], [])
        self.assertEqual(result.returncode, 0, result.stderr)
        overall, standards, brief = self.verdict_lines(result.stdout)
        self.assertEqual(standards, "standards: ship")
        self.assertEqual(brief, "brief: ship")
        self.assertEqual(overall, "verdict: ship")

    def test_overall_is_the_worst_axis_whichever_side_it_is(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        result = assemble(home, [], [finding("blocker")])
        self.assertEqual(result.returncode, 0, result.stderr)
        overall, standards, brief = self.verdict_lines(result.stdout)
        self.assertEqual(standards, "standards: ship")
        self.assertEqual(brief, "brief: rebuild")
        self.assertEqual(overall, "verdict: rebuild")

    def test_aggregation_is_deterministic_same_input_same_bytes(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        first = assemble(home, [finding("blocker"), finding()], [finding()])
        second = assemble(home, [finding("blocker"), finding()], [finding()])
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)


class ReviewBlockShape(unittest.TestCase):
    """The Review Block: `deck:` and `date:` reference lines, one overall
    `verdict:` line, then one section per axis — Standards first, Brief
    second, side by side, never merged — each with its own verdict and its
    Findings naming cards."""

    def test_block_lines_in_order(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        result = assemble(
            home,
            [finding("blocker", ("Corsair Captain", "Pirate's Cutlass"),
                     "a two-card island")],
            [finding("note", ("Vaporkin",), "off the stated intent")],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            [
                "deck: Probe Deck",
                f"date: {REFERENCE_DATE}",
                "verdict: rebuild",
                "",
                "standards: rebuild",
                "blocker — Corsair Captain; Pirate's Cutlass — a two-card island",
                "",
                "brief: playable",
                "note — Vaporkin — off the stated intent",
            ],
        )

    def test_axes_stay_side_by_side_never_reranked(self):
        # A brief blocker never floats above the standards section: sections
        # keep the fixed axis order whatever the severities say.
        home = TempFindings()
        self.addCleanup(home.cleanup)
        result = assemble(home, [finding()], [finding("blocker")])
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertLess(lines.index("standards: playable"),
                        lines.index("brief: rebuild"))


class FindingsCapAtFiveWorstFirst(unittest.TestCase):
    """At most five Findings per axis, worst first, with a one-line summary
    of the rest — and the Verdict still counts every Finding, capped or not:
    the cap trims the display, never the arithmetic."""

    def test_sixth_and_later_findings_fold_into_a_rest_line(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        findings = [finding(cards=(f"Card {n}",), problem=f"problem {n}")
                    for n in range(1, 8)]
        result = assemble(home, findings, [])
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        shown = [l for l in lines if l.startswith("note — ")]
        self.assertEqual(len(shown), 5)
        self.assertEqual([l.split(" — ")[1] for l in shown],
                         ["Card 1", "Card 2", "Card 3", "Card 4", "Card 5"])
        self.assertIn("rest: 2 more notes — Card 6; Card 7", lines)

    def test_worst_first_blockers_rise_above_notes(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        findings = [
            finding("note", ("Note One",)),
            finding("blocker", ("Blocker One",)),
            finding("note", ("Note Two",)),
            finding("blocker", ("Blocker Two",)),
        ]
        result = assemble(home, findings, [])
        self.assertEqual(result.returncode, 0, result.stderr)
        cards = [l.split(" — ")[1] for l in result.stdout.splitlines()
                 if l.startswith(("blocker — ", "note — "))]
        self.assertEqual(cards,
                         ["Blocker One", "Blocker Two", "Note One", "Note Two"])

    def test_a_blocker_past_the_cap_still_rebuilds_the_axis(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        findings = [finding(cards=(f"Note {n}",)) for n in range(1, 6)]
        findings.append(finding("blocker", ("Buried Blocker",)))
        result = assemble(home, findings, [])
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertIn("standards: rebuild", lines)
        self.assertIn("verdict: rebuild", lines)
        # Worst first: the blocker is shown, a note folds into the rest line.
        self.assertIn("blocker — Buried Blocker — a probe problem", lines)
        self.assertIn("rest: 1 more note — Note 5", lines)

    def test_five_findings_or_fewer_need_no_rest_line(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        result = assemble(home, [finding() for _ in range(5)], [])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("rest:", result.stdout)


class FindingShapeIsEnforced(unittest.TestCase):
    """A Finding is severity + named cards + the problem + at most one
    suggestion — an owned swap or an unowned Maybeboard candidate. Anything
    else is unusable input: the assembler refuses with exit 2 and no partial
    Block, naming what is wrong, so a malformed judgment is re-emitted
    rather than smuggled through."""

    def assert_refused(self, result, *needles):
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        for needle in needles:
            self.assertIn(needle, result.stderr)

    def test_swap_suggestion_renders_after_the_problem(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        result = assemble(
            home,
            [finding("note", ("Goblin Firebomb",), "never fires here",
                     swap="Voyaging Satyr")],
            [],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "note — Goblin Firebomb — never fires here — swap: Voyaging Satyr",
            result.stdout.splitlines(),
        )

    def test_maybeboard_suggestion_renders_as_maybeboard(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        result = assemble(
            home,
            [finding("note", ("Divination",), "one-shot draw below the ask",
                     maybeboard="Rhystic Study")],
            [],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "note — Divination — one-shot draw below the ask — "
            "maybeboard: Rhystic Study",
            result.stdout.splitlines(),
        )

    def test_two_suggestions_are_refused(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        result = assemble(
            home,
            [finding(swap="Voyaging Satyr", maybeboard="Rhystic Study")],
            [],
        )
        self.assert_refused(result, "at most one suggestion")

    def test_unknown_severity_is_refused(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        result = assemble(home, [finding(severity="fatal")], [])
        self.assert_refused(result, "fatal", "blocker")

    def test_a_finding_naming_no_cards_is_refused(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        result = assemble(home, [finding(cards=())], [])
        self.assert_refused(result, "cards")

    def test_a_finding_without_a_problem_is_refused(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        entry = finding()
        del entry["problem"]
        result = assemble(home, [entry], [])
        self.assert_refused(result, "problem")

    def test_unknown_keys_are_refused(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        result = assemble(home, [finding(fix="just edit the deck")], [])
        self.assert_refused(result, "fix")

    def test_a_refusal_names_the_axis_it_came_from(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        result = assemble(home, [], [finding(severity="fatal")])
        self.assert_refused(result, "brief")


class NoBriefMeansStandardsOnly(unittest.TestCase):
    """Any ManaBox deck is reviewable, tutor-built or not: with no Brief the
    review runs Standards-only, the Brief axis reports "no Brief available",
    and the overall Verdict is the Standards axis alone."""

    def test_brief_axis_reports_no_brief_available(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        result = assemble(home, [finding()], None)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertIn("brief: no Brief available", lines)
        self.assertIn("standards: playable", lines)
        self.assertIn("verdict: playable", lines)

    def test_clean_standards_still_ship_without_a_brief(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        result = assemble(home, [], None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verdict: ship", result.stdout.splitlines())

    def test_brief_findings_and_no_brief_are_mutually_exclusive(self):
        home = TempFindings()
        self.addCleanup(home.cleanup)
        brief_path = home.write("brief.json", [])
        result = run_cli(
            ASSEMBLER,
            "--deck-name", "Probe Deck", "--date", REFERENCE_DATE,
            "--standards", home.write("standards.json", []),
            "--brief", brief_path, "--no-brief",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


REVIEW_FLAWED_DECK = FIXTURES / "decks" / "tatyova-landfall-review-flawed.txt"


def run_fixture_suite(deck_path):
    return run_cli(
        RUNNER,
        "--suite", FIXTURES / "build" / "tatyova-landfall.suite.yaml",
        "--deck", deck_path,
        "--oracle", FIXTURES / "scryfall" / "oracle.jsonl",
        "--collection", FIXTURES / "collections" / "real-collection.csv",
        "--date", REFERENCE_DATE,
    )


def verdict_colors(report):
    import re
    return dict(
        (m.group(2), m.group(1))
        for m in (re.match(r"^(red|green)\s+(\S+) — ", line)
                  for line in report.splitlines())
        if m
    )


class ReviewFlawsAreBeyondCheckTerritory(unittest.TestCase):
    """The Review-flawed fixture Deck is the ADR 0006 boundary made flesh:
    its planted flaws are Review judgment — Smells and Brief infidelity —
    so the unmodified fixture Suite sees nothing new red on it. Every Check
    green on the clean fixture Deck stays green here; catching the flaws is
    the Review's job, not the runner's."""

    @classmethod
    def setUpClass(cls):
        cls.clean = run_fixture_suite(FIXTURES / "decks" / "tatyova-landfall.txt")
        cls.flawed = run_fixture_suite(REVIEW_FLAWED_DECK)

    def test_every_check_green_on_the_clean_deck_stays_green(self):
        clean = verdict_colors(self.clean.stdout)
        flawed = verdict_colors(self.flawed.stdout)
        self.assertTrue(clean, "no check lines parsed from the clean run")
        self.assertEqual(sorted(clean), sorted(flawed))
        for check_id, color in clean.items():
            if color == "green":
                self.assertEqual(
                    flawed.get(check_id), "green",
                    f"{check_id} went red on the Review-flawed Deck — a "
                    "planted flaw leaked into Check territory",
                )

    def test_the_planted_cards_are_all_in_the_deck_and_owned(self):
        import csv
        import io

        manifest = json.loads(
            (FIXTURES / "manifest.json").read_text(encoding="utf-8"))
        flaws = manifest["planted_flaws"].get(
            "decks/tatyova-landfall-review-flawed.txt")
        self.assertTrue(flaws, "the Review-flawed Deck registers no flaws")
        self.assertEqual({f["class"] for f in flaws} - {"standards", "brief"},
                         set(), "a Review-flawed flaw carries a Check class")
        smells = [f["smell"] for f in flaws if "smell" in f]
        self.assertTrue(smells, "no flaw names the Smell it plants")
        deck_text = REVIEW_FLAWED_DECK.read_text(encoding="utf-8")
        owned = {
            row["Name"]
            for row in csv.DictReader(io.StringIO(
                (FIXTURES / "collections" / "real-collection.csv")
                .read_bytes().decode("utf-8-sig")))
        }
        for flaw in flaws:
            for card in flaw["cards"]:
                self.assertIn(card, deck_text, f"{flaw['id']} names {card!r}")
                self.assertIn(card, owned,
                              f"{flaw['id']} card {card!r} is not owned — a "
                              "Review flaw must not smuggle in a Check flaw")


class CommanderProfileCarriesReviewStandards(unittest.TestCase):
    """Per-Format standards live in the Format profile as data (ADR 0005,
    0006), authored from the recorded Commander seeds: politics,
    functional-copy redundancy, answer spread. The review skill reads them
    on top of the Smell baseline; the profile overrides the baseline."""

    def review_standards(self):
        lines, inside = {}, False
        for line in PROFILE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            if not line.startswith(" "):
                inside = line.rstrip() == "review_standards:"
                continue
            if inside and not line.strip().startswith("#"):
                key, _, value = line.strip().partition(":")
                lines[key] = value.strip()
        return lines

    def test_the_three_commander_seeds_are_authored(self):
        standards = self.review_standards()
        for seed in ("politics", "functional-copy redundancy", "answer spread"):
            self.assertIn(seed, standards, f"no {seed!r} standard in the profile")
            self.assertTrue(standards[seed], f"{seed!r} carries no guidance text")

    def test_the_generator_still_reads_the_profile(self):
        # Regression: the new section must not disturb Suite generation —
        # the committed fixture Suite still reproduces byte-identical.
        result = run_cli(
            REPO / "skills" / "build" / "scripts" / "generate_suite.py",
            "--brief", FIXTURES / "briefs" / "commander-tatyova-landfall.txt",
            "--profile", PROFILE,
            "--oracle", FIXTURES / "scryfall" / "oracle.jsonl",
            "--date", REFERENCE_DATE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = (FIXTURES / "build" / "tatyova-landfall.suite.yaml").read_text(
            encoding="utf-8")
        self.assertEqual(result.stdout, expected)


class ReviewSmokeEvalRunsGreen(SmokeGradingMixin, unittest.TestCase):
    """Acceptance: the review-smoke eval case grades the whole seam offline —
    verdict arithmetic hard-graded through the assembler, the Review Block
    shape, the wiring, the locked Smell baseline, the Commander review
    standards, and the Review-flawed fixture registration — every mechanical
    expectation green, judgment quality left soft for dev-time runs."""

    CASE = "review-smoke"

    def test_case_exits_green(self):
        self.assertEqual(
            self.result.returncode, 0,
            f"review-smoke not green.\nstdout:\n{self.result.stdout}"
            f"\nstderr:\n{self.result.stderr}",
        )

    def test_verdict_arithmetic_graded_green(self):
        self.graded_green("arithmetic")

    def test_block_shape_graded_green(self):
        self.graded_green("deck: and date:")

    def test_findings_cap_graded_green(self):
        self.graded_green("at most five")

    def test_no_brief_path_graded_green(self):
        self.graded_green("no Brief available")

    def test_command_wiring_graded_green(self):
        self.graded_green("/tutor:review")

    def test_smell_baseline_graded_green(self):
        self.graded_green("Smell baseline")

    def test_commander_review_standards_graded_green(self):
        self.graded_green("review standards")

    def test_review_flaw_registration_graded_green(self):
        self.graded_green("Review-flawed")

    def test_live_judgment_stays_soft(self):
        # The harness posture: catching planted flaws live is judgment
        # quality — reported soft, never faked by a predicate.
        soft = self.grading["soft_expectations"]
        self.assertTrue(any("fans out" in text for text in soft),
                        f"no soft expectation covers the live fan-out: {soft}")
        self.assertTrue(any("catch every planted flaw" in text for text in soft),
                        f"no soft expectation covers catching flaws: {soft}")


if __name__ == "__main__":
    unittest.main()
