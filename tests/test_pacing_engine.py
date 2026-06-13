from src.pacing.engine import PredictivePacingEngine, PacingMetrics, PacingConfig


def test_pacing_needs_more_dials_when_agents_available():
    engine = PredictivePacingEngine(PacingConfig(max_dials_per_interval=5))
    metrics = PacingMetrics(
        agents_available=2,
        connect_rate=0.25,
        abandon_rate=0.0,
        calls_in_progress=0,
    )
    assert engine.calculate_dials_needed(metrics) >= 2


def test_pacing_backs_off_on_high_abandon():
    engine = PredictivePacingEngine(PacingConfig(max_dials_per_interval=10))
    base = PacingMetrics(agents_available=4, connect_rate=0.2, abandon_rate=0.0, calls_in_progress=0)
    hot = PacingMetrics(agents_available=4, connect_rate=0.2, abandon_rate=0.08, calls_in_progress=0)
    assert engine.calculate_dials_needed(hot) <= engine.calculate_dials_needed(base)


def test_rolling_connect_rate_tracks_outcomes():
    engine = PredictivePacingEngine()
    engine.record_outcome(connected=True)
    engine.record_outcome(connected=False)
    assert 0.4 <= engine.rolling_connect_rate() <= 0.6
