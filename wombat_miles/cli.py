"""Wombat Miles CLI - Award flight search tool."""

import asyncio
import logging
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Annotated, Optional

import typer
from rich.console import Console

from . import cache
from . import price_history
from . import alerts as alerts_mod
from .formatter import (
    console,
    print_calendar_view,
    print_multi_city_results,
    print_multi_date_summary,
    print_results,
    print_results_json,
    print_price_trend,
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

history_app = typer.Typer(help="Price history commands")
app.add_typer(history_app, name="history")

alert_app = typer.Typer(help="Award-flight alert commands")
app.add_typer(alert_app, name="alert")

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


async def _search_dates_concurrent(
    scrapers,
    origin: str,
    destination: str,
    dates: list[str],
    cabin: Optional[str],
    use_cache: bool,
    max_stops: int = 0,
    concurrency: int = 5,
) -> list[SearchResult]:
    """Search multiple dates concurrently with a semaphore rate limit.

    Uses a semaphore to cap simultaneous open browser contexts.
    Cached dates are returned immediately; only uncached dates use browser slots.
    """
    sem = asyncio.Semaphore(concurrency)

    async def bounded_search(search_date: str) -> SearchResult:
        # Check cache first — no browser needed
        all_cached = True
        for scraper in scrapers:
            key = cache.make_key(scraper.program_name, origin, destination, search_date)
            if not use_cache or cache.get(key) is None:
                all_cached = False
                break

        if all_cached:
            return await _search_date(scrapers, origin, destination, search_date, cabin, use_cache, max_stops)

        async with sem:
            return await _search_date(scrapers, origin, destination, search_date, cabin, use_cache, max_stops)

    tasks = [bounded_search(d) for d in dates]
    return await asyncio.gather(*tasks)


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
    no_history: Annotated[bool, typer.Option("--no-history", help="Do not record prices to history DB")] = False,
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

    # Auto-record prices to history DB (unless disabled)
    if not no_history:
        try:
            recorded = price_history.record_results(results, cabin)
            logger.debug(f"Recorded {recorded} price snapshots to history.")
            # Detect new lows vs. history
            alerts = price_history.detect_new_lows(results, cabin)
            if alerts:
                console.print("\n[bold yellow]🔔 New Price Low Detected![/bold yellow]")
                for alert in alerts:
                    console.print(
                        f"  [green]{alert['route']}[/green] on [cyan]{alert['flight_date']}[/cyan] "
                        f"({alert['cabin'].title()}, {alert['program']}): "
                        f"[bold green]{alert['new_miles']:,}[/bold green] miles "
                        f"[dim](was {alert['old_miles']:,}, ↓{alert['drop_pct']}%)[/dim]"
                    )
        except Exception as e:
            logger.warning(f"Price history recording failed: {e}")

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

    # Build all dates across requested months using dateutil-safe arithmetic
    dates_to_search = []
    for m_offset in range(months):
        # Compute target year and month safely (handles Dec→Jan rollover correctly)
        total_months = (start_date.year * 12 + start_date.month - 1) + m_offset
        target_year = total_months // 12
        target_month = total_months % 12 + 1
        _, days_in_month = cal_mod.monthrange(target_year, target_month)
        for d in range(1, days_in_month + 1):
            dates_to_search.append(f"{target_year}-{target_month:02d}-{d:02d}")

    use_cache = not no_cache

    console.print(
        f"[bold]Scanning {len(dates_to_search)} days for "
        f"{origin.upper()} → {destination.upper()}...[/bold]"
    )

    async def run_all():
        # Use concurrent search (up to 5 simultaneous browser contexts)
        # Cached results are served immediately without consuming a browser slot.
        return await _search_dates_concurrent(
            scrapers, origin.upper(), destination.upper(),
            dates_to_search, cabin, use_cache,
            max_stops=stops, concurrency=5,
        )

    results = asyncio.run(run_all())

    print_calendar_view(results, cabin, origin.upper(), destination.upper())


@app.command()
def multi_city(
    origins: Annotated[str, typer.Argument(help="Comma-separated origin airports (e.g. SFO,LAX,SEA)")],
    destination: Annotated[str, typer.Argument(help="Destination airport code (e.g. NRT)")],
    date_str: Annotated[Optional[str], typer.Argument(help="Date in YYYY-MM-DD format")] = None,
    cabin: Annotated[Optional[str], typer.Option("--class", "-c", help="Cabin class: economy, business, first")] = None,
    program: Annotated[str, typer.Option("--program", "-p", help="Program: alaska, aeroplan, all")] = "all",
    days: Annotated[int, typer.Option("--days", "-d", help="Search N days starting from date")] = 1,
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Skip cache")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose logging")] = False,
    stops: Annotated[int, typer.Option("--stops", help="Max stops (0=direct only, 1=one stop, etc.)")] = 0,
    output: Annotated[Optional[str], typer.Option("-o", help="Output file path (JSON)")] = None,
):
    """
    🌍 Search multiple origin cities to find the best award flight deals.

    Compares flights from different origins to the same destination,
    showing which city offers the best miles redemption value.

    Examples:

      wombat-miles multi-city SFO,LAX,SEA NRT 2025-06-01 --class business

      wombat-miles multi-city "SFO,OAK,SJC" NRT 2025-06-15 --program alaska --days 3

      wombat-miles multi-city SFO,LAX YYZ --start 2025-07-01 --class business
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if cabin and cabin not in ("economy", "business", "first"):
        console.print("[red]Invalid cabin. Choose: economy, business, first[/red]")
        raise typer.Exit(1)

    # Parse origins (comma-separated)
    origin_list = [o.strip().upper() for o in origins.split(",") if o.strip()]
    if not origin_list:
        console.print("[red]No valid origins provided. Use comma-separated codes like: SFO,LAX,SEA[/red]")
        raise typer.Exit(1)

    if len(origin_list) < 2:
        console.print("[yellow]Only one origin provided. Consider using `wombat-miles search` instead.[/yellow]")

    scrapers = _get_scrapers(program)

    # Build list of dates to search
    if not date_str:
        console.print("[yellow]No date specified. Use: wombat-miles multi-city SFO,LAX NRT 2025-06-01[/yellow]")
        raise typer.Exit(1)

    dates_to_search = []
    start_date = date.fromisoformat(date_str)
    for i in range(days):
        dates_to_search.append(str(start_date + timedelta(days=i)))

    use_cache = not no_cache
    destination_upper = destination.upper()

    # Search each origin
    all_results: dict[str, list[SearchResult]] = {}

    async def run_all():
        for origin_code in origin_list:
            console.print(
                f"[dim]Searching {origin_code} → {destination_upper} "
                f"({len(dates_to_search)} day(s))...[/dim]"
            )
            origin_results = []
            for search_date in dates_to_search:
                result = await _search_date(
                    scrapers, origin_code, destination_upper,
                    search_date, cabin, use_cache, max_stops=stops
                )
                origin_results.append(result)
            all_results[origin_code] = origin_results
        return all_results

    asyncio.run(run_all())

    # Output
    date_range_str = (
        f"{dates_to_search[0]}" if len(dates_to_search) == 1
        else f"{dates_to_search[0]} to {dates_to_search[-1]}"
    )

    if output:
        import json
        import dataclasses
        export_data = {}
        for origin_code, results in all_results.items():
            origin_flights = []
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
                    origin_flights.append(fd)
            export_data[origin_code] = origin_flights

        with open(output, "w") as fp:
            json.dump(export_data, fp, indent=2)
        console.print(f"[green]Results saved to {output} (JSON)[/green]")

    if not output:
        print_multi_city_results(all_results, cabin, destination_upper, date_range_str)


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


# ---------------------------------------------------------------------------
# history sub-commands
# ---------------------------------------------------------------------------

@history_app.command("show")
def history_show(
    origin: Annotated[str, typer.Argument(help="Origin airport code (e.g. SFO)")],
    destination: Annotated[str, typer.Argument(help="Destination airport code (e.g. NRT)")],
    cabin: Annotated[Optional[str], typer.Option("--class", "-c", help="Cabin: economy, business, first")] = None,
    days: Annotated[int, typer.Option("--days", "-d", help="Look back N days")] = 30,
):
    """
    📈 Show price history for a route.

    Displays the lowest miles seen over time, grouped by flight date.

    Example:

      wombat-miles history show SFO NRT --class business --days 60
    """
    if cabin and cabin not in ("economy", "business", "first"):
        console.print("[red]Invalid cabin. Choose: economy, business, first[/red]")
        raise typer.Exit(1)

    trend = price_history.get_price_trend(
        origin.upper(), destination.upper(), cabin, lookback_days=days
    )
    stats = price_history.get_stats(origin.upper(), destination.upper(), cabin)

    print_price_trend(trend, stats, origin.upper(), destination.upper(), cabin)


@history_app.command("stats")
def history_stats(
    origin: Annotated[str, typer.Argument(help="Origin airport code")],
    destination: Annotated[str, typer.Argument(help="Destination airport code")],
    cabin: Annotated[Optional[str], typer.Option("--class", "-c", help="Cabin filter")] = None,
):
    """
    📊 Show summary statistics for a route's price history.

    Example:

      wombat-miles history stats SFO NRT --class business
    """
    stats = price_history.get_stats(origin.upper(), destination.upper(), cabin)
    route = f"{origin.upper()} → {destination.upper()}"
    cabin_label = cabin.title() if cabin else "All Cabins"

    console.print(f"\n[bold blue]📊 Price History Stats: {route}  |  {cabin_label}[/bold blue]")

    if not stats.get("total_records"):
        console.print("[dim]No history data found. Run `wombat-miles search` first.[/dim]\n")
        return

    from rich.table import Table
    from rich import box as rich_box

    table = Table(box=rich_box.ROUNDED, show_header=False, pad_edge=True)
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value", justify="right")

    table.add_row("Total records", str(stats["total_records"]))
    table.add_row("Unique flight dates", str(stats["unique_flight_dates"]))
    table.add_row("Min miles seen", f"{stats['min_miles']:,}" if stats.get("min_miles") else "–")
    table.add_row("Max miles seen", f"{stats['max_miles']:,}" if stats.get("max_miles") else "–")
    table.add_row("Avg miles", f"{stats['avg_miles']:,}" if stats.get("avg_miles") else "–")
    table.add_row("First recorded", stats.get("first_seen") or "–")
    table.add_row("Last recorded", stats.get("last_seen") or "–")

    console.print(table)


@history_app.command("clear")
def history_clear(
    origin: Annotated[Optional[str], typer.Argument(help="Origin (optional)")] = None,
    destination: Annotated[Optional[str], typer.Argument(help="Destination (optional)")] = None,
    confirm: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
):
    """
    🗑  Clear price history.

    Without arguments clears ALL history (asks for confirmation).
    With origin+destination, clears only that route.

    Example:

      wombat-miles history clear SFO NRT

      wombat-miles history clear --yes
    """
    if origin and destination:
        count = price_history.clear_history(origin.upper(), destination.upper())
        console.print(f"[green]Cleared {count} records for {origin.upper()}→{destination.upper()}.[/green]")
    else:
        if not confirm:
            typer.confirm("Clear ALL price history?", abort=True)
        count = price_history.clear_history()
        console.print(f"[green]Cleared {count} total price history records.[/green]")


# ---------------------------------------------------------------------------
# alert sub-commands
# ---------------------------------------------------------------------------

@alert_app.command("add")
def alert_add(
    origin: Annotated[str, typer.Argument(help="Origin airport code (e.g. SFO)")],
    destination: Annotated[str, typer.Argument(help="Destination airport code (e.g. NRT)")],
    cabin: Annotated[Optional[str], typer.Option("--class", "-c", help="Cabin: economy, business, first")] = None,
    program: Annotated[str, typer.Option("--program", "-p", help="Program: alaska, aeroplan, all")] = "all",
    max_miles: Annotated[Optional[int], typer.Option("--max-miles", "-m", help="Trigger when miles ≤ this value")] = None,
    webhook: Annotated[Optional[str], typer.Option("--webhook", "-w", help="Discord webhook URL")] = None,
):
    """
    ➕ Create a new award-flight alert.

    The alert fires when availability is found matching your criteria.
    Use --max-miles to only be notified when the price is low enough.
    Pair with `wombat-miles monitor` (run via cron) to get notifications.

    Examples:

      wombat-miles alert add SFO NRT --class business --max-miles 70000 --webhook https://discord.com/api/webhooks/...

      wombat-miles alert add SFO YYZ --program aeroplan --max-miles 35000

      wombat-miles alert add SFO NRT   # notify on any availability
    """
    if cabin and cabin not in ("economy", "business", "first"):
        console.print("[red]Invalid cabin. Choose: economy, business, first[/red]")
        raise typer.Exit(1)

    alert_id = alerts_mod.add_alert(
        origin=origin.upper(),
        destination=destination.upper(),
        cabin=cabin,
        program=program,
        max_miles=max_miles,
        discord_webhook=webhook,
    )
    console.print(f"[green]✅ Alert #{alert_id} created:[/green] {origin.upper()} → {destination.upper()}", end="")
    if cabin:
        console.print(f" | {cabin.title()}", end="")
    if max_miles:
        console.print(f" | ≤ {max_miles:,} miles", end="")
    if webhook:
        console.print(f" | 🔔 Discord webhook set", end="")
    console.print()


@alert_app.command("list")
def alert_list(
    all_: Annotated[bool, typer.Option("--all", "-a", help="Include disabled alerts")] = False,
):
    """
    📋 List configured alerts.

    Example:

      wombat-miles alert list
    """
    from rich.table import Table
    from rich import box as rich_box

    alert_list_data = alerts_mod.list_alerts(include_disabled=all_)
    if not alert_list_data:
        console.print("[dim]No alerts configured. Use `wombat-miles alert add` to create one.[/dim]")
        return

    table = Table(
        title="🔔 Configured Alerts",
        box=rich_box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("ID", justify="right", style="dim", width=4)
    table.add_column("Route", style="bold")
    table.add_column("Cabin")
    table.add_column("Program")
    table.add_column("Max Miles", justify="right")
    table.add_column("Webhook", style="dim")
    table.add_column("Status")

    for a in alert_list_data:
        webhook_display = "✅ set" if a.discord_webhook else "[dim]—[/dim]"
        status = "[green]active[/green]" if a.enabled else "[dim]disabled[/dim]"
        table.add_row(
            str(a.id),
            f"{a.origin} → {a.destination}",
            a.cabin.title() if a.cabin else "[dim]any[/dim]",
            a.program,
            f"{a.max_miles:,}" if a.max_miles else "[dim]any[/dim]",
            webhook_display,
            status,
        )

    console.print(table)


@alert_app.command("remove")
def alert_remove(
    alert_id: Annotated[int, typer.Argument(help="Alert ID to remove")],
):
    """
    🗑  Remove an alert by ID.

    Example:

      wombat-miles alert remove 3
    """
    if alerts_mod.remove_alert(alert_id):
        console.print(f"[green]Alert #{alert_id} removed.[/green]")
    else:
        console.print(f"[red]Alert #{alert_id} not found.[/red]")
        raise typer.Exit(1)


@alert_app.command("history")
def alert_history(
    alert_id: Annotated[Optional[int], typer.Argument(help="Alert ID (optional, shows all if omitted)")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max rows to show")] = 20,
):
    """
    📜 Show recent alert fire history.

    Example:

      wombat-miles alert history
      wombat-miles alert history 2 --limit 10
    """
    from rich.table import Table
    from rich import box as rich_box

    history = alerts_mod.get_alert_history(alert_id, limit=limit)
    if not history:
        console.print("[dim]No alert history yet.[/dim]")
        return

    table = Table(
        title="📜 Alert Fire History",
        box=rich_box.ROUNDED,
        header_style="bold cyan",
    )
    table.add_column("Alert", justify="right", width=5)
    table.add_column("Flight Date")
    table.add_column("Flight #")
    table.add_column("Cabin")
    table.add_column("Program")
    table.add_column("Miles", justify="right")
    table.add_column("Taxes", justify="right")
    table.add_column("New Low")
    table.add_column("Fired At")

    for row in history:
        fired_str = (
            datetime.fromtimestamp(row["fired_at"]).strftime("%m-%d %H:%M")
            if row.get("fired_at")
            else "–"
        )
        table.add_row(
            str(row["alert_id"]),
            row.get("flight_date") or "–",
            row.get("flight_no") or "–",
            row.get("cabin") or "–",
            row.get("program") or "–",
            f"{row['miles']:,}" if row.get("miles") else "–",
            f"${row['taxes_usd']:.0f}" if row.get("taxes_usd") is not None else "–",
            "🔥 yes" if row.get("is_new_low") else "–",
            fired_str,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# monitor command — run all alerts, optionally fire webhooks
# ---------------------------------------------------------------------------

@app.command()
def monitor(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Check alerts but don't send notifications")] = False,
    program: Annotated[str, typer.Option("--program", "-p", help="Limit to program: alaska, aeroplan, all")] = "all",
    days: Annotated[int, typer.Option("--days", "-d", help="Search N days ahead for each alert route")] = 7,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Skip cache")] = False,
    dedup_hours: Annotated[float, typer.Option("--dedup-hours", help="Suppress re-firing within N hours")] = 24.0,
):
    """
    🔍 Run all configured alerts and send Discord notifications.

    Loops through every active alert, searches the configured route,
    and fires webhook notifications for matching fares.

    Typical cron setup (run every 6 hours):

      0 */6 * * *  wombat-miles monitor

    Examples:

      wombat-miles monitor --dry-run   # preview without sending notifications

      wombat-miles monitor --days 14 --verbose
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    active_alerts = alerts_mod.list_alerts()
    if not active_alerts:
        console.print("[dim]No active alerts. Use `wombat-miles alert add` to create one.[/dim]")
        return

    console.print(
        f"[bold]🔍 Running {len(active_alerts)} alert(s) "
        f"{'[DRY RUN] ' if dry_run else ''}...[/bold]"
    )

    # Group alerts by unique route to avoid duplicate searches
    route_groups: dict[tuple, list[alerts_mod.Alert]] = defaultdict(list)
    for a in active_alerts:
        route_groups[(a.origin, a.destination)].append(a)

    today = date.today()
    use_cache = not no_cache
    total_triggered = 0
    total_sent = 0

    for (origin, destination), route_alerts in route_groups.items():
        # Determine scraper program (use the alert's program or all if mixed)
        progs = {a.program for a in route_alerts}
        effective_program = list(progs)[0] if len(progs) == 1 else "all"
        if program != "all":
            effective_program = program

        try:
            scrapers = _get_scrapers(effective_program)
        except SystemExit:
            continue

        dates_to_search = [
            str(today + timedelta(days=i)) for i in range(days)
        ]

        console.print(
            f"  [cyan]{origin} → {destination}[/cyan] "
            f"({len(dates_to_search)} days, {effective_program})"
        )

        async def run_monitor_search(o, d, dts, s):
            return await _search_dates_concurrent(
                s, o, d, dts, cabin=None, use_cache=use_cache, concurrency=3
            )

        results = asyncio.run(run_monitor_search(origin, destination, dates_to_search, scrapers))

        # Auto-record to price_history
        try:
            price_history.record_results(results)
        except Exception as e:
            logger.warning("price_history.record_results failed: %s", e)

        # Check alerts
        triggered = alerts_mod.check_alerts(results, alerts=route_alerts, dedup_hours=dedup_hours)
        total_triggered += len(triggered)

        for t in triggered:
            new_low_badge = " [bold red]🔥 NEW LOW[/bold red]" if t.is_new_low else ""
            console.print(
                f"    🔔 Alert #{t.alert.id}: "
                f"[bold]{t.flight_date}[/bold] "
                f"{t.cabin.title()} {t.program} "
                f"[green]{t.miles:,} miles[/green] + ${t.taxes_usd:.0f}"
                f"{new_low_badge}"
            )

            sent = alerts_mod.fire_alert(t, dry_run=dry_run)
            if sent and t.alert.discord_webhook and not dry_run:
                console.print(f"      ✅ Discord notification sent")
                total_sent += 1
            elif dry_run:
                console.print(f"      [dim](dry-run – notification skipped)[/dim]")

    if total_triggered == 0:
        console.print("[dim]No alerts triggered.[/dim]")
    else:
        console.print(
            f"\n[bold green]✅ Done:[/bold green] "
            f"{total_triggered} alert(s) triggered"
            + (f", {total_sent} Discord notification(s) sent" if total_sent else "")
            + (" [dim](dry-run)[/dim]" if dry_run else "")
        )


def main():
    app()


if __name__ == "__main__":
    main()
