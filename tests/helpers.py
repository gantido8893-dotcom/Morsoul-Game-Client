import base64
import uuid

from morsoul_core import integrity

KEY_B64 = base64.b64encode(b"k" * 32).decode()
KEY = base64.b64decode(KEY_B64)
PASSWORD = "correct horse battery"


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def register(client, username: str, password: str = PASSWORD, email: str | None = None):
    body = {"username": username, "password": password}
    if email:
        body["email"] = email
    r = await client.post("/api/v1/auth/register", json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    return data["sessionToken"], data["userID"]


def base_payload(**over) -> dict:
    p = {
        "displayName": "Caelan",
        "reputation": 10,
        "currentCaseID": "case_01",
        "ending": None,
        "focusEnergy": {"value": 3.0, "asOfPlaytime": 100},
        "caseProgress": {"case_01": {"status": "in_progress"}},
        "evidence": {"clue_017": {"caseID": "case_01", "collectedAt": 1000, "via": "scan"}},
        "deductionLinks": {},
        "unlocks": {"tool": ["golem_eye"], "sector": [], "case": []},
        "runicLogs": {},
        "caseResults": {},
        "dialogue": {"npcs": {}, "statementsHeard": []},
        "board": {"nodes": {}},
        "puzzles": {},
        "notes": [],
        "checkpoint": None,
    }
    p.update(over)
    return p


def snapshot(
    profile_id: str, revision: int = 1, playtime: int = 3600, key: bytes = KEY, **payload_over
) -> dict:
    snap = {
        "profileID": profile_id,
        "schemaVersion": 1,
        "contentVersion": 1,
        "appVersion": "0.1.0",
        "revisionID": revision,
        "updatedAt": 1_700_000_000 + revision,
        "playtime": playtime,
        "payload": base_payload(**payload_over),
    }
    return integrity.seal(snap, key)


def new_profile() -> str:
    return str(uuid.uuid4())


async def put(client, token: str, profile_id: str, base: int, snap: dict):
    return await client.put(
        f"/api/v1/saves/{profile_id}", headers=auth(token), json={"baseRevision": base, "snapshot": snap}
    )
