from src.crm_db import CRMDatabase


def test_log_call_stores_dial_timestamps(tmp_path):
    db = CRMDatabase.__new__(CRMDatabase)
    db._path = str(tmp_path / "crm.sqlite3")
    db._init_db()

    db.log_call(
        1,
        "+12025550101",
        "ENDED",
        contact_name="Jane",
        duration_s=12.5,
        slot_id=0,
        dialed_at="2026-06-02 10:00:00",
        ringing_at="2026-06-02 10:00:05",
        connected_at="2026-06-02 10:00:12",
    )

    with db._conn() as con:
        row = con.execute(
            "SELECT dialed_at, ringing_at, connected_at FROM call_records WHERE phone=?",
            ("+12025550101",),
        ).fetchone()

    assert row["dialed_at"] == "2026-06-02 10:00:00"
    assert row["ringing_at"] == "2026-06-02 10:00:05"
    assert row["connected_at"] == "2026-06-02 10:00:12"


def test_existing_db_migrates_timestamp_columns(tmp_path):
    db = CRMDatabase.__new__(CRMDatabase)
    db._path = str(tmp_path / "crm.sqlite3")
    with db._conn() as con:
        con.execute(
            "CREATE TABLE call_records ("
            "id INTEGER PRIMARY KEY, user_id INTEGER, phone TEXT, status TEXT, timestamp TEXT)"
        )

    db._init_db()

    with db._conn() as con:
        cols = {
            row[1]
            for row in con.execute("PRAGMA table_info(call_records)").fetchall()
        }

    assert {"dialed_at", "ringing_at", "connected_at"}.issubset(cols)
