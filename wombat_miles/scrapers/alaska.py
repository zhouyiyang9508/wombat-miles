"""Alaska Atmos Rewards award flight scraper using Playwright."""

import asyncio
import json
import logging
from typing import Any, Optional

from .base import BaseScraper
from ..models import Flight, FlightFare, Segment

logger = logging.getLogger(__name__)

ALASKA_API_URL = "https://www.alaskaair.com/searchbff/V3/search"

CABIN_MAP = {
    "FIRST": "business",
    "BUSINESS": "business",
    "MAIN": "economy",
    "SAVER": "economy",
    "COACH": "economy",
}

# URLs to block for faster loading (analytics, ads, tracking)
BLOCK_URLS = [
    "cdn.appdynamics.com",
    "*.siteintercept.qualtrics.com",
    "dc.services.visualstudio.com",
    "js.adsrvr.org",
    "siteintercept.qualtrics.com",
    "bing.com",
    "tiktok.com",
    "www.googletagmanager.com",
    "facebook.net",
    "demdex.net",
    "cdn.uplift-platform.com",
    "doubleclick.net",
    "www.google-analytics.com",
    "collect.tealiumiq.com",
    "alaskaair-app.quantummetric.com",
    "facebook.com",
    "rl.quantummetric.com",
    "app.securiti.ai",
    "cdn.optimizely.com",
]


