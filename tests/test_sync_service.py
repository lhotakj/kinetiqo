import requests
import types
from unittest.mock import MagicMock

from kinetiqo.sync import SyncService, DESC_NOT_CONFIGURED, DESC_SKIPPED, DESC_UNCHANGED, DESC_UPDATED, DESC_FAILED


class DummyDescriptionContext:
    def __init__(self, rendered):
        self.rendered = rendered

    def render_for_activity(self, template, start_date, existing_description, activity=None):
        return self.rendered


class DummyHTTPError(requests.exceptions.HTTPError):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.response = types.SimpleNamespace(status_code=status_code)


def make_service():
    svc = object.__new__(SyncService)
    svc.config = types.SimpleNamespace()
    svc.strava = types.SimpleNamespace()
    svc.db = types.SimpleNamespace()
    svc._update_strava_unauthorized = False
    svc._rate_limit_warnings_queue = []
    return svc


def test_update_strava_not_configured(monkeypatch):
    svc = make_service()
    # get_template_for_activity should return falsy
    monkeypatch.setattr('kinetiqo.sync.get_template_for_activity', lambda cfg, st: None)
    status, msg = svc._update_strava_description(None, {'id': 1, 'sport_type': 'cycling'})
    assert status == DESC_NOT_CONFIGURED
    assert msg is None


def test_update_strava_skipped_when_unauthorized(monkeypatch):
    svc = make_service()
    svc._update_strava_unauthorized = True
    # Ensure template exists so code reaches the unauthorized-check branch
    monkeypatch.setattr('kinetiqo.sync.get_template_for_activity', lambda cfg, st: 'tpl')
    status, msg = svc._update_strava_description(None, {'id': 1, 'sport_type': 'cycling'})
    assert status == DESC_SKIPPED


def test_update_strava_unchanged(monkeypatch):
    svc = make_service()
    monkeypatch.setattr('kinetiqo.sync.get_template_for_activity', lambda cfg, st: 'tpl')
    svc.strava.get_activity_detail = lambda aid: {'description': 'same'}
    desc_ctx = DummyDescriptionContext('same')
    status, msg = svc._update_strava_description(desc_ctx, {'id': 2, 'sport_type': 'cycling', 'start_date': '2020-01-01'})
    assert status == DESC_UNCHANGED
    assert msg is None


def test_update_strava_updated(monkeypatch):
    svc = make_service()
    monkeypatch.setattr('kinetiqo.sync.get_template_for_activity', lambda cfg, st: 'tpl')
    svc.strava.get_activity_detail = lambda aid: {'description': 'old'}
    updated_called = {}

    def fake_update(aid, new):
        updated_called['ok'] = True

    svc.strava.update_activity_description = fake_update
    desc_ctx = DummyDescriptionContext('new')
    status, msg = svc._update_strava_description(desc_ctx, {'id': 3, 'sport_type': 'cycling', 'start_date': '2020-01-02'})
    assert status == DESC_UPDATED
    assert updated_called.get('ok') is True


def test_update_strava_http_401(monkeypatch):
    svc = make_service()
    monkeypatch.setattr('kinetiqo.sync.get_template_for_activity', lambda cfg, st: 'tpl')
    svc.strava.get_activity_detail = lambda aid: {'description': 'old'}

    def raise_http(aid, new):
        raise DummyHTTPError(401)

    svc.strava.update_activity_description = raise_http
    desc_ctx = DummyDescriptionContext('new')
    status, msg = svc._update_strava_description(desc_ctx, {'id': 4, 'sport_type': 'cycling', 'start_date': '2020-01-03'})
    assert status == DESC_FAILED
    assert svc._update_strava_unauthorized is True
    assert 'disabling' in msg.lower()


def test_update_strava_http_other(monkeypatch):
    svc = make_service()
    monkeypatch.setattr('kinetiqo.sync.get_template_for_activity', lambda cfg, st: 'tpl')
    svc.strava.get_activity_detail = lambda aid: {'description': 'old'}

    def raise_http(aid, new):
        raise DummyHTTPError(500)

    svc.strava.update_activity_description = raise_http
    desc_ctx = DummyDescriptionContext('new')
    status, msg = svc._update_strava_description(desc_ctx, {'id': 5, 'sport_type': 'cycling', 'start_date': '2020-01-04'})
    assert status == DESC_FAILED
    assert svc._update_strava_unauthorized is False
    assert msg is not None


def test_description_update_activity_ids_ordering(monkeypatch):
    svc = make_service()
    # Ensure UPDATE_STRAVA_MAX_ITEMS default is available from config module
    monkeypatch.setattr('kinetiqo.sync.UPDATE_STRAVA_MAX_ITEMS', 2)
    monkeypatch.setattr('kinetiqo.sync.get_template_for_activity', lambda cfg, st: 'tpl')
    activities = [
        {'id': 10, 'start_date': '2020-01-01'},
        {'id': 20, 'start_date': '2021-01-01'},
        {'id': 30, 'start_date': '2019-01-01'},
    ]
    ids = svc._description_update_activity_ids(activities)
    assert ids == {'20', '10'}


def test_retrigger_ai_agents_replaces_successes_and_retains_failed_cache(monkeypatch):
    svc = make_service()
    svc.db = MagicMock()
    monkeypatch.setattr(
        'kinetiqo.sync.get_template_for_activity',
        lambda cfg, sport: '{{agent-ai-road}} {{agent-ai-climb}}',
    )
    handler = MagicMock(side_effect=[
        ('Fresh road response', 'generated'),
        ('', 'failed'),
    ])
    context = types.SimpleNamespace(ai_handler=handler)
    activity = {
        'id': 42,
        'sport_type': 'Ride',
        'ai_responses': {
            'agent-ai-road': 'Old road response',
            'agent-ai-climb': 'Old climb response',
            'agent-ai-unused': 'Unused response',
        },
    }

    failed_agents = svc._retrigger_ai_agents(context, activity, {'road', 'climb'})

    assert failed_agents == ['climb (failed)']
    assert activity['ai_responses'] == {
        'agent-ai-road': 'Fresh road response',
        'agent-ai-climb': 'Old climb response',
        'agent-ai-unused': 'Unused response',
    }
    svc.db.update_activity_ai_responses.assert_called_once_with(42, activity['ai_responses'])


