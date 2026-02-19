"""Tests for the alerts module."""

import json
import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from datetime import date

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_alerts_db(tmp_path, monkeypatch):
    """Redirect the alerts DB to a temp directory for each test."""
    monkeypatch.setattr("wombat_miles.alerts.ALERTS_DIR", tmp_path)
    monkeypatch.setattr("wombat_miles.alerts.ALERTS_DB", tmp_path / "alerts.db")
    yield


@pytest.fixture
def sample_search_results():
    """Build a minimal list of SearchResult objects with one business-class fare."""
    from wombat_miles.models import Flight, FlightFare, SearchResult

    fare = FlightFare(
        miles=65_000,
        cash=85.0,
        cabin="business",
        booking_class="J",
        program="alaska",
    )
    flight = Flight(
        flight_no="AS 1",
        origin="SFO",
        destination="NRT",
        departure="2025-06-01 10:00:00",
        arrival="2025-06-02 14:00:00",
        duration=600,
        aircraft="789",
        fares=[fare],
    )
    result = MagicMock()
    result.origin = "SFO"
    result.destination = "NRT"
    result.date = "2025-06-01"
    result.flights = [flight]
    result.errors = []
    return [result]


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------

class TestAlertCRUD:
    def test_add_and_list(self):
        from wombat_miles import alerts

        aid = alerts.add_alert("SFO", "NRT", cabin="business", max_miles=70_000)
        assert aid == 1

        all_alerts = alerts.list_alerts()
        assert len(all_alerts) == 1
        a = all_alerts[0]
        assert a.origin == "SFO"
        assert a.destination == "NRT"
        assert a.cabin == "business"
        assert a.max_miles == 70_000
        assert a.enabled == 1

    def test_add_normalizes_case(self):
        from wombat_miles import alerts

        alerts.add_alert("sfo", "nrt")
        a = alerts.list_alerts()[0]
        assert a.origin == "SFO"
        assert a.destination == "NRT"

    def test_remove(self):
        from wombat_miles import alerts

        aid = alerts.add_alert("SFO", "NRT")
        assert alerts.remove_alert(aid) is True
        assert alerts.list_alerts() == []

    def test_remove_nonexistent(self):
        from wombat_miles import alerts

        assert alerts.remove_alert(999) is False

    def test_get_alert(self):
        from wombat_miles import alerts

        aid = alerts.add_alert("SFO", "NRT", cabin="business")
        a = alerts.get_alert(aid)
        assert a is not None
        assert a.cabin == "business"

    def test_enable_disable(self):
        from wombat_miles import alerts

        aid = alerts.add_alert("SFO", "NRT")
        alerts.enable_alert(aid, enabled=False)
        assert alerts.list_alerts() == []  # disabled, not returned
        assert alerts.list_alerts(include_disabled=True)[0].enabled == 0
        alerts.enable_alert(aid, enabled=True)
        assert len(alerts.list_alerts()) == 1

    def test_multiple_alerts(self):
        from wombat_miles import alerts

        alerts.add_alert("SFO", "NRT", cabin="business")
        alerts.add_alert("SFO", "YYZ", cabin="economy")
        alerts.add_alert("LAX", "LHR")
        assert len(alerts.list_alerts()) == 3


# ---------------------------------------------------------------------------
# check_alerts tests
# ---------------------------------------------------------------------------

class TestCheckAlerts:
    def test_matches_route_and_threshold(self, sample_search_results):
        from wombat_miles import alerts

        aid = alerts.add_alert("SFO", "NRT", cabin="business", max_miles=70_000)
        triggered = alerts.check_alerts(sample_search_results)
        assert len(triggered) == 1
        t = triggered[0]
        assert t.miles == 65_000
        assert t.cabin == "business"
        assert t.alert.id == aid

    def test_no_match_above_threshold(self, sample_search_results):
        from wombat_miles import alerts

        alerts.add_alert("SFO", "NRT", cabin="business", max_miles=60_000)  # 65k > 60k
        triggered = alerts.check_alerts(sample_search_results)
        assert triggered == []

    def test_no_match_wrong_route(self, sample_search_results):
        from wombat_miles import alerts

        alerts.add_alert("LAX", "NRT", cabin="business", max_miles=70_000)
        triggered = alerts.check_alerts(sample_search_results)
        assert triggered == []

    def test_no_threshold_triggers_on_any_fare(self, sample_search_results):
        from wombat_miles import alerts

        alerts.add_alert("SFO", "NRT")  # no max_miles
        triggered = alerts.check_alerts(sample_search_results)
        assert len(triggered) == 1

    def test_cabin_filter(self, sample_search_results):
        from wombat_miles import alerts

        alerts.add_alert("SFO", "NRT", cabin="first")  # only first class
        triggered = alerts.check_alerts(sample_search_results)
        assert triggered == []

    def test_program_filter(self, sample_search_results):
        from wombat_miles import alerts

        alerts.add_alert("SFO", "NRT", program="aeroplan")  # wrong program
        triggered = alerts.check_alerts(sample_search_results)
        assert triggered == []

    def test_dedup_prevents_double_fire(self, sample_search_results):
        from wombat_miles import alerts

        aid = alerts.add_alert("SFO", "NRT", cabin="business", max_miles=70_000)
        # First check + fire
        triggered = alerts.check_alerts(sample_search_results)
        assert len(triggered) == 1
        alerts.fire_alert(triggered[0])  # log to alert_history

        # Second check — should be suppressed within 24h
        triggered2 = alerts.check_alerts(sample_search_results, dedup_hours=24)
        assert len(triggered2) == 0

    def test_dedup_zero_allows_refire(self, sample_search_results):
        from wombat_miles import alerts

        aid = alerts.add_alert("SFO", "NRT", cabin="business", max_miles=70_000)
        triggered = alerts.check_alerts(sample_search_results)
        alerts.fire_alert(triggered[0])

        # dedup_hours=0 → always fire
        triggered2 = alerts.check_alerts(sample_search_results, dedup_hours=0)
        assert len(triggered2) == 1


