"""Utility script to inspect and dump the encrypted SQLCipher game.db."""

from __future__ import annotations

import json
from pathlib import Path

from morsoul_core.keystore import get_or_create_key
from morsoul_core.paths import game_db_path
from morsoul_core.savestore import connect


def view_database() -> None:
    db_file = game_db_path()
    print(f"\n📂 Database Path: {db_file}")

    if not db_file.exists():
        print("❌ game.db does not exist yet.")
        return

    key = get_or_create_key()

    with connect(db_file, key) as conn:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]

        print(f"📊 Found tables: {', '.join(tables)}\n")

        for table in tables:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            print(f"=== Table: {table} ({len(rows)} rows) ===")
            for r in rows:
                d = dict(r)
                # Pretty print JSON fields for readability
                for k, v in list(d.items()):
                    if isinstance(v, str) and (v.startswith("{") or v.startswith("[")):
                        try:
                            d[k] = json.loads(v)
                        except Exception:
                            pass
                print(json.dumps(d, indent=2, default=str))
            print()


def export_unencrypted(output_path: Path | str = "game_decrypted.db") -> None:
    """Export to a standard unencrypted SQLite DB you can open in DB Browser for SQLite."""
    out_file = Path(output_path)
    if out_file.exists():
        out_file.unlink()

    db_file = game_db_path()
    key = get_or_create_key()

    with connect(db_file, key) as conn:
        conn.execute(f"ATTACH DATABASE '{out_file.resolve()}' AS plaintext KEY ''")
        conn.execute("SELECT sqlcipher_export('plaintext')")
        conn.execute("DETACH DATABASE plaintext")

    print(f"✅ Exported decrypted database to: {out_file.resolve()}")
    print("👉 You can now open this file directly in DB Browser for SQLite!")


if __name__ == "__main__":
    import sys

    if "--export" in sys.argv:
        export_unencrypted()
    else:
        view_database()
