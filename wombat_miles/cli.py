"""Wombat Miles CLI - Award flight search tool."""

import asyncio
import logging
import sys
from datetime import date, timedelta
from typing import Annotated, Optional

import typer
from rich.console import Console

from . import cache
from .formatter import (
    console,
    print_calendar_view,
    print_multi_date_summary,
    print_results,
    print_results_json,
    results_to_csv,
)
from .models import SearchResult
from .scrapers import AlaskaScraper, AeroplanScraper

app = typer.Typer(
    name="wombat-miles",
    help="🦘 Search award flight availability without paying for seats.aero",
    rich_markup_mode="rich",
)

cache_app = typer.Typer(help="Cache management commands")
app.add_typer(cache_app, name="cache")

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _get_scrapers(program: str):
    """Return list of scrapers based on program selection."""
    all_scrapers = {
        "alaska": AlaskaScraper(),
        "aeroplan": AeroplanScraper(),
    }
    if program == "all":
        return list(all_scrapers.values())
    if program not in all_scrapers:
        console.print(f"[red]Unknown program: {program}. Choose from: alaska, aeroplan, all[/red]")
        raise typer.Exit(1)
    return [all_scrapers[program]]


async def _search_date(
    scrapers,
    origin: str,
    destination: str,
    search_date: str,
    cabin: Optional[str],
    use_cache: bool,
    max_stops: int = 0,
) -> SearchResult:
    """Run search for a single date across all scrapers."""
    all_flights = []
    all_errors = []

    tasks = []
    for scraper in scrapers:
        cache_key = cache.make_key(scraper.program_name, origin, destination, search_date)
        cached = cache.get(cache_key) if use_cache else None

        if cached is not None:
            logger.info(f"Cache hit for {scraper.program_name} {origin}->{destination} {search_date}")
            tasks.append(("cached", cached, cache_key, scraper))
        else:
            tasks.append(("fetch", None, cache_key, scraper))

    # Run uncached searches concurrently
    async def fetch_scraper(scraper, cache_key):
        try:
            flights = await scraper.search(origin, destination, search_date, cabin, max_stops=max_stops)
            # Serialize for cache (simple dict form)
            import dataclasses
            raw = [dataclasses.asdict(f) for f in flights]
            if use_cache:
                cache.set(cache_key, raw)
            return flights, None
        except Exception as e:
            return [], str(e)

    fetch_tasks = [(t, c, k, s) for t, c, k, s in tasks if t == "fetch"]
    cached_tasks = [(t, c, k, s) for t, c, k, s in tasks if t == "cached"]

    # Process cached results
    for _, cached_data, _, scraper in cached_tasks:
        from .models import Flight, FlightFare
        flights = []
        for f_dict in cached_data:
            fares = [FlightFare(**fa) for fa in f_dict.pop("fares", [])]
            flight = Flight(**f_dict, fares=fares)
            flights.append(flight)
        all_flights.extend(flights)

    # Fetch uncached
    if fetch_tasks:
        results = await asyncio.gather(
            *[fetch_scraper(s, k) for _, _, k, s in fetch_tasks],
            return_exceptions=False,
        )
        for (flights, error) in results:
            all_flights.extend(flights)
            if error:
                all_errors.append(error)

    return SearchResult(
        origin=origin,
        destination=destination,
        date=search_date,
        flights=all_flights,
        errors=all_errors,
    )


