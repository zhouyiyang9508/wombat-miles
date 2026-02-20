"""Tests for the recommendation engine."""

import pytest
from wombat_miles.models import Flight, FlightFare
from wombat_miles.recommend import (
    calculate_cabin_multiplier,
    calculate_score,
    get_destinations_by_region,
    get_distance,
    rank_redemptions,
)


def test_get_distance():
    """Test distance lookup."""
    # Known distance
    assert get_distance("SFO", "NRT") == 5140
    assert get_distance("NRT", "SFO") == 5140  # Reverse lookup

    # Unknown distance (should return default estimate)
    assert get_distance("ABC", "XYZ") == 4000


def test_cabin_multiplier():
    """Test cabin value multipliers."""
    assert calculate_cabin_multiplier("economy") == 1.0
    assert calculate_cabin_multiplier("business") == 2.5
    assert calculate_cabin_multiplier("first") == 3.0


def test_calculate_score():
    """Test score calculation."""
    # Business class to Tokyo: good value
    fare = FlightFare(
        miles=70000,
        cash=50.0,
        cabin="business",
        booking_class="J",
        program="alaska",
    )
    distance = 5140
    score = calculate_score(fare, distance)
    assert score > 0
    assert isinstance(score, float)

    # Economy to Tokyo: lower score
    fare_econ = FlightFare(
        miles=35000,
        cash=50.0,
        cabin="economy",
        booking_class="U",
        program="alaska",
    )
    score_econ = calculate_score(fare_econ, distance)
    assert score_econ < score  # Business should score higher

    # Over budget penalty
    score_budget = calculate_score(fare, distance, max_miles=60000)
    assert score_budget < score  # Should be heavily penalized


def test_rank_redemptions():
    """Test ranking of multiple redemptions."""
    # Create mock flights
    flights = []

    # Flight 1: SFO->NRT business, 70k miles
    flight1 = Flight(
        flight_no="AS 123",
        origin="SFO",
        destination="NRT",
        departure="2025-06-01T10:00:00",
        arrival="2025-06-01T14:00:00",
        duration=660,
        aircraft="787-9",
        fares=[
            FlightFare(
                miles=70000,
                cash=50.0,
                cabin="business",
                booking_class="J",
                program="alaska",
            )
        ],
    )
    flights.append(("SFO", "NRT", "2025-06-01", flight1))

    # Flight 2: SFO->LAX economy, 12.5k miles (domestic, should rank lower)
    flight2 = Flight(
        flight_no="AS 456",
        origin="SFO",
        destination="LAX",
        departure="2025-06-01T08:00:00",
        arrival="2025-06-01T10:30:00",
        duration=150,
        aircraft="737",
        fares=[
            FlightFare(
                miles=12500,
                cash=5.6,
                cabin="economy",
                booking_class="U",
                program="alaska",
            )
        ],
    )
    flights.append(("SFO", "LAX", "2025-06-01", flight2))

    # Flight 3: SFO->HKG first, 120k miles (expensive but premium)
    flight3 = Flight(
        flight_no="CX 789",
        origin="SFO",
        destination="HKG",
        departure="2025-06-01T12:00:00",
        arrival="2025-06-02T18:00:00",
        duration=900,
        aircraft="777-300ER",
        fares=[
            FlightFare(
                miles=120000,
                cash=100.0,
                cabin="first",
                booking_class="F",
                program="aeroplan",
            )
        ],
    )
    flights.append(("SFO", "HKG", "2025-06-01", flight3))

    # Rank without filters
    recs = rank_redemptions(flights)
    assert len(recs) == 3
    assert all(r.score > 0 for r in recs)

    # First class HKG or business NRT should rank highest
    top_rec = recs[0]
    assert top_rec.destination in ("HKG", "NRT")
    assert top_rec.fare.cabin in ("business", "first")

    # Filter by cabin=business
    recs_biz = rank_redemptions(flights, cabin="business")
    assert len(recs_biz) == 1
    assert recs_biz[0].fare.cabin == "business"

    # Filter by max_miles=80000 (should exclude HKG first class)
    recs_budget = rank_redemptions(flights, max_miles=80000)
    assert len(recs_budget) == 2
    assert all(r.fare.miles <= 80000 for r in recs_budget)

    # Filter by program=alaska
    recs_alaska = rank_redemptions(flights, program="alaska")
    assert len(recs_alaska) == 2
    assert all(r.fare.program == "alaska" for r in recs_alaska)


def test_get_destinations_by_region():
    """Test destination filtering by region."""
    # All destinations
    all_dests = get_destinations_by_region()
    assert len(all_dests) > 0
    assert "NRT" in all_dests
    assert "LHR" in all_dests

    # Asia only
    asia_dests = get_destinations_by_region("asia")
    assert len(asia_dests) > 0
    assert "NRT" in asia_dests
    assert "LHR" not in asia_dests

    # Europe only
    europe_dests = get_destinations_by_region("europe")
    assert len(europe_dests) > 0
    assert "LHR" in europe_dests
    assert "NRT" not in europe_dests

    # With limit
    limited = get_destinations_by_region("asia", limit=3)
    assert len(limited) == 3

    # Unknown region returns all
    unknown = get_destinations_by_region("mars")
    assert len(unknown) > 0


def test_recommendation_format():
    """Test Recommendation dataclass formatting."""
    from wombat_miles.recommend import Recommendation

    flight = Flight(
        flight_no="AS 123",
        origin="SFO",
        destination="NRT",
        departure="2025-06-01T10:00:00",
        arrival="2025-06-01T14:00:00",
        duration=660,
        aircraft="787-9",
    )

    fare = FlightFare(
        miles=70000,
        cash=50.0,
        cabin="business",
        booking_class="J",
        program="alaska",
    )

    rec = Recommendation(
        origin="SFO",
        destination="NRT",
        date="2025-06-01",
        flight=flight,
        fare=fare,
        score=150.5,
        distance_miles=5140,
        cash_per_mile=0.071,
        cents_per_flight_mile=0.97,
        cabin_multiplier=2.5,
    )

    summary = rec.format_summary()
    assert "SFO→NRT" in summary
    assert "2025-06-01" in summary
    assert "Business" in summary
    assert "70,000 miles" in summary
    assert "$50.00" in summary
    assert "5,140 mi" in summary
    assert "0.97¢/mi" in summary
