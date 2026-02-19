"""Output formatting for award search results."""

import csv
import io
import json
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
