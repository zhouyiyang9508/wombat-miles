"""
Connection flight search and matching logic.
Finds viable connecting itineraries between three airports (A→B→C).
"""
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Optional
from .models import Flight


@dataclass
class ConnectionItinerary:
    """A complete connection itinerary with two flight segments."""
    first_segment: Flight
    second_segment: Flight
    layover_minutes: int
    total_miles: int
    total_cash: float
    total_duration_minutes: int
    
    @property
    def origin(self) -> str:
        return self.first_segment.origin
    
    @property
    def destination(self) -> str:
        return self.second_segment.destination
    
    @property
    def via(self) -> str:
        return self.first_segment.destination
    
    @property
    def departure(self) -> datetime:
        return self.first_segment.departure
    
    @property
    def arrival(self) -> datetime:
        return self.second_segment.arrival


def find_connections(
    first_leg: List[Flight],
    second_leg: List[Flight],
    min_layover_hours: float = 2.0,
    max_layover_hours: float = 24.0,
    cabin: Optional[str] = None,
) -> List[ConnectionItinerary]:
    """
    Match flights from first_leg (A→B) with second_leg (B→C) to form viable connections.
    
    Args:
        first_leg: Flights from origin to connection point
        second_leg: Flights from connection point to final destination
        min_layover_hours: Minimum layover time (default 2h)
        max_layover_hours: Maximum layover time (default 24h)
        cabin: Filter by cabin class (economy/business/first)
    
    Returns:
        List of ConnectionItinerary objects, sorted by total miles
    """
    connections = []
    min_layover = timedelta(hours=min_layover_hours)
    max_layover = timedelta(hours=max_layover_hours)
    
    for f1 in first_leg:
        # Filter first segment by cabin if specified
        if cabin:
            f1_fares = [fare for fare in f1.fares if fare.cabin.lower() == cabin.lower()]
            if not f1_fares:
                continue
            f1_best_fare = min(f1_fares, key=lambda x: x.miles)
        else:
            if not f1.fares:
                continue
            f1_best_fare = min(f1.fares, key=lambda x: x.miles)
        
        for f2 in second_leg:
            # Check connection feasibility
            layover = f2.departure - f1.arrival
            if not (min_layover <= layover <= max_layover):
                continue
            
            # Ensure connection airport matches
            if f1.destination != f2.origin:
                continue
            
            # Filter second segment by cabin if specified
            if cabin:
                f2_fares = [fare for fare in f2.fares if fare.cabin.lower() == cabin.lower()]
                if not f2_fares:
                    continue
                f2_best_fare = min(f2_fares, key=lambda x: x.miles)
            else:
                if not f2.fares:
                    continue
                f2_best_fare = min(f2.fares, key=lambda x: x.miles)
            
            # Calculate totals
            total_miles = f1_best_fare.miles + f2_best_fare.miles
            total_cash = f1_best_fare.cash + f2_best_fare.cash
            layover_minutes = int(layover.total_seconds() / 60)
            total_duration = f1.duration + f2.duration + layover_minutes
            
            connections.append(ConnectionItinerary(
                first_segment=f1,
                second_segment=f2,
                layover_minutes=layover_minutes,
                total_miles=total_miles,
                total_cash=total_cash,
                total_duration_minutes=total_duration,
            ))
    
    # Sort by total miles
    connections.sort(key=lambda x: x.total_miles)
    return connections


def format_duration(minutes: int) -> str:
    """Format duration in minutes as 'Xh Ym'."""
    hours = minutes // 60
    mins = minutes % 60
    if hours == 0:
        return f"{mins}m"
    return f"{hours}h {mins}m"
