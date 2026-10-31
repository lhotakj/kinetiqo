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


def test_sync_start_loading_indicator(monkeypatch):
    app.config['LOGIN_DISABLED'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()

    class SyncJobRepo(DummyRepo):
        def recover_expired_sync_jobs(self):
            return 0

        def has_active_sync_job(self, owner_id):
            return False

        def create_sync_job(self, job_id, sync_type, owner_id, options):
            self.job_id = job_id
            self.options = options

        def close(self):
            pass

    class UnstartedThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

    dummy_repo = SyncJobRepo()
    monkeypatch.setattr('kinetiqo.web.app.create_repository', lambda cfg: dummy_repo)
    monkeypatch.setattr('kinetiqo.web.app.ensure_startup_profile_sync', lambda: None)
    monkeypatch.setattr('kinetiqo.web.app.threading.Thread', UnstartedThread)

    for sync_type in ['fast', 'full']:
        resp = client.post(f'/sync/start/{sync_type}')
        assert resp.status_code == 200
        html_text = resp.get_data(as_text=True)
        assert f'/api/sync/stream/{dummy_repo.job_id}' in html_text
        assert 'sse-connect=' in html_text
        assert 'Sync in progress...' in html_text
        assert dummy_repo.options['full_sync'] is (sync_type == 'full')
        assert dummy_repo.options['retrigger_ai_agents'] is False

    resp = client.post('/sync/start/fast', data={'retrigger_ai_agents': 'on'})
    assert resp.status_code == 200
    assert dummy_repo.options['retrigger_ai_agents'] is True

def test_web_startup_interrupts_persisted_sync_jobs_once(monkeypatch):
    import importlib

    web_module = importlib.import_module('kinetiqo.web.app')
    monkeypatch.setattr(web_module, '_startup_sync_done', False)
    monkeypatch.setattr(web_module, '_startup_sync_jobs_cleared', False)
    monkeypatch.setitem(app.config, 'TESTING', False)

    class StartupRepo:
        def __init__(self):
            self.interruptions = 0

        def interrupt_active_sync_jobs(self):
            self.interruptions += 1

    repo = StartupRepo()
    monkeypatch.setattr(web_module, 'get_db', lambda: repo)
    monkeypatch.setattr(web_module, 'sync_all_profile_env_vars', lambda config, repository: None)

    web_module.ensure_startup_profile_sync()
    web_module.ensure_startup_profile_sync()

    assert repo.interruptions == 1


def test_fastsync_post_accepts_rendered_form_csrf_token(monkeypatch):
    import re

    monkeypatch.setitem(app.config, 'LOGIN_DISABLED', True)
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    client = app.test_client()

    class SyncJobRepo(DummyRepo):
        def get_profile(self):
            return {'enable_weather_data': False}

        def recover_expired_sync_jobs(self):
            return 0

        def has_active_sync_job(self, owner_id):
            return False

        def create_sync_job(self, job_id, sync_type, owner_id, options):
            self.job_id = job_id

        def close(self):
            pass

    class UnstartedThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

    dummy_repo = SyncJobRepo()
    monkeypatch.setattr('kinetiqo.web.app.create_repository', lambda cfg: dummy_repo)
    monkeypatch.setattr('kinetiqo.web.app.ensure_startup_profile_sync', lambda: None)
    monkeypatch.setattr('kinetiqo.web.app.threading.Thread', UnstartedThread)

    page = client.get('/fastsync')
    assert page.status_code == 200
    page_html = page.get_data(as_text=True)
    assert '#syncCsrfToken' in page_html
    assert 'id="retriggerAiAgents"' in page_html
    assert 'window.confirm' not in page_html
    match = re.search(r'id="syncCsrfToken" type="hidden" name="csrf_token" value="([^"]+)"',
                      page_html)
    assert match

    response = client.post('/sync/start/fast', data={'csrf_token': match.group(1)})
    assert response.status_code == 200


def test_base_template_authenticated_vs_anonymous_user(monkeypatch):
    """Base template renders user initial when authenticated, and fallback 'U' when anonymous."""
    app.config['LOGIN_DISABLED'] = True
    client = app.test_client()
    monkeypatch.setattr('kinetiqo.web.app.ensure_startup_profile_sync', lambda: None)

    class DummyUser:
        is_authenticated = True
        id = "jarda"

    # Authenticated user
    monkeypatch.setattr('kinetiqo.web.app.current_user', DummyUser())
    resp_auth = client.get('/login')
    html_auth = resp_auth.get_data(as_text=True)
    # Login page extends base.html or has its own template, check another endpoint that extends base.html
    class PosterDummyRepo(DummyRepo):
        def get_activities_by_ids(self, activity_ids):
            return [{'id': activity_ids[0], 'name': 'Ride', 'distance': 10000}]

    monkeypatch.setattr('kinetiqo.web.app.create_repository', lambda cfg: PosterDummyRepo())
    resp_poster = client.get('/poster/100')
    html_poster = resp_poster.get_data(as_text=True)
    assert 'J' in html_poster
    assert 'jarda' in html_poster

    # Anonymous user lacking 'id' attribute
    class AnonymousUser:
        is_authenticated = False

    monkeypatch.setattr('kinetiqo.web.app.current_user', AnonymousUser())
    resp_anon = client.get('/poster/100')
    assert resp_anon.status_code == 200
    html_anon = resp_anon.get_data(as_text=True)
    assert 'U' in html_anon


def test_sync_stream_replays_owned_job_events(monkeypatch):
    """The read-only stream replays events for the owning user."""
    app.config['LOGIN_DISABLED'] = True
    client = app.test_client()
    monkeypatch.setattr('kinetiqo.web.app.ensure_startup_profile_sync', lambda: None)

    class SyncJobRepo(DummyRepo):
        def get_sync_job(self, job_id):
            return {'job_id': job_id, 'owner_id': 'admin', 'status': 'completed'}

        def get_sync_job_events(self, job_id, after_sequence):
            if after_sequence == 0:
                return [{'event_sequence': 1, 'payload': {'html': '<p>progress</p>'}}]
            return []

        def close(self):
            pass

    monkeypatch.setattr('kinetiqo.web.app.create_repository', lambda cfg: SyncJobRepo())
    response = client.get('/api/sync/stream/job-1')
    assert response.status_code == 200
    assert b'id: 1\nevent: message\ndata: <p>progress</p>' in b''.join(response.response)
