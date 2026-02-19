"""Aeroplan (Air Canada) award flight scraper using Playwright."""

import asyncio
import json
import logging
from typing import Any, Optional

from .base import BaseScraper
from ..models import Flight, FlightFare

logger = logging.getLogger(__name__)

AEROPLAN_URL = "https://www.aircanada.com/aeroplan/redeem/availability/outbound"
API_URL_PATTERN = "**/loyalty/dapidynamic/**/v2/search/air-bounds"

CABIN_MAP = {
    "eco": "economy",
    "ecoPremium": "economy",
    "business": "business",
    "first": "first",
}


class AeroplanScraper(BaseScraper):
    """Scraper for Aeroplan award availability using Playwright browser automation."""

    def __init__(self, timeout: float = 45.0, headless: bool = True):
        self.timeout = timeout
        self.headless = headless

    @property
    def program_name(self) -> str:
        return "aeroplan"

    async def search(
        self,
        origin: str,
        destination: str,
        date: str,
        cabin: Optional[str] = None,
    ) -> list[Flight]:
        """Search Aeroplan award availability using browser automation."""
        try:
            from playwright.async_api import async_playwright, TimeoutError as PWTimeoutError
        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return []

        params = (
            f"org0={origin.upper()}&dest0={destination.upper()}"
            f"&departureDate0={date}&lang=en-CA&tripType=O"
            f"&ADT=1&YTH=0&CHD=0&INF=0&INS=0&marketCode=TNB"
        )
        url = f"{AEROPLAN_URL}?{params}"

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=self.headless,
                    args=[
                        "--no-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                    ],
                )
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/121.0.0.0 Safari/537.36"
                    ),
                    locale="en-CA",
                    viewport={"width": 1280, "height": 800},
                )

                # Set up request interception
                api_response_future: asyncio.Future = asyncio.get_event_loop().create_future()

                async def handle_response(response):
                    if (
                        "/loyalty/dapidynamic/" in response.url
                        and "/v2/search/air-bounds" in response.url
                        and not api_response_future.done()
                    ):
                        try:
                            body = await response.json()
                            api_response_future.set_result(body)
                        except Exception as e:
                            if not api_response_future.done():
                                api_response_future.set_exception(e)

                page = await context.new_page()
                page.on("response", handle_response)

                logger.info(f"Aeroplan: navigating to search page for {origin}->{destination} on {date}")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)

                # Wait for API response
                try:
                    raw_data = await asyncio.wait_for(
                        asyncio.shield(api_response_future),
                        timeout=self.timeout,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "Aeroplan: API response not captured within timeout. "
                        "Possible anti-bot detection. Try running with headless=False."
                    )
                    await browser.close()
                    return []

                await browser.close()

        except Exception as e:
            logger.error(f"Aeroplan scraper error: {e}")
            return []

        flights = self._parse_response(raw_data, origin.upper(), destination.upper())

        # Filter by cabin if specified
        if cabin:
            flights = [f for f in flights if any(fare.cabin == cabin for fare in f.fares)]
            for f in flights:
                f.fares = [fare for fare in f.fares if fare.cabin == cabin]

        return flights

    def _parse_response(self, raw: dict, origin: str, destination: str) -> list[Flight]:
        """Parse Aeroplan API response into Flight objects."""
        errors = raw.get("errors", [])
        if errors:
            for err in errors:
                logger.warning(f"Aeroplan API error: {err.get('title', 'Unknown error')}")
            return []

        data = raw.get("data", {})
        if not data:
            return []

        air_bound_groups = data.get("airBoundGroups", [])
        if not air_bound_groups:
            logger.info("No award availability found (Aeroplan)")
            return []

        dictionaries = raw.get("dictionaries", {})
        flight_dict = dictionaries.get("flight", {})
        aircraft_dict = dictionaries.get("aircraft", {})

        results: list[Flight] = []

        for group in air_bound_groups:
            bound_details = group.get("boundDetails", {})
            segments = bound_details.get("segments", [])

            # Skip connections
            if len(segments) != 1:
                continue

            flight_id = segments[0].get("flightId", "")
            flight_info = flight_dict.get(flight_id)
            if not flight_info:
                continue

            dep_loc = flight_info.get("departure", {})
            arr_loc = flight_info.get("arrival", {})

            seg_origin = dep_loc.get("locationCode", "")
            seg_dest = arr_loc.get("locationCode", "")

            # Only direct matches
            if seg_origin != origin or seg_dest != destination:
                continue

            marketing_code = flight_info.get("marketingAirlineCode", "")
            marketing_number = flight_info.get("marketingFlightNumber", "")
            flight_no = f"{marketing_code} {marketing_number}".strip()

            aircraft_code = flight_info.get("aircraftCode", "")
            aircraft = aircraft_dict.get(aircraft_code, aircraft_code)

            duration_sec = flight_info.get("duration", 0)
            duration_min = duration_sec // 60 if duration_sec > 0 else 0

            flight = Flight(
                flight_no=flight_no,
                origin=seg_origin,
                destination=seg_dest,
                departure=dep_loc.get("dateTime", "")[:19].replace("T", " "),
                arrival=arr_loc.get("dateTime", "")[:19].replace("T", " "),
                duration=duration_min,
                aircraft=aircraft or "Unknown",
                has_wifi=None,
            )

            # Parse fares
            cabin_best: dict[str, FlightFare] = {}

            for air_bound in group.get("airBounds", []):
                avail_details = air_bound.get("availabilityDetails", [{}])
                if not avail_details:
                    continue

                detail = avail_details[0]
                cabin_raw = detail.get("cabin", "eco")
                cabin = CABIN_MAP.get(cabin_raw, "economy")
                booking_class = detail.get("bookingClass", "?")

                # Special case: UA markets Business class as First (I booking class)
                if booking_class == "I" and marketing_code == "UA":
                    cabin = "economy"

                prices = air_bound.get("prices", {})
                conversion = prices.get("milesConversion", {})
                converted = conversion.get("convertedMiles", {})
                remaining = conversion.get("remainingNonConverted", {})

                miles = converted.get("base", 0)
                taxes_cents = converted.get("totalTaxes", 0)
                cash = round(taxes_cents / 100, 2)
                currency = remaining.get("currencyCode", "USD")

                fare = FlightFare(
                    miles=miles,
                    cash=cash,
                    cabin=cabin,
                    booking_class=booking_class,
                    program="aeroplan",
                )

                existing = cabin_best.get(cabin)
                if existing is None or miles < existing.miles:
                    cabin_best[cabin] = fare

            flight.fares = list(cabin_best.values())
            if flight.fares:
                results.append(flight)

        return results