# ---------------------------------------------------------------------------
# fire_alert / webhook tests
# ---------------------------------------------------------------------------

class TestFireAlert:
    def _make_triggered(self):
        from wombat_miles.alerts import Alert, TriggeredAlert

        alert = Alert(
            id=1,
            origin="SFO",
            destination="NRT",
            cabin="business",
            program="alaska",
            max_miles=70_000,
            discord_webhook=None,
            enabled=1,
            created_at="2025-01-01",
        )
        return TriggeredAlert(
            alert=alert,
            flight_no="AS 1",
            origin="SFO",
            destination="NRT",
            flight_date="2025-06-01",
            departure="2025-06-01 10:00:00",
            arrival="2025-06-02 14:00:00",
            duration=600,
            cabin="business",
            program="alaska",
            miles=65_000,
            taxes_usd=85.0,
        )

    def test_dry_run_no_http_call(self):
        from wombat_miles import alerts

        t = self._make_triggered()
        t.alert.discord_webhook = "https://discord.com/api/webhooks/fake"

        with patch("urllib.request.urlopen") as mock_open:
            result = alerts.fire_alert(t, dry_run=True)
            mock_open.assert_not_called()
        assert result is True  # dry_run always True

    def test_webhook_sent_on_fire(self):
        from wombat_miles import alerts

        t = self._make_triggered()
        t.alert.discord_webhook = "https://discord.com/api/webhooks/fake"

        mock_resp = MagicMock()
        mock_resp.status = 204
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = alerts.fire_alert(t, dry_run=False)

        assert result is True

    def test_no_webhook_configured(self):
        from wombat_miles import alerts

        t = self._make_triggered()
        t.alert.discord_webhook = None
        result = alerts.fire_alert(t, dry_run=False)
        assert result is True  # no webhook = no-op, not failure

    def test_history_recorded(self):
        from wombat_miles import alerts

        t = self._make_triggered()
        t.alert.discord_webhook = None
        alerts.fire_alert(t)

        history = alerts.get_alert_history()
        assert len(history) == 1
        assert history[0]["miles"] == 65_000
        assert history[0]["cabin"] == "business"


# ---------------------------------------------------------------------------
# build_discord_embed tests
# ---------------------------------------------------------------------------

class TestBuildDiscordEmbed:
    def _make_triggered(self, is_new_low=False):
        from wombat_miles.alerts import Alert, TriggeredAlert

        alert = Alert(
            id=1, origin="SFO", destination="NRT",
            cabin="business", program="alaska", max_miles=70_000,
            discord_webhook=None, enabled=1, created_at="",
        )
        return TriggeredAlert(
            alert=alert,
            flight_no="AS 1",
            origin="SFO", destination="NRT",
            flight_date="2025-06-01",
            departure="2025-06-01 10:00:00",
            arrival="2025-06-02 14:00:00",
            duration=600,
            cabin="business",
            program="alaska",
            miles=65_000,
            taxes_usd=85.0,
            is_new_low=is_new_low,
            prev_low_miles=72_000 if is_new_low else None,
        )

    def test_embed_keys(self):
        from wombat_miles.alerts import build_discord_embed

        embed = build_discord_embed(self._make_triggered())
        assert "title" in embed
        assert "description" in embed
        assert "color" in embed
        assert "footer" in embed

    def test_new_low_flag(self):
        from wombat_miles.alerts import build_discord_embed

        embed = build_discord_embed(self._make_triggered(is_new_low=True))
        assert "NEW LOW" in embed["title"]
        assert "72,000" in embed["description"]

    def test_normal_alert_no_new_low_badge(self):
        from wombat_miles.alerts import build_discord_embed

        embed = build_discord_embed(self._make_triggered(is_new_low=False))
        assert "NEW LOW" not in embed["title"]

    def test_miles_formatted(self):
        from wombat_miles.alerts import build_discord_embed

        embed = build_discord_embed(self._make_triggered())
        assert "65,000" in embed["description"]


# ---------------------------------------------------------------------------
# Alert.description property
# ---------------------------------------------------------------------------

class TestAlertDescription:
    def test_description_with_all_fields(self):
        from wombat_miles.alerts import Alert

        a = Alert(
            id=1, origin="SFO", destination="NRT",
            cabin="business", program="alaska", max_miles=70_000,
            discord_webhook=None, enabled=1, created_at="",
        )
        desc = a.description
        assert "SFO → NRT" in desc
        assert "Business" in desc
        assert "70,000" in desc
        assert "alaska" in desc

    def test_description_minimal(self):
        from wombat_miles.alerts import Alert

        a = Alert(
            id=1, origin="SFO", destination="NRT",
            cabin=None, program="all", max_miles=None,
            discord_webhook=None, enabled=1, created_at="",
        )
        desc = a.description
        assert "SFO → NRT" in desc
        assert "Business" not in desc
