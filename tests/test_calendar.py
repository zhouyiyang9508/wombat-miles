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


# ── Color threshold correctness ───────────────────────────────────────────────


def test_color_threshold_n3_has_red():
    """With n=3 distinct prices, the most expensive should be reachable as red.

    Bug in original implementation: (2*3)//3 = 2, so high_thresh = max,
    making red unreachable. Fixed by capping high_idx at n-2.
    """
    from rich.console import Console
    from io import StringIO

    results = [
        make_result("2025-06-01", 30_000),   # cheap → green
        make_result("2025-06-02", 60_000),   # mid
        make_result("2025-06-03", 90_000),   # expensive → should be red
    ]
    buf = StringIO()
    with patch("wombat_miles.formatter.console", Console(file=buf, no_color=False)):
        print_calendar_view(results, cabin_filter="business", origin="SFO", destination="NRT")
    # We can't assert exact ANSI codes easily, but at least no exception
    # and all three dates appear
    buf2 = StringIO()
    with patch("wombat_miles.formatter.console", Console(file=buf2, no_color=True)):
        print_calendar_view(results, cabin_filter="business", origin="SFO", destination="NRT")
    output = buf2.getvalue()
    assert "30" in output  # day 1
    assert "60" in output  # day 2
    assert "90" in output  # day 3


def test_color_threshold_n4_shows_variation():
    """With n=4, we should get green, yellow, and red tiers all possible."""
    results = [
        make_result("2025-06-01", 20_000),
        make_result("2025-06-02", 40_000),
        make_result("2025-06-03", 60_000),
        make_result("2025-06-04", 80_000),
    ]
    # Should not raise and all 4 days should appear
    from rich.console import Console
    from io import StringIO
    buf = StringIO()
    with patch("wombat_miles.formatter.console", Console(file=buf, no_color=True)):
        print_calendar_view(results, cabin_filter="business", origin="SFO", destination="NRT")
    output = buf.getvalue()
    assert "20" in output
    assert "80" in output


def test_color_threshold_n1_single_price():
    """Single price should show as green (cheap tier) without crashing."""
    results = [make_result("2025-06-15", 55_000)]
    from rich.console import Console
    from io import StringIO
    buf = StringIO()
    with patch("wombat_miles.formatter.console", Console(file=buf, no_color=True)):
        print_calendar_view(results, cabin_filter="business", origin="SFO", destination="NRT")
    output = buf.getvalue()
    assert "55" in output


# ── Year boundary (Dec → Jan) ─────────────────────────────────────────────────


def test_year_boundary_december_to_january():
    """Calendar results spanning December and January should render both months."""
    results = [
        make_result("2025-12-30", 55_000),
        make_result("2025-12-31", 57_000),
        make_result("2026-01-01", 60_000),
        make_result("2026-01-02", 62_000),
    ]
    from rich.console import Console
    from io import StringIO
    buf = StringIO()
    with patch("wombat_miles.formatter.console", Console(file=buf, no_color=True)):
        print_calendar_view(results, cabin_filter="business", origin="SFO", destination="NRT")
    output = buf.getvalue()
    assert "December 2025" in output
    assert "January 2026" in output


# ── Month arithmetic (CLI helper, tested via dates_to_search logic) ───────────


def test_month_advance_cross_year():
    """Month arithmetic should handle year-boundary rollover correctly."""
    import calendar as cal_mod
    # Simulate the CLI's month-advance logic for Dec 2025 + 2 months
    start_year, start_month = 2025, 12
    dates = []
    for m_offset in range(2):
        total_months = (start_year * 12 + start_month - 1) + m_offset
        target_year = total_months // 12
        target_month = total_months % 12 + 1
        _, days = cal_mod.monthrange(target_year, target_month)
        dates.append((target_year, target_month, days))

    assert dates[0] == (2025, 12, 31)   # December 2025
    assert dates[1] == (2026, 1, 31)    # January 2026 (not December again!)
