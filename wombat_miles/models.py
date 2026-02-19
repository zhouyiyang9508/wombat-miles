"""Data models for wombat-miles award flight search."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FlightFare:
    """Represents a single fare/price option for a flight."""
    miles: int
    cash: float  # taxes/fees in USD
    cabin: str   # economy / business / first
    booking_class: str  # e.g. I, J, C, U, etc.
    program: str  # alaska / aeroplan
    is_saver: bool = False

    def cabin_display(self) -> str:
        return {
            "economy": "Economy",
            "business": "Business",
            "first": "First",
        }.get(self.cabin, self.cabin.title())


@dataclass
class Flight:
    """Represents a flight with available award fares."""
    flight_no: str
    origin: str
    destination: str
    departure: str  # ISO datetime string, e.g. "2024-06-01 10:30:00"
    arrival: str
    duration: int   # minutes
    aircraft: str
    fares: list[FlightFare] = field(default_factory=list)
    has_wifi: Optional[bool] = None

    def best_fare(self, cabin: Optional[str] = None) -> Optional[FlightFare]:
        """Get the lowest-miles fare, optionally filtered by cabin."""
        fares = self.fares
        if cabin:
            fares = [f for f in fares if f.cabin == cabin]
        if not fares:
            return None
        return min(fares, key=lambda f: f.miles)

    def format_duration(self) -> str:
        h = self.duration // 60
        m = self.duration % 60
        return f"{h}h{m:02d}m"


@dataclass
class SearchResult:
    """Aggregated search results from one or more programs."""
    origin: str
    destination: str
    date: str
    flights: list[Flight] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
