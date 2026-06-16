import argparse

import pytest

from scripts import live_call_smoke


def _args(**overrides):
    values = {
        "numbers": [],
        "from_crm": False,
        "crm_limit": 0,
        "live_test_live_test": False,
        "live_test_file": "",
        "live_test_limit": 45,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_default_smoke_numbers_are_owner_test_numbers(monkeypatch):
    monkeypatch.setattr(
        live_call_smoke,
        "_load_crm_numbers",
        lambda _limit: pytest.fail("default smoke path should not load CRM numbers"),
    )

    assert live_call_smoke.select_smoke_numbers(_args(), account_count=3) == [
        "+15127616455",
        "+17085681794",
        "+14044651478",
    ]


def test_from_crm_must_be_explicit(monkeypatch):
    monkeypatch.setattr(live_call_smoke, "_load_crm_numbers", lambda limit: [f"+1{limit:010d}"])

    assert live_call_smoke.select_smoke_numbers(
        _args(from_crm=True, crm_limit=7),
        account_count=3,
    ) == ["+10000000007"]


def test_positional_numbers_override_default_list(monkeypatch):
    monkeypatch.setattr(
        live_call_smoke,
        "_load_crm_numbers",
        lambda _limit: pytest.fail("positional numbers should not load CRM numbers"),
    )

    assert live_call_smoke.select_smoke_numbers(
        _args(numbers=["7085681794"]),
        account_count=3,
    ) == ["+17085681794"]


def test_distinct_line_count_treats_duplicate_email_as_one_line():
    accounts = [
        {"email": "mary@ftsolutionapp.com", "profile": "mary_1"},
        {"email": "Mary@ftsolutionapp.com", "profile": "mary_2"},
        {"email": "agent2@example.com", "profile": "agent_2"},
    ]

    assert live_call_smoke.distinct_line_count(accounts, requested=3) == 2


def test_live_test_mode_loads_owner_excel_with_default_limit(monkeypatch):
    calls = {}

    def fake_load_excel(path, limit):
        calls["path"] = path
        calls["limit"] = limit
        return ["+15550000001"]

    monkeypatch.setattr(live_call_smoke, "_load_excel_numbers", fake_load_excel)

    assert live_call_smoke.select_smoke_numbers(
        _args(live_test_live_test=True, live_test_file="phones_test.xlsx"),
        account_count=3,
    ) == ["+15550000001"]
    assert calls == {"path": "phones_test.xlsx", "limit": 45}


def test_live_test_confirmation_phrase_is_stable():
    assert (
        live_call_smoke.LIVE_TEST_CONFIRMATION
        == "I OWN OR HAVE PERMISSION TO CALL THESE NUMBERS"
    )
