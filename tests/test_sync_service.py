import types
import requests
import pytest

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
