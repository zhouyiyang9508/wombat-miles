"""Optimal award redemption recommendation engine."""

from dataclasses import dataclass
from typing import Optional
import math
from collections import defaultdict

from .models import Flight, FlightFare


# Popular destinations from major US hubs
POPULAR_DESTINATIONS = {
    "asia": [
        "NRT",  # Tokyo Narita
        "HND",  # Tokyo Haneda
        "ICN",  # Seoul
        "HKG",  # Hong Kong
        "SIN",  # Singapore
        "TPE",  # Taipei
        "BKK",  # Bangkok
        "DEL",  # Delhi
    ],
    "europe": [
        "LHR",  # London
        "CDG",  # Paris
        "FRA",  # Frankfurt
        "AMS",  # Amsterdam
        "FCO",  # Rome
        "BCN",  # Barcelona
        "ZRH",  # Zurich
        "CPH",  # Copenhagen
    ],
    "oceania": [
        "SYD",  # Sydney
        "MEL",  # Melbourne
        "AKL",  # Auckland
    ],
    "domestic": [
        "JFK",  # New York JFK
        "BOS",  # Boston
        "MIA",  # Miami
        "LAX",  # Los Angeles
        "SEA",  # Seattle
    ],
}

# Approximate flight distances (miles) from major West Coast hubs
# Used for CPM calculation (cents per mile flown)
DISTANCES = {
    # Asia from SFO/LAX
    ("SFO", "NRT"): 5140,
    ("SFO", "HND"): 5140,
    ("SFO", "ICN"): 5963,
    ("SFO", "HKG"): 6927,
    ("SFO", "SIN"): 8447,
    ("SFO", "TPE"): 6804,
    ("SFO", "BKK"): 7928,
    ("SFO", "DEL"): 7706,
    ("LAX", "NRT"): 5478,
    ("LAX", "HND"): 5478,
    ("LAX", "ICN"): 6000,
    ("LAX", "HKG"): 7260,
    ("LAX", "SIN"): 8770,
    ("LAX", "TPE"): 6800,
    ("LAX", "BKK"): 8150,
    ("LAX", "DEL"): 8000,
    # Europe from SFO/LAX
    ("SFO", "LHR"): 5367,
    ("SFO", "CDG"): 5570,
    ("SFO", "FRA"): 5682,
    ("SFO", "AMS"): 5583,
    ("SFO", "FCO"): 6269,
    ("SFO", "BCN"): 5979,
    ("SFO", "ZRH"): 5801,
    ("SFO", "CPH"): 5421,
    ("LAX", "LHR"): 5456,
    ("LAX", "CDG"): 5660,
    ("LAX", "FRA"): 5770,
    ("LAX", "AMS"): 5670,
    ("LAX", "FCO"): 6350,
    ("LAX", "BCN"): 6070,
    ("LAX", "ZRH"): 5890,
    ("LAX", "CPH"): 5510,
    # Oceania from SFO/LAX
    ("SFO", "SYD"): 7416,
    ("SFO", "MEL"): 7920,
    ("SFO", "AKL"): 6510,
    ("LAX", "SYD"): 7488,
    ("LAX", "MEL"): 7920,
    ("LAX", "AKL"): 6520,
    # Domestic from SFO
    ("SFO", "JFK"): 2586,
    ("SFO", "BOS"): 2704,
    ("SFO", "MIA"): 2590,
    ("SFO", "LAX"): 337,
    ("SFO", "SEA"): 679,
    # Domestic from LAX
    ("LAX", "JFK"): 2475,
    ("LAX", "BOS"): 2611,
    ("LAX", "MIA"): 2342,
    ("LAX", "SEA"): 954,
    # SEA to Asia/Europe (common too)
    ("SEA", "NRT"): 4783,
    ("SEA", "HND"): 4783,
    ("SEA", "ICN"): 5217,
    ("SEA", "HKG"): 6485,
    ("SEA", "LHR"): 4800,
    ("SEA", "CDG"): 5020,
}


@dataclass
class Recommendation:
    """A single award redemption recommendation."""
    origin: str
    destination: str
    date: str
    flight: Flight
    fare: FlightFare
    score: float
    distance_miles: int
    cash_per_mile: float  # ¢ per award mile
    cents_per_flight_mile: float  # ¢ per actual flight mile (CPM)
    cabin_multiplier: float

    def format_summary(self) -> str:
        """One-line summary of the recommendation."""
        return (
            f"{self.origin}→{self.destination} {self.date} "
            f"{self.fare.cabin_display()} {self.fare.miles:,} miles + ${self.fare.cash:.2f} "
            f"({self.distance_miles:,} mi, {self.cents_per_flight_mile:.2f}¢/mi)"
        )


