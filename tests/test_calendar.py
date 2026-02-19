"""Tests for calendar view formatter."""

import pytest
from unittest.mock import patch
from io import StringIO

from wombat_miles.formatter import print_calendar_view
from wombat_miles.models import Flight, FlightFare, SearchResult


def make_flight(
    date_str: str,
    miles: int,
    cabin: str = "business",
    program: str = "alaska",
) -> Flight:
    """Helper to create a Flight with a single fare."""
    return Flight(
        flight_no="AS 100",
        origin="SFO",
        destination="NRT",
        departure=f"{date_str} 10:00:00",
        arrival=f"{date_str} 16:00:00",
        duration=600,
        aircraft="Boeing 787",
        fares=[
            FlightFare(
                miles=miles,
                cash=50.0,
                cabin=cabin,
                booking_class="J",
                program=program,
            )
        ],
    )


def make_result(date_str: str, miles: int, cabin: str = "business") -> SearchResult:
    return SearchResult(
        origin="SFO",
        destination="NRT",
        date=date_str,
        flights=[make_flight(date_str, miles, cabin)],
    )


def make_empty_result(date_str: str) -> SearchResult:
    return SearchResult(
        origin="SFO",
        destination="NRT",
        date=date_str,
        flights=[],
    )


# ── Basic rendering ──────────────────────────────────────────────────────────


def test_calendar_view_renders_without_error(capsys):
    """Calendar view should render a full month without raising."""
    results = [
        make_result("2025-06-01", 55_000),
        make_result("2025-06-15", 60_000),
        make_result("2025-06-28", 70_000),
    ] + [make_empty_result(f"2025-06-{d:02d}") for d in [2, 3, 4, 5, 6, 7, 8]]
    # Should not raise
    print_calendar_view(results, cabin_filter="business", origin="SFO", destination="NRT")


def test_calendar_view_empty_results(capsys):
    """Empty results should print a graceful 'no results' message."""
    from rich.console import Console
    from io import StringIO

    buf = StringIO()
    with patch("wombat_miles.formatter.console", Console(file=buf, no_color=True)):
        print_calendar_view([], cabin_filter="business")
    output = buf.getvalue()
    assert "No results" in output


def test_calendar_view_all_empty_dates():
    """All searched dates with no availability should show dim dashes."""
    results = [make_empty_result(f"2025-07-{d:02d}") for d in range(1, 6)]
    # Should not raise, just shows dashes
    print_calendar_view(results, cabin_filter="business", origin="SFO", destination="NRT")


# ── Price coloring logic ─────────────────────────────────────────────────────


def test_price_thresholds_low_medium_high():
    """With three distinct price tiers, colors should vary (no crash)."""
    results = [
        make_result("2025-06-01", 30_000),   # cheap
        make_result("2025-06-02", 60_000),   # medium
        make_result("2025-06-03", 90_000),   # expensive
    ]
    # Should not raise
    print_calendar_view(results, cabin_filter="business", origin="SFO", destination="NRT")


def test_single_date_renders():
    """Calendar with a single date should still render."""
    results = [make_result("2025-06-15", 55_000)]
    print_calendar_view(results, cabin_filter="business", origin="SFO", destination="NRT")


# ── Multi-month support ──────────────────────────────────────────────────────


def test_multi_month_calendar():
    """Dates spanning two months should produce two separate calendar tables."""
    results = [
        make_result("2025-06-28", 55_000),
        make_result("2025-06-29", 57_000),
        make_result("2025-07-01", 60_000),
        make_result("2025-07-02", 62_000),
    ]
    from rich.console import Console
    from io import StringIO

    buf = StringIO()
    with patch("wombat_miles.formatter.console", Console(file=buf, no_color=True)):
        print_calendar_view(results, cabin_filter="business", origin="SFO", destination="NRT")
    output = buf.getvalue()
    # Both months should appear in the title
    assert "June 2025" in output
    assert "July 2025" in output


# ── Summary footer ───────────────────────────────────────────────────────────


def test_summary_shows_best_price(capsys):
    """Summary footer should identify the cheapest date."""
    results = [
        make_result("2025-06-05", 55_000),
        make_result("2025-06-10", 45_000),  # best
        make_result("2025-06-20", 70_000),
    ]
    from rich.console import Console
    from io import StringIO

    buf = StringIO()
    with patch("wombat_miles.formatter.console", Console(file=buf, no_color=True)):
        print_calendar_view(results, cabin_filter="business", origin="SFO", destination="NRT")
    output = buf.getvalue()
    assert "2025-06-10" in output
    assert "45,000" in output


def test_summary_count():
    """Summary should show correct fraction of days with availability."""
    results = [
        make_result("2025-06-01", 55_000),
        make_empty_result("2025-06-02"),
        make_empty_result("2025-06-03"),
    ]
    from rich.console import Console
    from io import StringIO

    buf = StringIO()
    with patch("wombat_miles.formatter.console", Console(file=buf, no_color=True)):
        print_calendar_view(results, cabin_filter="business", origin="SFO", destination="NRT")
    output = buf.getvalue()
    assert "1/3" in output


# ── Cabin filtering ──────────────────────────────────────────────────────────


def test_cabin_filter_excludes_wrong_cabin():
    """With business filter, economy-only flights should not appear as available."""
    eco_result = SearchResult(
        origin="SFO",
        destination="NRT",
        date="2025-06-10",
        flights=[make_flight("2025-06-10", 25_000, cabin="economy")],
    )
    results = [eco_result]
    from rich.console import Console
    from io import StringIO

    buf = StringIO()
    with patch("wombat_miles.formatter.console", Console(file=buf, no_color=True)):
        print_calendar_view(results, cabin_filter="business", origin="SFO", destination="NRT")
    output = buf.getvalue()
    # With business filter, this date should show "–" (no biz fares)
    assert "0/1" in output


def test_no_cabin_filter_shows_all():
    """Without cabin filter, all fares should count toward availability."""
    result = SearchResult(
        origin="SFO",
        destination="NRT",
        date="2025-06-10",
        flights=[make_flight("2025-06-10", 25_000, cabin="economy")],
    )
    results = [result]
    from rich.console import Console
    from io import StringIO

    buf = StringIO()
    with patch("wombat_miles.formatter.console", Console(file=buf, no_color=True)):
        print_calendar_view(results, cabin_filter=None, origin="SFO", destination="NRT")
    output = buf.getvalue()
    assert "1/1" in output


# ── Mixed programs ───────────────────────────────────────────────────────────


def test_mixed_programs_picks_cheapest():
    """When multiple programs have availability, pick the cheapest."""
    result = SearchResult(
        origin="SFO",
        destination="NRT",
        date="2025-06-10",
        flights=[
            make_flight("2025-06-10", 60_000, program="aeroplan"),
            make_flight("2025-06-10", 55_000, program="alaska"),
        ],
    )
    from rich.console import Console
    from io import StringIO

    buf = StringIO()
    with patch("wombat_miles.formatter.console", Console(file=buf, no_color=True)):
        print_calendar_view([result], cabin_filter="business", origin="SFO", destination="NRT")
    output = buf.getvalue()
    # Best price = 55k (alaska)
    assert "55" in output
    assert "alaska" in output
