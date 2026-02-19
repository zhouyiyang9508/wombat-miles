"""Tests for price_history module using in-memory SQLite."""

import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from wombat_miles import price_history as ph
from wombat_miles.models import Flight, FlightFare, SearchResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def use_temp_db(tmp_path, monkeypatch):
    """Redirect price history to a temporary directory for each test."""
    monkeypatch.setattr(ph, "HISTORY_DIR", tmp_path)
    monkeypatch.setattr(ph, "HISTORY_FILE", tmp_path / "price_history.db")
    yield


def _make_result(
    origin="SFO",
    destination="NRT",
    flight_date="2025-06-01",
    cabin="business",
    miles=60_000,
    program="alaska",
    cash=80.0,
) -> SearchResult:
    fare = FlightFare(
        miles=miles,
        cash=cash,
        cabin=cabin,
        booking_class="I",
        program=program,
    )
    flight = Flight(
        flight_no="AS 1",
        origin=origin,
        destination=destination,
        departure=f"{flight_date} 10:00:00",
        arrival=f"{flight_date} 14:00:00",
        duration=600,
        aircraft="789",
        fares=[fare],
    )
    return SearchResult(
        origin=origin,
        destination=destination,
        date=flight_date,
        flights=[flight],
    )


# ---------------------------------------------------------------------------
# Tests: record_results
# ---------------------------------------------------------------------------

def test_record_results_basic():
    result = _make_result()
    count = ph.record_results([result])
    assert count == 1


def test_record_results_cabin_filter():
    result = _make_result()
    # Filter to "first" — no fares match, nothing recorded
    count = ph.record_results([result], cabin_filter="first")
    assert count == 0


def test_record_results_multiple_fares():
    fare_eco = FlightFare(miles=30_000, cash=50.0, cabin="economy", booking_class="U", program="alaska")
    fare_biz = FlightFare(miles=70_000, cash=90.0, cabin="business", booking_class="I", program="alaska")
    flight = Flight(
        flight_no="AS 2",
        origin="SFO", destination="NRT",
        departure="2025-06-05 08:00:00", arrival="2025-06-06 12:00:00",
        duration=660, aircraft="788",
        fares=[fare_eco, fare_biz],
    )
    result = SearchResult(origin="SFO", destination="NRT", date="2025-06-05", flights=[flight])
    count = ph.record_results([result])
    assert count == 2


# ---------------------------------------------------------------------------
# Tests: get_stats
# ---------------------------------------------------------------------------

def test_get_stats_empty():
    stats = ph.get_stats("SFO", "NRT")
    assert stats == {"total_records": 0}


def test_get_stats_with_data():
    results = [
        _make_result(flight_date="2025-06-01", miles=60_000),
        _make_result(flight_date="2025-06-02", miles=50_000),
        _make_result(flight_date="2025-06-03", miles=70_000),
    ]
    for r in results:
        ph.record_results([r])

    stats = ph.get_stats("SFO", "NRT")
    assert stats["total_records"] == 3
    assert stats["min_miles"] == 50_000
    assert stats["max_miles"] == 70_000
    assert stats["avg_miles"] == 60_000
    assert stats["unique_flight_dates"] == 3


def test_get_stats_cabin_filter():
    result = _make_result(cabin="business", miles=65_000)
    ph.record_results([result])

    # Querying for "economy" should return empty
    stats = ph.get_stats("SFO", "NRT", cabin="economy")
    assert stats["total_records"] == 0

    # Querying for "business" returns data
    stats = ph.get_stats("SFO", "NRT", cabin="business")
    assert stats["total_records"] == 1
    assert stats["min_miles"] == 65_000


# ---------------------------------------------------------------------------
# Tests: get_price_trend
# ---------------------------------------------------------------------------

def test_get_price_trend_empty():
    trend = ph.get_price_trend("SFO", "NRT")
    assert trend == []


def test_get_price_trend_returns_min():
    # Record two prices for the same date — trend should show the minimum
    r1 = _make_result(flight_date="2025-06-01", miles=70_000)
    r2 = _make_result(flight_date="2025-06-01", miles=55_000)  # lower
    ph.record_results([r1])
    ph.record_results([r2])

    trend = ph.get_price_trend("SFO", "NRT")
    assert len(trend) == 1
    assert trend[0]["min_miles"] == 55_000
    assert trend[0]["sample_count"] == 2


