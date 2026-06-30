from src.system_profile import recommended_slots, system_ram_gb, chrome_process_count


def test_recommended_slots_caps_on_low_ram(monkeypatch):
    monkeypatch.setattr("src.system_profile.system_ram_gb", lambda: 8.0)
    monkeypatch.setattr("src.system_profile.chrome_process_count", lambda: 0)
    assert recommended_slots(3) == 1


def test_recommended_slots_caps_when_chrome_heavy(monkeypatch):
    monkeypatch.setattr("src.system_profile.system_ram_gb", lambda: 32.0)
    monkeypatch.setattr("src.system_profile.chrome_process_count", lambda: 25)
    assert recommended_slots(3) == 1


def test_recommended_slots_allows_two_on_mid_ram(monkeypatch):
    monkeypatch.setattr("src.system_profile.system_ram_gb", lambda: 12.0)
    monkeypatch.setattr("src.system_profile.chrome_process_count", lambda: 5)
    assert recommended_slots(3) == 2


def test_recommended_slots_allows_fifteen_on_high_ram(monkeypatch):
    monkeypatch.setattr("src.system_profile.system_ram_gb", lambda: 64.0)
    monkeypatch.setattr("src.system_profile.chrome_process_count", lambda: 2)
    assert recommended_slots(20) == 15


def test_effective_enable_ai_audio_respects_low_ram(monkeypatch):
    monkeypatch.setattr("src.system_profile.system_ram_gb", lambda: 8.0)
    monkeypatch.setattr("src.system_profile.chrome_process_count", lambda: 30)
    from src.system_profile import effective_enable_ai_audio

    assert effective_enable_ai_audio({"enable_ai_audio": True, "amd_mode": "heuristic"}) is False
    assert effective_enable_ai_audio({"enable_ai_audio": True, "amd_mode": "off"}) is False
