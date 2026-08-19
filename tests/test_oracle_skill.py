"""Tests for the oracle skill's deterministic seam (issue #51).

Every test exercises the skill's script through its public seams only:

- the CLI: ``python3 skills/oracle/scripts/build_oracle.py`` (exit code,
  stdout report), and
- the Oracle it writes: ``oracle.jsonl`` beside the Export.

Offline tests resolve against the pinned Scryfall snapshot (``--snapshot``);
the live-endpoint contract — batching, throttle, mandatory headers, the
Name + Set fallback — is exercised against a local HTTP stub, never the
live API.
"""

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO / "skills" / "oracle" / "scripts" / "build_oracle.py"
FIXTURES = REPO / "evals" / "fixtures"
SNAPSHOT = FIXTURES / "scryfall" / "snapshot.jsonl"
REAL_EXPORT = FIXTURES / "collections" / "real-collection.csv"

# Known-good literals from the committed realism fixture (ManaBox 4.1.12,
# 577 rows) — independent of the script under test.
REAL_EXPORT_NEWEST_ADDED = "2026-08-15T21:10:47.241Z"


def run_oracle(*args, cwd):
    """Run the oracle script CLI and return the CompletedProcess."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=300,
    )


def collection_home(tmp, export=REAL_EXPORT):
    """A temp Collection home holding a copy of an Export as collection.csv."""
    home = pathlib.Path(tmp)
    shutil.copy(export, home / "collection.csv")
    return home


class OracleWrittenBesideExport(unittest.TestCase):
    """Acceptance: the Oracle is written beside the Export, line one
    recording generated_at plus the source Export's newest Added watermark."""

    def test_snapshot_mode_writes_oracle_beside_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = collection_home(tmp)
            result = run_oracle(
                "--collection", str(home / "collection.csv"),
                "--snapshot", str(SNAPSHOT),
                cwd=home,
            )
            self.assertEqual(
                result.returncode, 0,
                f"oracle build failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            oracle_path = home / "oracle.jsonl"
            self.assertTrue(oracle_path.is_file(), "oracle.jsonl not written beside the Export")

            with oracle_path.open(encoding="utf-8") as handle:
                meta = json.loads(handle.readline())["oracle_meta"]
            self.assertEqual(meta["source_export_newest_added"], REAL_EXPORT_NEWEST_ADDED)
            with SNAPSHOT.open(encoding="utf-8") as handle:
                snap_meta = json.loads(handle.readline())["snapshot_meta"]
            self.assertEqual(
                meta["generated_at"], snap_meta["captured_at"],
                "snapshot mode pins generated_at to the snapshot's captured_at "
                "(facts exactly as fresh as the snapshot; runs stay deterministic)",
            )


class SnapshotModeIsDeterministic(unittest.TestCase):
    """Acceptance: the smoke eval runs offline against the pinned snapshot —
    deterministic, so two runs over the same inputs are byte-identical."""

    def test_two_runs_byte_identical(self):
        outputs = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tmp:
                home = collection_home(tmp)
                result = run_oracle(
                    "--collection", str(home / "collection.csv"),
                    "--snapshot", str(SNAPSHOT),
                    cwd=home,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                outputs.append((home / "oracle.jsonl").read_bytes())
        self.assertEqual(outputs[0], outputs[1])


class OfflineSmokeEval(unittest.TestCase):
    """Acceptance: the smoke eval runs offline against the pinned Scryfall
    snapshot — never the live API — through the #48 harness's conventions."""

    def test_oracle_smoke_case_grades_green_with_a_soft_tier(self):
        result = subprocess.run(
            [sys.executable, str(REPO / "evals" / "run_evals.py"), "--case", "oracle-smoke"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(
            result.returncode, 0,
            f"oracle-smoke eval not green.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        grading = json.loads(
            (REPO / "evals" / "results" / "oracle-smoke" / "grading.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(grading["summary"]["failed"], 0)
        self.assertGreaterEqual(grading["summary"]["passed"], 4)
        self.assertTrue(
            grading["soft_expectations"],
            "the oracle case must leave its judgment expectation to the soft tier",
        )


class OracleShape(unittest.TestCase):
    """Acceptance: one JSON line per unique card name — prints deduped, token
    rows excluded, basic lands included, multi-faced cards flattened with //.
    Fields exactly: name, mana value, colors, color identity, type line,
    oracle text, legalities trimmed to the four sanctioned Formats, the
    game_changer boolean, and — for the Kitchen 20 packet Checks (issue #57)
    — the deduped printing's rarity and the keywords list. No UUIDs."""

    FIELDS = {
        "name", "mana_value", "colors", "color_identity", "type_line",
        "oracle_text", "legalities", "game_changer", "rarity", "keywords",
    }

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        home = collection_home(cls.tmp.name)
        cls.result = run_oracle(
            "--collection", str(home / "collection.csv"),
            "--snapshot", str(SNAPSHOT),
            cwd=home,
        )
        cls.lines = (home / "oracle.jsonl").read_text(encoding="utf-8").splitlines()
        cls.records = [json.loads(line) for line in cls.lines[1:]]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_fields_are_exactly_the_oracle_shape(self):
        for record in self.records:
            self.assertEqual(set(record), self.FIELDS, f"wrong fields on {record.get('name')}")
            self.assertEqual(
                set(record["legalities"]),
                {"standard", "pioneer", "modern", "commander"},
                f"{record['name']}: legalities not trimmed to the four sanctioned Formats",
            )
            self.assertIsInstance(record["game_changer"], bool)

    def test_one_line_per_unique_name_sorted(self):
        names = [record["name"] for record in self.records]
        self.assertEqual(names, sorted(names))
        self.assertEqual(len(names), len(set(names)), "duplicate card names — prints not deduped")

    def test_token_rows_excluded_basics_included_multiface_flattened(self):
        names = {record["name"] for record in self.records}
        # The realism Export holds 18 token rows; Copy exists only as a token.
        self.assertNotIn("Copy", names, "token rows leaked into the Oracle")
        self.assertIn("Forest", names, "basic lands missing from the Oracle")
        self.assertIn(
            "Adventurous Eater // Have a Bite", names,
            "multi-faced card not flattened with //",
        )

    def test_no_uuids(self):
        import re
        uuid = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
        for line in self.lines[1:]:
            self.assertIsNone(uuid.search(line), f"UUID leaked into the Oracle: {line[:80]}")

    def test_records_agree_with_the_fixture_oracle(self):
        """The fixture Oracle (derived by evals/fixtures/scryfall/
        derive_oracle.py from the same snapshot) is the independent known-good:
        every card the skill writes must match it byte for byte."""
        fixture_lines = (FIXTURES / "scryfall" / "oracle.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        fixture_by_name = {
            json.loads(line)["name"]: line for line in fixture_lines[1:]
        }
        for line, record in zip(self.lines[1:], self.records):
            self.assertIn(record["name"], fixture_by_name)
            self.assertEqual(line, fixture_by_name[record["name"]],
                             f"{record['name']}: skill Oracle line differs from the fixture Oracle")


def snapshot_card(name):
    """A card object from the pinned snapshot, by exact name."""
    with SNAPSHOT.open(encoding="utf-8") as handle:
        next(handle)
        for line in handle:
            card = json.loads(line)
            if card["name"] == name:
                return card
    raise LookupError(name)


class TolerantExportParsing(unittest.TestCase):
    """Acceptance: header-keyed (never positional), RFC-4180 quoting-aware,
    UTF-8 with BOM tolerance; malformed rows are skipped and reported with a
    count and examples; the only hard failure is a header missing the
    identity columns."""

    def build(self, csv_text, filename="collection.csv"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        home = pathlib.Path(tmp.name)
        (home / filename).write_bytes(csv_text.encode("utf-8"))
        result = run_oracle(
            "--collection", str(home / filename),
            "--snapshot", str(SNAPSHOT),
            cwd=home,
        )
        return home, result

    def test_header_keyed_bom_and_quoting(self):
        """Reordered columns, an unknown extra column, a UTF-8 BOM, a quoted
        comma name, and a quoted embedded newline all parse."""
        alania = snapshot_card("Alania, Divergent Storm")
        witness = snapshot_card("Llanowar Elves")
        csv_text = (
            "﻿Quantity,Name,Shelf,Set code,Scryfall ID,Added\n"
            f'1,"{alania["name"]}",A,{alania["set"].upper()},{alania["id"]},2026-08-01T09:00:00.000Z\n'
            f'1,{witness["name"]},"top\nrow",{witness["set"].upper()},{witness["id"]},2026-08-02T09:00:00.000Z\n'
        )
        home, result = self.build(csv_text)
        self.assertEqual(result.returncode, 0, result.stderr)
        names = {
            json.loads(line)["name"]
            for line in (home / "oracle.jsonl").read_text(encoding="utf-8").splitlines()[1:]
        }
        self.assertEqual(names, {alania["name"], witness["name"]})

    def test_malformed_rows_skipped_and_reported_with_count_and_examples(self):
        witness = snapshot_card("Llanowar Elves")
        csv_text = (
            "Name,Set code,Scryfall ID,Added\n"
            f"{witness['name']},{witness['set'].upper()},{witness['id']},2026-08-02T09:00:00.000Z\n"
            "Orphaned Name,,,\n"  # a Name alone identifies nothing
            ",,,\n"
        )
        home, result = self.build(csv_text)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2 malformed rows skipped", result.stdout)
        self.assertIn("row 3", result.stdout, "skipped-row examples missing from the report")
        names = {
            json.loads(line)["name"]
            for line in (home / "oracle.jsonl").read_text(encoding="utf-8").splitlines()[1:]
        }
        self.assertEqual(names, {witness["name"]}, "the good row must still resolve")

    def test_header_missing_identity_columns_is_the_hard_failure(self):
        home, result = self.build(
            "Binder Name,Quantity,Foil\nMy binder,1,normal\n"
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("identity columns", result.stderr)
        self.assertFalse((home / "oracle.jsonl").exists(), "no Oracle on a hard failure")

    def test_name_and_set_columns_alone_are_an_identity_path(self):
        """A header with Name + Set code but no Scryfall ID column still
        works — identity needs one path, not every column."""
        witness = snapshot_card("Llanowar Elves")
        csv_text = (
            "Name,Set code,Added\n"
            f"{witness['name']},{witness['set'].upper()},2026-08-02T09:00:00.000Z\n"
        )
        home, result = self.build(csv_text)
        self.assertEqual(result.returncode, 0, result.stderr)
        names = {
            json.loads(line)["name"]
            for line in (home / "oracle.jsonl").read_text(encoding="utf-8").splitlines()[1:]
        }
        self.assertEqual(names, {witness["name"]})


class NameSetFallback(unittest.TestCase):
    """Acceptance: Scryfall ID first, Name + Set code fallback for migrated
    or deleted IDs."""

    def test_migrated_id_resolves_via_name_and_set(self):
        elves = snapshot_card("Llanowar Elves")
        csv_text = (
            "Name,Set code,Scryfall ID,Added\n"
            # A migrated ID: valid shape, unknown to the snapshot.
            f"{elves['name']},{elves['set'].upper()},00000000-0000-0000-0000-000000000000,"
            "2026-08-02T09:00:00.000Z\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            (home / "collection.csv").write_text(csv_text, encoding="utf-8")
            result = run_oracle(
                "--collection", str(home / "collection.csv"),
                "--snapshot", str(SNAPSHOT),
                cwd=home,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("1 by Name + Set code fallback", result.stdout)
            names = {
                json.loads(line)["name"]
                for line in (home / "oracle.jsonl").read_text(encoding="utf-8").splitlines()[1:]
            }
            self.assertEqual(names, {elves["name"]})

    def test_unresolvable_card_reported_not_fatal(self):
        elves = snapshot_card("Llanowar Elves")
        csv_text = (
            "Name,Set code,Scryfall ID,Added\n"
            f"{elves['name']},{elves['set'].upper()},{elves['id']},2026-08-02T09:00:00.000Z\n"
            "Storm Crow,9ED,,2026-08-02T09:00:00.000Z\n"  # identified, but not in the snapshot
        )
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            (home / "collection.csv").write_text(csv_text, encoding="utf-8")
            result = run_oracle(
                "--collection", str(home / "collection.csv"),
                "--snapshot", str(SNAPSHOT),
                cwd=home,
            )
            self.assertEqual(result.returncode, 0, "an unresolved card must degrade, not fail")
            self.assertIn("Storm Crow", result.stdout)
            self.assertIn("1 cards left out of the Oracle", result.stdout)
            names = {
                json.loads(line)["name"]
                for line in (home / "oracle.jsonl").read_text(encoding="utf-8").splitlines()[1:]
            }
            self.assertEqual(names, {elves["name"]})


class ScryfallStub:
    """A local fake of Scryfall's POST /cards/collection, backed by the
    pinned snapshot — so the live-path contract (batching, throttle,
    mandatory headers, not_found echoes) is testable with no live API."""

    def __init__(self):
        import http.server
        import threading
        import time as time_module

        with SNAPSHOT.open(encoding="utf-8") as handle:
            next(handle)
            cards = [json.loads(line) for line in handle]
        by_id = {c["id"]: c for c in cards}
        by_name_set = {}
        for c in cards:
            by_name_set.setdefault((c["name"].casefold(), c["set"]), c)
        self.requests = []  # (monotonic arrival, headers dict, identifiers list)
        stub = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length))
                stub.requests.append(
                    (time_module.monotonic(), dict(self.headers), body["identifiers"])
                )
                data, not_found = [], []
                for ident in body["identifiers"]:
                    if "id" in ident:
                        card = by_id.get(ident["id"])
                    else:
                        card = by_name_set.get((ident["name"].casefold(), ident["set"]))
                    if card is None:
                        not_found.append(ident)
                    else:
                        data.append(card)
                payload = json.dumps(
                    {"object": "list", "not_found": not_found, "data": data}
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/cards/collection"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class LiveEndpointContract(unittest.TestCase):
    """Acceptance: unique cards batch-resolve via Scryfall's collection
    endpoint — 75 identifiers per call, max 2 calls/second, mandatory
    User-Agent and Accept headers — Scryfall ID first, Name + Set code
    fallback. Exercised against a local stub, never the live API."""

    def setUp(self):
        self.stub = ScryfallStub()
        self.addCleanup(self.stub.close)

    def run_against_stub(self, csv_text):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        home = pathlib.Path(tmp.name)
        (home / "collection.csv").write_text(csv_text, encoding="utf-8")
        result = run_oracle(
            "--collection", str(home / "collection.csv"),
            "--api-url", self.stub.url,
            cwd=home,
        )
        return home, result

    def test_batches_of_75_throttled_with_mandatory_headers(self):
        with SNAPSHOT.open(encoding="utf-8") as handle:
            next(handle)
            cards = [json.loads(line) for line in handle]
        eighty = [c for c in cards if c.get("layout") == "normal"][:80]
        csv_text = "Name,Set code,Scryfall ID,Added\n" + "".join(
            f"\"{c['name']}\",{c['set'].upper()},{c['id']},2026-08-02T09:00:00.000Z\n"
            for c in eighty
        )
        home, result = self.run_against_stub(csv_text)
        self.assertEqual(result.returncode, 0, result.stderr)

        self.assertEqual(
            [len(idents) for _, _, idents in self.stub.requests], [75, 5],
            "80 unique cards must arrive as one batch of 75 and one of 5",
        )
        for _, headers, _ in self.stub.requests:
            self.assertIn("tutor", headers.get("User-Agent", ""),
                          "every call carries an identifying User-Agent")
            self.assertEqual(headers.get("Accept"), "application/json",
                             "every call carries the mandatory Accept header")
        gap = self.stub.requests[1][0] - self.stub.requests[0][0]
        self.assertGreaterEqual(gap, 0.5, f"calls {gap:.3f}s apart — over 2 calls/second")

        with (home / "oracle.jsonl").open(encoding="utf-8") as handle:
            meta = json.loads(handle.readline())["oracle_meta"]
            names = {json.loads(line)["name"] for line in handle}
        self.assertEqual(names, {c["name"] for c in eighty})
        self.assertTrue(meta["generated_at"], "live mode must record a generated_at")

    def test_not_found_id_falls_back_to_name_and_set_in_a_second_pass(self):
        elves = snapshot_card("Llanowar Elves")
        aether = snapshot_card("Aetherspouts")
        csv_text = (
            "Name,Set code,Scryfall ID,Added\n"
            f"{aether['name']},{aether['set'].upper()},{aether['id']},2026-08-02T09:00:00.000Z\n"
            f"{elves['name']},{elves['set'].upper()},11111111-2222-3333-4444-555555555555,"
            "2026-08-02T09:00:00.000Z\n"
        )
        home, result = self.run_against_stub(csv_text)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 by Name + Set code fallback", result.stdout)

        fallback_idents = [
            ident
            for _, _, idents in self.stub.requests
            for ident in idents
            if "name" in ident
        ]
        self.assertEqual(
            fallback_idents,
            [{"name": elves["name"], "set": elves["set"]}],
            "the migrated ID must be retried as a Name + Set code identifier",
        )
        names = {
            json.loads(line)["name"]
            for line in (home / "oracle.jsonl").read_text(encoding="utf-8").splitlines()[1:]
        }
        self.assertEqual(names, {elves["name"], aether["name"]})

    def test_network_failure_is_a_hard_failure(self):
        elves = snapshot_card("Llanowar Elves")
        self.stub.close()  # the port goes dark
        csv_text = (
            "Name,Set code,Scryfall ID,Added\n"
            f"{elves['name']},{elves['set'].upper()},{elves['id']},2026-08-02T09:00:00.000Z\n"
        )
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        home = pathlib.Path(tmp.name)
        (home / "collection.csv").write_text(csv_text, encoding="utf-8")
        result = run_oracle(
            "--collection", str(home / "collection.csv"),
            "--api-url", self.stub.url,
            cwd=home,
        )
        self.assertEqual(result.returncode, 2)
        self.assertFalse((home / "oracle.jsonl").exists(), "no Oracle on a network failure")


if __name__ == "__main__":
    unittest.main()
