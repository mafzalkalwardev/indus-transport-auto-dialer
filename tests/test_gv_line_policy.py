from autodialer_gui import allow_duplicate_gv_accounts, gv_available_line_count
from src.system_profile import effective_requested_slots


def test_duplicate_email_counts_once_by_default():
    accounts = [
        {"email": "line@example.com", "profile": "line_a"},
        {"email": "LINE@example.com", "profile": "line_b"},
        {"email": "other@example.com", "profile": "other"},
    ]

    assert gv_available_line_count(accounts) == 2


def test_duplicate_profiles_can_count_as_concurrent_test_slots():
    accounts = [
        {"email": "line@example.com", "profile": "line_a"},
        {"email": "LINE@example.com", "profile": "line_b"},
        {"email": "line@example.com", "profile": "line_c"},
        {"email": "line@example.com", "profile": "line_d"},
        {"email": "line@example.com", "profile": "line_e"},
    ]

    assert gv_available_line_count(accounts, allow_duplicates=True) == 5


def test_duplicate_gv_account_flag_is_explicit():
    assert allow_duplicate_gv_accounts({}) is False
    assert allow_duplicate_gv_accounts({"allow_duplicate_gv_accounts": True}) is True


def test_force_requested_slots_honors_five_line_live_test(monkeypatch):
    monkeypatch.setattr("src.system_profile.system_ram_gb", lambda: 8.0)
    monkeypatch.setattr("src.system_profile.chrome_process_count", lambda: 30)

    assert effective_requested_slots(5, {"force_requested_slots": True}) == 5
