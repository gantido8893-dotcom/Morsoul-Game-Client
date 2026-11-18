import json

import pytest


@pytest.fixture
def content_dir(tmp_path):
    d = tmp_path / "content"
    d.mkdir()
    (d / "cases.json").write_text(
        json.dumps(
            [
                {"caseID": "case_01", "order": 1},
                {"caseID": "case_02", "order": 2},
                {"caseID": "case_03", "order": 3},
            ]
        )
    )
    (d / "clues.json").write_text(
        json.dumps(
            [
                {"clueID": "clue_017", "caseID": "case_01"},
                {"clueID": "clue_021", "caseID": "case_01"},
                {"clueID": "clue_030", "caseID": "case_01"},
            ]
        )
    )
    (d / "abilities.json").write_text(
        json.dumps(
            [
                {"toolID": "golem_eye", "unlockedBy": {"type": "start"}},
                {"toolID": "aether_sight", "unlockedBy": {"type": "case_completed", "value": "case_03"}},
            ]
        )
    )
    (d / "sectors.json").write_text(json.dumps([{"sectorID": "sector_docks"}]))
    return d
