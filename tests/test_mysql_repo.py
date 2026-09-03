import types

from kinetiqo.db.mysql import MySQLRepository


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
        self.database = None

    def cursor(self, dictionary=False):
        return self._cursor_obj

    def close(self):
        self.closed = True

    def ping(self, reconnect=True, attempts=1, delay=0):
        if self.closed:
            raise ConnectionError("closed")


def make_repo_with_conn(conn):
    repo = object.__new__(MySQLRepository)
    repo.config = types.SimpleNamespace(mysql_database='db', mysql_host='h', mysql_port=3306,
                                        mysql_user='u', mysql_password='p')
    repo.conn = conn
    return repo


def test_flightcheck_success():
    rows = [('activities',), ('streams',), ('logs',)]
    cursor = DummyCursor(rows=rows)
    conn = DummyConn(closed=False, cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    assert repo.flightcheck() is True


def test_flightcheck_missing_table():
    rows = [('activities',), ('streams',)]
    cursor = DummyCursor(rows=rows)
    conn = DummyConn(closed=False, cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    assert repo.flightcheck() is False


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
