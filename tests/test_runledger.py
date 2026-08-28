import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "runledger.py"
SPEC = importlib.util.spec_from_file_location("super_guare_runledger", MODULE_PATH)
runledger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runledger)


class RunLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.contract = self.root / "contract.md"
        self.contract.write_text("# Contract\n\nObservable closure.\n", encoding="utf-8")
        self.state = runledger.new_run(
            run_id="case-1",
            title="Durable test",
            repo="example/repo",
            base="base123",
            head="head123",
            max_rounds=2,
        )
        runledger.pin_contract(self.state, self.contract)

    def tearDown(self):
        self.temp.cleanup()

    def _roles(self, implementer_family="openai", reviewer_family="anthropic"):
        runledger.assign_role(self.state, "implementer", "codex", implementer_family)
        runledger.assign_role(self.state, "reviewer", "claude", reviewer_family)

    def _to_adjudicate(self):
        self._roles()
        runledger.enter(self.state, "ready")
        runledger.enter(self.state, "implement")
        runledger.enter(self.state, "review")
        runledger.enter(self.state, "adjudicate")

    def test_contract_drift_blocks_implementation(self):
        runledger.enter(self.state, "ready")
        self.contract.write_text("# Changed contract\n", encoding="utf-8")

        with self.assertRaisesRegex(runledger.Refused, "contract changed"):
            runledger.enter(self.state, "implement")

        self.assertEqual(self.state["node"], "ready")

    def test_contract_cannot_be_re_pinned_during_implementation(self):
        runledger.enter(self.state, "ready")
        runledger.enter(self.state, "implement")

        with self.assertRaisesRegex(runledger.Refused, "pin contract"):
            runledger.pin_contract(self.state, self.contract)

    def test_re_pinned_contract_requires_new_implementation_and_review(self):
        self._to_adjudicate()
        self.contract.write_text("# Contract v2\n", encoding="utf-8")
        runledger.pin_contract(self.state, self.contract)

        with self.assertRaisesRegex(runledger.Refused, "implementation"):
            runledger.enter(self.state, "verify")

    def test_undetermined_check_fails_closed(self):
        runledger.record_check(self.state, "database", "undetermined", "DATABASE_URL missing")

        with self.assertRaisesRegex(runledger.Undetermined, "database"):
            runledger.enter(self.state, "ready")

    def test_same_family_reviewer_is_refused(self):
        self._roles(implementer_family="openai", reviewer_family="openai")
        runledger.enter(self.state, "ready")
        runledger.enter(self.state, "implement")

        with self.assertRaisesRegex(runledger.Refused, "different engine families"):
            runledger.enter(self.state, "review")

    def test_criteria_to_unit_coverage_is_required_only_for_partitioned_runs(self):
        runledger.add_criterion(self.state, "AC1", "Persist the repaired state")
        runledger.add_criterion(self.state, "AC2", "Preserve the clean-session path")
        runledger.add_unit(self.state, "repair", ["AC1"], [])
        runledger.enter(self.state, "ready")

        with self.assertRaisesRegex(runledger.Refused, "AC2"):
            runledger.enter(self.state, "implement")

        runledger.enter(self.state, "hold")
        runledger.enter(self.state, "premise")
        runledger.defer_criterion(self.state, "AC2", "Owned by a verified follow-up")
        runledger.enter(self.state, "ready")
        runledger.enter(self.state, "implement")

    def test_unit_dependency_cycle_is_refused(self):
        runledger.add_criterion(self.state, "AC1", "Observable closure")
        runledger.add_unit(self.state, "one", ["AC1"], ["two"])
        runledger.add_unit(self.state, "two", ["AC1"], ["one"])
        runledger.enter(self.state, "ready")

        with self.assertRaisesRegex(runledger.Refused, "cycle"):
            runledger.enter(self.state, "implement")

    def test_severe_findings_block_verify_and_stable_identity_stops_loops(self):
        self._to_adjudicate()
        runledger.add_finding(self.state, "F1", "DB-LOSS", "P0", "Write can disappear")
        runledger.decide_finding(self.state, "F1", "confirmed")

        with self.assertRaisesRegex(runledger.Refused, "F1"):
            runledger.enter(self.state, "verify")

        runledger.enter(self.state, "implement")
        runledger.enter(self.state, "review")
        runledger.enter(self.state, "adjudicate")
        runledger.add_finding(self.state, "F2", "DB-LOSS", "P0", "Write can still disappear")
        runledger.decide_finding(self.state, "F2", "confirmed")

        with self.assertRaisesRegex(runledger.Refused, "DB-LOSS"):
            runledger.enter(self.state, "implement")

    def test_confirmed_severe_finding_requires_a_new_implementation_and_review_before_resolution(self):
        self._to_adjudicate()
        runledger.add_finding(self.state, "F1", "DB-LOSS", "P0", "Write can disappear")
        runledger.decide_finding(self.state, "F1", "confirmed")

        with self.assertRaisesRegex(runledger.Refused, "implementation and review"):
            runledger.resolve_finding(self.state, "F1", "arbitrary evidence")

        runledger.enter(self.state, "implement")
        runledger.update_tree(self.state, head="corrected-head")
        runledger.enter(self.state, "review")
        runledger.enter(self.state, "adjudicate")
        runledger.resolve_finding(self.state, "F1", "regression passes on corrected head")
        snapshot = runledger.build_snapshot(self.state)
        self.assertEqual(snapshot["content"]["findings"][0]["origin_review_head"], "head123")
        self.assertEqual(snapshot["content"]["findings"][0]["resolution_head"], "corrected-head")
        runledger.enter(self.state, "verify")

    def test_confirmed_severe_finding_cannot_resolve_after_re_review_of_the_same_head(self):
        self._to_adjudicate()
        runledger.add_finding(self.state, "F1", "DB-LOSS", "P1", "Write can disappear")
        runledger.decide_finding(self.state, "F1", "confirmed")
        runledger.enter(self.state, "implement")
        runledger.enter(self.state, "review")
        runledger.enter(self.state, "adjudicate")

        with self.assertRaisesRegex(runledger.Refused, "corrected head"):
            runledger.resolve_finding(self.state, "F1", "same head was reviewed again")

    def test_delayed_confirmation_keeps_the_finding_origin_separate_from_confirmation_timing(self):
        self._to_adjudicate()
        runledger.add_finding(self.state, "F1", "DB-LOSS", "P1", "Write can disappear")
        self.assertEqual(self.state["findings"][0].get("origin_review_head"), "head123")
        runledger.enter(self.state, "implement")
        runledger.update_tree(self.state, head="candidate-head")
        runledger.enter(self.state, "review")
        runledger.enter(self.state, "adjudicate")
        runledger.decide_finding(self.state, "F1", "confirmed")
        self.assertEqual(self.state["findings"][0].get("confirmation_round"), 2)
        runledger.update_tree(self.state, head="head123")
        runledger.enter(self.state, "implement")
        runledger.enter(self.state, "review")
        runledger.enter(self.state, "adjudicate")

        with self.assertRaisesRegex(runledger.Refused, "corrected head"):
            runledger.resolve_finding(self.state, "F1", "the original head was reviewed again")

    def test_tree_changed_after_review_cannot_supply_resolution_proof_until_re_reviewed(self):
        self._to_adjudicate()
        runledger.add_finding(self.state, "F1", "DB-LOSS", "P1", "Write can disappear")
        runledger.decide_finding(self.state, "F1", "confirmed")
        runledger.enter(self.state, "implement")
        runledger.update_tree(self.state, head="corrected-head")
        runledger.enter(self.state, "review")
        runledger.enter(self.state, "adjudicate")
        runledger.update_tree(self.state, head="unreviewed-head")

        with self.assertRaisesRegex(runledger.Refused, "new review"):
            runledger.resolve_finding(self.state, "F1", "unreviewed head claims the correction")

    def test_resolved_severe_finding_reopens_when_a_later_review_returns_to_its_origin_head(self):
        self._to_adjudicate()
        runledger.add_finding(self.state, "F1", "DB-LOSS", "P1", "Write can disappear")
        runledger.decide_finding(self.state, "F1", "confirmed")
        runledger.enter(self.state, "implement")
        runledger.update_tree(self.state, head="corrected-head")
        runledger.enter(self.state, "review")
        runledger.enter(self.state, "adjudicate")
        runledger.resolve_finding(self.state, "F1", "correction proved on corrected head")
        runledger.enter(self.state, "verify")
        runledger.enter(self.state, "adjudicate")
        runledger.enter(self.state, "implement")
        runledger.update_tree(self.state, head="head123")
        runledger.enter(self.state, "review")
        runledger.enter(self.state, "adjudicate")

        with self.assertRaisesRegex(runledger.Refused, "F1"):
            runledger.enter(self.state, "verify")

    def test_confirmed_severe_finding_cannot_downgrade_to_suspected_to_bypass_correction(self):
        self._to_adjudicate()
        runledger.add_finding(self.state, "F1", "DB-LOSS", "P1", "Write can disappear")
        runledger.decide_finding(self.state, "F1", "confirmed")
        runledger.decide_finding(self.state, "F1", "suspected")

        with self.assertRaisesRegex(runledger.Refused, "implementation and review"):
            runledger.resolve_finding(self.state, "F1", "downgraded label")

        with self.assertRaisesRegex(runledger.Refused, "F1"):
            runledger.enter(self.state, "verify")

    def test_explicit_rejection_remains_a_valid_severe_finding_disposition(self):
        self._to_adjudicate()
        runledger.add_finding(self.state, "F1", "DB-LOSS", "P1", "Write can disappear")
        runledger.decide_finding(self.state, "F1", "confirmed")
        runledger.decide_finding(self.state, "F1", "rejected")
        runledger.enter(self.state, "verify")

    def test_non_severe_finding_keeps_the_normal_same_cycle_resolution_flow(self):
        self._to_adjudicate()
        runledger.add_finding(self.state, "F1", "COPY", "P2", "Typo in a handoff")
        runledger.decide_finding(self.state, "F1", "confirmed")
        runledger.resolve_finding(self.state, "F1", "corrected copy")
        runledger.enter(self.state, "verify")

    def test_ready_detour_does_not_bypass_convergence(self):
        self._to_adjudicate()
        runledger.add_finding(self.state, "F1", "DB-LOSS", "P0", "First occurrence")
        runledger.decide_finding(self.state, "F1", "confirmed")
        runledger.enter(self.state, "implement")
        runledger.enter(self.state, "review")
        runledger.enter(self.state, "adjudicate")
        runledger.add_finding(self.state, "F2", "DB-LOSS", "P0", "Second occurrence")
        runledger.decide_finding(self.state, "F2", "confirmed")
        runledger.enter(self.state, "ready")

        with self.assertRaisesRegex(runledger.Refused, "DB-LOSS"):
            runledger.enter(self.state, "implement")

    def test_snapshot_separates_structure_and_content_pins(self):
        self._roles()
        runledger.add_criterion(self.state, "AC1", "Observable closure")
        snap = runledger.build_snapshot(self.state)

        self.assertEqual(snap["kind"], "super-guare.run.snapshot")
        self.assertEqual(snap["structure"]["node"], "premise")
        self.assertEqual(snap["content"]["contract_sha256"], self.state["contract"]["sha256"])
        self.assertEqual(snap["content"]["roles"]["reviewer"]["family"], "anthropic")
        self.assertEqual(snap["content"]["criteria"][0]["id"], "AC1")

    def test_done_requires_positive_effect_and_resolved_severe_findings(self):
        self._to_adjudicate()

        with self.assertRaisesRegex(runledger.Refused, "verify"):
            runledger.record_check(self.state, "effect", "ok", "too early")

        runledger.enter(self.state, "verify")

        with self.assertRaisesRegex(runledger.Refused, "effect"):
            runledger.enter(self.state, "done")

        runledger.record_check(self.state, "effect", "ok", "real entrypoint returned repaired state")
        runledger.enter(self.state, "done")

    def test_failed_effect_is_preserved_in_history_but_does_not_deadlock_correction(self):
        self._to_adjudicate()
        runledger.enter(self.state, "verify")
        runledger.record_check(self.state, "effect", "not-ok", "real entrypoint is still stale")
        runledger.enter(self.state, "adjudicate")

        self.assertNotIn("effect", self.state["checks"])
        self.assertEqual(self.state["check_history"][-1]["verdict"], "not-ok")
        runledger.enter(self.state, "implement")

    def test_undetermined_effect_can_resume_through_hold(self):
        self._to_adjudicate()
        runledger.enter(self.state, "verify")
        runledger.record_check(self.state, "effect", "undetermined", "environment unavailable")
        runledger.enter(self.state, "hold")

        self.assertNotIn("effect", self.state["checks"])
        self.assertEqual(self.state["check_history"][-1]["verdict"], "undetermined")
        runledger.enter(self.state, "premise")
        runledger.enter(self.state, "ready")

    def test_rejected_finding_reopened_as_confirmed_is_not_resolved(self):
        self._to_adjudicate()
        runledger.add_finding(self.state, "F1", "AUTH", "P0", "Boundary bypass")
        runledger.decide_finding(self.state, "F1", "rejected")
        runledger.decide_finding(self.state, "F1", "confirmed")

        finding = self.state["findings"][0]
        self.assertFalse(finding["resolved"])
        self.assertIsNone(finding["resolution_evidence"])
        with self.assertRaisesRegex(runledger.Refused, "F1"):
            runledger.enter(self.state, "verify")

    def test_new_failed_check_blocks_review_and_terminal_mutations_are_refused(self):
        self._roles()
        runledger.enter(self.state, "ready")
        runledger.enter(self.state, "implement")
        runledger.record_check(self.state, "database", "not-ok", "write failed")

        with self.assertRaisesRegex(runledger.Refused, "database"):
            runledger.enter(self.state, "review")

        runledger.record_check(self.state, "database", "ok", "write now durable")
        runledger.enter(self.state, "review")
        runledger.enter(self.state, "adjudicate")
        runledger.enter(self.state, "verify")
        runledger.record_check(self.state, "effect", "ok", "verified current head")
        runledger.enter(self.state, "done")
        with self.assertRaisesRegex(runledger.Refused, "terminal"):
            runledger.update_tree(self.state, head="other")

    def test_tree_change_after_review_requires_another_review(self):
        self._to_adjudicate()
        runledger.update_tree(self.state, head="new-head")

        with self.assertRaisesRegex(runledger.Refused, "review"):
            runledger.enter(self.state, "verify")

    def test_plan_cannot_mutate_in_verify(self):
        self._to_adjudicate()
        runledger.enter(self.state, "verify")

        with self.assertRaisesRegex(runledger.Refused, "criterion"):
            runledger.add_criterion(self.state, "AC-late", "Late scope")

    def test_atomic_round_trip(self):
        path = runledger.state_path(self.root, self.state["run_id"])
        runledger.save_state(path, self.state)
        loaded = runledger.load_state(path)

        self.assertEqual(loaded["run_id"], "case-1")
        self.assertEqual(json.dumps(loaded, sort_keys=True), json.dumps(self.state, sort_keys=True))

    def test_malformed_persisted_state_fails_as_undetermined(self):
        path = runledger.state_path(self.root, "broken")
        path.parent.mkdir(parents=True)
        path.write_text('{"kind":"super-guare.run","version":1}', encoding="utf-8")

        with self.assertRaisesRegex(runledger.Undetermined, "missing"):
            runledger.load_state(path)

        path.write_text('{"kind":"super-guare.run","version":1,"node":[]}', encoding="utf-8")
        with self.assertRaises(runledger.Undetermined):
            runledger.load_state(path)

    def test_non_string_unit_members_fail_closed_when_loading_persisted_state(self):
        self.state["criteria"].append(
            {"id": "AC1", "text": "Persist the repaired state", "status": "required", "reason": None}
        )
        self.state["units"].append({"id": "repair", "covers": ["AC1"], "depends_on": []})
        path = runledger.state_path(self.root, self.state["run_id"])
        runledger.save_state(path, self.state)
        loaded = runledger.load_state(path)
        self.assertEqual(loaded["units"][0], {"id": "repair", "covers": ["AC1"], "depends_on": []})
        valid_payload = json.loads(path.read_text(encoding="utf-8"))

        for member_field, invalid_member in (("covers", {"AC1": True}), ("depends_on", ["repair"])):
            payload = json.loads(json.dumps(valid_payload))
            payload["units"][0][member_field] = [invalid_member]
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.subTest(member_field=member_field):
                with self.assertRaisesRegex(runledger.Undetermined, "unit member"):
                    runledger.load_state(path)
                result = subprocess.run(
                    [sys.executable, str(MODULE_PATH), "--dir", str(self.root), "--run", self.state["run_id"], "enter", "implement"],
                    text=True,
                    capture_output=True,
                    encoding="utf-8",
                    check=False,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("unit member", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_legacy_confirmed_severe_finding_cannot_downgrade_to_suspected_and_bypass_unknown_metadata(self):
        self._to_adjudicate()
        runledger.add_finding(self.state, "F1", "DB-LOSS", "P1", "Write can disappear")
        runledger.decide_finding(self.state, "F1", "confirmed")
        path = runledger.state_path(self.root, self.state["run_id"])
        runledger.save_state(path, self.state)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.pop("review_heads", None)
        for key in (
            "confirmed_round",
            "confirmed_head",
            "origin_review_head",
            "confirmation_round",
            "ever_confirmed",
            "resolution_round",
            "resolution_head",
        ):
            payload["findings"][0].pop(key, None)
        path.write_text(json.dumps(payload), encoding="utf-8")

        legacy = runledger.load_state(path)
        runledger.decide_finding(legacy, "F1", "suspected")
        with self.assertRaisesRegex(runledger.Undetermined, "origin"):
            runledger.resolve_finding(legacy, "F1", "legacy evidence")

    def test_legacy_severe_suspected_finding_with_no_history_fails_closed(self):
        self._to_adjudicate()
        runledger.add_finding(self.state, "F1", "DB-LOSS", "P1", "Write can disappear")
        runledger.decide_finding(self.state, "F1", "suspected")
        path = runledger.state_path(self.root, self.state["run_id"])
        runledger.save_state(path, self.state)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.pop("review_heads", None)
        for key in (
            "origin_review_head",
            "confirmation_round",
            "ever_confirmed",
            "resolution_round",
            "resolution_head",
        ):
            payload["findings"][0].pop(key, None)
        path.write_text(json.dumps(payload), encoding="utf-8")

        legacy = runledger.load_state(path)
        with self.assertRaisesRegex(runledger.Undetermined, "origin"):
            runledger.resolve_finding(legacy, "F1", "legacy suspected evidence")

    def test_persisted_origin_head_must_match_the_finding_review_round(self):
        self._to_adjudicate()
        runledger.add_finding(self.state, "F1", "DB-LOSS", "P1", "Write can disappear")
        runledger.decide_finding(self.state, "F1", "confirmed")
        runledger.enter(self.state, "implement")
        runledger.enter(self.state, "review")
        runledger.enter(self.state, "adjudicate")
        path = runledger.state_path(self.root, self.state["run_id"])
        runledger.save_state(path, self.state)
        self.assertEqual(runledger.load_state(path)["findings"][0]["origin_review_head"], "head123")
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["findings"][0]["origin_review_head"] = "decoy-head"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(runledger.Undetermined, "origin review head"):
            runledger.load_state(path)

    def test_persisted_confirmation_history_cannot_contradict_ever_confirmed(self):
        self._to_adjudicate()
        runledger.add_finding(self.state, "F1", "DB-LOSS", "P1", "Write can disappear")
        runledger.decide_finding(self.state, "F1", "confirmed")
        runledger.decide_finding(self.state, "F1", "suspected")
        path = runledger.state_path(self.root, self.state["run_id"])
        runledger.save_state(path, self.state)
        self.assertTrue(runledger.load_state(path)["findings"][0]["ever_confirmed"])
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["findings"][0]["ever_confirmed"] = False
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(runledger.Undetermined, "confirmation"):
            runledger.load_state(path)

    def test_transient_confirmation_pair_cannot_bypass_a_severe_suspected_finding(self):
        self._to_adjudicate()
        runledger.add_finding(self.state, "F1", "DB-LOSS", "P1", "Write can disappear")
        runledger.decide_finding(self.state, "F1", "suspected")
        path = runledger.state_path(self.root, self.state["run_id"])
        runledger.save_state(path, self.state)
        self.state["findings"][0].update(
            {"confirmed_round": 1, "confirmed_head": "head123", "ever_confirmed": False}
        )
        with self.assertRaisesRegex(runledger.Undetermined, "confirmation"):
            runledger.resolve_finding(self.state, "F1", "in-memory hybrid evidence")
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["findings"][0].update(
            {"confirmed_round": 1, "confirmed_head": "head123", "ever_confirmed": False}
        )
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(runledger.Undetermined, "transient confirmation"):
            runledger.load_state(path)

    def test_stale_writer_is_refused_instead_of_losing_an_update(self):
        path = runledger.state_path(self.root, self.state["run_id"])
        runledger.save_state(path, self.state)
        writer_a = runledger.load_state(path)
        writer_b = runledger.load_state(path)
        runledger.record_check(writer_a, "a", "ok", "first writer")
        runledger.save_state(path, writer_a)
        runledger.record_check(writer_b, "b", "ok", "stale writer")

        with self.assertRaisesRegex(runledger.Refused, "stale"):
            runledger.save_state(path, writer_b)

    def test_active_writer_lock_is_fail_closed(self):
        path = runledger.state_path(self.root, self.state["run_id"])
        runledger.save_state(path, self.state)
        lock = path.with_name(path.name + ".lock")

        with runledger.exclusive_lock(lock):
            with self.assertRaisesRegex(runledger.Refused, "another writer"):
                runledger.save_state(path, self.state)

    def test_cli_persists_state_and_uses_exit_two_for_unknown_evidence(self):
        runs = self.root / "runs"

        def cli(*args):
            return subprocess.run(
                [sys.executable, str(MODULE_PATH), "--dir", str(runs), "--run", "cli-1", *args],
                text=True,
                capture_output=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(
            cli("init", "--title", "CLI", "--repo", "example/repo", "--base", "base", "--head", "head").returncode,
            0,
        )
        self.assertEqual(cli("pin-contract", "--file", str(self.contract)).returncode, 0)
        self.assertEqual(cli("check", "--name", "database", "--verdict", "undetermined", "--evidence", "not configured").returncode, 2)
        blocked = cli("enter", "ready")
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("database", blocked.stderr)
        shown = cli("show")
        self.assertEqual(shown.returncode, 0)
        self.assertIn("node: premise", shown.stdout)

        active = runledger.state_path(runs, "cli-1")
        overwrite = cli("snapshot", "--out", str(active))
        self.assertEqual(overwrite.returncode, 1)
        self.assertIn("active run state", overwrite.stderr)

    def test_cli_happy_path_reaches_done_and_exports_snapshot(self):
        runs = self.root / "runs"
        snapshot = self.root / "snapshot.json"

        def cli(*args):
            result = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--dir", str(runs), "--run", "happy", *args],
                text=True,
                capture_output=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

        cli("init", "--title", "Happy", "--repo", "example/repo", "--base", "base", "--head", "head")
        cli("pin-contract", "--file", str(self.contract))
        cli("assign-role", "--name", "implementer", "--engine", "codex", "--family", "openai")
        cli("assign-role", "--name", "reviewer", "--engine", "claude", "--family", "anthropic")
        cli("enter", "ready")
        cli("enter", "implement")
        cli("tree", "--head", "reviewed-head")
        cli("enter", "review")
        cli("enter", "adjudicate")
        cli("enter", "verify")
        cli("check", "--name", "effect", "--verdict", "ok", "--evidence", "real entrypoint verified")
        cli("enter", "done")
        cli("snapshot", "--out", str(snapshot))

        payload = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertEqual(payload["structure"]["node"], "done")
        self.assertEqual(payload["content"]["tree"]["head"], "reviewed-head")


if __name__ == "__main__":
    unittest.main()
