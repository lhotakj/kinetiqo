import json
import types
from unittest import mock

import pytest

from kinetiqo.web.app import app


class DummyRepo:
    def __init__(self, distance=None, altitude=None):
        self._distance = distance
        self._altitude = altitude

    def get_elevation_streams_for_activity(self, activity_id):
        return (self._distance, self._altitude)


def test_elevation_from_db(monkeypatch):
    app.config['LOGIN_DISABLED'] = True
    client = app.test_client()

    dummy_repo = DummyRepo(distance=[1, 2, 3], altitude=[10, 20, 30])
    monkeypatch.setattr('kinetiqo.web.app.create_repository', lambda cfg: dummy_repo)

    resp = client.get('/api/poster/elevation/123')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['distance'] == [1, 2, 3]
    assert data['altitude'] == [10, 20, 30]


def test_elevation_from_strava(monkeypatch):
    app.config['LOGIN_DISABLED'] = True
    client = app.test_client()

    # Repo returns None -> force Strava fallback
    dummy_repo = DummyRepo(distance=None, altitude=None)
    monkeypatch.setattr('kinetiqo.web.app.create_repository', lambda cfg: dummy_repo)

    # Patch kinetiqo.strava.StravaClient.get_streams
    class DummyClient:
        def __init__(self, cfg):
            pass

        def get_streams(self, activity_id):
            return {'distance': {'data': [5, 6]}, 'altitude': {'data': [50, 60]}}

    monkeypatch.setattr('kinetiqo.strava.StravaClient', DummyClient)

    resp = client.get('/api/poster/elevation/456')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['distance'] == [5, 6]
    assert data['altitude'] == [50, 60]


def test_poster_page_controls(monkeypatch):
    app.config['LOGIN_DISABLED'] = True
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = 'admin'

    class PosterDummyRepo(DummyRepo):
        def get_activities_by_ids(self, activity_ids):
            return [{'id': activity_ids[0], 'name': 'Morning Ride', 'distance': 10000}]

    dummy_repo = PosterDummyRepo()
    monkeypatch.setattr('kinetiqo.web.app.create_repository', lambda cfg: dummy_repo)

    resp = client.get('/poster/789')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="boxVisible_title"' in html
    assert 'id="boxVisible_stats"' in html
    assert 'id="boxVisible_elevation"' in html
    assert 'data-box-id="boxTitle"' in html
    assert 'data-box-id="boxStats"' in html
    assert 'data-box-id="boxElevation"' in html
    assert 'data-box-id="posterSize"' in html
    assert 'data-box-id="background"' in html
    assert 'id="bgTypeSelect"' in html
    assert 'Poster content' in html
    assert 'id="bgColor"' in html
    assert 'id="clearImageBtn"' in html
    assert 'id="mapProviderSelect"' in html
    assert 'id="mapOpacity"' in html
    assert 'id="mapLineColor"' in html
    assert 'id="mapLineOpacity"' in html
    assert 'id="mapLineWidth"' in html
    assert 'id="posterMap"' in html