class AlaskaScraper(BaseScraper):
    """Scraper for Alaska Atmos Rewards award availability using Playwright."""

    def __init__(self, timeout: float = 45.0, headless: bool = True):
        self.timeout = timeout
        self.headless = headless

    @property
    def program_name(self) -> str:
        return "alaska"

    async def search(
        self,
        origin: str,
        destination: str,
        date: str,
        cabin: Optional[str] = None,
        max_stops: int = 0,
    ) -> list[Flight]:
        """Search Alaska award availability using browser automation."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return []

        api_url = (
            f"{ALASKA_API_URL}?origins={origin.upper()}&destinations={destination.upper()}"
            f"&dates={date}&numADTs=1&fareView=as_awards"
            f"&sessionID=&solutionSetIDs=&solutionIDs="
        )

        raw_data = await self._fetch_with_playwright(api_url, origin.upper(), destination.upper())
        if raw_data is None:
            return []

        flights = self._parse_response(raw_data, origin.upper(), destination.upper(), max_stops=max_stops)

        if cabin:
            flights = [f for f in flights if any(fare.cabin == cabin for fare in f.fares)]
            for f in flights:
                f.fares = [fare for fare in f.fares if fare.cabin == cabin]

        return flights

    async def _fetch_with_playwright(self, api_url: str, origin: str, destination: str) -> Optional[dict]:
        """Use Playwright to navigate to the API endpoint and capture the JSON response."""
        from playwright.async_api import async_playwright, TimeoutError as PWTimeoutError

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=self.headless,
                    args=[
                        "--no-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                    ],
                )
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/121.0.0.0 Safari/537.36"
                    ),
                    locale="en-US",
                    viewport={"width": 1280, "height": 800},
                )

                api_response_future: asyncio.Future = asyncio.get_event_loop().create_future()

                async def handle_response(response):
                    if (
                        "/searchbff/V3/search" in response.url
                        and not api_response_future.done()
                    ):
                        try:
                            if response.status == 200:
                                body = await response.json()
                                api_response_future.set_result(body)
                            else:
                                logger.warning(f"Alaska API returned status {response.status}")
                                if not api_response_future.done():
                                    api_response_future.set_result(None)
                        except Exception as e:
                            if not api_response_future.done():
                                api_response_future.set_exception(e)

                page = await context.new_page()

                # Block analytics/ads for speed
                async def handle_route(route):
                    url = route.request.url
                    for pattern in BLOCK_URLS:
                        pattern_clean = pattern.replace("*.", "")
                        if pattern_clean in url:
                            await route.abort()
                            return
                    await route.continue_()

                await page.route("**/*", handle_route)
                page.on("response", handle_response)

                logger.info(f"Alaska: navigating to API for {origin}->{destination} on {api_url.split('dates=')[1].split('&')[0]}")

                try:
                    await page.goto(
                        "https://www.alaskaair.com/",
                        wait_until="domcontentloaded",
                        timeout=15000,
                    )
                except Exception:
                    pass  # Ignore navigation errors for the home page

                # Now go to the API endpoint
                await page.goto(api_url, wait_until="commit", timeout=20000)

                try:
                    raw_data = await asyncio.wait_for(
                        asyncio.shield(api_response_future),
                        timeout=self.timeout,
                    )
                    await browser.close()
                    return raw_data
                except asyncio.TimeoutError:
                    logger.warning("Alaska API: timeout waiting for response")
                    await browser.close()
                    return None

        except Exception as e:
            logger.error(f"Alaska Playwright error: {e}")
            return None

    def _parse_response(self, raw: dict, origin: str, destination: str, max_stops: int = 0) -> list[Flight]:
        """Parse Alaska API response into Flight objects."""
        if raw is None:
            return []

        slices = raw.get("slices")
        if not slices:
            logger.info("No scheduled flights between cities (Alaska)")
            return []

        results: list[Flight] = []

        for slice_data in slices:
            segments_raw = slice_data.get("segments", [])
            num_segments = len(segments_raw)
            stops = num_segments - 1

            # Filter by max stops
            if stops > max_stops:
                continue

            # Check that the route starts and ends correctly
            first_seg = segments_raw[0]
            last_seg = segments_raw[-1]
            itinerary_origin = first_seg.get("departureStation", "")
            itinerary_dest = last_seg.get("arrivalStation", "")

            if itinerary_origin != origin or itinerary_dest != destination:
                continue

            # Build segment list
            parsed_segments: list[Segment] = []
            total_duration = 0
            all_wifi = True
            any_wifi_known = False
            aircraft_list = []

            for seg in segments_raw:
                carrier = seg.get("publishingCarrier", {})
                seg_flight_no = f"{carrier.get('carrierCode', '')} {carrier.get('flightNumber', '')}".strip()

                amenities = seg.get("amenities", [])
                seg_wifi = "Wi-Fi" in amenities if amenities else None
                if seg_wifi is not None:
                    any_wifi_known = True
                    if not seg_wifi:
                        all_wifi = False

                duration_raw = seg.get("duration", 0)
                if isinstance(duration_raw, int):
                    seg_duration = duration_raw
                elif isinstance(duration_raw, str):
                    seg_duration = self._parse_duration(duration_raw)
                else:
                    seg_duration = 0
                total_duration += seg_duration

                aircraft_list.append(seg.get("aircraft", "Unknown"))

                parsed_segments.append(Segment(
                    flight_no=seg_flight_no,
                    origin=seg.get("departureStation", ""),
                    destination=seg.get("arrivalStation", ""),
                    departure=seg.get("departureTime", "")[:19].replace("T", " "),
                    arrival=seg.get("arrivalTime", "")[:19].replace("T", " "),
                    duration=seg_duration,
                    aircraft=seg.get("aircraft", "Unknown"),
                    has_wifi=seg_wifi,
                ))

            # Build display flight number (join segment flight numbers)
            if num_segments == 1:
                display_flight_no = parsed_segments[0].flight_no
            else:
                display_flight_no = " → ".join(s.flight_no for s in parsed_segments)

            has_wifi = all_wifi if any_wifi_known else None

            flight = Flight(
                flight_no=display_flight_no,
                origin=itinerary_origin,
                destination=itinerary_dest,
                departure=parsed_segments[0].departure,
                arrival=parsed_segments[-1].arrival,
                duration=total_duration,
                aircraft=", ".join(dict.fromkeys(aircraft_list)),  # deduplicate preserving order
                has_wifi=has_wifi,
                segments=parsed_segments,
            )

            # Parse fares
            fares_raw = slice_data.get("fares", {})
            if isinstance(fares_raw, dict):
                fares_raw = list(fares_raw.values())

            cabin_best: dict[str, FlightFare] = {}

            for fare_data in fares_raw:
                booking_codes = fare_data.get("bookingCodes", [])
                cabins_raw = fare_data.get("cabins", [])
                if not booking_codes or not cabins_raw:
                    continue

                cabin_raw = cabins_raw[0]
                cabin = CABIN_MAP.get(cabin_raw, "economy")
                booking_class = booking_codes[0]
                miles = fare_data.get("milesPoints", 0)
                cash = fare_data.get("grandTotal", 0.0)
                is_saver = cabin_raw == "SAVER"

                fare = FlightFare(
                    miles=miles,
                    cash=float(cash),
                    cabin=cabin,
                    booking_class=booking_class,
                    program="alaska",
                    is_saver=is_saver,
                )

                existing = cabin_best.get(cabin)
                if existing is None or miles < existing.miles:
                    cabin_best[cabin] = fare

            flight.fares = list(cabin_best.values())
            if flight.fares:
                results.append(flight)

        return results

    @staticmethod
    def _parse_duration(s: str) -> int:
        """Parse duration string to minutes."""
        try:
            return int(s)
        except ValueError:
            pass
        total = 0
        if "h" in s:
            parts = s.split("h")
            total += int(parts[0]) * 60
            s = parts[1]
        if "m" in s:
            total += int(s.replace("m", ""))
        return total
