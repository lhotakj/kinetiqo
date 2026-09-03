import types
import pytest

from kinetiqo.db.postgresql import PostgresqlRepository


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
        self.closed = closed
        self._cursor_obj = cursor_obj or DummyCursor()
        self.autocommit = False

    def cursor(self):
        return self._cursor_obj

    def close(self):
        self.closed = True


def make_repo_with_conn(conn):
    repo = object.__new__(PostgresqlRepository)
    repo.config = types.SimpleNamespace(postgresql_database='db', postgresql_host='h', postgresql_port=5432,
                                        postgresql_user='u', postgresql_password='p', postgresql_ssl_mode='disable')
    repo.conn = conn
    repo._from_pool = False
    return repo


def test_flightcheck_success():
    # simulate cursor returning table rows that include activities, streams, logs
    rows = [('activities',), ('streams',), ('logs',)]
    cursor = DummyCursor(rows=rows)
    conn = DummyConn(closed=False, cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    assert repo.flightcheck() is True


def test_flightcheck_missing_table():
    rows = [('activities',), ('streams',)]  # missing logs
    cursor = DummyCursor(rows=rows)
    conn = DummyConn(closed=False, cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    assert repo.flightcheck() is False


def test_ensure_connected_reconnects(monkeypatch):
    # Simulate closed connection that triggers reconnect via _connect
    cursor = DummyCursor()
    conn = DummyConn(closed=True, cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    new_conn = DummyConn(closed=False, cursor_obj=cursor)
    called = {}

    def fake_connect(dbname=None):
        called['ok'] = True
        return new_conn

    monkeypatch.setattr(repo, '_connect', fake_connect)

    # Should not raise and should replace conn
    repo._ensure_connected()
    assert called.get('ok') is True
    assert repo.conn is new_conn
