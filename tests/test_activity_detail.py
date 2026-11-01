"""Unit tests for Activity Detail routes, analytics, and repository methods."""

import io
import json
from unittest.mock import MagicMock, patch
import pytest
from PIL import Image

from kinetiqo.analytics.activity_summary import (
    calculate_coggan_zones,
    calculate_hr_zones,
    calculate_climb_breakdown,
    calculate_mmp_summary,
    build_activity_analytics,
)
from kinetiqo.web.app import app


class DummyActivityDetailRepo:
    def __init__(self, activity=None, streams=None, profile=None):
        self._activity = activity or {
            "id": 999123,
            "activity_id": 999123,
            "name": "Morning Alpine Ride",
            "type": "Ride",
            "sport": "Ride",
            "distance": 45000.0,
            "moving_time": 5400,
            "elapsed_time": 5800,
            "total_elevation_gain": 850.0,
            "start_date": "2026-05-18T09:30:00+00:00",
            "average_speed": 8.33,
            "max_speed": 16.5,
            "average_heartrate": 145,
            "max_heartrate": 178,
            "average_cadence": 86,
            "average_watts": 210.0,
            "max_watts": 650.0,
            "weighted_average_watts": 235.0,
            "device_watts": True,
            "calories": 1150.0,
            "kilojoules": 1134.0,
            "achievement_count": 3,
            "pr_count": 1,
            "suffer_score": 110,
            "average_temp": 19.5,
            "elev_high": 1250.0,
            "elev_low": 400.0,
            "gear_id": "b12345",
            "has_heartrate": True,
            "workout_type": 10,
            "trophies": {"1": 1, "2": 0},
            "ai_responses": {"agent-ai-coach": "Great sustained pacing and hill climbs."},
            "weather_temp_min": 17.0,
            "weather_temp_max": 22.0,
            "weather_temp_avg": 19.5,
            "weather_condition": "Partly Cloudy",
            "weather_condition_icon": "partly-cloudy-day",
            "weather_wind_deg": 180,
            "weather_wind_speed": 12.5,
            "weather_wind_gust_max": 22.0,
            "weather_precipitation": "0.0",
        }
        self._streams = streams or [
            {"ts": i, "distance": i * 10.0, "altitude": 400.0 + (i * 0.1), "heartrate": 130 + (i % 30),
             "watts": 200.0 + (i % 100), "cadence": 85, "speed": 8.0, "lat": 50.0 + (i * 0.0001),
             "lng": 14.0 + (i * 0.0001), "grade_smooth": 2.0, "moving": True}
            for i in range(100)
        ]
        self._profile = profile or {
            "athlete_id": 1,
            "ftp": 250,
            "weight": 72.0,
            "strava_agents_config": json.dumps({
                "enabled": True,
                "agents": [
                    {"name": "coach", "prompt": "Analyze workout pacing."},
                    {"name": "witty", "prompt": "Short joke summary."}
                ]
            })
        }
        self.updated_ai_responses = None

    def get_activity_detail(self, activity_id):
        if str(activity_id) == str(self._activity.get("id")):
            return dict(self._activity)
        return None

    def get_profile(self):
        return dict(self._profile)

    def get_stream_coverage(self, activity_id):
        return {"has_streams": True, "count": len(self._streams)}

    def get_activity_stream_window(self, activity_id, columns, max_rows=20000):
        if str(activity_id) == str(self._activity.get("id")):
            return list(self._streams[:max_rows])
        return []

    def get_activity_weather(self, activity_id):
        return {"temp_avg": 19.5}

    def update_activity_ai_responses(self, activity_id, ai_responses):
        self.updated_ai_responses = ai_responses
        self._activity["ai_responses"] = ai_responses

    def get_activity_name(self, activity_id):
        return self._activity.get("name")


# ─── 1. Unit Tests for Analytics Computations ─────────────────────────────────

def test_calculate_coggan_zones():
    watts = [100.0, 150.0, 200.0, 240.0, 280.0, 320.0, 450.0]
    ftp = 250.0
    zones = calculate_coggan_zones(watts, ftp)
    assert len(zones) == 7
    assert zones[0]["zone"] == "Z1"
    assert zones[0]["name"] == "Active Recovery"
    assert zones[0]["seconds"] >= 1
    # Check total percentage sums to ~100%
    total_pct = sum(z["percent"] for z in zones)
    assert 99.0 <= total_pct <= 101.0


def test_calculate_hr_zones():
    hrs = [110, 125, 140, 155, 175]
    max_hr = 190
    zones = calculate_hr_zones(hrs, max_hr)
    assert len(zones) == 5
    assert zones[0]["zone"] == "Z1"
    assert zones[4]["zone"] == "Z5"
    assert sum(z["seconds"] for z in zones) == len(hrs)


def test_calculate_climb_breakdown():
    dist = [0.0, 100.0, 200.0, 300.0]
    alt = [100.0, 105.0, 105.0, 100.0]  # Climb (5%), Flat (0%), Descent (-5%)
    grades = [None, 5.0, 0.0, -5.0]
    res = calculate_climb_breakdown(dist, alt, grades)
    assert res["climb_km"] > 0
    assert res["flat_km"] > 0
    assert res["desc_km"] > 0
    assert res["max_grade"] == 5.0
    assert res["min_grade"] == -5.0


def test_calculate_mmp_summary():
    ts = list(range(100))
    watts = [250.0] * 100
    ftp = 250.0
    mmp = calculate_mmp_summary(ts, watts, ftp)
    assert len(mmp) == 6
    assert mmp[0]["duration"] == 5
    assert mmp[0]["watts"] == 250
    assert mmp[0]["pct_ftp"] == 100