def test_get_price_trend_sorted_by_date():
    for flight_date, miles in [("2025-06-03", 60_000), ("2025-06-01", 50_000), ("2025-06-02", 55_000)]:
        ph.record_results([_make_result(flight_date=flight_date, miles=miles)])

    trend = ph.get_price_trend("SFO", "NRT")
    dates = [row["flight_date"] for row in trend]
    assert dates == sorted(dates)


def test_get_price_trend_lookback():
    # Record an old entry
    old_r = _make_result(flight_date="2025-01-01", miles=80_000)
    conn = ph._get_conn()
    old_time = time.time() - 40 * 86400  # 40 days ago
    conn.execute(
        "INSERT INTO price_snapshots "
        "(origin, destination, flight_date, cabin, program, miles, taxes_usd, flight_no, recorded_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("SFO", "NRT", "2025-01-01", "business", "alaska", 80_000, 80.0, "AS1", old_time),
    )
    conn.commit()
    conn.close()

    # Recent entry
    ph.record_results([_make_result(flight_date="2025-06-10", miles=60_000)])

    # lookback_days=30 should exclude the 40-day-old entry
    trend = ph.get_price_trend("SFO", "NRT", lookback_days=30)
    flight_dates = [row["flight_date"] for row in trend]
    assert "2025-01-01" not in flight_dates
    assert "2025-06-10" in flight_dates


# ---------------------------------------------------------------------------
# Tests: detect_new_lows
# ---------------------------------------------------------------------------

def test_detect_new_lows_no_history():
    # First time seeing this route — no history, so no alerts
    result = _make_result(miles=60_000)
    alerts = ph.detect_new_lows([result])
    assert alerts == []


def test_detect_new_lows_price_unchanged():
    r1 = _make_result(miles=60_000)
    ph.record_results([r1])

    # Same price — not a new low
    r2 = _make_result(miles=60_000)
    alerts = ph.detect_new_lows([r2])
    assert alerts == []


def test_detect_new_lows_price_higher():
    r1 = _make_result(miles=60_000)
    ph.record_results([r1])

    r2 = _make_result(miles=70_000)
    alerts = ph.detect_new_lows([r2])
    assert alerts == []


def test_detect_new_lows_new_low_detected():
    r1 = _make_result(miles=70_000)
    ph.record_results([r1])

    r2 = _make_result(miles=55_000)  # 55k < 70k → new low
    alerts = ph.detect_new_lows([r2])

    assert len(alerts) == 1
    assert alerts[0]["new_miles"] == 55_000
    assert alerts[0]["old_miles"] == 70_000
    assert alerts[0]["drop_pct"] == round((70_000 - 55_000) / 70_000 * 100, 1)


def test_detect_new_lows_cabin_filter():
    # Record business fare
    r1 = _make_result(cabin="business", miles=70_000)
    ph.record_results([r1])

    # Lower fare in economy should not trigger business alert
    fare_eco = FlightFare(miles=30_000, cash=50.0, cabin="economy", booking_class="U", program="alaska")
    flight = Flight(
        flight_no="AS 3", origin="SFO", destination="NRT",
        departure="2025-06-01 10:00:00", arrival="2025-06-01 14:00:00",
        duration=600, aircraft="789", fares=[fare_eco],
    )
    r2 = SearchResult(origin="SFO", destination="NRT", date="2025-06-01", flights=[flight])

    # Filter to business only — economy fare shouldn't appear
    alerts = ph.detect_new_lows([r2], cabin_filter="business")
    assert alerts == []


# ---------------------------------------------------------------------------
# Tests: clear_history
# ---------------------------------------------------------------------------

def test_clear_history_route():
    ph.record_results([_make_result()])
    count = ph.clear_history("SFO", "NRT")
    assert count == 1
    stats = ph.get_stats("SFO", "NRT")
    assert stats["total_records"] == 0


def test_clear_history_all():
    ph.record_results([_make_result(origin="SFO", destination="NRT")])
    ph.record_results([_make_result(origin="LAX", destination="LHR")])
    count = ph.clear_history()
    assert count == 2
