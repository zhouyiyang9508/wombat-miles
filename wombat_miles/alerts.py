"""Alert management for wombat-miles.

Stores configured route alerts in SQLite and fires Discord/Slack/email
notifications when award availability meets the configured thresholds.

Alert triggers:
  - New availability found on a route (any fare)
  - Miles drop below a configured max_miles threshold
  - New price low vs. historical minimum (integrates with price_history)

Usage::

    # programmatic
    from wombat_miles.alerts import add_alert, check_alerts, fire_alert

    alert_id = add_alert("SFO", "NRT", cabin="business", max_miles=70_000,
                          webhooks=["https://discord.com/api/webhooks/..."],
                          email_to=["user@example.com"], email_config="default")
    # after a search:
    triggered = check_alerts(search_results)
    for t in triggered:
        fire_alert(t)
"""

import json
import logging
import smtplib
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ALERTS_DIR = Path.home() / ".wombat-miles"
ALERTS_DB = ALERTS_DIR / "alerts.db"

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Alert:
    """A configured award-flight alert."""
    id: int
    origin: str
    destination: str
    cabin: Optional[str]       # economy / business / first / None (any)
    program: str               # alaska / aeroplan / all
    max_miles: Optional[int]   # fire when best fare ≤ this value (None = any)
    webhooks: list[str] = field(default_factory=list)  # Discord/Slack webhook URLs
    email_to: list[str] = field(default_factory=list)  # email recipients
    email_config: Optional[str] = None  # email config name (references email_configs table)
    enabled: int = 1           # 1 = active, 0 = disabled
    created_at: str = ""

    @property
    def route(self) -> str:
        return f"{self.origin} → {self.destination}"

    @property
    def description(self) -> str:
        parts = [self.route]
        if self.cabin:
            parts.append(self.cabin.title())
        if self.max_miles:
            parts.append(f"≤ {self.max_miles:,} miles")
        if self.program != "all":
            parts.append(f"({self.program})")
        return " | ".join(parts)
    
    @property
    def notification_summary(self) -> str:
        """Human-readable summary of configured notifications."""
        parts = []
        if self.webhooks:
            parts.append(f"{len(self.webhooks)} webhook(s)")
        if self.email_to:
            parts.append(f"{len(self.email_to)} email(s)")
        return ", ".join(parts) if parts else "none"


@dataclass
class EmailConfig:
    """SMTP email configuration."""
    name: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str
    from_addr: str
    use_tls: bool = True