def get_distance(origin: str, destination: str) -> int:
    """Get approximate flight distance in miles."""
    key = (origin, destination)
    if key in DISTANCES:
        return DISTANCES[key]
    # Reverse lookup
    reverse_key = (destination, origin)
    if reverse_key in DISTANCES:
        return DISTANCES[reverse_key]
    # Rough estimate if not in table (assume medium-haul international)
    return 4000


def calculate_cabin_multiplier(cabin: str) -> float:
    """
    Cabin value multiplier for redemption value calculation.
    Business/First class miles are worth more due to higher cash prices.
    """
    if cabin == "first":
        return 3.0
    if cabin == "business":
        return 2.5
    return 1.0  # economy


def calculate_score(
    fare: FlightFare,
    distance_miles: int,
    max_miles: Optional[int] = None,
) -> float:
    """
    Calculate a recommendation score for an award redemption.
    
    Higher score = better value redemption.
    
    Factors:
    1. Cents per mile (CPM): cash / miles * 100
       - Lower CPM = better value (paying less cash per mile)
    2. Distance flown: longer flights = better value
    3. Cabin class: business/first worth more
    4. Miles availability: prefer options within user's budget
    
    Returns a composite score (higher is better).
    """
    cabin_mult = calculate_cabin_multiplier(fare.cabin)
    
    # CPM for actual flight miles (not award miles)
    # This represents "cents per mile flown" - typical benchmark is 1.0-2.0¢
    cash_cents = fare.cash * 100
    cents_per_flight_mile = cash_cents / distance_miles if distance_miles > 0 else 10.0
    
    # Cash per award mile (how much cash you pay per award mile redeemed)
    cash_per_mile = cash_cents / fare.miles if fare.miles > 0 else 10.0
    
    # Base score: distance * cabin multiplier / miles
    # This rewards long-haul premium cabin redemptions
    base_score = (distance_miles * cabin_mult) / fare.miles if fare.miles > 0 else 0
    
    # Penalty for high cash component (prefer lower taxes/fees)
    # Award tickets should minimize cash outlay
    cash_penalty = cash_per_mile * 0.5
    
    # Penalty if over budget
    budget_penalty = 0
    if max_miles and fare.miles > max_miles:
        budget_penalty = 1000  # Large penalty for unaffordable options
    
    final_score = base_score - cash_penalty - budget_penalty
    
    return max(0, final_score)


def rank_redemptions(
    flights: list[tuple[str, str, str, Flight]],  # (origin, dest, date, flight)
    cabin: Optional[str] = None,
    max_miles: Optional[int] = None,
    program: Optional[str] = None,
) -> list[Recommendation]:
    """
    Rank all available award redemptions by value.
    
    Args:
        flights: List of (origin, destination, date, flight) tuples
        cabin: Filter by cabin class
        max_miles: User's available miles (filters out unaffordable options)
        program: Filter by program (alaska/aeroplan)
    
    Returns:
        List of Recommendation objects sorted by score (best first)
    """
    recommendations = []
    
    for origin, destination, date, flight in flights:
        distance = get_distance(origin, destination)
        
        for fare in flight.fares:
            # Apply filters
            if cabin and fare.cabin != cabin:
                continue
            if program and fare.program != program:
                continue
            if max_miles and fare.miles > max_miles:
                continue
            
            cabin_mult = calculate_cabin_multiplier(fare.cabin)
            cash_cents = fare.cash * 100
            cash_per_mile = cash_cents / fare.miles if fare.miles > 0 else 0
            cents_per_flight_mile = cash_cents / distance if distance > 0 else 0
            
            score = calculate_score(fare, distance, max_miles)
            
            rec = Recommendation(
                origin=origin,
                destination=destination,
                date=date,
                flight=flight,
                fare=fare,
                score=score,
                distance_miles=distance,
                cash_per_mile=cash_per_mile,
                cents_per_flight_mile=cents_per_flight_mile,
                cabin_multiplier=cabin_mult,
            )
            recommendations.append(rec)
    
    # Sort by score descending
    recommendations.sort(key=lambda r: r.score, reverse=True)
    
    return recommendations


def get_destinations_by_region(
    region: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[str]:
    """
    Get destination list, optionally filtered by region.
    
    Args:
        region: "asia", "europe", "oceania", "domestic", or None (all)
        limit: Max number of destinations to return
    
    Returns:
        List of IATA airport codes
    """
    if region and region in POPULAR_DESTINATIONS:
        destinations = POPULAR_DESTINATIONS[region]
    else:
        # All destinations
        destinations = []
        for dests in POPULAR_DESTINATIONS.values():
            destinations.extend(dests)
    
    if limit:
        destinations = destinations[:limit]
    
    return destinations
