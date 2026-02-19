"""Base scraper interface."""

from abc import ABC, abstractmethod
from typing import Optional
from ..models import Flight


class BaseScraper(ABC):
    """Abstract base class for all award scrapers."""

    @property
    @abstractmethod
    def program_name(self) -> str:
        """Name of the frequent flyer program."""
        ...

    @abstractmethod
    async def search(
        self,
        origin: str,
        destination: str,
        date: str,
        cabin: Optional[str] = None,
    ) -> list[Flight]:
        """
        Search for award availability.
        
        Args:
            origin: IATA airport code (e.g. "SFO")
            destination: IATA airport code (e.g. "NRT")
            date: Date in YYYY-MM-DD format
            cabin: Optional cabin filter (economy/business/first)
            
        Returns:
            List of flights with available award fares.
        """
        ...
