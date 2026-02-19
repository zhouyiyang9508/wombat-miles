"""Tests for Alaska Atmos Rewards scraper."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wombat_miles.scrapers.alaska import AlaskaScraper
from tests.mock_data import (
    ALASKA_RESPONSE,
    ALASKA_EMPTY_RESPONSE,
    ALASKA_NO_SLICES_RESPONSE,
    ALASKA_INTL_RESPONSE,
)


def test_parse_basic():
    """Test parsing a normal Alaska API response."""
    scraper = AlaskaScraper()
    flights = scraper._parse_response(ALASKA_RESPONSE, "SFO", "LAX")

    # Should get 2 direct flights (connection skipped)
    assert len(flights) == 2, f"Expected 2 flights, got {len(flights)}"

    # First flight
    f1 = flights[0]
    assert f1.flight_no == "AS 1234"
    assert f1.origin == "SFO"
    assert f1.destination == "LAX"
    assert f1.duration == 95
    assert f1.has_wifi is True
    assert "737-900" in f1.aircraft

    # Should have 2 distinct cabin fares (economy and business)
    cabins = {f.cabin for f in f1.fares}
    assert "economy" in cabins
    assert "business" in cabins

    # Economy should pick the lowest (SAVER at 5000, not MAIN at 7500)
    eco_fare = next(f for f in f1.fares if f.cabin == "economy")
    assert eco_fare.miles == 5000
    assert eco_fare.is_saver is True

    # Business/First (mapped to business)
    biz_fare = next(f for f in f1.fares if f.cabin == "business")
    assert biz_fare.miles == 15000


def test_parse_empty():
    """Test parsing empty response."""
    scraper = AlaskaScraper()
    flights = scraper._parse_response(ALASKA_EMPTY_RESPONSE, "SFO", "LAX")
    assert flights == []


def test_parse_no_slices():
    """Test parsing response with no slices key."""
    scraper = AlaskaScraper()
    flights = scraper._parse_response(ALASKA_NO_SLICES_RESPONSE, "SFO", "LAX")
    assert flights == []


def test_parse_international():
    """Test parsing international business class response."""
    scraper = AlaskaScraper()
    flights = scraper._parse_response(ALASKA_INTL_RESPONSE, "SEA", "NRT")

    assert len(flights) == 1
    f = flights[0]
    assert f.flight_no == "JL 69"
    assert f.origin == "SEA"
    assert f.destination == "NRT"
    assert f.duration == 630
    assert f.format_duration() == "10h30m"

    biz = next((fare for fare in f.fares if fare.cabin == "business"), None)
    assert biz is not None
    assert biz.miles == 55000
    assert biz.cash == 86.20
    assert biz.booking_class == "J"


def test_connections_skipped():
    """Test that connecting flights are skipped."""
    scraper = AlaskaScraper()
    flights = scraper._parse_response(ALASKA_RESPONSE, "SFO", "LAX")
    # Only 2 direct flights, not the connection
    assert len(flights) == 2
    for f in flights:
        assert f.origin == "SFO"
        assert f.destination == "LAX"


def test_origin_dest_filter():
    """Test that mismatched origin/destination flights are filtered."""
    scraper = AlaskaScraper()
    # Search for SEA->LAX but response has SFO->LAX flights
    flights = scraper._parse_response(ALASKA_RESPONSE, "SEA", "LAX")
    assert flights == []


def test_duration_parse():
    """Test duration parsing."""
    assert AlaskaScraper._parse_duration("95") == 95
    assert AlaskaScraper._parse_duration("2h30m") == 150
    assert AlaskaScraper._parse_duration("10h0m") == 600


def test_best_fare():
    """Test Flight.best_fare() method."""
    scraper = AlaskaScraper()
    flights = scraper._parse_response(ALASKA_RESPONSE, "SFO", "LAX")
    f = flights[0]

    best_biz = f.best_fare("business")
    assert best_biz is not None
    assert best_biz.miles == 15000

    best_eco = f.best_fare("economy")
    assert best_eco is not None
    assert best_eco.miles == 5000

    best_any = f.best_fare()
    assert best_any is not None
    assert best_any.miles == 5000  # economy saver is cheapest


if __name__ == "__main__":
    test_parse_basic()
    test_parse_empty()
    test_parse_no_slices()
    test_parse_international()
    test_connections_skipped()
    test_origin_dest_filter()
    test_duration_parse()
    test_best_fare()
    print("✅ All Alaska tests passed!")