@app.command()
def search(
    origin: Annotated[str, typer.Argument(help="Origin airport code (e.g. SFO)")],
    destination: Annotated[str, typer.Argument(help="Destination airport code (e.g. NRT)")],
    date_str: Annotated[Optional[str], typer.Argument(help="Date in YYYY-MM-DD format")] = None,
    cabin: Annotated[Optional[str], typer.Option("--class", "-c", help="Cabin class: economy, business, first")] = None,
    program: Annotated[str, typer.Option("--program", "-p", help="Program: alaska, aeroplan, all")] = "all",
    days: Annotated[int, typer.Option("--days", "-d", help="Search N days starting from date")] = 1,
    start: Annotated[Optional[str], typer.Option(help="Start date for range search (YYYY-MM-DD)")] = None,
    end: Annotated[Optional[str], typer.Option(help="End date for range search (YYYY-MM-DD)")] = None,
    output: Annotated[Optional[str], typer.Option("-o", help="Output file path (JSON)")] = None,
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Skip cache")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose logging")] = False,
    stops: Annotated[int, typer.Option("--stops", help="Max stops (0=direct only, 1=one stop, etc.)")] = 0,
    summary: Annotated[bool, typer.Option("--summary", "-s", help="Show summary table for date ranges")] = False,
):
    """
    🔍 Search for award flight availability.

    Examples:

      wombat-miles search SFO NRT 2025-06-01 --class business

      wombat-miles search SFO NRT 2025-06-01 --program alaska --stops 1

      wombat-miles search SFO YYZ --start 2025-06-01 --end 2025-06-30 --class business --summary
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if cabin and cabin not in ("economy", "business", "first"):
        console.print("[red]Invalid cabin. Choose: economy, business, first[/red]")
        raise typer.Exit(1)

    scrapers = _get_scrapers(program)

    # Build list of dates to search
    dates_to_search = []
    if start and end:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
        current = start_date
        while current <= end_date:
            dates_to_search.append(str(current))
            current += timedelta(days=1)
    elif date_str:
        start_date = date.fromisoformat(date_str)
        for i in range(days):
            dates_to_search.append(str(start_date + timedelta(days=i)))
    else:
        # Default to today + 30 days
        console.print("[yellow]No date specified. Use: wombat-miles search SFO NRT 2025-06-01[/yellow]")
        raise typer.Exit(1)

    use_cache = not no_cache

    async def run_all():
        all_results = []
        for search_date in dates_to_search:
            console.print(f"[dim]Searching {origin.upper()} → {destination.upper()} on {search_date}...[/dim]")
            result = await _search_date(
                scrapers, origin.upper(), destination.upper(),
                search_date, cabin, use_cache, max_stops=stops
            )
            all_results.append(result)
        return all_results

    results = asyncio.run(run_all())

    # Output
    if output:
        if output.endswith(".csv"):
            csv_str = results_to_csv(results, cabin)
            with open(output, "w") as fp:
                fp.write(csv_str)
            console.print(f"[green]Results saved to {output} (CSV)[/green]")
        else:
            import json
            import dataclasses
            all_data = []
            for r in results:
                for f in r.flights:
                    fares = f.fares
                    if cabin:
                        fares = [fa for fa in fares if fa.cabin == cabin]
                    if not fares:
                        continue
                    fd = dataclasses.asdict(f)
                    fd["fares"] = [dataclasses.asdict(fa) for fa in fares]
                    fd["date"] = r.date
                    all_data.append(fd)
            with open(output, "w") as fp:
                json.dump(all_data, fp, indent=2)
            console.print(f"[green]Results saved to {output} (JSON)[/green]")

    if len(results) > 1 and summary:
        print_multi_date_summary(results, cabin)

    if not output:
        for result in results:
            print_results(result, cabin)


@app.command()
def calendar_view(
    origin: Annotated[str, typer.Argument(help="Origin airport code (e.g. SFO)")],
    destination: Annotated[str, typer.Argument(help="Destination airport code (e.g. NRT)")],
    month: Annotated[Optional[str], typer.Argument(help="Month in YYYY-MM format (default: next month)")] = None,
    cabin: Annotated[Optional[str], typer.Option("--class", "-c", help="Cabin: economy, business, first")] = None,
    program: Annotated[str, typer.Option("--program", "-p", help="Program: alaska, aeroplan, all")] = "all",
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Skip cache")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose logging")] = False,
    stops: Annotated[int, typer.Option("--stops", help="Max stops (0=direct only)")] = 0,
    months: Annotated[int, typer.Option("--months", "-m", help="Number of months to display")] = 1,
):
    """
    📅 Show award availability as a monthly calendar grid.

    Each cell shows the best available miles price.
    Colors: [bold green]green=cheap[/bold green], [yellow]yellow=moderate[/yellow], [red]red=expensive[/red], dim=no availability.

    Examples:

      wombat-miles calendar-view SFO NRT 2025-06 --class business

      wombat-miles calendar-view SFO YYZ 2025-07 --program aeroplan --months 2

      wombat-miles calendar-view SFO NRT --class business   (searches next month)
    """
    import calendar as cal_mod

    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if cabin and cabin not in ("economy", "business", "first"):
        console.print("[red]Invalid cabin. Choose: economy, business, first[/red]")
        raise typer.Exit(1)

    scrapers = _get_scrapers(program)

    # Parse start month
    if month:
        try:
            start_date = date.fromisoformat(f"{month}-01")
        except ValueError:
            console.print(f"[red]Invalid month format: {month}. Use YYYY-MM (e.g. 2025-06)[/red]")
            raise typer.Exit(1)
    else:
        today = date.today()
        # Default to next month
        if today.month == 12:
            start_date = date(today.year + 1, 1, 1)
        else:
            start_date = date(today.year, today.month + 1, 1)

    # Build all dates across requested months
    dates_to_search = []
    for m_offset in range(months):
        # Advance by m_offset months
        target_year = start_date.year + (start_date.month - 1 + m_offset) // 12
        target_month = (start_date.month - 1 + m_offset) % 12 + 1
        _, days_in_month = cal_mod.monthrange(target_year, target_month)
        for d in range(1, days_in_month + 1):
            dates_to_search.append(f"{target_year}-{target_month:02d}-{d:02d}")

    use_cache = not no_cache

    console.print(
        f"[bold]Scanning {len(dates_to_search)} days for "
        f"{origin.upper()} → {destination.upper()}...[/bold]"
    )

    async def run_all():
        all_results = []
        for search_date in dates_to_search:
            result = await _search_date(
                scrapers, origin.upper(), destination.upper(),
                search_date, cabin, use_cache, max_stops=stops,
            )
            all_results.append(result)
        return all_results

    results = asyncio.run(run_all())

    print_calendar_view(results, cabin, origin.upper(), destination.upper())


@cache_app.command("clear")
def cache_clear(
    expired_only: Annotated[bool, typer.Option("--expired", help="Clear only expired entries")] = False,
):
    """Clear the search results cache."""
    if expired_only:
        count = cache.clear_expired()
        console.print(f"[green]Cleared {count} expired cache entries.[/green]")
    else:
        cache.clear_all()
        console.print("[green]Cache cleared.[/green]")


@cache_app.command("info")
def cache_info():
    """Show cache location and stats."""
    from . import cache as cache_mod
    console.print(f"Cache file: [blue]{cache_mod.CACHE_FILE}[/blue]")
    if cache_mod.CACHE_FILE.exists():
        size_kb = cache_mod.CACHE_FILE.stat().st_size / 1024
        console.print(f"Cache size: {size_kb:.1f} KB")
    else:
        console.print("[dim]No cache file yet.[/dim]")


def main():
    app()


if __name__ == "__main__":
    main()