def test_sync_skips_activity_detail_for_existing_activities(monkeypatch):
    from collections import deque
    svc = make_service()
    mock_db = MagicMock()
    mock_db.acquire_sync_lease.return_value = True
    mock_db.get_synced_activity_ids.return_value = {'1001', '1002'}
    mock_db.get_profile.return_value = {}
    svc.db = mock_db

    mock_strava = MagicMock()
    # 2 existing activities, both having achievements
    activities = [
        {'id': 1001, 'name': 'Ride 1', 'sport_type': 'Ride', 'achievement_count': 5, 'start_date': '2024-01-01T00:00:00Z'},
        {'id': 1002, 'name': 'Ride 2', 'sport_type': 'Ride', 'achievement_count': 3, 'start_date': '2024-01-02T00:00:00Z'},
    ]
    mock_strava.get_activities.side_effect = lambda container, after=None: (container.extend(activities), iter([]))[1]
    svc.strava = mock_strava

    # Disallow description updates so needs_desc is False
    monkeypatch.setattr('kinetiqo.sync.any_update_strava_template_configured', lambda cfg: False)
    monkeypatch.setattr('kinetiqo.sync.load_verified_trophies', lambda: {})
    monkeypatch.setattr('kinetiqo.sync.save_verified_trophies', MagicMock())

    deque(svc.sync(full_sync=True, trigger='test'), maxlen=0)

    # Both activities should be written to DB, but get_activity_detail should NOT be called in Phase 1!
    assert mock_db.write_activity.call_count == 2
    mock_strava.get_activity_detail.assert_not_called()


def test_sync_halts_immediately_on_strava_auth_error(monkeypatch):
    from collections import deque
    from kinetiqo.strava import StravaAuthError

    svc = make_service()
    mock_db = MagicMock()
    mock_db.acquire_sync_lease.return_value = True
    mock_db.get_synced_activity_ids.return_value = set()  # new activities
    mock_db.get_profile.return_value = {}
    svc.db = mock_db

    mock_strava = MagicMock()
    activities = [
        {'id': 1001, 'name': 'Ride 1', 'sport_type': 'Ride', 'achievement_count': 1, 'start_date': '2024-01-01T00:00:00Z'},
        {'id': 1002, 'name': 'Ride 2', 'sport_type': 'Ride', 'achievement_count': 1, 'start_date': '2024-01-02T00:00:00Z'},
        {'id': 1003, 'name': 'Ride 3', 'sport_type': 'Ride', 'achievement_count': 1, 'start_date': '2024-01-03T00:00:00Z'},
    ]
    mock_strava.get_activities.side_effect = lambda container, after=None: (container.extend(activities), iter([]))[1]
    mock_resp = MagicMock(status_code=401)
    mock_strava.get_activity_detail.side_effect = StravaAuthError("401 Client Error: Unauthorized", response=mock_resp)
    svc.strava = mock_strava

    monkeypatch.setattr('kinetiqo.sync.any_update_strava_template_configured', lambda cfg: False)
    monkeypatch.setattr('kinetiqo.sync.load_verified_trophies', lambda: {})
    monkeypatch.setattr('kinetiqo.sync.save_verified_trophies', MagicMock())

    deque(svc.sync(full_sync=True, trigger='test'), maxlen=0)

    # Crucial assertion: get_activity_detail was called ONLY ONCE and the loop immediately stopped
    assert mock_strava.get_activity_detail.call_count == 1
    mock_strava.get_athlete.assert_not_called()


def test_sync_yields_and_records_rate_limit_warning(monkeypatch):
    """When a 90% rate limit warning is detected, sync yields it and includes in final warnings."""
    svc = make_service()
    svc._rate_limit_warnings_queue = []
    mock_db = MagicMock()
    mock_db.acquire_sync_lease.return_value = True
    mock_db.get_synced_activity_ids.return_value = set()
    mock_db.get_profile.return_value = {}
    svc.db = mock_db

    mock_strava = MagicMock()
    activities = [
        {'id': 1001, 'name': 'Ride 1', 'sport_type': 'Ride', 'achievement_count': 0, 'start_date': '2024-01-01T00:00:00Z'},
    ]
    mock_strava.get_activities.side_effect = lambda container, after=None: (container.extend(activities), iter([]))[1]
    mock_strava.get_athlete.return_value = {'id': 99}
    mock_strava.get_athlete_koms.return_value = []
    # Simulate a rate limit warning queued by the client
    rate_warning = "Strava API rate limit warning: 90% limit has been reached (15-minute: 92/100 requests used, 8 remaining)."
    mock_strava.pop_rate_limit_warnings.return_value = [rate_warning]
    svc.strava = mock_strava

    monkeypatch.setattr('kinetiqo.sync.any_update_strava_template_configured', lambda cfg: False)
    monkeypatch.setattr('kinetiqo.sync.load_verified_trophies', lambda: {})
    monkeypatch.setattr('kinetiqo.sync.save_verified_trophies', MagicMock())

    events = list(svc.sync(full_sync=True, trigger='test'))
    event_texts = "".join(events)

    # Must be yielded during sync and rendered in final warnings card
    assert "90% limit has been reached" in event_texts
    assert "15-minute: 92/100" in event_texts