def test_build_activity_analytics():
    rows = [
        {"ts": i, "watts": 200 + i, "heartrate": 140, "distance": i * 10.0, "altitude": 300.0, "grade_smooth": 0.0}
        for i in range(20)
    ]
    analytics = build_activity_analytics(rows, ftp=250, max_hr=190)
    assert "coggan_zones" in analytics
    assert "hr_zones" in analytics
    assert "mmp_table" in analytics
    assert "climb_stats" in analytics


# ─── 2. Web Route Tests ───────────────────────────────────────────────────────

@pytest.fixture
def test_client(monkeypatch):
    app.config["LOGIN_DISABLED"] = True
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    dummy_repo = DummyActivityDetailRepo()
    monkeypatch.setattr("kinetiqo.web.app.get_db", lambda: dummy_repo)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = "admin"
        sess["athlete_id"] = 1
    return client, dummy_repo


def test_activity_detail_page_found(test_client):
    client, repo = test_client
    resp = client.get("/activity/999123")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Morning Alpine Ride" in html
    assert "Telemetry Streams" in html
    assert "AI Analysis &amp; Coaching Insights" in html or "AI Analysis & Coaching Insights" in html
    assert "Coggan Power Zones" in html
    assert "Peak Power (MMP)" in html
    assert "Stored Activity Weather" in html
    assert "OpenStreetMap" in html
    assert 'value="openstreetmap"' in html


def test_activity_detail_page_not_found(test_client):
    client, repo = test_client
    resp = client.get("/activity/99999999")
    assert resp.status_code == 302
    assert "/activities" in resp.headers["Location"]


def test_activity_streams_api(test_client):
    client, repo = test_client
    resp = client.get("/api/activity/999123/streams?max_points=50")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["has_streams"] is True
    assert len(data["points"]) > 0
    assert "altitude" in data["points"][0]
    assert "watts" in data["points"][0]
    assert data["bounds"] is not None


def test_activity_ai_analyze_success(test_client, monkeypatch):
    client, repo = test_client

    # Mock ChatService and run_agent_prompt
    with patch("kinetiqo.chat.service.ChatService") as mock_chat_cls, \
         patch("kinetiqo.chat.agent_runner.run_agent_prompt") as mock_run_agent:
        mock_run_agent.return_value = ("Strong effort on the climbs, well paced.", "generated")

        resp = client.post(
            "/api/activity/999123/ai-analyze",
            json={"agent_name": "coach", "custom_directive": "Focus on climbing"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["response"] == "Strong effort on the climbs, well paced."
        assert data["agent_name"] == "coach"
        assert repo.updated_ai_responses.get("agent-ai-coach") == "Strong effort on the climbs, well paced."


def test_activity_ai_analyze_unconfigured_agent(test_client):
    client, repo = test_client
    resp = client.post(
        "/api/activity/999123/ai-analyze",
        json={"agent_name": "nonexistent-agent"},
    )
    assert resp.status_code == 422
    data = resp.get_json()
    assert data["success"] is False
    assert "not configured" in data["error"]


def test_activity_photo_upload_and_clear(test_client, tmp_path, monkeypatch):
    client, repo = test_client

    # Create dummy PNG bytes
    img = Image.new("RGB", (100, 100), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    # Upload photo
    resp = client.post(
        "/api/activity/upload/999123",
        data={"file": (io.BytesIO(png_bytes), "test.png")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200

    # Get photo
    resp_get = client.get("/api/activity/photo/999123")
    assert resp_get.status_code == 200
    assert resp_get.mimetype == "image/png"

    # Clear photo
    resp_clear = client.post("/api/activity/clear-image/999123")
    assert resp_clear.status_code == 200

    # Photo should now be 404
    resp_get_404 = client.get("/api/activity/photo/999123")
    assert resp_get_404.status_code == 404


def test_activity_export_mocked(test_client, monkeypatch):
    client, repo = test_client

    mock_page = MagicMock()
    mock_page.pdf.return_value = b"%PDF-1.4 dummy pdf bytes"
    mock_element = MagicMock()
    mock_element.screenshot.return_value = b"\x89PNG\r\n\x1a\n dummy png bytes"
    mock_page.locator.return_value = mock_element

    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page
    mock_browser = MagicMock()
    mock_browser.new_context.return_value = mock_context

    mock_playwright = MagicMock()
    mock_playwright.chromium.launch.return_value = mock_browser

    class MockSyncPlaywright:
        def __enter__(self):
            return mock_playwright
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: MockSyncPlaywright())

    # PNG Export test
    resp_png = client.post(
        "/api/activity/export/999123",
        json={"format": "png", "width": 1280, "ratio": "auto"},
    )
    assert resp_png.status_code == 200
    assert resp_png.mimetype == "image/png"
    assert b"dummy png" in resp_png.data

    # PDF Export test
    resp_pdf = client.post(
        "/api/activity/export/999123",
        json={"format": "pdf", "width": 1280, "ratio": "4:3"},
    )
    assert resp_pdf.status_code == 200
    assert resp_pdf.mimetype == "application/pdf"
    assert b"dummy pdf" in resp_pdf.data


def test_activity_detail_zero_arg_get_profile_contract(test_client):
    """Ensure activity_detail route complies with DatabaseRepository.get_profile() 0-arg contract."""
    client, repo = test_client
    with pytest.raises(TypeError):
        repo.get_profile(123)

    resp = client.get("/activity/999123")
    assert resp.status_code == 200



