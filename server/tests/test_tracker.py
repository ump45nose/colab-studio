"""Tests for `server/tracker.py`."""
from __future__ import annotations

from server import tracker


def test_record_usage_calculates_session_and_burn():
    raw = {
        "subscription_tier": "PRO",
        "paid_balance": 80.0,
        "free_balance": 20.0,
        "balance": 100.0,
        "burn_rates_hourly": {"l4": 2.0, "a100": 5.0},
        "eligible_gpus": ["l4", "a100"],
    }
    res1 = tracker.record_usage(raw, "l4", runtime_active=True)
    assert res1["current_burn_rate"] == 2.0
    assert res1["remaining_hours_active"] == 50.0
    assert res1["burn_rates_hourly"]["g2-standard-12"] == 2.0

    raw2 = {**raw, "balance": 96.5}
    res2 = tracker.record_usage(raw2, "l4", runtime_active=True)
    assert res2["session_used"] == 3.5
    assert res2["today_used"] == 3.5


def test_record_stage_filters_outliers():
    for d in (10.0, 11.0, 12.0):
        tracker.record_stage("image", "正在生成", warm=True, duration_s=d)
    # Outlier (> 4x median) should be ignored
    tracker.record_stage("image", "正在生成", warm=True, duration_s=200.0)
    est = tracker.get_estimates()["image:正在生成"]
    assert est["warm"] == 11.0
    assert est["samples"] == 3
