"""Tests for Aeroplan scraper."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wombat_miles.scrapers.aeroplan import AeroplanScraper
from tests.mock_data import (
    AEROPLAN_RESPONSE,
    AEROPLAN_EMPTY_RESPONSE,
    AEROPLAN_ERROR_RESPONSE,
)


def test_parse_basic():
    """Test parsing a normal Aeroplan response."""
    scraper = AeroplanScraper()
    flights = scraper._parse_response(AEROPLAN_RESPONSE, "SFO", "YYZ")

    # Should get 2 direct flights (connection skipped)
    assert len(flights) == 2, f"Expected 2 flights, got {len(flights)}"

    # First flight: AC 758
    f1 = flights[0]
    assert f1.flight_no == "AC 758"
    assert f1.origin == "SFO"
    assert f1.destination == "YYZ"
    assert "787" in f1.aircraft

    # Duration: 18900 seconds = 315 minutes
    assert f1.duration == 315

    # Should have business and economy fares
    cabins = {f.cabin for f in f1.fares}
    assert "business" in cabins
    assert "economy" in cabins

    biz = next(f for f in f1.fares if f.cabin == "business")
    assert biz.miles == 60000
    assert biz.cash == 250.0  # 25000 cents = $250
    assert biz.booking_class == "J"
    assert biz.program == "aeroplan"

    eco = next(f for f in f1.fares if f.cabin == "economy")
    assert eco.miles == 25000


def test_parse_second_flight():
    """Test the second flight in the response."""
    scraper = AeroplanScraper()
    flights = scraper._parse_response(AEROPLAN_RESPONSE, "SFO", "YYZ")

    f2 = flights[1]
    assert f2.flight_no == "AC 760"
    assert "A330" in f2.aircraft

    # Only has business class
    assert len(f2.fares) == 1
    assert f2.fares[0].cabin == "business"
    assert f2.fares[0].miles == 70000


def test_connections_skipped():
    """Test that connecting flights are skipped."""
    scraper = AeroplanScraper()
    flights = scraper._parse_response(AEROPLAN_RESPONSE, "SFO", "YYZ")
    assert len(flights) == 2
    for f in flights:
        assert f.origin == "SFO"
        assert f.destination == "YYZ"


def test_parse_empty():
    """Test empty response."""
    scraper = AeroplanScraper()
    flights = scraper._parse_response(AEROPLAN_EMPTY_RESPONSE, "SFO", "YYZ")
    assert flights == []


def test_parse_error():
    """Test error response."""
    scraper = AeroplanScraper()
    flights = scraper._parse_response(AEROPLAN_ERROR_RESPONSE, "SFO", "YYZ")
    assert flights == []


def test_origin_dest_filter():
    """Test origin/destination filtering."""
    scraper = AeroplanScraper()
    # Search for SFO->LHR but response has SFO->YYZ
    flights = scraper._parse_response(AEROPLAN_RESPONSE, "SFO", "LHR")
    assert flights == []


def test_cabin_mapping():
    """Test that cabin names are correctly mapped."""
    scraper = AeroplanScraper()
    flights = scraper._parse_response(AEROPLAN_RESPONSE, "SFO", "YYZ")
    f = flights[0]
    cabin_set = {fare.cabin for fare in f.fares}
    # All cabins should be normalized
    for c in cabin_set:
        assert c in ("economy", "business", "first"), f"Unexpected cabin: {c}"


if __name__ == "__main__":
    test_parse_basic()
    test_parse_second_flight()
    test_connections_skipped()
    test_parse_empty()
    test_parse_error()
    test_origin_dest_filter()
    test_cabin_mapping()
    print("✅ All Aeroplan tests passed!")
