"""Output formatting for award search results."""

import calendar
import csv
import io
import json
from datetime import date
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich import box
from rich.text import Text

from .models import Flight, FlightFare, SearchResult

console = Console()

CABIN_STYLES = {
    "economy": "green",
    "business": "yellow",
    "first": "red bold",
}

PROGRAM_LABELS = {
    "alaska": "Alaska ✈",
    "aeroplan": "Aeroplan ✈",
}


def format_miles(miles: int) -> str:
    """Format miles with comma separator."""
    return f"{miles:,}"


def format_cash(cash: float, currency: str = "USD") -> str:
    """Format cash amount."""
    return f"${cash:.0f}"


def print_results(
    result: SearchResult,
    cabin_filter: Optional[str] = None,
    show_all_cabins: bool = False,
) -> None:
    """Print search results as a rich table."""
    flights = result.flights

    if not flights:
        if result.errors:
            for err in result.errors:
                console.print(f"[red]⚠ {err}[/red]")
        else:
            console.print(
                f"[dim]No award availability found for "
                f"{result.origin} → {result.destination} on {result.date}[/dim]"
            )
        return

    # Sort by miles (best fare for the requested cabin)
    def sort_key(f: Flight):
        best = f.best_fare(cabin_filter)
        return best.miles if best else 999_999_999

    flights.sort(key=sort_key)

    title = (
        f"✈  {result.origin} → {result.destination}  |  {result.date}"
        + (f"  |  {cabin_filter.title()} class" if cabin_filter else "")
    )
    console.print(f"\n[bold blue]{title}[/bold blue]")

    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        show_lines=False,
        pad_edge=True,
    )

    table.add_column("Flight", style="white", no_wrap=True)
    table.add_column("Departs", no_wrap=True)
    table.add_column("Arrives", no_wrap=True)
    table.add_column("Duration", justify="right")
    table.add_column("Stops", justify="center")
    table.add_column("Aircraft")
    table.add_column("Miles", justify="right", style="bold")
    table.add_column("Taxes", justify="right")
    table.add_column("Cabin", justify="center")
    table.add_column("Program")
    table.add_column("WiFi", justify="center")

    for flight in flights:
        fares_to_show = flight.fares
        if cabin_filter and not show_all_cabins:
            fares_to_show = [f for f in flight.fares if f.cabin == cabin_filter]

        # Sort fares: business first, then economy
        fares_to_show = sorted(fares_to_show, key=lambda f: (
            {"business": 0, "first": 0, "economy": 1}.get(f.cabin, 2),
            f.miles
        ))

        wifi_display = (
            "📶" if flight.has_wifi is True
            else "✗" if flight.has_wifi is False
            else "–"
        )

        stops_display = flight.stops_display()
        stops_style = "green" if flight.is_direct else ("yellow" if flight.stops == 1 else "red")
        stops_text = Text(stops_display, style=stops_style)

        for i, fare in enumerate(fares_to_show):
            cabin_style = CABIN_STYLES.get(fare.cabin, "white")
            cabin_text = Text(fare.cabin.title(), style=cabin_style)
            program_label = PROGRAM_LABELS.get(fare.program, fare.program)

            if i == 0:
                table.add_row(
                    flight.flight_no,
                    flight.departure[11:16] if len(flight.departure) > 10 else flight.departure,
                    flight.arrival[11:16] if len(flight.arrival) > 10 else flight.arrival,
                    flight.format_duration(),
                    stops_text,
                    flight.aircraft or "–",
                    format_miles(fare.miles),
                    format_cash(fare.cash),
                    cabin_text,
                    program_label,
                    wifi_display,
                )
            else:
                # Additional fare rows (indented)
                table.add_row(
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    format_miles(fare.miles),
                    format_cash(fare.cash),
                    cabin_text,
                    program_label,
                    "",
                )

    console.print(table)

    total = len(flights)
    console.print(
        f"[dim]{total} flight{'s' if total != 1 else ''} found.[/dim]\n"
    )


def print_results_json(result: SearchResult, cabin_filter: Optional[str] = None) -> None:
    """Print results as JSON."""
    flights_data = []
    for flight in result.flights:
        fares = flight.fares
        if cabin_filter:
            fares = [f for f in fares if f.cabin == cabin_filter]
        if not fares:
            continue
        flights_data.append({
            "flight_no": flight.flight_no,
            "origin": flight.origin,
            "destination": flight.destination,
            "departure": flight.departure,
            "arrival": flight.arrival,
            "duration_min": flight.duration,
            "aircraft": flight.aircraft,
            "has_wifi": flight.has_wifi,
            "fares": [
                {
                    "miles": f.miles,
                    "cash_usd": f.cash,
                    "cabin": f.cabin,
                    "booking_class": f.booking_class,
                    "program": f.program,
                    "is_saver": f.is_saver,
                }
                for f in fares
            ],
        })

    output = {
        "origin": result.origin,
        "destination": result.destination,
        "date": result.date,
        "flights": flights_data,
        "errors": result.errors,
    }
    print(json.dumps(output, indent=2))


