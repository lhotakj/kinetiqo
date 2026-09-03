import types

from kinetiqo.db.firebird import FirebirdRepository


class DummyCursor:
    def __init__(self, rows=None, fetchone_val=None):
        self._rows = rows or []
        self._fetchone_val = fetchone_val

    def execute(self, sql, params=None):
        self._last_sql = sql

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._fetchone_val

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DummyConn:
    def __init__(self, closed=False, cursor_obj=None):
        self._closed = closed
        self._cursor_obj = cursor_obj or DummyCursor()

    def cursor(self):
        return self._cursor_obj

    def close(self):
        self._closed = True

    def is_closed(self):
        return self._closed


def make_repo_with_conn(conn):
    repo = object.__new__(FirebirdRepository)
    repo.config = types.SimpleNamespace(firebird_database='db', firebird_host='h', firebird_port=3050,
                                        firebird_user='u', firebird_password='p')
    repo.conn = conn
    repo._last_verified = 0.0
    return repo


def test_ensure_connected_no_reconnect_when_recently_verified(monkeypatch):
    cursor = DummyCursor()
    conn = DummyConn(closed=False, cursor_obj=cursor)
    repo = make_repo_with_conn(conn)
    # Simulate recently verified
    repo._last_verified = 1000000.0

    # Should return without raising
    repo._ensure_connected()


def test_ensure_connected_reconnects(monkeypatch):
    cursor = DummyCursor()
    conn = DummyConn(closed=True, cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    new_conn = DummyConn(closed=False, cursor_obj=cursor)
    called = {}

    def fake_connect():
        called['ok'] = True
        return new_conn

    monkeypatch.setattr(repo, '_connect', fake_connect)

    repo._ensure_connected()
    assert called.get('ok') is True
    assert repo.conn is new_conn


def test_ensure_database_creates_on_failure(monkeypatch):
    cursor = DummyCursor()
    conn = DummyConn(closed=False, cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    # Simulate initial check failing by making cursor.execute raise
    def bad_execute(sql, params=None):
        raise Exception('db missing')

    cursor.execute = bad_execute

    created = {}

    def fake_create_db(sql):
        created['ok'] = True

    # Ensure firebird.driver.create_database exists
    monkeypatch.setitem(__import__('sys').modules, 'firebird', types.SimpleNamespace(driver=types.SimpleNamespace(create_database=fake_create_db)))

    # Patch _connect to return a new conn after creation
    new_conn = DummyConn(closed=False, cursor_obj=cursor)
    monkeypatch.setattr(repo, '_connect', lambda: new_conn)

    repo._ensure_database()
    assert created.get('ok') is True
