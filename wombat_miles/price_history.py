"""Price history tracking for award fares using SQLite.

Each time a search is run, prices are recorded automatically.
Over time, this builds a dataset that enables:
- Detecting new price lows
- Showing price trends for a route
- Understanding seasonal patterns
"""

import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

HISTORY_DIR = Path.home() / ".wombat-miles"
HISTORY_FILE = HISTORY_DIR / "price_history.db"


def _get_conn() -> sqlite3.Connection:
    """Return an open SQLite connection, creating schema if needed."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(HISTORY_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS price_snapshots (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            origin       TEXT    NOT NULL,
            destination  TEXT    NOT NULL,
            flight_date  TEXT    NOT NULL,
            cabin        TEXT    NOT NULL,
            program      TEXT    NOT NULL,
            miles        INTEGER NOT NULL,
            taxes_usd    REAL    NOT NULL,
            flight_no    TEXT,
            recorded_at  REAL    NOT NULL   -- UNIX timestamp
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_route_date
        ON price_snapshots(origin, destination, flight_date, cabin)
    """)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def record_results(results: list, cabin_filter: Optional[str] = None) -> int:
    """Persist price snapshots from a list of SearchResult objects.

    Only records fares matching *cabin_filter* (or all cabins if None).
    Returns the number of rows inserted.
    """
    conn = _get_conn()
    now = time.time()
    count = 0

    for result in results:
        for flight in result.flights:
            fares = flight.fares
            if cabin_filter:
                fares = [f for f in fares if f.cabin == cabin_filter]
            for fare in fares:
                conn.execute(
                    """
                    INSERT INTO price_snapshots
                        (origin, destination, flight_date, cabin, program,
                         miles, taxes_usd, flight_no, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.origin,
                        result.destination,
                        result.date,
                        fare.cabin,
                        fare.program,
                        fare.miles,
                        fare.cash,
                        flight.flight_no,
                        now,
                    ),
                )
                count += 1

    conn.commit()
    conn.close()
    return count


# ---------------------------------------------------------------------------
# Querying
# ---------------------------------------------------------------------------

def get_price_trend(
    origin: str,
    destination: str,
    cabin: Optional[str] = None,
    lookback_days: int = 30,
) -> list[dict]:
    """Return aggregated price history for a route.

    Groups by (flight_date, cabin, program) and returns the minimum miles
    seen in each group, ordered by flight_date ascending.

    Args:
        origin: IATA origin code (e.g. "SFO").
        destination: IATA destination code (e.g. "NRT").
        cabin: Optional cabin filter ("economy", "business", "first").
        lookback_days: Only include snapshots from this many days ago.

    Returns:
        List of dicts with keys:
            flight_date, cabin, program, min_miles, avg_taxes,
            sample_count, last_seen (human-readable).
    """
    conn = _get_conn()
    since = time.time() - lookback_days * 86400

    params: list = [origin.upper(), destination.upper(), since]
    cabin_clause = ""
    if cabin:
        cabin_clause = "AND cabin = ?"
        params.append(cabin)

    rows = conn.execute(
        f"""
        SELECT origin, destination, flight_date, cabin, program,
               MIN(miles)      AS min_miles,
               AVG(taxes_usd)  AS avg_taxes,
               COUNT(*)        AS sample_count,
               MAX(recorded_at) AS last_seen
        FROM   price_snapshots
        WHERE  origin = ? AND destination = ? AND recorded_at >= ?
               {cabin_clause}
        GROUP  BY flight_date, cabin, program
        ORDER  BY flight_date ASC, min_miles ASC
        """,
        params,
    ).fetchall()
    conn.close()

    return [
        {
            "origin": row[0],
            "destination": row[1],
            "flight_date": row[2],
            "cabin": row[3],
            "program": row[4],
            "min_miles": row[5],
            "avg_taxes": round(row[6], 2) if row[6] is not None else None,
            "sample_count": row[7],
            "last_seen": datetime.fromtimestamp(row[8]).strftime("%Y-%m-%d %H:%M"),
        }
        for row in rows
    ]


def get_stats(
    origin: str,
    destination: str,
    cabin: Optional[str] = None,
) -> dict:
    """Return summary statistics for a route.

    Returns a dict with keys:
        total_records, min_miles, max_miles, avg_miles,
        first_seen, last_seen, unique_flight_dates.
    Returns {"total_records": 0} if no data exists.
    """
    conn = _get_conn()
    params: list = [origin.upper(), destination.upper()]
    cabin_clause = ""
    if cabin:
        cabin_clause = "AND cabin = ?"
        params.append(cabin)

    row = conn.execute(
        f"""
        SELECT COUNT(*),
               MIN(miles), MAX(miles), AVG(miles),
               MIN(recorded_at), MAX(recorded_at),
               COUNT(DISTINCT flight_date)
        FROM   price_snapshots
        WHERE  origin = ? AND destination = ?
               {cabin_clause}
        """,
        params,
    ).fetchone()
    conn.close()

    if not row or not row[0]:
        return {"total_records": 0}

    return {
        "total_records": row[0],
        "min_miles": row[1],
        "max_miles": row[2],
        "avg_miles": round(row[3]) if row[3] is not None else None,
        "first_seen": (
            datetime.fromtimestamp(row[4]).strftime("%Y-%m-%d") if row[4] else None
        ),
        "last_seen": (
            datetime.fromtimestamp(row[5]).strftime("%Y-%m-%d %H:%M") if row[5] else None
        ),
        "unique_flight_dates": row[6],
    }


def detect_new_lows(
    results: list,
    cabin_filter: Optional[str] = None,
    lookback_days: int = 30,
) -> list[dict]:
    """Compare current search results against historical minimums.

    A "new low" is detected when the current fare is strictly lower than
    all previously recorded fares for the same route / flight_date / cabin /
    program within the *lookback_days* window.

    Returns a list of alert dicts, each containing:
        route, flight_date, cabin, program,
        new_miles, old_miles, drop_pct.
    """
    alerts: list[dict] = []
    conn = _get_conn()
    since = time.time() - lookback_days * 86400

    for result in results:
        for flight in result.flights:
            fares = flight.fares
            if cabin_filter:
                fares = [f for f in fares if f.cabin == cabin_filter]
            for fare in fares:
                row = conn.execute(
                    """
                    SELECT MIN(miles)
                    FROM   price_snapshots
                    WHERE  origin = ? AND destination = ? AND flight_date = ?
                           AND cabin = ? AND program = ? AND recorded_at >= ?
                    """,
                    (
                        result.origin,
                        result.destination,
                        result.date,
                        fare.cabin,
                        fare.program,
                        since,
                    ),
                ).fetchone()

                historical_min = row[0] if row and row[0] is not None else None

                if historical_min is not None and fare.miles < historical_min:
                    drop_pct = round(
                        (historical_min - fare.miles) / historical_min * 100, 1
                    )
                    alerts.append(
                        {
                            "route": f"{result.origin}→{result.destination}",
                            "flight_date": result.date,
                            "cabin": fare.cabin,
                            "program": fare.program,
                            "new_miles": fare.miles,
                            "old_miles": historical_min,
                            "drop_pct": drop_pct,
                        }
                    )

    conn.close()
    return alerts


def clear_history(origin: Optional[str] = None, destination: Optional[str] = None) -> int:
    """Delete price history records.

    If origin/destination are provided, only delete records for that route.
    Returns number of rows deleted.
    """
    conn = _get_conn()
    if origin and destination:
        cursor = conn.execute(
            "DELETE FROM price_snapshots WHERE origin=? AND destination=?",
            (origin.upper(), destination.upper()),
        )
    else:
        cursor = conn.execute("DELETE FROM price_snapshots")
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count