def print_multi_date_summary(
    results: list[SearchResult],
    cabin_filter: Optional[str] = None,
) -> None:
    """Print a compact summary table for multiple dates."""
    from rich.table import Table

    table = Table(
        title=f"Award Availability Summary",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("Date")
    table.add_column("Flights", justify="right")
    table.add_column("Best Miles (Business)", justify="right", style="yellow")
    table.add_column("Best Miles (Economy)", justify="right", style="green")
    table.add_column("Programs")

    for result in results:
        flights = result.flights
        if cabin_filter:
            flights = [
                f for f in flights
                if any(fare.cabin == cabin_filter for fare in f.fares)
            ]

        biz_best = None
        eco_best = None
        programs = set()

        for f in result.flights:
            for fare in f.fares:
                programs.add(fare.program)
                if fare.cabin == "business":
                    if biz_best is None or fare.miles < biz_best:
                        biz_best = fare.miles
                elif fare.cabin == "economy":
                    if eco_best is None or fare.miles < eco_best:
                        eco_best = fare.miles

        prog_str = ", ".join(sorted(programs)) if programs else "–"

        table.add_row(
            result.date,
            str(len(result.flights)),
            format_miles(biz_best) if biz_best else "–",
            format_miles(eco_best) if eco_best else "–",
            prog_str,
        )

    console.print(table)


def results_to_csv(results: list[SearchResult], cabin_filter: Optional[str] = None) -> str:
    """Convert results to CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "date", "flight_no", "origin", "destination", "departure", "arrival",
        "duration_min", "stops", "aircraft", "cabin", "miles", "taxes_usd",
        "booking_class", "program", "is_saver", "has_wifi",
    ])

    for result in results:
        for flight in result.flights:
            fares = flight.fares
            if cabin_filter:
                fares = [f for f in fares if f.cabin == cabin_filter]
            for fare in fares:
                writer.writerow([
                    result.date,
                    flight.flight_no,
                    flight.origin,
                    flight.destination,
                    flight.departure,
                    flight.arrival,
                    flight.duration,
                    flight.stops,
                    flight.aircraft,
                    fare.cabin,
                    fare.miles,
                    fare.cash,
                    fare.booking_class,
                    fare.program,
                    fare.is_saver,
                    flight.has_wifi,
                ])

    return output.getvalue()


def print_price_trend(
    trend: list[dict],
    stats: dict,
    origin: str,
    destination: str,
    cabin_filter: Optional[str] = None,
) -> None:
    """Print price history as a rich table showing lowest miles per flight date."""
    route = f"{origin} → {destination}"
    cabin_label = cabin_filter.title() if cabin_filter else "All Cabins"

    console.print(f"\n[bold blue]📈 Price History: {route}  |  {cabin_label}[/bold blue]")

    if not trend:
        console.print("[dim]No history data found. Run `wombat-miles search` first to build history.[/dim]\n")
        return

    # Compute thresholds for relative coloring
    all_miles = [row["min_miles"] for row in trend]
    if len(all_miles) >= 2:
        sorted_m = sorted(all_miles)
        n = len(sorted_m)
        low_thresh = sorted_m[min(n // 3, n - 2)]
        high_thresh = sorted_m[min((2 * n) // 3, n - 2)]
    elif len(all_miles) == 1:
        low_thresh = high_thresh = all_miles[0]
    else:
        low_thresh = high_thresh = 0

    def miles_style(m: int) -> str:
        if m <= low_thresh:
            return "bold green"
        elif m <= high_thresh:
            return "yellow"
        return "red"

    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Flight Date")
    table.add_column("Cabin", justify="center")
    table.add_column("Program")
    table.add_column("Best Miles", justify="right")
    table.add_column("Avg Taxes", justify="right")
    table.add_column("Samples", justify="right")
    table.add_column("Last Seen")

    for row in trend:
        style = miles_style(row["min_miles"])
        table.add_row(
            row["flight_date"],
            Text(row["cabin"].title(), style=CABIN_STYLES.get(row["cabin"], "white")),
            PROGRAM_LABELS.get(row["program"], row["program"]),
            Text(f"{row['min_miles']:,}", style=style),
            f"${row['avg_taxes']:.0f}" if row["avg_taxes"] is not None else "–",
            str(row["sample_count"]),
            row["last_seen"],
        )

    console.print(table)

    if stats.get("total_records"):
        console.print(
            f"[dim]{stats['total_records']} total records  |  "
            f"all-time low: [bold green]{stats['min_miles']:,} miles[/bold green]  |  "
            f"tracking since {stats['first_seen']}[/dim]\n"
        )


def print_calendar_view(
    results: list[SearchResult],
    cabin_filter: Optional[str] = None,
    origin: str = "",
    destination: str = "",
) -> None:
    """Print award availability as a monthly calendar grid.

    Each cell shows the best available miles price for that day.
    Colors are relative: green=cheap, yellow=moderate, red=expensive.
    Dim cells = searched but no availability found.
    """
    if not results:
        console.print("[dim]No results to display.[/dim]")
        return

    # Build date -> (best_miles, best_program, cabin) map
    date_fares: dict[str, tuple[int, str, str]] = {}
    for result in results:
        best_miles = None
        best_program = None
        best_cabin = None
        for flight in result.flights:
            fare = flight.best_fare(cabin_filter)
            if fare and (best_miles is None or fare.miles < best_miles):
                best_miles = fare.miles
                best_program = fare.program
                best_cabin = fare.cabin
        if best_miles is not None:
            date_fares[result.date] = (best_miles, best_program or "", best_cabin or "")

    # Compute price thresholds for relative coloring (tercile-based).
    # Use (n-1) guard so that when n is small (1-3), the top tier is always
    # reachable: high_thresh index is capped at n-2 so sorted_prices[-1] > it.
    all_prices = [v[0] for v in date_fares.values()]
    if len(all_prices) >= 2:
        sorted_prices = sorted(all_prices)
        n = len(sorted_prices)
        # Low threshold: bottom ~1/3 (index n//3, but at most n-2)
        low_idx = min(n // 3, n - 2)
        # High threshold: bottom ~2/3 (index (2n)//3, but at most n-2)
        # so the top element is always > high_thresh → always shows red
        high_idx = min((2 * n) // 3, n - 2)
        low_thresh = sorted_prices[low_idx]
        high_thresh = sorted_prices[high_idx]
    elif len(all_prices) == 1:
        # Single price — always show as green (best available)
        low_thresh = high_thresh = all_prices[0]
    else:
        low_thresh = high_thresh = 0

    def price_style(miles: int) -> str:
        if miles <= low_thresh:
            return "bold green"
        elif miles <= high_thresh:
            return "yellow"
        else:
            return "red"

    # Group results by (year, month)
    months_seen: list[tuple[int, int]] = []
    for result in results:
        d = date.fromisoformat(result.date)
        key = (d.year, d.month)
        if key not in months_seen:
            months_seen.append(key)

    cabin_label = cabin_filter.title() if cabin_filter else "All Cabins"
    route_label = f"{origin} → {destination}" if (origin and destination) else ""

    total_avail = len(date_fares)
    total_searched = len(results)

    # Pre-build set of all searched dates for O(1) lookup in the cell loop
    searched_dates: set[str] = {r.date for r in results}

    for year, month in months_seen:
        month_name = calendar.month_name[month]
        title = f"✈  {route_label}  |  {month_name} {year}  |  {cabin_label}"
        console.print(f"\n[bold blue]{title}[/bold blue]")

        table = Table(
            box=box.SIMPLE_HEAD,
            show_header=True,
            header_style="bold cyan",
            padding=(0, 1),
        )
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for day in day_names:
            table.add_column(day, justify="center", width=9)

        cal_weeks = calendar.monthcalendar(year, month)
        for week in cal_weeks:
            row_cells = []
            for day_num in week:
                if day_num == 0:
                    row_cells.append(Text(""))
                    continue
                date_str = f"{year}-{month:02d}-{day_num:02d}"
                if date_str in date_fares:
                    miles, program, cab = date_fares[date_str]
                    miles_k = f"{miles // 1000}k"
                    style = price_style(miles)
                    cell = Text(f"{day_num:2d}\n{miles_k}", style=style)
                else:
                    if date_str in searched_dates:
                        cell = Text(f"{day_num:2d}\n–", style="dim")
                    else:
                        cell = Text(f"{day_num:2d}", style="dim")
                row_cells.append(cell)
            table.add_row(*row_cells)

        console.print(table)

    # Summary footer
    console.print(
        f"[dim]{total_avail}/{total_searched} days with availability.[/dim]"
    )
    if date_fares:
        best_day, (best_miles, best_prog, _) = min(
            date_fares.items(), key=lambda x: x[1][0]
        )
        console.print(
            f"[bold]Best price:[/bold] [yellow]{best_day}[/yellow] — "
            f"[bold green]{best_miles:,} miles[/bold green] ({best_prog})\n"
        )