@dataclass
class TriggeredAlert:
    """Represents a fired alert with matching flight details."""
    alert: Alert
    flight_no: str
    origin: str
    destination: str
    flight_date: str
    departure: str
    arrival: str
    duration: int
    cabin: str
    program: str
    miles: int
    taxes_usd: float
    is_new_low: bool = False
    prev_low_miles: Optional[int] = None

    @property
    def drop_pct(self) -> Optional[float]:
        if self.is_new_low and self.prev_low_miles:
            return round((self.prev_low_miles - self.miles) / self.prev_low_miles * 100, 1)
        return None


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    """Return an open SQLite connection, creating the schema if needed."""
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ALERTS_DB)
    conn.row_factory = sqlite3.Row
    
    # Create or migrate alerts table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            origin           TEXT    NOT NULL,
            destination      TEXT    NOT NULL,
            cabin            TEXT,
            program          TEXT    NOT NULL DEFAULT 'all',
            max_miles        INTEGER,
            discord_webhook  TEXT,
            webhooks         TEXT,              -- JSON array of webhook URLs
            email_to         TEXT,              -- JSON array of email addresses
            email_config     TEXT,              -- email config name
            enabled          INTEGER NOT NULL DEFAULT 1,
            created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    
    # Migrate old discord_webhook to new webhooks column (idempotent)
    try:
        conn.execute("SELECT webhooks FROM alerts LIMIT 1")
    except sqlite3.OperationalError:
        # Column doesn't exist, add it
        conn.execute("ALTER TABLE alerts ADD COLUMN webhooks TEXT")
        conn.execute("ALTER TABLE alerts ADD COLUMN email_to TEXT")
        conn.execute("ALTER TABLE alerts ADD COLUMN email_config TEXT")
        # Migrate old discord_webhook values
        conn.execute("""
            UPDATE alerts 
            SET webhooks = json_array(discord_webhook)
            WHERE discord_webhook IS NOT NULL AND webhooks IS NULL
        """)
        conn.commit()
    
    # Email configurations table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS email_configs (
            name       TEXT PRIMARY KEY,
            smtp_host  TEXT NOT NULL,
            smtp_port  INTEGER NOT NULL,
            smtp_user  TEXT NOT NULL,
            smtp_pass  TEXT NOT NULL,
            from_addr  TEXT NOT NULL,
            use_tls    INTEGER NOT NULL DEFAULT 1
        )
    """)
    
    # Fired-alerts log (for dedup / audit trail)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alert_history (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id     INTEGER NOT NULL,
            flight_no    TEXT,
            flight_date  TEXT,
            cabin        TEXT,
            program      TEXT,
            miles        INTEGER,
            taxes_usd    REAL,
            is_new_low   INTEGER DEFAULT 0,
            fired_at     REAL    NOT NULL
        )
    """)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def add_alert(
    origin: str,
    destination: str,
    cabin: Optional[str] = None,
    program: str = "all",
    max_miles: Optional[int] = None,
    webhooks: Optional[list[str]] = None,
    email_to: Optional[list[str]] = None,
    email_config: Optional[str] = None,
) -> int:
    """Persist a new alert. Returns the new alert id."""
    conn = _get_conn()
    webhooks_json = json.dumps(webhooks) if webhooks else None
    email_to_json = json.dumps(email_to) if email_to else None
    
    cur = conn.execute(
        """
        INSERT INTO alerts (origin, destination, cabin, program, max_miles, webhooks, email_to, email_config)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (origin.upper(), destination.upper(), cabin, program, max_miles, webhooks_json, email_to_json, email_config),
    )
    conn.commit()
    alert_id = cur.lastrowid
    conn.close()
    logger.info("Alert #%d created: %s→%s", alert_id, origin, destination)
    return alert_id


def _row_to_alert(row: sqlite3.Row) -> Alert:
    """Convert a DB row to an Alert object, parsing JSON fields."""
    d = dict(row)
    # Parse JSON fields
    d["webhooks"] = json.loads(d.get("webhooks") or "[]")
    d["email_to"] = json.loads(d.get("email_to") or "[]")
    # Remove old discord_webhook field if present
    d.pop("discord_webhook", None)
    return Alert(**d)


def list_alerts(include_disabled: bool = False) -> list[Alert]:
    """Return configured alerts."""
    conn = _get_conn()
    where = "" if include_disabled else "WHERE enabled = 1"
    rows = conn.execute(
        f"SELECT * FROM alerts {where} ORDER BY id"
    ).fetchall()
    conn.close()
    return [_row_to_alert(r) for r in rows]


def get_alert(alert_id: int) -> Optional[Alert]:
    """Fetch a single alert by id."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
    conn.close()
    return _row_to_alert(row) if row else None


def remove_alert(alert_id: int) -> bool:
    """Hard-delete an alert. Returns True if a row was deleted."""
    conn = _get_conn()
    cur = conn.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def enable_alert(alert_id: int, enabled: bool = True) -> bool:
    """Enable or disable an alert without deleting it."""
    conn = _get_conn()
    cur = conn.execute(
        "UPDATE alerts SET enabled = ? WHERE id = ?", (1 if enabled else 0, alert_id)
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Email Config CRUD
# ---------------------------------------------------------------------------

def add_email_config(
    name: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    from_addr: str,
    use_tls: bool = True,
) -> None:
    """Persist an email configuration."""
    conn = _get_conn()
    conn.execute(
        """
        INSERT OR REPLACE INTO email_configs (name, smtp_host, smtp_port, smtp_user, smtp_pass, from_addr, use_tls)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (name, smtp_host, smtp_port, smtp_user, smtp_pass, from_addr, 1 if use_tls else 0),
    )
    conn.commit()
    conn.close()
    logger.info("Email config '%s' saved", name)


def list_email_configs() -> list[EmailConfig]:
    """Return all email configurations (passwords redacted)."""
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM email_configs ORDER BY name").fetchall()
    conn.close()
    return [
        EmailConfig(
            name=r["name"],
            smtp_host=r["smtp_host"],
            smtp_port=r["smtp_port"],
            smtp_user=r["smtp_user"],
            smtp_pass="***",  # redacted
            from_addr=r["from_addr"],
            use_tls=bool(r["use_tls"]),
        )
        for r in rows
    ]


def get_email_config(name: str) -> Optional[EmailConfig]:
    """Fetch an email config by name (with full password)."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM email_configs WHERE name = ?", (name,)).fetchone()
    conn.close()
    if not row:
        return None
    return EmailConfig(
        name=row["name"],
        smtp_host=row["smtp_host"],
        smtp_port=row["smtp_port"],
        smtp_user=row["smtp_user"],
        smtp_pass=row["smtp_pass"],
        from_addr=row["from_addr"],
        use_tls=bool(row["use_tls"]),
    )


def remove_email_config(name: str) -> bool:
    """Delete an email configuration."""
    conn = _get_conn()
    cur = conn.execute("DELETE FROM email_configs WHERE name = ?", (name,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Alert matching
# ---------------------------------------------------------------------------

def check_alerts(
    search_results: list,
    alerts: Optional[list[Alert]] = None,
    dedup_hours: float = 24.0,
) -> list[TriggeredAlert]:
    """Match search results against configured alerts.

    Args:
        search_results: list of SearchResult objects from a scraper run.
        alerts: optional list of Alert objects (loaded from DB if None).
        dedup_hours: suppress re-firing the same alert+flight within N hours.

    Returns:
        list of TriggeredAlert objects (may be empty).
    """
    if alerts is None:
        alerts = list_alerts()
    if not alerts:
        return []

    conn = _get_conn()
    triggered: list[TriggeredAlert] = []
    since_dedup = time.time() - dedup_hours * 3600

    for result in search_results:
        for alert in alerts:
            # Route filter
            if alert.origin != result.origin or alert.destination != result.destination:
                continue

            for flight in result.flights:
                # Program filter
                best_fare = flight.best_fare(alert.cabin)
                if best_fare is None:
                    continue
                if alert.program != "all" and best_fare.program != alert.program:
                    continue

                # Miles threshold filter
                if alert.max_miles is not None and best_fare.miles > alert.max_miles:
                    continue

                # Dedup: skip if we already fired this exact combo recently
                already_fired = conn.execute(
                    """
                    SELECT 1 FROM alert_history
                    WHERE alert_id = ? AND flight_date = ? AND cabin = ?
                          AND program = ? AND miles = ? AND fired_at >= ?
                    LIMIT 1
                    """,
                    (
                        alert.id,
                        result.date,
                        best_fare.cabin,
                        best_fare.program,
                        best_fare.miles,
                        since_dedup,
                    ),
                ).fetchone()
                if already_fired:
                    continue

                # Check if it's a new historical low
                is_new_low = False
                prev_low = None
                try:
                    from . import price_history
                    stats = price_history.get_stats(
                        result.origin, result.destination, best_fare.cabin
                    )
                    if stats.get("min_miles") and best_fare.miles < stats["min_miles"]:
                        is_new_low = True
                        prev_low = stats["min_miles"]
                except Exception:
                    pass

                triggered.append(
                    TriggeredAlert(
                        alert=alert,
                        flight_no=flight.flight_no,
                        origin=result.origin,
                        destination=result.destination,
                        flight_date=result.date,
                        departure=flight.departure,
                        arrival=flight.arrival,
                        duration=flight.duration,
                        cabin=best_fare.cabin,
                        program=best_fare.program,
                        miles=best_fare.miles,
                        taxes_usd=best_fare.cash,
                        is_new_low=is_new_low,
                        prev_low_miles=prev_low,
                    )
                )

    conn.close()
    return triggered


# ---------------------------------------------------------------------------
# Notification dispatch
# ---------------------------------------------------------------------------

def build_discord_embed(t: TriggeredAlert) -> dict:
    """Build a Discord embed dict for a triggered alert."""
    cabin_emoji = {"economy": "🪑", "business": "🛋️", "first": "👑"}.get(t.cabin, "✈️")
    program_emoji = {"alaska": "🌲", "aeroplan": "🍁"}.get(t.program, "✈️")

    title_parts = [f"🦘 Award Alert: {t.origin} → {t.destination}"]
    if t.is_new_low:
        title_parts.append(" 🔥 NEW LOW!")
    title = "".join(title_parts)

    # Color: new low = red (danger/attention), normal = green
    color = 0xFF4444 if t.is_new_low else 0x00CC44

    description_lines = [
        f"{cabin_emoji} **{t.cabin.title()}** · {program_emoji} {t.program.title()}",
        f"🗓️ **{t.flight_date}** · ✈ {t.flight_no}",
        f"⏰ {t.departure[11:16] if len(t.departure) > 11 else t.departure} → {t.arrival[11:16] if len(t.arrival) > 11 else t.arrival}",
        f"💰 **{t.miles:,} miles** + ${t.taxes_usd:.0f} taxes",
    ]
    if t.is_new_low and t.prev_low_miles:
        description_lines.append(
            f"📉 Previous low: {t.prev_low_miles:,} miles (↓{t.drop_pct}%)"
        )

    footer_text = f"wombat-miles · alert #{t.alert.id}"
    if t.alert.max_miles:
        footer_text += f" · threshold ≤ {t.alert.max_miles:,} miles"

    return {
        "title": title,
        "description": "\n".join(description_lines),
        "color": color,
        "footer": {"text": footer_text},
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


def _send_webhook(webhook_url: str, t: TriggeredAlert) -> bool:
    """Send a single webhook notification."""
    embed = build_discord_embed(t)
    payload = json.dumps({"embeds": [embed]}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 204)
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        logger.warning("Webhook failed (%s): %s", webhook_url[:50], e)
        return False


def _send_email(email_config: EmailConfig, to_addr: str, t: TriggeredAlert) -> bool:
    """Send a single email notification."""
    # Build email content
    subject = f"🦘 Award Alert: {t.origin} → {t.destination}"
    if t.is_new_low:
        subject += " 🔥 NEW LOW!"

    cabin_emoji = {"economy": "🪑", "business": "🛋️", "first": "👑"}.get(t.cabin, "✈️")
    program_emoji = {"alaska": "🌲", "aeroplan": "🍁"}.get(t.program, "✈️")
    
    body_lines = [
        f"{cabin_emoji} {t.cabin.title()} · {program_emoji} {t.program.title()}",
        f"🗓️ {t.flight_date} · ✈ {t.flight_no}",
        f"⏰ {t.departure} → {t.arrival}",
        f"💰 {t.miles:,} miles + ${t.taxes_usd:.0f} taxes",
    ]
    if t.is_new_low and t.prev_low_miles:
        body_lines.append(f"📉 Previous low: {t.prev_low_miles:,} miles (↓{t.drop_pct}%)")
    body_lines.append("")
    body_lines.append(f"— wombat-miles alert #{t.alert.id}")
    
    body = "\n".join(body_lines)

    # Create message
    msg = MIMEMultipart("alternative")
    msg["From"] = email_config.from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    # Send via SMTP
    try:
        if email_config.use_tls:
            server = smtplib.SMTP(email_config.smtp_host, email_config.smtp_port, timeout=10)
            server.starttls()
        else:
            server = smtplib.SMTP(email_config.smtp_host, email_config.smtp_port, timeout=10)
        
        server.login(email_config.smtp_user, email_config.smtp_pass)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        logger.warning("Email failed (to %s): %s", to_addr, e)
        return False


def fire_alert(t: TriggeredAlert, dry_run: bool = False) -> bool:
    """Send webhook + email notifications for a triggered alert.

    Records the fired alert in alert_history (even on dry_run).

    Returns:
        True if at least one notification was sent (or dry_run=True), False if all failed.
    """
    success_count = 0
    total_attempts = 0

    # Send webhooks
    if t.alert.webhooks and not dry_run:
        for webhook_url in t.alert.webhooks:
            total_attempts += 1
            if _send_webhook(webhook_url, t):
                success_count += 1
    
    # Send emails
    if t.alert.email_to and t.alert.email_config and not dry_run:
        email_config = get_email_config(t.alert.email_config)
        if email_config:
            for to_addr in t.alert.email_to:
                total_attempts += 1
                if _send_email(email_config, to_addr, t):
                    success_count += 1
        else:
            logger.warning("Email config '%s' not found, skipping email notifications", t.alert.email_config)
    
    if dry_run:
        logger.info("[dry-run] Would notify: %s %s %d miles", t.origin, t.flight_date, t.miles)
        success_count = 1  # treat dry-run as success

    # Log to alert_history regardless of success (audit trail)
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO alert_history
            (alert_id, flight_no, flight_date, cabin, program, miles, taxes_usd, is_new_low, fired_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            t.alert.id,
            t.flight_no,
            t.flight_date,
            t.cabin,
            t.program,
            t.miles,
            t.taxes_usd,
            1 if t.is_new_low else 0,
            time.time(),
        ),
    )
    conn.commit()
    conn.close()
    
    return success_count > 0 or total_attempts == 0


def get_alert_history(alert_id: Optional[int] = None, limit: int = 50) -> list[dict]:
    """Return recent alert fire history."""
    conn = _get_conn()
    if alert_id:
        rows = conn.execute(
            "SELECT * FROM alert_history WHERE alert_id = ? ORDER BY fired_at DESC LIMIT ?",
            (alert_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM alert_history ORDER BY fired_at DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
