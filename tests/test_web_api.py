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
