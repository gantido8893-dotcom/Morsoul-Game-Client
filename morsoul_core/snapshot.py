"""The snapshot: a JSON copy of one profile's progress, exchanged between the encrypted local
database, the launcher and the cloud (game backend spec, section 8). It never contains content text.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from morsoul_core.limits import (
    MAX_CASES,
    MAX_EVIDENCE,
    MAX_NOTE_CONTENT,
    MAX_NOTE_TITLE,
    MAX_NOTES,
    MAX_PINS,
)

ContentID = Annotated[str, StringConstraints(pattern=r"^[0-9a-zA-Z_-]{1,64}$")]
Hex64 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
ProfileID = Annotated[str, StringConstraints(pattern=r"^[0-9a-zA-Z_-]{1,64}$")]
Short = Annotated[str, StringConstraints(max_length=64)]
UnixSeconds = Annotated[int, Field(ge=0)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FocusEnergy(Strict):
    value: float = Field(ge=0, le=1000, allow_inf_nan=False)
    asOfPlaytime: UnixSeconds


class CaseProgress(Strict):
    status: Literal["locked", "available", "in_progress", "completed", "unstarted", "failed"]
    progressVersion: int = Field(1, ge=1)
    objectiveID: ContentID | None = None
    warrantGranted: bool = False
    failedAttempts: int = Field(0, ge=0)
    hintTier: int = Field(0, ge=0, le=4)
    deductionSolved: bool = False
    interrogationResult: Literal["success", "flawed"] | None = None
    completedAt: UnixSeconds | None = None
    updatedAt: UnixSeconds | None = None


class EvidenceItem(Strict):
    caseID: ContentID
    collectedAt: UnixSeconds
    via: Literal["scan", "dialogue", "hint", "puzzle", "reward", "examine", "search"]


class Unlocks(Strict):
    tool: list[ContentID] = Field(default_factory=list, max_length=100)
    sector: list[ContentID] = Field(default_factory=list, max_length=100)
    case: list[ContentID] = Field(default_factory=list, max_length=100)


class RunicLog(Strict):
    foundAt: UnixSeconds | None = None
    decryptedAt: UnixSeconds | None = None


class CaseResult(Strict):
    conclusionID: str = Field(default="", max_length=64)
    correct: bool
    flawed: bool
    strikes: int = Field(0, ge=0, le=10)
    attempts: int = Field(1, ge=1)
    completedAt: UnixSeconds


class NpcState(Strict):
    stage: int = Field(0, ge=0)
    variant: Short = "default"
    flags: list[Short] = Field(default_factory=list, max_length=50)


class Dialogue(Strict):
    npcs: dict[ContentID, NpcState] = Field(default_factory=dict, max_length=200)
    statementsHeard: list[ContentID] = Field(default_factory=list, max_length=1000)


class BoardNode(Strict):
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)


class Board(Strict):
    nodes: dict[ContentID, BoardNode] = Field(default_factory=dict, max_length=MAX_PINS)


class Puzzle(Strict):
    solved: bool
    attempts: int = Field(0, ge=0)


class Note(Strict):
    entryID: Short
    title: str = Field(max_length=MAX_NOTE_TITLE)
    content: str = Field(max_length=MAX_NOTE_CONTENT)
    linkedClueID: ContentID | None = None


class Payload(Strict):
    displayName: Annotated[str, StringConstraints(pattern=r"^[\w \-]{1,20}$")]
    reputation: int = Field(0, ge=0)
    currentCaseID: ContentID | None
    ending: Literal["bad", "normal", "true"] | None
    focusEnergy: FocusEnergy
    caseProgress: dict[ContentID, CaseProgress] = Field(max_length=MAX_CASES)
    evidence: dict[ContentID, EvidenceItem] = Field(max_length=MAX_EVIDENCE)
    deductionLinks: dict[ContentID, list[tuple[ContentID, ContentID]]]
    unlocks: Unlocks
    runicLogs: dict[Literal["1", "2", "3", "4"], RunicLog]
    caseResults: dict[ContentID, CaseResult]
    dialogue: Dialogue
    board: Board
    puzzles: dict[ContentID, Puzzle] = Field(max_length=500)
    notes: list[Note] = Field(max_length=MAX_NOTES)
    checkpoint: dict[str, Any] | None = None


class Snapshot(Strict):
    profileID: ProfileID
    schemaVersion: int = Field(ge=1)
    contentVersion: int = Field(ge=1)
    appVersion: Annotated[str, StringConstraints(max_length=32)] | None = None
    revisionID: int = Field(ge=1)
    updatedAt: UnixSeconds
    playtime: UnixSeconds
    stateHash: Hex64
    signature: Hex64
    payload: Payload
