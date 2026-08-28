#!/usr/bin/env python3
"""Durable, stdlib-only run ledger for SUPER guare.

The ledger enforces workflow facts. It does not launch agents, decide technical
claims, or replace the SUPER's adjudication.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path


VERSION = 1
SEVERE = {"P0", "P1"}
VERDICTS = {"ok", "not-ok", "undetermined"}
DECISIONS = {"confirmed", "suspected", "rejected"}
NODES = {"premise", "ready", "hold", "reject", "implement", "review", "adjudicate", "verify", "done", "escalated"}
EDGES = {
    "premise": {"ready", "hold", "reject"},
    "hold": {"premise"},
    "ready": {"implement", "hold", "reject"},
    "implement": {"review", "hold"},
    "review": {"adjudicate", "hold"},
    "adjudicate": {"implement", "ready", "verify", "escalated", "hold"},
    "verify": {"done", "adjudicate", "hold"},
    "reject": set(),
    "done": set(),
    "escalated": set(),
}
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class LedgerError(Exception):
    exit_code = 1


class Refused(LedgerError):
    """A known fact makes the requested transition invalid."""


class Undetermined(LedgerError):
    """A required fact could not be established."""

    exit_code = 2


class UsageError(LedgerError):
    exit_code = 2


def now() -> int:
    return int(time.time())


def csv_ids(raw: str | None) -> list[str]:
    return [item.strip() for item in (raw or "").split(",") if item.strip()]


def state_path(root: str | Path, run_id: str) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise UsageError("run id must use only letters, digits, dot, underscore, or hyphen")
    return Path(root) / run_id / "run.json"


def new_run(
    run_id: str,
    title: str,
    repo: str,
    base: str,
    head: str,
    max_rounds: int = 2,
) -> dict:
    state_path(".", run_id)  # validate only
    if max_rounds < 1:
        raise UsageError("max_rounds must be at least 1")
    stamp = now()
    return {
        "kind": "super-guare.run",
        "version": VERSION,
        "run_id": run_id,
        "title": title,
        "created_at": stamp,
        "updated_at": stamp,
        "node": "premise",
        "path": ["premise"],
        "max_rounds": max_rounds,
        "review_round": 0,
        "review_heads": [],
        "generation": 0,
        "tree": {"repo": repo, "base": base, "head": head},
        "contract": None,
        "requires_implementation": False,
        "requires_review": False,
        "roles": {},
        "checks": {},
        "check_history": [],
        "criteria": [],
        "units": [],
        "findings": [],
    }


@contextmanager
def exclusive_lock(path: Path):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+b")
    except OSError as exc:
        raise Undetermined(f"cannot open run lock: {exc}") from exc
    try:
        if path.stat().st_size == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise Refused("run is being updated by another writer") from exc
        yield
    finally:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        handle.close()


def save_state(path: str | Path, state: dict) -> None:
    validate_state(state)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    expected_generation = state.get("generation", 0)
    lock_path = target.with_name(target.name + ".lock")
    temp = target.with_name(f".{target.name}.{os.getpid()}.{time.time_ns()}.tmp")
    with exclusive_lock(lock_path):
        current_generation = 0
        if target.exists():
            try:
                with target.open(encoding="utf-8") as handle:
                    current_generation = json.load(handle).get("generation", -1)
            except (OSError, json.JSONDecodeError, AttributeError) as exc:
                raise Undetermined(f"cannot compare current run generation: {exc}") from exc
        if current_generation != expected_generation:
            raise Refused(
                f"stale run state: loaded generation {expected_generation}, current generation {current_generation}"
            )
        stamp = now()
        payload = dict(state)
        payload["generation"] = expected_generation + 1
        payload["updated_at"] = stamp
        try:
            with temp.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
        except OSError as exc:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            raise Undetermined(f"cannot persist run state: {exc}") from exc
        state["generation"] = payload["generation"]
        state["updated_at"] = stamp


def load_state(path: str | Path) -> dict:
    target = Path(path)
    try:
        with target.open(encoding="utf-8") as handle:
            state = json.load(handle)
    except FileNotFoundError as exc:
        raise UsageError(f"run not found: {target}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise Undetermined(f"cannot read run state: {exc}") from exc
    if not isinstance(state, dict):
        raise Undetermined("run state must be a JSON object")
    if state.get("kind") != "super-guare.run" or state.get("version") != VERSION:
        raise UsageError("unsupported run state")
    validate_state(state)
    return state


def validate_finding_metadata(finding: dict, review_heads: dict[int, str], review_round: int) -> None:
    """Reject coherent-looking finding fields that contradict durable review history."""
    origin_head = finding.get("origin_review_head")
    confirmation_round = finding.get("confirmation_round")
    resolution_round = finding.get("resolution_round")
    resolution_head = finding.get("resolution_head")
    ever_confirmed = finding.get("ever_confirmed")
    transient_confirmation_round = finding.get("confirmed_round")
    transient_confirmation_head = finding.get("confirmed_head")
    has_new_metadata = any(
        key in finding
        for key in (
            "origin_review_head",
            "confirmation_round",
            "ever_confirmed",
            "resolution_round",
            "resolution_head",
        )
    )

    if origin_head is not None:
        if review_heads.get(finding["round"]) != origin_head:
            raise ValueError("finding origin review head")
    if (transient_confirmation_round is None) != (transient_confirmation_head is None):
        raise ValueError("finding transient confirmation metadata")
    if transient_confirmation_round is not None:
        if ever_confirmed is not True:
            raise ValueError("finding transient confirmation history")
        if review_heads.get(transient_confirmation_round) != transient_confirmation_head:
            raise ValueError("finding transient confirmation review")
        if (
            origin_head is None
            or confirmation_round is None
            or confirmation_round != transient_confirmation_round
        ):
            raise ValueError("finding transient confirmation cannot be reconciled")
    if confirmation_round is not None:
        if ever_confirmed is not True:
            raise ValueError("finding confirmation history")
        if (
            confirmation_round < finding["round"]
            or confirmation_round > review_round
            or confirmation_round not in review_heads
        ):
            raise ValueError("finding confirmation round")
    if (resolution_round is None) != (resolution_head is None):
        raise ValueError("finding resolution metadata")
    if resolution_round is not None:
        if (
            ever_confirmed is not True
            or confirmation_round is None
            or finding["decision"] not in {"confirmed", "suspected"}
            or not finding["resolved"]
        ):
            raise ValueError("finding resolution history")
        if resolution_round <= confirmation_round or review_heads.get(resolution_round) != resolution_head:
            raise ValueError("finding resolution round")
    if finding["severity"] in SEVERE and finding["decision"] == "confirmed" and has_new_metadata:
        if ever_confirmed is not True or confirmation_round is None:
            raise ValueError("finding confirmed metadata")
    if finding["severity"] in SEVERE and ever_confirmed is True and finding["decision"] != "rejected":
        if confirmation_round is None:
            raise ValueError("finding confirmation history")


def validate_state(state: dict) -> None:
    required = {
        "run_id": str,
        "title": str,
        "node": str,
        "path": list,
        "tree": dict,
        "roles": dict,
        "checks": dict,
        "check_history": list,
        "criteria": list,
        "units": list,
        "findings": list,
        "max_rounds": int,
        "review_round": int,
        "generation": int,
        "requires_implementation": bool,
        "requires_review": bool,
    }
    missing = [name for name in required if name not in state]
    if missing:
        raise Undetermined(f"run state is missing required field(s): {', '.join(sorted(missing))}")
    invalid = [name for name, expected in required.items() if not isinstance(state[name], expected)]
    if invalid or state["node"] not in NODES:
        detail = ", ".join(sorted(invalid)) or "node"
        raise Undetermined(f"run state has invalid field(s): {detail}")
    try:
        state_path(".", state["run_id"])
        if state["max_rounds"] < 1 or state["review_round"] < 0 or state["generation"] < 0:
            raise ValueError("negative counter")
        if not state["path"] or any(node not in NODES for node in state["path"]):
            raise ValueError("invalid path")
        for key in ("repo", "base", "head"):
            if key not in state["tree"] or not isinstance(state["tree"][key], str):
                raise ValueError(f"tree.{key}")
        review_heads: dict[int, str] = {}
        if "review_heads" in state:
            if not isinstance(state["review_heads"], list):
                raise ValueError("review heads")
            seen_rounds: set[int] = set()
            for review in state["review_heads"]:
                if not isinstance(review, dict) or not isinstance(review.get("round"), int) or not isinstance(review.get("head"), str):
                    raise ValueError("review head")
                if review["round"] < 1 or review["round"] > state["review_round"] or review["round"] in seen_rounds:
                    raise ValueError("review head round")
                seen_rounds.add(review["round"])
                review_heads[review["round"]] = review["head"]
        contract = state.get("contract")
        if contract is not None:
            for key, expected in (("path", str), ("sha256", str), ("bytes", int)):
                if not isinstance(contract.get(key), expected):
                    raise ValueError(f"contract.{key}")
        for role in state["roles"].values():
            if not isinstance(role, dict) or not isinstance(role.get("engine"), str) or not isinstance(role.get("family"), str):
                raise ValueError("role")
        for name, check in state["checks"].items():
            if not isinstance(name, str) or not isinstance(check, dict) or check.get("verdict") not in VERDICTS:
                raise ValueError("check")
            if not isinstance(check.get("evidence"), str) or not isinstance(check.get("at"), int):
                raise ValueError("check evidence")
        for entry in state["check_history"]:
            if not isinstance(entry, dict) or entry.get("verdict") not in VERDICTS:
                raise ValueError("check history")
            if not all(isinstance(entry.get(key), expected) for key, expected in (("name", str), ("evidence", str), ("at", int))):
                raise ValueError("check history entry")
        for criterion in state["criteria"]:
            if not isinstance(criterion, dict) or criterion.get("status") not in {"required", "deferred"}:
                raise ValueError("criterion")
            if not isinstance(criterion.get("id"), str) or not isinstance(criterion.get("text"), str):
                raise ValueError("criterion fields")
        for unit in state["units"]:
            if not isinstance(unit, dict) or not isinstance(unit.get("id"), str):
                raise ValueError("unit")
            if not isinstance(unit.get("covers"), list) or not isinstance(unit.get("depends_on"), list):
                raise ValueError("unit fields")
            if any(not isinstance(member, str) for member in unit["covers"] + unit["depends_on"]):
                raise ValueError("unit member")
        for finding in state["findings"]:
            if not isinstance(finding, dict) or finding.get("severity") not in {"P0", "P1", "P2", "P3"}:
                raise ValueError("finding")
            if finding.get("decision") not in DECISIONS | {None} or not isinstance(finding.get("resolved"), bool):
                raise ValueError("finding decision")
            for key, expected in (("id", str), ("defect_id", str), ("summary", str), ("round", int)):
                if not isinstance(finding.get(key), expected):
                    raise ValueError(f"finding.{key}")
            for key, expected in (
                ("confirmed_round", int),
                ("confirmation_round", int),
                ("confirmed_head", str),
                ("origin_review_head", str),
                ("resolution_round", int),
                ("resolution_head", str),
            ):
                if key in finding and finding[key] is not None and not isinstance(finding[key], expected):
                    raise ValueError(f"finding.{key}")
            if "ever_confirmed" in finding and not isinstance(finding["ever_confirmed"], bool):
                raise ValueError("finding.ever_confirmed")
            validate_finding_metadata(finding, review_heads, state["review_round"])
    except (KeyError, TypeError, ValueError, UsageError) as exc:
        raise Undetermined(f"run state has invalid nested data: {exc}") from exc


def file_pin(path: str | Path) -> dict:
    source = Path(path).resolve()
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise Undetermined(f"cannot read contract: {exc}") from exc
    return {
        "path": str(source),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }


def pin_contract(state: dict, path: str | Path) -> None:
    require_active(state, "pin contract")
    if state["node"] not in {"premise", "adjudicate"}:
        raise Refused("pin contract only in premise or adjudicate; return to an adjudication boundary first")
    state["contract"] = file_pin(path)
    if state["node"] == "adjudicate":
        state["requires_implementation"] = True
        state["requires_review"] = True


def contract_status(state: dict) -> tuple[str, str | None]:
    pin = state.get("contract")
    if not pin:
        return "unpinned", None
    try:
        current = file_pin(pin["path"])
    except Undetermined as exc:
        return "unreadable", str(exc)
    if current["sha256"] != pin["sha256"]:
        return "changed", f"pinned {pin['sha256'][:12]}, current {current['sha256'][:12]}"
    return "ok", None


def require_current_contract(state: dict) -> None:
    status, detail = contract_status(state)
    if status == "unpinned":
        raise Undetermined("no contract is pinned")
    if status == "unreadable":
        raise Undetermined(detail or "contract is unreadable")
    if status == "changed":
        raise Refused(f"contract changed since adjudication: {detail}")


def update_tree(state: dict, base: str | None = None, head: str | None = None) -> None:
    require_phase(state, "update tree", {"premise", "ready", "implement", "adjudicate"})
    if base is not None:
        state["tree"]["base"] = base
    if head is not None:
        state["tree"]["head"] = head
    if state["node"] == "adjudicate":
        state["requires_review"] = True


def assign_role(state: dict, name: str, engine: str, family: str) -> None:
    require_phase(state, "assign role", {"premise", "ready", "implement", "adjudicate"})
    if not name or not engine or not family:
        raise UsageError("role name, engine, and family are required")
    state["roles"][name] = {"engine": engine, "family": family}
    if state["node"] == "adjudicate":
        state["requires_review"] = True


def record_check(state: dict, name: str, verdict: str, evidence: str) -> None:
    require_active(state, "record check")
    if verdict not in VERDICTS:
        raise UsageError(f"verdict must be one of: {', '.join(sorted(VERDICTS))}")
    if not evidence.strip():
        raise UsageError("check evidence must not be empty")
    if name == "effect" and state["node"] != "verify":
        raise Refused("effect must be checked in the current verify phase")
    entry = {"name": name, "verdict": verdict, "evidence": evidence, "at": now()}
    state["checks"][name] = {key: value for key, value in entry.items() if key != "name"}
    state["check_history"].append(entry)


def blocking_checks(state: dict) -> tuple[list[str], list[str]]:
    failed = [name for name, check in state["checks"].items() if check["verdict"] == "not-ok"]
    unknown = [name for name, check in state["checks"].items() if check["verdict"] == "undetermined"]
    return sorted(failed), sorted(unknown)


def require_checks_clear(state: dict) -> None:
    failed, unknown = blocking_checks(state)
    if failed:
        raise Refused(f"failing check(s): {', '.join(failed)}")
    if unknown:
        raise Undetermined(f"undetermined check(s): {', '.join(unknown)}")


def _find(items: list[dict], item_id: str) -> dict | None:
    return next((item for item in items if item["id"] == item_id), None)


def require_active(state: dict, action: str) -> None:
    if state["node"] in {"reject", "done", "escalated"}:
        raise Refused(f"cannot {action} after terminal node {state['node']}")


def require_phase(state: dict, action: str, allowed: set[str]) -> None:
    require_active(state, action)
    if state["node"] not in allowed:
        raise Refused(f"cannot {action} in {state['node']}; allowed: {', '.join(sorted(allowed))}")


def mark_plan_changed(state: dict) -> None:
    if state["node"] == "adjudicate":
        state["requires_implementation"] = True
        state["requires_review"] = True


def add_criterion(state: dict, criterion_id: str, text: str) -> None:
    require_phase(state, "add criterion", {"premise", "adjudicate"})
    if _find(state["criteria"], criterion_id):
        raise UsageError(f"criterion already exists: {criterion_id}")
    state["criteria"].append({"id": criterion_id, "text": text, "status": "required", "reason": None})
    mark_plan_changed(state)


def defer_criterion(state: dict, criterion_id: str, reason: str) -> None:
    require_phase(state, "defer criterion", {"premise", "adjudicate"})
    criterion = _find(state["criteria"], criterion_id)
    if not criterion:
        raise UsageError(f"unknown criterion: {criterion_id}")
    if not reason.strip():
        raise UsageError("deferring a criterion requires a reason")
    criterion.update({"status": "deferred", "reason": reason})
    mark_plan_changed(state)


def add_unit(state: dict, unit_id: str, covers: list[str], depends_on: list[str]) -> None:
    require_phase(state, "add unit", {"premise", "adjudicate"})
    if _find(state["units"], unit_id):
        raise UsageError(f"unit already exists: {unit_id}")
    known = {criterion["id"] for criterion in state["criteria"]}
    missing = sorted(set(covers) - known)
    if missing:
        raise UsageError(f"unit references unknown criteria: {', '.join(missing)}")
    if unit_id in depends_on:
        raise UsageError("a unit cannot depend on itself")
    state["units"].append({"id": unit_id, "covers": list(dict.fromkeys(covers)), "depends_on": list(dict.fromkeys(depends_on))})
    mark_plan_changed(state)


def require_coverage(state: dict) -> None:
    units = state["units"]
    if not units:
        return  # flat path
    empty = [unit["id"] for unit in units if not unit["covers"]]
    if empty:
        raise Refused(f"unit(s) cover no criterion: {', '.join(empty)}")
    known_units = {unit["id"] for unit in units}
    unknown_deps = sorted({dep for unit in units for dep in unit["depends_on"] if dep not in known_units})
    if unknown_deps:
        raise Refused(f"unknown unit dependencies: {', '.join(unknown_deps)}")
    dependencies = {unit["id"]: unit["depends_on"] for unit in units}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(unit_id: str) -> None:
        if unit_id in visiting:
            raise Refused(f"unit dependency cycle includes: {unit_id}")
        if unit_id in visited:
            return
        visiting.add(unit_id)
        for dependency in dependencies[unit_id]:
            visit(dependency)
        visiting.remove(unit_id)
        visited.add(unit_id)

    for unit_id in sorted(dependencies):
        visit(unit_id)
    covered = {criterion for unit in units for criterion in unit["covers"]}
    missing = [criterion["id"] for criterion in state["criteria"] if criterion["status"] == "required" and criterion["id"] not in covered]
    if missing:
        raise Refused(f"required criteria covered by no unit: {', '.join(missing)}")


def add_finding(state: dict, finding_id: str, defect_id: str, severity: str, summary: str) -> None:
    require_phase(state, "add finding", {"review", "adjudicate"})
    if _find(state["findings"], finding_id):
        raise UsageError(f"finding already exists: {finding_id}")
    severity = severity.upper()
    if severity not in {"P0", "P1", "P2", "P3"}:
        raise UsageError("severity must be P0, P1, P2, or P3")
    round_number = state["review_round"]
    if round_number < 1:
        raise Undetermined("no review round has started")
    try:
        origin_review_head = reviewed_head(state, round_number)
    except Undetermined:
        origin_review_head = None
    state["findings"].append(
        {
            "id": finding_id,
            "defect_id": defect_id or finding_id,
            "severity": severity,
            "summary": summary,
            "round": round_number,
            "decision": None,
            "resolved": False,
            "resolution_evidence": None,
            "origin_review_head": origin_review_head,
            "confirmation_round": None,
            "ever_confirmed": False,
            "resolution_round": None,
            "resolution_head": None,
        }
    )


def reviewed_head(state: dict, round_number: int) -> str:
    matches = [item for item in state.get("review_heads", []) if item.get("round") == round_number]
    if len(matches) != 1:
        raise Undetermined(f"review round {round_number} has no recorded reviewed head")
    return matches[0]["head"]


def decide_finding(state: dict, finding_id: str, decision: str) -> None:
    require_phase(state, "decide finding", {"adjudicate"})
    finding = _find(state["findings"], finding_id)
    if not finding:
        raise UsageError(f"unknown finding: {finding_id}")
    if decision not in DECISIONS:
        raise UsageError(f"decision must be one of: {', '.join(sorted(DECISIONS))}")
    prior_decision = finding["decision"]
    if finding["severity"] in SEVERE and prior_decision == "confirmed":
        finding["ever_confirmed"] = True
    decision_changed = prior_decision != decision
    if decision_changed:
        finding["resolved"] = False
        finding["resolution_evidence"] = None
        finding["resolution_round"] = None
        finding["resolution_head"] = None
    finding["decision"] = decision
    if decision == "rejected":
        finding["resolved"] = True
        finding["resolution_evidence"] = "rejected by adjudicator"
    elif decision == "confirmed" and finding["severity"] in SEVERE:
        finding["ever_confirmed"] = True
        if decision_changed:
            finding["confirmation_round"] = state["review_round"]


def requires_confirmed_severe_cycle(finding: dict) -> bool:
    return (
        finding["severity"] in SEVERE
        and finding["decision"] != "rejected"
        and (
            finding.get("ever_confirmed", False)
            or finding["decision"] == "confirmed"
            or "ever_confirmed" not in finding
            or finding.get("confirmed_round") is not None
            or finding.get("confirmed_head") is not None
        )
    )


def require_current_severe_cycle(state: dict, finding: dict) -> str:
    origin_head = finding.get("origin_review_head")
    confirmation_round = finding.get("confirmation_round")
    if origin_head is None:
        raise Undetermined("confirmed severe finding has no recorded origin reviewed head")
    if confirmation_round is None:
        raise Undetermined("confirmed severe finding has no recorded confirmation round")
    if state["review_round"] <= confirmation_round:
        raise Refused("confirmed P0/P1 finding requires a new implementation and review before resolution")
    current_reviewed_head = reviewed_head(state, state["review_round"])
    if state.get("requires_review") or state["tree"]["head"] != current_reviewed_head:
        raise Refused("the current tree has not passed a new review")
    if current_reviewed_head == origin_head:
        raise Refused("confirmed P0/P1 finding requires review of a corrected head before resolution")
    return current_reviewed_head


def severe_finding_is_closed(state: dict, finding: dict) -> bool:
    if finding["decision"] == "rejected":
        return True
    if not finding["resolved"]:
        return False
    if not requires_confirmed_severe_cycle(finding):
        return True
    origin_head = finding.get("origin_review_head")
    confirmation_round = finding.get("confirmation_round")
    resolution_round = finding.get("resolution_round")
    resolution_head = finding.get("resolution_head")
    if None in (origin_head, confirmation_round, resolution_round, resolution_head):
        return False
    if resolution_round <= confirmation_round or resolution_head == origin_head:
        return False
    if state.get("requires_review") or state["tree"]["head"] != resolution_head:
        return False
    try:
        return (
            reviewed_head(state, resolution_round) == resolution_head
            and reviewed_head(state, state["review_round"]) == resolution_head
        )
    except Undetermined:
        return False


def resolve_finding(state: dict, finding_id: str, evidence: str) -> None:
    require_phase(state, "resolve finding", {"adjudicate"})
    finding = _find(state["findings"], finding_id)
    if not finding:
        raise UsageError(f"unknown finding: {finding_id}")
    if finding["decision"] not in {"confirmed", "suspected"}:
        raise Refused("only a confirmed or suspected finding can be resolved")
    if not evidence.strip():
        raise UsageError("resolution evidence must not be empty")
    if requires_confirmed_severe_cycle(finding):
        current_reviewed_head = require_current_severe_cycle(state, finding)
        finding["resolution_round"] = state["review_round"]
        finding["resolution_head"] = current_reviewed_head
    finding["resolved"] = True
    finding["resolution_evidence"] = evidence


def open_severe(state: dict) -> list[dict]:
    return [
        finding
        for finding in state["findings"]
        if finding["severity"] in SEVERE
        and finding["decision"] != "rejected"
        and not severe_finding_is_closed(state, finding)
    ]


def require_no_open_severe(state: dict) -> None:
    severe = open_severe(state)
    if severe:
        raise Refused(f"open P0/P1 finding(s): {', '.join(item['id'] for item in severe)}")


def require_convergence(state: dict) -> None:
    severe = [finding for finding in state["findings"] if finding["severity"] in SEVERE and finding["decision"] != "rejected"]
    rounds = sorted({finding["round"] for finding in severe})
    by_defect: dict[str, set[int]] = {}
    for finding in severe:
        by_defect.setdefault(finding["defect_id"], set()).add(finding["round"])
    stuck = sorted(defect for defect, seen_rounds in by_defect.items() if len(seen_rounds) >= state["max_rounds"])
    if stuck:
        raise Refused(f"defect(s) survived the correction budget: {', '.join(stuck)}")
    if len(rounds) >= state["max_rounds"]:
        raise Refused("adjudication correction budget exhausted; respec or escalate")


def require_distinct_review_families(state: dict) -> None:
    implementer = state["roles"].get("implementer")
    reviewer = state["roles"].get("reviewer")
    if not implementer or not reviewer:
        raise Undetermined("implementer and reviewer roles must be assigned")
    if not implementer.get("family") or not reviewer.get("family"):
        raise Undetermined("implementer and reviewer families must be known")
    if implementer["family"] == reviewer["family"]:
        raise Refused("implementer and reviewer must use different engine families")


def require_tree_pin(state: dict) -> None:
    missing = [name for name in ("repo", "base", "head") if not state["tree"].get(name)]
    if missing:
        raise Undetermined(f"tree pin is incomplete: {', '.join(missing)}")


def guard_transition(state: dict, destination: str) -> None:
    current = state["node"]
    if destination not in NODES:
        raise UsageError(f"unknown node: {destination}")
    if destination not in EDGES[current]:
        raise Refused(f"illegal transition: {current} -> {destination}")

    if destination == "ready":
        require_current_contract(state)
        require_checks_clear(state)
    elif destination == "implement":
        require_current_contract(state)
        require_checks_clear(state)
        require_coverage(state)
        if state["findings"]:
            require_convergence(state)
    elif destination == "review":
        require_current_contract(state)
        require_checks_clear(state)
        require_tree_pin(state)
        require_distinct_review_families(state)
    elif destination == "verify":
        require_current_contract(state)
        require_checks_clear(state)
        require_no_open_severe(state)
        if state.get("requires_implementation"):
            raise Refused("the changed contract or plan has not passed a new implementation")
        if state.get("requires_review"):
            raise Refused("the current contract, tree, plan, or role assignment has not passed a new review")
    elif destination == "done":
        require_current_contract(state)
        require_checks_clear(state)
        require_no_open_severe(state)
        effect = state["checks"].get("effect")
        if not effect:
            raise Refused("effect check is required before done")
        if effect["verdict"] == "undetermined":
            raise Undetermined("effect check is undetermined")
        if effect["verdict"] != "ok":
            raise Refused("effect check is not ok")


def enter(state: dict, destination: str) -> None:
    current = state["node"]
    guard_transition(state, destination)
    if destination == "verify":
        state["checks"].pop("effect", None)
    if current == "verify" and destination in {"adjudicate", "hold"}:
        state["checks"].pop("effect", None)
    if destination == "review":
        state["review_round"] += 1
        state.setdefault("review_heads", []).append({"round": state["review_round"], "head": state["tree"]["head"]})
        state["requires_implementation"] = False
        state["requires_review"] = False
    state["node"] = destination
    state["path"].append(destination)


def build_snapshot(state: dict) -> dict:
    contract = state.get("contract") or {}
    status, detail = contract_status(state)
    return {
        "kind": "super-guare.run.snapshot",
        "version": VERSION,
        "at": now(),
        "run_id": state["run_id"],
        "title": state["title"],
        "structure": {
            "node": state["node"],
            "path": list(state["path"]),
            "legal_next": sorted(EDGES[state["node"]]),
            "max_rounds": state["max_rounds"],
            "review_round": state["review_round"],
            "generation": state["generation"],
            "unit_count": len(state["units"]),
        },
        "content": {
            "tree": dict(state["tree"]),
            "contract_path": contract.get("path"),
            "contract_sha256": contract.get("sha256"),
            "contract_status": status,
            "contract_detail": detail,
            "roles": dict(state["roles"]),
            "criteria": [dict(item) for item in state["criteria"]],
            "units": [dict(item) for item in state["units"]],
            "review_heads": [dict(item) for item in state.get("review_heads", [])],
            "findings": [dict(item) for item in state["findings"]],
            "checks": dict(state["checks"]),
            "check_history": [dict(item) for item in state["check_history"]],
            "open_severe": [
                {"id": item["id"], "defect_id": item["defect_id"], "severity": item["severity"]}
                for item in open_severe(state)
            ],
            "rounds": sorted({item["round"] for item in state["findings"]}),
        },
    }


def print_show(state: dict) -> None:
    status, detail = contract_status(state)
    print(f"run {state['run_id']}: {state['title']}")
    print(f"node: {state['node']}; next: {', '.join(sorted(EDGES[state['node']])) or '(terminal)'}")
    print(f"tree: {state['tree'].get('repo') or '?'} {state['tree'].get('base') or '?'}..{state['tree'].get('head') or '?'}")
    print(f"contract: {status}" + (f" ({detail})" if detail else ""))
    print(f"criteria: {len(state['criteria'])}; units: {len(state['units'])}; open severe: {len(open_severe(state))}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default=".super-guare/runs", help="run storage root")
    parser.add_argument("--run", required=True, help="run identifier")
    sub = parser.add_subparsers(dest="command", required=True)

    cmd = sub.add_parser("init")
    cmd.add_argument("--title", required=True)
    cmd.add_argument("--repo", required=True)
    cmd.add_argument("--base", required=True)
    cmd.add_argument("--head", required=True)
    cmd.add_argument("--max-rounds", type=int, default=2)

    cmd = sub.add_parser("pin-contract")
    cmd.add_argument("--file", required=True)

    cmd = sub.add_parser("tree")
    cmd.add_argument("--base")
    cmd.add_argument("--head")

    cmd = sub.add_parser("assign-role")
    cmd.add_argument("--name", required=True)
    cmd.add_argument("--engine", required=True)
    cmd.add_argument("--family", required=True)

    cmd = sub.add_parser("check")
    cmd.add_argument("--name", required=True)
    cmd.add_argument("--verdict", choices=sorted(VERDICTS), required=True)
    cmd.add_argument("--evidence", required=True)

    cmd = sub.add_parser("add-criterion")
    cmd.add_argument("--id", required=True)
    cmd.add_argument("--text", required=True)

    cmd = sub.add_parser("defer-criterion")
    cmd.add_argument("--id", required=True)
    cmd.add_argument("--reason", required=True)

    cmd = sub.add_parser("add-unit")
    cmd.add_argument("--id", required=True)
    cmd.add_argument("--covers", default="")
    cmd.add_argument("--depends-on", default="")

    cmd = sub.add_parser("add-finding")
    cmd.add_argument("--id", required=True)
    cmd.add_argument("--defect-id")
    cmd.add_argument("--severity", choices=["P0", "P1", "P2", "P3"], required=True)
    cmd.add_argument("--summary", required=True)

    cmd = sub.add_parser("decide-finding")
    cmd.add_argument("--id", required=True)
    cmd.add_argument("--decision", choices=sorted(DECISIONS), required=True)

    cmd = sub.add_parser("resolve-finding")
    cmd.add_argument("--id", required=True)
    cmd.add_argument("--evidence", required=True)

    cmd = sub.add_parser("enter")
    cmd.add_argument("node", choices=sorted(NODES))

    sub.add_parser("show")

    cmd = sub.add_parser("snapshot")
    cmd.add_argument("--out")
    cmd.add_argument("--json", action="store_true")
    return parser


def run_command(args: argparse.Namespace) -> int:
    path = state_path(args.dir, args.run)
    if args.command == "init":
        if path.exists():
            raise Refused(f"run already exists: {args.run}")
        state = new_run(args.run, args.title, args.repo, args.base, args.head, args.max_rounds)
        save_state(path, state)
        print(path)
        return 0

    state = load_state(path)
    mutates = True
    result_code = 0
    if args.command == "pin-contract":
        pin_contract(state, args.file)
    elif args.command == "tree":
        update_tree(state, args.base, args.head)
    elif args.command == "assign-role":
        assign_role(state, args.name, args.engine, args.family)
    elif args.command == "check":
        record_check(state, args.name, args.verdict, args.evidence)
        if args.verdict == "undetermined":
            result_code = 2
    elif args.command == "add-criterion":
        add_criterion(state, args.id, args.text)
    elif args.command == "defer-criterion":
        defer_criterion(state, args.id, args.reason)
    elif args.command == "add-unit":
        add_unit(state, args.id, csv_ids(args.covers), csv_ids(args.depends_on))
    elif args.command == "add-finding":
        add_finding(state, args.id, args.defect_id or args.id, args.severity, args.summary)
    elif args.command == "decide-finding":
        decide_finding(state, args.id, args.decision)
    elif args.command == "resolve-finding":
        resolve_finding(state, args.id, args.evidence)
    elif args.command == "enter":
        enter(state, args.node)
    elif args.command == "show":
        mutates = False
        print_show(state)
    elif args.command == "snapshot":
        mutates = False
        snap = build_snapshot(state)
        payload = json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.out:
            out = Path(args.out)
            if out.resolve() == path.resolve():
                raise Refused("snapshot output cannot overwrite the active run state")
            out.parent.mkdir(parents=True, exist_ok=True)
            temp = out.with_name(out.name + ".tmp")
            temp.write_text(payload, encoding="utf-8", newline="\n")
            os.replace(temp, out)
        if args.json or not args.out:
            print(payload, end="")
    else:  # pragma: no cover - argparse prevents this
        raise UsageError(f"unsupported command: {args.command}")

    if mutates:
        save_state(path, state)
    return result_code


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_command(args)
    except LedgerError as exc:
        print(f"{exc.__class__.__name__.upper()}: {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
