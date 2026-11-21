"""Rules the server applies to an uploaded snapshot (game backend spec, section 8).

Not enforced here on purpose: "progress never goes backwards". After a sync conflict a player may
deliberately keep an older local save, and the server keeps history so nothing is lost.
"""

import re
from dataclasses import asdict, dataclass
from typing import Any

from morsoul_core.content import Content
from morsoul_core.limits import KEY_PATTERN, MAX_DEPTH, MAX_LINKS_PER_CASE, MAX_PINS, SUPPORTED_SCHEMA_VERSION
from morsoul_core.snapshot import Snapshot

_KEY = re.compile(KEY_PATTERN)


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def check_keys(raw: Any, path: str = "", depth: int = 0) -> list[Issue]:
    """Every dict key must be a plain identifier and nesting must stay shallow (MongoDB safety)."""
    issues: list[Issue] = []
    if depth > MAX_DEPTH:
        return [Issue("TOO_DEEP", path, "The save is nested too deeply")]
    if isinstance(raw, dict):
        for k, v in raw.items():
            if not isinstance(k, str) or not _KEY.match(k):
                issues.append(Issue("INVALID_KEY", path, "A key contains characters that are not allowed"))
                if len(issues) >= 5:
                    return issues
                continue
            issues += check_keys(v, f"{path}.{k}" if path else k, depth + 1)
            if len(issues) >= 5:
                return issues
    elif isinstance(raw, list):
        for i, v in enumerate(raw):
            issues += check_keys(v, f"{path}[{i}]", depth + 1)
            if len(issues) >= 5:
                return issues
    return issues


def validate_snapshot(snap: Snapshot, content: Content) -> list[Issue]:
    issues: list[Issue] = []

    def add(code: str, path: str, message: str) -> None:
        issues.append(Issue(code, path, message))

    if snap.schemaVersion > SUPPORTED_SCHEMA_VERSION:
        add("SAVE_FROM_NEWER_VERSION", "schemaVersion", "This save comes from a newer version of the game")
        return issues

    p = snap.payload
    evidence = set(p.evidence)

    # --- known IDs (only when the game files are available) ---
    if content.cases:
        for case_id in p.caseProgress:
            if case_id not in content.cases:
                add("UNKNOWN_ID", f"payload.caseProgress.{case_id}", "Unknown case")
        for case_id in p.caseResults:
            if case_id not in content.cases:
                add("UNKNOWN_ID", f"payload.caseResults.{case_id}", "Unknown case")
        for case_id in p.deductionLinks:
            if case_id not in content.cases:
                add("UNKNOWN_ID", f"payload.deductionLinks.{case_id}", "Unknown case")
        for case_id in p.unlocks.case:
            if case_id not in content.cases:
                add("UNKNOWN_ID", "payload.unlocks.case", f"Unknown case {case_id}")
    if content.clues:
        for clue_id, item in p.evidence.items():
            clue = content.clues.get(clue_id)
            if clue is None:
                add("UNKNOWN_ID", f"payload.evidence.{clue_id}", "Unknown clue")
            elif clue.get("caseID") != item.caseID:
                add("UNKNOWN_ID", f"payload.evidence.{clue_id}", "Clue belongs to a different case")
    if content.tools:
        for tool in p.unlocks.tool:
            if tool not in content.tools:
                add("UNKNOWN_ID", "payload.unlocks.tool", f"Unknown tool {tool}")
    if content.sectors:
        for sector in p.unlocks.sector:
            if sector not in content.sectors:
                add("UNKNOWN_ID", "payload.unlocks.sector", f"Unknown sector {sector}")

    # --- the current case must exist in the progress table ---
    if p.currentCaseID and p.currentCaseID not in p.caseProgress and content.cases:
        add("UNKNOWN_ID", "payload.currentCaseID", "The current case has no progress entry")

    # --- unlocks must be earned (tools that unlock when a case is completed) ---
    for tool in p.unlocks.tool:
        rule = (content.tools.get(tool) or {}).get("unlockedBy") or {}
        if rule.get("type") == "case_completed":
            needed = rule.get("value")
            progress = p.caseProgress.get(needed) if isinstance(needed, str) else None
            if progress is None or progress.status != "completed":
                add(
                    "UNLOCK_NOT_EARNED",
                    "payload.unlocks.tool",
                    f"{tool} is unlocked but its case is not completed",
                )

    # --- deduction links and board only use clues that were found ---
    for case_id, links in p.deductionLinks.items():
        if len(links) > MAX_LINKS_PER_CASE:
            add("LINK_INVALID", f"payload.deductionLinks.{case_id}", "Too many links")
        seen: set[frozenset[str]] = set()
        for a, b in links:
            if a == b:
                add("LINK_INVALID", f"payload.deductionLinks.{case_id}", "A clue cannot link to itself")
            elif a not in evidence or b not in evidence:
                add(
                    "LINK_INVALID",
                    f"payload.deductionLinks.{case_id}",
                    "A link uses a clue that was not found",
                )
            key = frozenset((a, b))
            if key in seen:
                add("LINK_INVALID", f"payload.deductionLinks.{case_id}", "Duplicate link")
            seen.add(key)
    if len(p.board.nodes) > MAX_PINS:
        add("BOARD_INVALID", "payload.board.nodes", "Too many pinned clues")
    for clue_id in p.board.nodes:
        if clue_id not in evidence:
            add("BOARD_INVALID", f"payload.board.nodes.{clue_id}", "A pinned clue was not found")

    # --- notes may only point at found clues ---
    for i, note in enumerate(p.notes):
        if note.linkedClueID and note.linkedClueID not in evidence:
            add("NOTE_INVALID", f"payload.notes[{i}]", "A note links to a clue that was not found")

    # --- results only exist for completed cases ---
    for case_id in p.caseResults:
        progress = p.caseProgress.get(case_id)
        if progress is None or progress.status != "completed":
            add(
                "RESULT_MISMATCH",
                f"payload.caseResults.{case_id}",
                "A result exists for a case that is not completed",
            )

    # --- ending rule: True needs all four Runic Logs, Normal means fewer than four ---
    logs = len(p.runicLogs)
    if p.ending == "true" and logs < 4:
        add("ENDING_MISMATCH", "payload.ending", "The True Ending needs all four Runic Logs")
    if p.ending == "normal" and logs >= 4:
        add("ENDING_MISMATCH", "payload.ending", "With all four Runic Logs the ending should be True")

    # --- focus timestamp cannot be in the future of the playtime clock ---
    if p.focusEnergy.asOfPlaytime > snap.playtime:
        add("FOCUS_AFTER_PLAYTIME", "payload.focusEnergy", "Focus time is later than the total playtime")

    return issues


def plausibility(snap: Snapshot, min_seconds_per_case: int, min_seconds_per_clue: int) -> list[str]:
    """Soft checks. A save that fails these is stored and flagged for an administrator, never rejected."""
    reasons: list[str] = []
    p = snap.payload
    done = sum(1 for c in p.caseProgress.values() if c.status == "completed")
    if snap.playtime < done * min_seconds_per_case:
        reasons.append(f"{done} completed cases in only {snap.playtime}s of playtime")
    if snap.playtime < len(p.evidence) * min_seconds_per_clue:
        reasons.append(f"{len(p.evidence)} clues in only {snap.playtime}s of playtime")
    return reasons
