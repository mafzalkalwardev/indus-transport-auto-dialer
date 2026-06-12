from src.crm_db import CRMDatabase


def test_completed_phones_include_terminal_call_outcomes(tmp_path):
    db = CRMDatabase.__new__(CRMDatabase)
    db._path = str(tmp_path / "crm.sqlite3")
    db._init_db()

    statuses = {
        "+12025550101": "ENDED",
        "+12025550102": "ENDED_MANUALLY",
        "+12025550103": "VOICEMAIL",
        "+12025550104": "NO_ANSWER",
        "+12025550105": "BUSY",
        "+12025550106": "FAILED",
        "+12025550107": "RINGING",
    }
    with db._conn() as con:
        for phone, status in statuses.items():
            con.execute(
                "INSERT INTO call_records "
                "(user_id, phone, contact_name, status, timestamp) "
                "VALUES (?,?,?,?,datetime('now'))",
                (1, phone, "", status),
            )

    completed = db.get_completed_phones()

    assert "+12025550101" in completed
    assert "+12025550102" in completed
    assert "+12025550103" in completed
    assert "+12025550104" in completed
    assert "+12025550105" in completed
    assert "+12025550106" in completed
    assert "+12025550107" not in completed
