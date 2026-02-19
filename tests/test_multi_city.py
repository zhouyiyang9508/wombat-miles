"""Unit tests for multi-city search functionality."""

import pytest
from datetime import date
from wombat_miles.models import Flight, FlightFare, SearchResult
from wombat_miles.formatter import print_multi_city_results
from io import StringIO
from rich.console import Console


@pytest.fixture
def mock_multi_city_results():
    """Create mock search results for multiple origins."""
    # SFO results
    sfo_flight = Flight(
        flight_no="AS 1234",
        origin="SFO",
        destination="NRT",
        departure="2025-06-01T10:00",
        arrival="2025-06-02T14:00",
        duration=600,
        aircraft="B777",
        fares=[
            FlightFare(
                miles=70000,
                cash=50.0,
                cabin="business",
                booking_class="J",
                program="alaska",
            )
        ],
        has_wifi=True,
    )

    sfo_result = SearchResult(
        origin="SFO",
        destination="NRT",
        date="2025-06-01",
        flights=[sfo_flight],
        errors=[],
    )

    # LAX results (cheaper)
    lax_flight = Flight(
        flight_no="AS 5678",
        origin="LAX",
        destination="NRT",
        departure="2025-06-01T12:00",
        arrival="2025-06-02T16:00",
        duration=620,
        aircraft="B787",
        fares=[
            FlightFare(
                miles=65000,
                cash=45.0,
                cabin="business",
                booking_class="J",
                program="alaska",
            )
        ],
        has_wifi=True,
    )

    lax_result = SearchResult(
        origin="LAX",
        destination="NRT",
        date="2025-06-01",
        flights=[lax_flight],
        errors=[],
    )

    # SEA results (most expensive)
    sea_flight = Flight(
        flight_no="AS 9999",
        origin="SEA",
        destination="NRT",
        departure="2025-06-01T14:00",
        arrival="2025-06-02T18:00",
        duration=640,
        aircraft="B777",
        fares=[
            FlightFare(
                miles=75000,
                cash=55.0,
                cabin="business",
                booking_class="J",
                program="alaska",
            )
        ],
        has_wifi=False,
    )

    sea_result = SearchResult(
        origin="SEA",
        destination="NRT",
        date="2025-06-01",
        flights=[sea_flight],
        errors=[],
    )

    return {
        "SFO": [sfo_result],
        "LAX": [lax_result],
        "SEA": [sea_result],
    }


def test_multi_city_results_sorting(mock_multi_city_results):
    """Test that multi-city results are sorted by miles correctly."""
    # Capture console output
    string_io = StringIO()
    test_console = Console(file=string_io, force_terminal=True, width=120)

    # Temporarily replace the global console in formatter
    from wombat_miles import formatter
    original_console = formatter.console
    formatter.console = test_console

    try:
        print_multi_city_results(
            mock_multi_city_results,
            cabin_filter="business",
            destination="NRT",
            search_date="2025-06-01",
        )
        output = string_io.getvalue()

        # Check that LAX (cheapest) appears first in the comparison
        assert "LAX" in output
        assert "65,000" in output  # LAX best price

        # Check summary table has all three origins
        assert "SFO" in output
        assert "SEA" in output

    finally:
        # Restore original console
        formatter.console = original_console


def test_multi_city_empty_results():
    """Test multi-city with no results."""
    string_io = StringIO()
    test_console = Console(file=string_io, force_terminal=True, width=120)

    from wombat_miles import formatter
    original_console = formatter.console
    formatter.console = test_console

    try:
        print_multi_city_results(
            {},
            cabin_filter="business",
            destination="NRT",
            search_date="2025-06-01",
        )
        output = string_io.getvalue()
        assert "No results" in output

    finally:
        formatter.console = original_console


def test_multi_city_cabin_filter(mock_multi_city_results):
    """Test that cabin filter works correctly in multi-city search."""
    # Add economy fares to one flight
    mock_multi_city_results["SFO"][0].flights[0].fares.append(
        FlightFare(
            miles=35000,
            cash=25.0,
            cabin="economy",
            booking_class="Y",
            program="alaska",
        )
    )

    string_io = StringIO()
    test_console = Console(file=string_io, force_terminal=True, width=120)

    from wombat_miles import formatter
    original_console = formatter.console
    formatter.console = test_console

    try:
        # Filter for business only
        print_multi_city_results(
            mock_multi_city_results,
            cabin_filter="business",
            destination="NRT",
            search_date="2025-06-01",
        )
        output = string_io.getvalue()

        # Should show business class results
        assert "70,000" in output  # SFO business
        assert "65,000" in output  # LAX business

        # Should NOT show economy fare
        assert "35,000" not in output

    finally:
        formatter.console = original_console


def test_multi_city_multiple_dates():
    """Test multi-city search across multiple dates."""
    # Create results for two dates
    flight1 = Flight(
        flight_no="AS 1234",
        origin="SFO",
        destination="NRT",
        departure="2025-06-01T10:00",
        arrival="2025-06-02T14:00",
        duration=600,
        aircraft="B777",
        fares=[
            FlightFare(
                miles=70000,
                cash=50.0,
                cabin="business",
                booking_class="J",
                program="alaska",
            )
        ],
        has_wifi=True,
    )

    flight2 = Flight(
        flight_no="AS 5678",
        origin="SFO",
        destination="NRT",
        departure="2025-06-02T10:00",
        arrival="2025-06-03T14:00",
        duration=600,
        aircraft="B777",
        fares=[
            FlightFare(
                miles=65000,  # Better price on day 2
                cash=45.0,
                cabin="business",
                booking_class="J",
                program="alaska",
            )
        ],
        has_wifi=True,
    )

    results = {
        "SFO": [
            SearchResult("SFO", "NRT", "2025-06-01", [flight1], []),
            SearchResult("SFO", "NRT", "2025-06-02", [flight2], []),
        ]
    }

    string_io = StringIO()
    test_console = Console(file=string_io, force_terminal=True, width=120)

    from wombat_miles import formatter
    original_console = formatter.console
    formatter.console = test_console

    try:
        print_multi_city_results(
            results,
            cabin_filter="business",
            destination="NRT",
            search_date="2025-06-01 to 2025-06-02",
        )
        output = string_io.getvalue()

        # Should show best price (65k) in summary
        assert "65,000" in output
        # Should show 2 flights total (check both flights appear in detailed table)
        assert "AS 5678" in output
        assert "AS 1234" in output
        # Check that it's from 1 origin
        assert "1" in output  # 1 origin

    finally:
        formatter.console = original_console
