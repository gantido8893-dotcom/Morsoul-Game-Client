import copy

from morsoul_core import integrity
from morsoul_core.content import Content
from morsoul_core.manifest import generate_keypair, sign_manifest, verify_manifest
from morsoul_core.snapshot import Snapshot
from morsoul_core.validation import check_keys, plausibility, validate_snapshot
from tests.helpers import KEY, new_profile, snapshot


def test_canonical_is_stable_and_sorted():
    assert integrity.canonical({"b": 1, "a": [2, 1]}) == b'{"a":[2,1],"b":1}'
    assert integrity.canonical({"a": 1, "b": 2}) == integrity.canonical({"b": 2, "a": 1})


def test_seal_verify_roundtrip_and_tamper_detection():
    snap = snapshot(new_profile())
    assert integrity.verify(snap, KEY) == []
    bad = copy.deepcopy(snap)
    bad["payload"]["reputation"] = 9999
    assert integrity.verify(bad, KEY)  # hash no longer matches
    bad2 = copy.deepcopy(snap)
    bad2["playtime"] += 1
    assert integrity.verify(bad2, KEY)  # envelope change breaks the signature
    assert integrity.verify(snap, b"x" * 32)  # wrong key


def test_nan_is_rejected():
    snap = snapshot(new_profile())
    snap["payload"]["checkpoint"] = {"x": float("nan")}
    try:
        integrity.verify(snap, KEY)
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_check_keys_blocks_operator_and_dotted_keys_and_depth():
    assert check_keys({"a": {"b": 1}}) == []
    assert check_keys({"$where": 1})
    assert check_keys({"a.b": 1})
    deep: dict = {}
    cur = deep
    for _ in range(12):
        cur["n"] = {}
        cur = cur["n"]
    assert check_keys(deep)


def _model(**over):
    return Snapshot.model_validate(snapshot(new_profile(), **over))


def test_validate_snapshot_accepts_a_clean_save():
    assert validate_snapshot(_model(), Content.empty()) == []


def test_ending_rules():
    logs3 = {str(i): {"foundAt": 1} for i in (1, 2, 3)}
    logs4 = {str(i): {"foundAt": 1} for i in (1, 2, 3, 4)}
    assert [i.code for i in validate_snapshot(_model(ending="true", runicLogs=logs3), Content.empty())] == [
        "ENDING_MISMATCH"
    ]
    assert [i.code for i in validate_snapshot(_model(ending="normal", runicLogs=logs4), Content.empty())] == [
        "ENDING_MISMATCH"
    ]
    assert validate_snapshot(_model(ending="true", runicLogs=logs4), Content.empty()) == []
    assert validate_snapshot(_model(ending="normal", runicLogs=logs3), Content.empty()) == []


def test_links_board_notes_must_use_found_clues():
    codes = {
        i.code
        for i in validate_snapshot(
            _model(
                deductionLinks={"case_01": [["clue_017", "clue_999"], ["clue_017", "clue_017"]]},
                board={"nodes": {"clue_999": {"x": 0.1, "y": 0.2}}},
                notes=[{"entryID": "n1", "title": "t", "content": "c", "linkedClueID": "clue_999"}],
            ),
            Content.empty(),
        )
    }
    assert codes == {"LINK_INVALID", "BOARD_INVALID", "NOTE_INVALID"}


def test_results_only_for_completed_cases():
    res = {"case_01": {"conclusionID": "concl_a", "correct": True, "flawed": False, "completedAt": 5}}
    assert [i.code for i in validate_snapshot(_model(caseResults=res), Content.empty())] == [
        "RESULT_MISMATCH"
    ]


def test_focus_time_cannot_exceed_playtime():
    codes = [
        i.code
        for i in validate_snapshot(
            _model(focusEnergy={"value": 1.0, "asOfPlaytime": 999999}), Content.empty()
        )
    ]
    assert codes == ["FOCUS_AFTER_PLAYTIME"]


def test_content_rules(content_dir):
    content = Content.load(content_dir)
    assert content.loaded
    bad = _model(evidence={"clue_999": {"caseID": "case_01", "collectedAt": 1, "via": "scan"}})
    assert "UNKNOWN_ID" in {i.code for i in validate_snapshot(bad, content)}
    wrong_case = _model(evidence={"clue_017": {"caseID": "case_02", "collectedAt": 1, "via": "scan"}})
    assert "UNKNOWN_ID" in {i.code for i in validate_snapshot(wrong_case, content)}
    unearned = _model(unlocks={"tool": ["golem_eye", "aether_sight"], "sector": [], "case": []})
    assert [i.code for i in validate_snapshot(unearned, content)] == ["UNLOCK_NOT_EARNED"]
    earned = _model(
        unlocks={"tool": ["golem_eye", "aether_sight"], "sector": [], "case": []},
        caseProgress={"case_01": {"status": "in_progress"}, "case_03": {"status": "completed"}},
    )
    assert validate_snapshot(earned, content) == []


def test_newer_schema_is_refused():
    snap = snapshot(new_profile())
    snap["schemaVersion"] = 2
    snap = integrity.seal(snap, KEY)
    assert [i.code for i in validate_snapshot(Snapshot.model_validate(snap), Content.empty())] == [
        "SAVE_FROM_NEWER_VERSION"
    ]


def test_plausibility_flags_impossible_progress():
    progress = {f"case_0{i}": {"status": "completed"} for i in range(1, 4)}
    assert plausibility(_model(caseProgress=progress, playtime=60), 300, 5)
    assert not plausibility(_model(caseProgress=progress, playtime=100_000), 300, 5)


def test_manifest_sign_and_verify():
    pem, pub = generate_keypair()
    manifest = {"appVersion": "1.0.0", "contentVersion": 1, "publishedAt": 1, "files": []}
    sig = sign_manifest(manifest, pem)
    assert verify_manifest(manifest, sig, pub)
    assert not verify_manifest({**manifest, "appVersion": "9.9.9"}, sig, pub)
    _, other_pub = generate_keypair()
    assert not verify_manifest(manifest, sig, other_pub)
