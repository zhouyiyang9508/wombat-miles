"""Tests for connection flight search."""
import pytest
from datetime import datetime, timedelta
from wombat_miles.connection import find_connections, format_duration
from wombat_miles.models import Flight, FlightFare


def make_flight(
    flight_no: str,
    origin: str,
    destination: str,
    departure: datetime,
    arrival: datetime,
    miles: int,
    cash: float = 50.0,
    cabin: str = "business",
) -> Flight:
    """Helper to create a test flight."""
    duration = int((arrival - departure).total_seconds() / 60)
    return Flight(
        flight_no=flight_no,
        origin=origin,
        destination=destination,
        departure=departure,
        arrival=arrival,
        duration=duration,
        aircraft="Boeing 777",
        fares=[
            FlightFare(
                miles=miles,
                cash=cash,
                cabin=cabin,
                booking_class="J",
                program="alaska",
            )
        ],
        has_wifi=True,
    )


def test_find_connections_basic():
    """Test basic connection matching."""
    base_time = datetime(2025, 6, 15, 8, 0)
    
    # SFO -> ICN (8:00-14:00, 6h flight)
    first_leg = [
        make_flight("AS1", "SFO", "ICN", base_time, base_time + timedelta(hours=6), 60000)
    ]
    
    # ICN -> BKK (17:00-21:00, 4h flight) — 3h layover
    second_leg = [
        make_flight("AS2", "ICN", "BKK", base_time + timedelta(hours=9), base_time + timedelta(hours=13), 30000)
    ]
    
    connections = find_connections(first_leg, second_leg, min_layover_hours=2, max_layover_hours=24)
    
    assert len(connections) == 1
    conn = connections[0]
    assert conn.origin == "SFO"
    assert conn.via == "ICN"
    assert conn.destination == "BKK"
    assert conn.layover_minutes == 180  # 3 hours
    assert conn.total_miles == 90000
    assert conn.total_cash == 100.0
    assert conn.total_duration_minutes == 6*60 + 4*60 + 180  # flight1 + flight2 + layover


def test_find_connections_too_short_layover():
    """Test that connections with too-short layover are rejected."""
    base_time = datetime(2025, 6, 15, 8, 0)
    
    first_leg = [
        make_flight("AS1", "SFO", "ICN", base_time, base_time + timedelta(hours=6), 60000)
    ]
    
    # Second flight departs 1h after first arrives (too short)
    second_leg = [
        make_flight("AS2", "ICN", "BKK", base_time + timedelta(hours=7), base_time + timedelta(hours=11), 30000)
    ]
    
    connections = find_connections(first_leg, second_leg, min_layover_hours=2, max_layover_hours=24)
    
    assert len(connections) == 0


def test_find_connections_too_long_layover():
    """Test that connections with too-long layover are rejected."""
    base_time = datetime(2025, 6, 15, 8, 0)
    
    first_leg = [
        make_flight("AS1", "SFO", "ICN", base_time, base_time + timedelta(hours=6), 60000)
    ]
    
    # Second flight departs 25h later (too long)
    second_leg = [
        make_flight("AS2", "ICN", "BKK", base_time + timedelta(hours=31), base_time + timedelta(hours=35), 30000)
    ]
    
    connections = find_connections(first_leg, second_leg, min_layover_hours=2, max_layover_hours=24)
    
    assert len(connections) == 0


def test_find_connections_mismatched_airports():
    """Test that connections with mismatched airports are rejected."""
    base_time = datetime(2025, 6, 15, 8, 0)
    
    # First leg ends at ICN
    first_leg = [
        make_flight("AS1", "SFO", "ICN", base_time, base_time + timedelta(hours=6), 60000)
    ]
    
    # Second leg starts at NRT (different airport)
    second_leg = [
        make_flight("AS2", "NRT", "BKK", base_time + timedelta(hours=9), base_time + timedelta(hours=13), 30000)
    ]
    
    connections = find_connections(first_leg, second_leg, min_layover_hours=2, max_layover_hours=24)
    
    assert len(connections) == 0


