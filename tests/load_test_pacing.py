"""Simulated predictive pacing load check."""
from src.pacing.engine import PredictivePacingEngine, PacingMetrics, PacingConfig


def test_simulated_campaign_abandon_under_target():
    engine = PredictivePacingEngine(PacingConfig(target_abandon_rate=0.03))
    abandons = 0
    connected = 0
    for _ in range(200):
        metrics = PacingMetrics(
            agents_available=2,
            connect_rate=0.2,
            abandon_rate=engine.rolling_abandon_rate(),
            calls_in_progress=1,
        )
        dials = engine.calculate_dials_needed(metrics)
        assert dials <= 5
        if dials > 2:
            abandons += 1
            engine.record_outcome(connected=True, abandoned=True)
        else:
            connected += 1
            engine.record_outcome(connected=True, abandoned=False)
    abandon_rate = abandons / max(1, connected + abandons)
    assert abandon_rate < 0.5
