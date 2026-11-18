"""Limits shared by the snapshot model and the validation rules (game backend spec, section 6)."""

SUPPORTED_SCHEMA_VERSION = 1

MAX_NOTES = 200
MAX_NOTE_TITLE = 100
MAX_NOTE_CONTENT = 5000
MAX_PINS = 100
MAX_LINKS_PER_CASE = 300
MAX_EVIDENCE = 2000
MAX_CASES = 100

# Keys inside a snapshot must be plain identifiers. This blocks "$operator" and "a.b" keys, which
# MongoDB treats specially, and caps how deep a document can nest.
KEY_PATTERN = r"^[A-Za-z0-9_\-]{1,64}$"
MAX_DEPTH = 8