def test_find_connections_multiple_options():
    """Test with multiple flights on each leg."""
    base_time = datetime(2025, 6, 15, 8, 0)
    
    first_leg = [
        make_flight("AS1", "SFO", "ICN", base_time, base_time + timedelta(hours=6), 60000),
        make_flight("AS3", "SFO", "ICN", base_time + timedelta(hours=2), base_time + timedelta(hours=8), 55000),
    ]
    
    second_leg = [
        make_flight("AS2", "ICN", "BKK", base_time + timedelta(hours=9), base_time + timedelta(hours=13), 30000),
        make_flight("AS4", "ICN", "BKK", base_time + timedelta(hours=12), base_time + timedelta(hours=16), 32000),
    ]
    
    connections = find_connections(first_leg, second_leg, min_layover_hours=2, max_layover_hours=24)
    
    # Should find 3 valid connections:
    # AS1 + AS2 (3h layover)
    # AS1 + AS4 (6h layover)
    # AS3 + AS4 (4h layover)
    # (AS3 + AS2 has only 1h layover, too short)
    assert len(connections) == 3
    
    # Should be sorted by total miles
    assert connections[0].total_miles == 87000  # AS3 + AS4 (55k + 32k)
    assert connections[1].total_miles == 90000  # AS1 + AS2 (60k + 30k)
    assert connections[2].total_miles == 92000  # AS1 + AS4 (60k + 32k)


def test_find_connections_cabin_filter():
    """Test cabin filtering."""
    base_time = datetime(2025, 6, 15, 8, 0)
    
    # First leg has both economy and business
    first_leg = [
        Flight(
            flight_no="AS1",
            origin="SFO",
            destination="ICN",
            departure=base_time,
            arrival=base_time + timedelta(hours=6),
            duration=360,
            aircraft="Boeing 777",
            fares=[
                FlightFare(miles=25000, cash=30.0, cabin="economy", booking_class="Y", program="alaska"),
                FlightFare(miles=60000, cash=50.0, cabin="business", booking_class="J", program="alaska"),
            ],
            has_wifi=True,
        )
    ]
    
    # Second leg only has business
    second_leg = [
        make_flight("AS2", "ICN", "BKK", base_time + timedelta(hours=9), base_time + timedelta(hours=13), 30000, cabin="business")
    ]
    
    # Filter for business class only
    connections = find_connections(first_leg, second_leg, min_layover_hours=2, max_layover_hours=24, cabin="business")
    
    assert len(connections) == 1
    assert connections[0].total_miles == 90000  # 60k + 30k (business fares)


def test_find_connections_no_matching_cabin():
    """Test when no flights match the cabin filter."""
    base_time = datetime(2025, 6, 15, 8, 0)
    
    first_leg = [
        make_flight("AS1", "SFO", "ICN", base_time, base_time + timedelta(hours=6), 60000, cabin="business")
    ]
    
    second_leg = [
        make_flight("AS2", "ICN", "BKK", base_time + timedelta(hours=9), base_time + timedelta(hours=13), 30000, cabin="economy")
    ]
    
    # Filter for first class (not available)
    connections = find_connections(first_leg, second_leg, min_layover_hours=2, max_layover_hours=24, cabin="first")
    
    assert len(connections) == 0


def test_format_duration():
    """Test duration formatting."""
    assert format_duration(45) == "45m"
    assert format_duration(60) == "1h 0m"
    assert format_duration(90) == "1h 30m"
    assert format_duration(185) == "3h 5m"
    assert format_duration(0) == "0m"


def test_connection_itinerary_properties():
    """Test ConnectionItinerary properties."""
    from wombat_miles.connection import ConnectionItinerary
    
    base_time = datetime(2025, 6, 15, 8, 0)
    first = make_flight("AS1", "SFO", "ICN", base_time, base_time + timedelta(hours=6), 60000)
    second = make_flight("AS2", "ICN", "BKK", base_time + timedelta(hours=9), base_time + timedelta(hours=13), 30000)
    
    conn = ConnectionItinerary(
        first_segment=first,
        second_segment=second,
        layover_minutes=180,
        total_miles=90000,
        total_cash=100.0,
        total_duration_minutes=780,
    )
    
    assert conn.origin == "SFO"
    assert conn.via == "ICN"
    assert conn.destination == "BKK"
    assert conn.departure == base_time
    assert conn.arrival == base_time + timedelta(hours=13)


def test_find_connections_empty_legs():
    """Test with empty flight lists."""
    assert find_connections([], [], min_layover_hours=2, max_layover_hours=24) == []
    
    base_time = datetime(2025, 6, 15, 8, 0)
    first_leg = [make_flight("AS1", "SFO", "ICN", base_time, base_time + timedelta(hours=6), 60000)]
    
    assert find_connections(first_leg, [], min_layover_hours=2, max_layover_hours=24) == []
    assert find_connections([], first_leg, min_layover_hours=2, max_layover_hours=24) == []
