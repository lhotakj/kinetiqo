import json
import types
from datetime import datetime, timezone
from unittest import mock

import pytest

from kinetiqo.db.mysql import MySQLRepository, _get_mysql_pool


class DummyCursor:
    def __init__(self, query_responses=None, default_rows=None, default_fetchone=None, dictionary=False):
        self.query_responses = query_responses or {}
        self.default_rows = default_rows or []
        self.default_fetchone = default_fetchone
        self.dictionary = dictionary
        self.executed = []
        self.executed_many = []
        self._current_rows = list(self.default_rows)
        self._current_fetchone = self.default_fetchone

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        matched = False
        for pattern, resp in self.query_responses.items():
            if pattern.lower() in sql.lower():
                if isinstance(resp, tuple):
                    self._current_rows = resp[0]
                    self._current_fetchone = resp[1]
                elif isinstance(resp, list):
                    self._current_rows = resp
                    self._current_fetchone = resp[0] if resp else None
                else:
                    self._current_rows = [resp]
                    self._current_fetchone = resp
                matched = True
                break
        if not matched:
            self._current_rows = list(self.default_rows)
            self._current_fetchone = self.default_fetchone

    def executemany(self, sql, seq_of_params):
        self.executed_many.append((sql, list(seq_of_params)))

    def fetchall(self):
        return list(self._current_rows)

    def fetchone(self):
        return self._current_fetchone

    def __iter__(self):
        return iter(self._current_rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DummyConn:
    def __init__(self, closed=False, cursor_obj=None, cursor_factory=None):
        self.closed = closed
        self._cursor_obj = cursor_obj or DummyCursor()
        self._cursor_factory = cursor_factory
        self.autocommit = False
        self.database = None
        self.committed = False

    def cursor(self, dictionary=False):
        if self._cursor_factory:
            return self._cursor_factory(dictionary=dictionary)
        if dictionary:
            self._cursor_obj.dictionary = True
        return self._cursor_obj

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True

    def is_connected(self):
        return not self.closed

    def ping(self, reconnect=True, attempts=1, delay=0):
        if self.closed:
            raise ConnectionError("closed")


def make_repo_with_conn(conn):
    repo = object.__new__(MySQLRepository)
    repo.config = types.SimpleNamespace(
        mysql_database="db",
        mysql_host="h",
        mysql_port=3306,
        mysql_user="u",
        mysql_password="p",
    )
    repo.conn = conn
    return repo


# ---------------------------------------------------------------------------
# Health checks and connection management
# ---------------------------------------------------------------------------

def test_flightcheck_success():
    rows = [("activities",), ("streams",), ("logs",)]
    cursor = DummyCursor(query_responses={"information_schema.tables": rows})
    conn = DummyConn(closed=False, cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    assert repo.flightcheck() is True


def test_flightcheck_missing_table():
    rows = [("activities",), ("streams",)]
    cursor = DummyCursor(query_responses={"information_schema.tables": rows})
    conn = DummyConn(closed=False, cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    assert repo.flightcheck() is False


def test_flightcheck_exception():
    class FailingConn(DummyConn):
        def cursor(self, dictionary=False):
            raise RuntimeError("Database unavailable")

    repo = make_repo_with_conn(FailingConn())
    assert repo.flightcheck() is False


def test_ensure_connected_reconnects(monkeypatch):
    cursor = DummyCursor()
    conn = DummyConn(closed=True, cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    new_conn = DummyConn(closed=False, cursor_obj=cursor)
    called = {}

    def fake_connect():
        called["ok"] = True
        return new_conn

    monkeypatch.setattr(repo, "_connect", fake_connect)

    repo._ensure_connected()
    assert called.get("ok") is True
    assert repo.conn is new_conn
    assert repo.conn.autocommit is True


def test_ensure_connected_restores_autocommit():
    cursor = DummyCursor()
    conn = DummyConn(closed=False, cursor_obj=cursor)
    conn.autocommit = False
    repo = make_repo_with_conn(conn)

    repo._ensure_connected()
    assert repo.conn.autocommit is True


def test_get_mysql_version():
    cursor = DummyCursor(default_fetchone=("8.0.35-commercial",))
    conn = DummyConn(cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    assert repo.get_mysql_version() == "8.0.35-commercial"


# ---------------------------------------------------------------------------
# Activities: queries and summaries
# ---------------------------------------------------------------------------

def test_get_latest_activity_time():
    dt_utc = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    cursor = DummyCursor(default_fetchone=(dt_utc,))
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))
    assert repo.get_latest_activity_time() == int(dt_utc.timestamp())

    # Naive datetime handling
    dt_naive = datetime(2026, 6, 15, 12, 0, 0)
    cursor_naive = DummyCursor(default_fetchone=(dt_naive,))
    repo_naive = make_repo_with_conn(DummyConn(cursor_obj=cursor_naive))
    assert repo_naive.get_latest_activity_time() == int(dt_utc.timestamp())

    # None handling
    cursor_none = DummyCursor(default_fetchone=None)
    repo_none = make_repo_with_conn(DummyConn(cursor_obj=cursor_none))
    assert repo_none.get_latest_activity_time() is None


def test_get_synced_activity_ids():
    cursor = DummyCursor(default_rows=[(1001,), (1002,), (1003,)])
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))
    ids = repo.get_synced_activity_ids()
    assert ids == {"1001", "1002", "1003"}


def test_get_synced_activity_ids_since():
    cursor = DummyCursor(default_rows=[(2001,), (2002,)])
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))
    ids = repo.get_synced_activity_ids_since(1700000000)
    assert ids == {"2001", "2002"}
    assert "start_date >= %s" in cursor.executed[0][0]


def test_get_activities():
    dt = datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc)
    raw_rows = [
        {
            "id": 1,
            "name": "Morning Ride",
            "type": "Ride",
            "distance": 45000.0,
            "moving_time": 5400,
            "total_elevation_gain": 450.0,
            "start_date": dt,
            "trophies": '{"koms": 1, "prs": 2}',
        }
    ]
    cursor = DummyCursor(default_rows=raw_rows)
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))
    res = repo.get_activities(limit=10)
    assert len(res) == 1
    assert res[0]["start_date"] == dt.isoformat()
    assert res[0]["trophies"] == {"koms": 1, "prs": 2}


def test_get_activities_web_pagination_and_sorting():
    cursor = DummyCursor(default_rows=[])
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    repo.get_activities_web(limit=25, offset=50, sort_by="distance", sort_order="ASC")
    sql, params = cursor.executed[0]
    assert "ORDER BY distance ASC" in sql
    assert "LIMIT %s OFFSET %s" in sql
    assert list(params) == [25, 50]

    # Invalid column fallback
    cursor.executed.clear()
    repo.get_activities_web(limit=10, sort_by="malicious_drop_table", sort_order="invalid")
    sql, params = cursor.executed[0]
    assert "ORDER BY start_date ASC" in sql


def test_get_activities_web_filters():
    cursor = DummyCursor(default_rows=[])
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    repo.get_activities_web(
        types=["Ride", "Run"],
        start_date="2026-01-01",
        end_date="2026-01-31",
    )
    sql, params = cursor.executed[0]
    assert "sport IN (%s, %s)" in sql
    assert "start_date >= %s" in sql
    assert "start_date <= %s" in sql
    assert params[0] == "Ride"
    assert params[1] == "Run"
    assert params[2] == "2026-01-01"
    assert params[3] == "2026-01-31 23:59:59.999999"


def test_get_activities_by_ids():
    repo = make_repo_with_conn(DummyConn())
    assert repo.get_activities_by_ids([]) == []

    dt = datetime(2026, 4, 10, 8, 0, 0, tzinfo=timezone.utc)
    raw_rows = [{"id": 123, "start_date": dt, "trophies": None}]
    cursor = DummyCursor(default_rows=raw_rows)
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    res = repo.get_activities_by_ids(["123", "456"])
    assert len(res) == 1
    assert res[0]["start_date"] == dt.isoformat()
    assert "WHERE activity_id IN (%s, %s)" in cursor.executed[0][0]


def test_get_activities_totals():
    cursor = DummyCursor(default_fetchone={"total_distance": 120000.0, "total_elevation": 1500.0, "total_moving_time": 18000})
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    res = repo.get_activities_totals(types=["Ride"], start_date="2026-01-01", end_date="2026-01-10")
    assert res["total_distance"] == 120000.0
    sql, params = cursor.executed[0]
    assert "COALESCE(SUM(distance), 0)" in sql
    assert "sport IN (%s)" in sql


def test_count_activities():
    cursor = DummyCursor(default_fetchone=(42,))
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    count = repo.count_activities(types=["Ride"], start_date="2026-01-01", end_date="2026-01-31")
    assert count == 42
    sql, params = cursor.executed[0]
    assert "SELECT COUNT(*) FROM activities" in sql


# ---------------------------------------------------------------------------
# Write and delete activity operations
# ---------------------------------------------------------------------------

def test_write_activity_normal():
    cursor = DummyCursor()
    conn = DummyConn(cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    activity = {
        "id": 99999,
        "name": "Evening Tempo",
        "sport_type": "Ride",
        "start_date": "2026-07-20T17:30:00Z",
        "athlete": {"id": 12345},
        "distance": 32000.0,
        "moving_time": 3600,
        "trophies": {"1": 1, "2": 2},
    }

    repo.write_activity(activity)
    assert len(cursor.executed) == 1
    sql, params = cursor.executed[0]
    assert "INSERT INTO activities" in sql
    assert "ON DUPLICATE KEY" in sql
    assert conn.committed is True
    assert params[1] == 99999
    assert json.loads(params[29]) == {"1": 1, "2": 2}


def test_write_activity_epoch_fallback():
    cursor = DummyCursor()
    conn = DummyConn(cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    activity = {
        "id": 88888,
        "name": "Old Activity",
        "sport_type": "Run",
        "start_date": "1969-12-31T23:59:59Z",
        "athlete": {"id": 12345},
    }

    repo.write_activity(activity)
    sql, params = cursor.executed[0]
    start_dt = params[0]
    assert start_dt == datetime(1970, 1, 1, 0, 0, 1, tzinfo=timezone.utc)


def test_update_activity_trophies():
    cursor = DummyCursor()
    conn = DummyConn(cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    repo.update_activity_trophies(12345, {"rank_1": 2})
    sql, params = cursor.executed[0]
    assert "UPDATE activities SET trophies = %s WHERE activity_id = %s" in sql
    assert json.loads(params[0]) == {"rank_1": 2}
    assert params[1] == 12345
    assert conn.committed is True


def test_get_activities_needing_trophies():
    dt = datetime(2026, 3, 1, tzinfo=timezone.utc)
    cursor = DummyCursor(default_rows=[{"id": 1, "name": "Race", "sport": "Ride", "start_date": dt}])
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    res = repo.get_activities_needing_trophies(limit=25)
    assert len(res) == 1
    assert res[0]["start_date"] == dt.isoformat()
    assert "WHERE achievement_count > 0" in cursor.executed[0][0]


def test_delete_activity():
    cursor = DummyCursor()
    conn = DummyConn(cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    repo.delete_activity("54321")
    sql, params = cursor.executed[0]
    assert "DELETE FROM activities WHERE activity_id = %s" in sql
    assert params == (54321,)
    assert conn.committed is True


def test_delete_activities():
    repo = make_repo_with_conn(DummyConn())
    repo.delete_activities([])  # No-op

    cursor = DummyCursor()
    conn = DummyConn(cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    repo.delete_activities(["101", "102"])
    sql, params = cursor.executed[0]
    assert "DELETE FROM activities WHERE activity_id IN (%s, %s)" in sql
    assert params == [101, 102]
    assert conn.committed is True


# ---------------------------------------------------------------------------
# Streams operations
# ---------------------------------------------------------------------------

def test_write_activity_streams():
    cursor = DummyCursor()
    conn = DummyConn(cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    activity = {
        "id": 1234,
        "sport_type": "Ride",
        "athlete": {"id": 99},
        "start_date": "2026-05-10T08:00:00Z",
    }
    streams = {
        "time": {"data": [0, 10, 20]},
        "latlng": {"data": [[50.0, 14.0], [50.1, 14.1], [50.2, 14.2]]},
        "watts": {"data": [200, 250, 300]},
        "altitude": {"data": [200.0, 205.0, 210.0]},
    }

    repo.write_activity_streams(activity, streams)
    assert len(cursor.executed) == 1
    assert "DELETE FROM streams WHERE activity_id = %s" in cursor.executed[0][0]
    assert len(cursor.executed_many) == 1
    assert "INSERT INTO streams" in cursor.executed_many[0][0]
    rows = cursor.executed_many[0][1]
    assert len(rows) == 3
    assert rows[0][1] == 1234
    assert rows[0][4] == 50.0
    assert rows[0][11] == 200
    assert conn.committed is True


def test_get_streams_for_activities():
    repo = make_repo_with_conn(DummyConn())
    assert repo.get_streams_for_activities([]) == {}

    raw_rows = [
        {"activity_id": 100, "lat": 50.0, "lng": 14.0},
        {"activity_id": 100, "lat": 50.1, "lng": 14.1},
        {"activity_id": 200, "lat": 51.0, "lng": 15.0},
    ]
    cursor = DummyCursor(default_rows=raw_rows)
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    res = repo.get_streams_for_activities(["100", "200"])
    assert len(res["100"]) == 2
    assert len(res["200"]) == 1
    assert res["100"][0] == {"lat": 50.0, "lng": 14.0}


def test_get_streams_coords_for_activities():
    repo = make_repo_with_conn(DummyConn())
    assert repo.get_streams_coords_for_activities([]) == {}

    raw_rows = [
        (100, 50.0, 14.0),
        (100, 50.1, 14.1),
        (200, 51.0, 15.0),
    ]
    cursor = DummyCursor(default_rows=raw_rows)
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    res = repo.get_streams_coords_for_activities(["100", "200"])
    assert res["100"] == [[50.0, 14.0], [50.1, 14.1]]
    assert res["200"] == [[51.0, 15.0]]


def test_get_streams_bounds_for_activities():
    repo = make_repo_with_conn(DummyConn())
    assert repo.get_streams_bounds_for_activities([]) is None

    cursor = DummyCursor(default_fetchone=(49.5, 13.8, 50.5, 14.8))
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    bounds = repo.get_streams_bounds_for_activities(["100"])
    assert bounds == (49.5, 13.8, 50.5, 14.8)


def test_get_activity_name():
    cursor = DummyCursor(default_fetchone=("Gran Fondo Alps",))
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))
    assert repo.get_activity_name("777") == "Gran Fondo Alps"
    assert cursor.executed[0][1] == (777,)


def test_get_activity_average_cadence():
    cursor = DummyCursor(default_fetchone=(88.5,))
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))
    assert repo.get_activity_average_cadence("777") == 88.5

    cursor_none = DummyCursor(default_fetchone=None)
    repo_none = make_repo_with_conn(DummyConn(cursor_obj=cursor_none))
    assert repo_none.get_activity_average_cadence("777") is None


def test_get_elevation_streams_for_activity():
    cursor = DummyCursor(default_rows=[(0.0, 250.0), (100.0, 255.0), (200.0, 260.0)])
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))
    dist, alt = repo.get_elevation_streams_for_activity("555")
    assert dist == [0.0, 100.0, 200.0]
    assert alt == [250.0, 255.0, 260.0]

    cursor_empty = DummyCursor(default_rows=[])
    repo_empty = make_repo_with_conn(DummyConn(cursor_obj=cursor_empty))
    assert repo_empty.get_elevation_streams_for_activity("555") == ([], [])


def test_get_watts_streams_for_activities():
    repo = make_repo_with_conn(DummyConn())
    assert repo.get_watts_streams_for_activities([]) == {}

    cursor = DummyCursor(default_rows=[(1, 200.0), (1, 210.0), (2, 300.0)])
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))
    res = repo.get_watts_streams_for_activities(["1", "2"])
    assert res["1"] == [200.0, 210.0]
    assert res["2"] == [300.0]


def test_get_best_power_per_activity(monkeypatch):
    cursor = DummyCursor(default_rows=[(1, 200.0), (1, 300.0), (1, 400.0)])
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    powers = repo.get_best_power_per_activity(["1"], duration_seconds=2)
    assert "1" in powers
    assert powers["1"] == 350.0  # max 2-sec avg: (300+400)/2


def test_get_activity_ids_by_types():
    repo = make_repo_with_conn(DummyConn())
    assert repo.get_activity_ids_by_types([]) == []

    dt = datetime(2026, 6, 1, tzinfo=timezone.utc)
    cursor = DummyCursor(default_rows=[{"id": 1, "name": "Morning Ride", "start_date": dt}])
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    res = repo.get_activity_ids_by_types(["Ride"], since_date="2026-01-01", watts_only=True)
    assert len(res) == 1
    assert res[0]["start_date"] == dt.isoformat()
    sql, params = cursor.executed[0]
    assert "average_watts IS NOT NULL" in sql
    assert "start_date >= %s" in sql


def test_get_table_record_counts():
    cursor = DummyCursor(default_fetchone=(150,))
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))
    counts = repo.get_table_record_counts()
    assert counts == {"activities": 150, "streams": 150, "logs": 150}


def test_get_activities_with_suffer_score():
    dt = datetime(2026, 7, 1, tzinfo=timezone.utc)
    cursor = DummyCursor(default_rows=[{"start_date": dt, "suffer_score": 85}])
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    res = repo.get_activities_with_suffer_score(days=30)
    assert len(res) == 1
    assert res[0]["start_date"] == dt.isoformat()
    assert "start_date >= %s" in cursor.executed[0][0]

    cursor.executed.clear()
    repo.get_activities_with_suffer_score(days=None)
    assert "start_date >= %s" not in cursor.executed[0][0]


# ---------------------------------------------------------------------------
# Athlete Profile & Goals
# ---------------------------------------------------------------------------

def test_profile_operations():
    cursor = DummyCursor(default_fetchone={
        "athlete_id": 1234,
        "first_name": "Test",
        "last_name": "Rider",
        "weight": 70.5,
        "ftp": 280.0,
        "gps_simplification": 1,
    })
    conn = DummyConn(cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    profile = repo.get_profile()
    assert profile["athlete_id"] == 1234

    repo.upsert_profile(
        athlete_id=1234,
        first_name="Test",
        last_name="Rider",
        weight=71.0,
        ftp=285.0,
        gps_simplification=2,
    )
    assert len(cursor.executed) >= 2
    sql, params = cursor.executed[-1]
    assert "INSERT INTO profile" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    assert params[0] == 1234
    assert params[3] == 71.0
    assert params[4] == 285.0
    assert params[12] == 2
    assert conn.committed is True


def test_goals_operations():
    cursor = DummyCursor(default_rows=[{
        "activity_type_id": "Ride",
        "weekly_distance_goal": 200.0,
        "monthly_distance_goal": 800.0,
        "yearly_distance_goal": 10000.0,
        "weekly_elevation_goal": 2000.0,
        "monthly_elevation_goal": 8000.0,
        "yearly_elevation_goal": 100000.0,
    }])
    conn = DummyConn(cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    goals = repo.get_goals(athlete_id=1234)
    assert len(goals) == 1
    assert goals[0]["weekly_distance_goal"] == 200.0

    repo.upsert_goal(
        athlete_id=1234,
        activity_type_id="Ride",
        weekly_distance_goal=250.0,
        monthly_distance_goal=1000.0,
        yearly_distance_goal=12000.0,
        weekly_elevation_goal=2500.0,
        monthly_elevation_goal=10000.0,
        yearly_elevation_goal=120000.0,
    )
    sql, params = cursor.executed[-1]
    assert "INSERT INTO activity_goals" in sql
    assert params[0] == 1234
    assert params[1] == "Ride"
    assert params[2] == 250.0


# ---------------------------------------------------------------------------
# Sync Logs & Benchmarks
# ---------------------------------------------------------------------------

def test_sync_logs():
    cursor = DummyCursor()
    conn = DummyConn(cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    repo.log_sync(added=5, removed=1, trigger="manual", success=True, action="sync", user="admin")
    sql, params = cursor.executed[0]
    assert "INSERT INTO logs" in sql
    assert params == (5, 1, "manual", True, "sync", "admin")
    assert conn.committed is True

    dt = datetime(2026, 8, 1, tzinfo=timezone.utc)
    cursor_logs = DummyCursor(default_rows=[{"timestamp": dt, "added": 5, "removed": 1}])
    repo_logs = make_repo_with_conn(DummyConn(cursor_obj=cursor_logs))
    logs = repo_logs.get_logs(limit=10)
    assert len(logs) == 1
    assert logs[0]["timestamp"] == dt.isoformat()


def test_run_benchmarks():
    cursor = DummyCursor(
        query_responses={
            "JOIN streams": [(1, 50.0, 14.0)],
        },
        default_rows=[{"id": 1, "name": "Ride", "start_date": "2026-05-01", "trophies": None}],
    )
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    res = repo.run_benchmarks(scope_days=30)
    assert "gps_ms" in res
    assert "order_name_ms" in res
    assert "order_dist_ms" in res
    assert "order_elev_ms" in res


def test_close_and_context_manager():
    conn = DummyConn(closed=False)
    repo = make_repo_with_conn(conn)

    with repo as r:
        assert r is repo
        assert not conn.closed

    assert conn.closed


def test_create_database():
    cursor = DummyCursor()
    conn = DummyConn(cursor_obj=cursor)
    conn.database = "other_db"
    repo = make_repo_with_conn(conn)

    repo._create_database()
    assert conn.database == "db"
    assert "CREATE DATABASE IF NOT EXISTS db" in cursor.executed[0][0]


def test_initialize_schema(monkeypatch):
    called = {}
    class FakeSchemaManager:
        def __init__(self, conn, db_type):
            called["db_type"] = db_type
        def ensure_schema(self):
            called["ensured"] = True

    monkeypatch.setattr("kinetiqo.db.mysql.SchemaManager", FakeSchemaManager)
    repo = make_repo_with_conn(DummyConn())
    repo.initialize_schema()
    assert called["db_type"] == "mysql"
    assert called["ensured"] is True


def test_get_mysql_pool(monkeypatch):
    config = types.SimpleNamespace(
        mysql_host="localhost",
        mysql_port=3306,
        mysql_user="root",
        mysql_password="pwd",
        mysql_database="kinetiqo",
    )
    called = {}
    class FakePool:
        def __init__(self, pool_name, pool_size, **kwargs):
            called["pool_name"] = pool_name
            called["kwargs"] = kwargs

    monkeypatch.setattr("kinetiqo.db.mysql.mysql.connector.pooling.MySQLConnectionPool", FakePool)
    monkeypatch.setattr("kinetiqo.db.mysql._mysql_pool", None)

    pool = _get_mysql_pool(config)
    assert pool is not None
    assert called["pool_name"] == "kinetiqo_mysql_pool"
    assert called["kwargs"]["database"] == "kinetiqo"


def test_init_repo_success(monkeypatch):
    config = types.SimpleNamespace(mysql_database="test_db")
    fake_conn = DummyConn()
    called = {}

    def fake_connect(self):
        called["connect"] = True
        return fake_conn

    def fake_create_db(self):
        called["create_db"] = True

    monkeypatch.setattr(MySQLRepository, "_connect", fake_connect)
    monkeypatch.setattr(MySQLRepository, "_create_database", fake_create_db)

    repo = MySQLRepository(config)
    assert called["connect"] is True
    assert called["create_db"] is True
    assert repo.conn is fake_conn


def test_connect_via_pool(monkeypatch):
    fake_conn = DummyConn()
    class FakePool:
        def get_connection(self):
            return fake_conn

    monkeypatch.setattr("kinetiqo.db.mysql._get_mysql_pool", lambda cfg: FakePool())
    repo = make_repo_with_conn(None)
    conn = repo._connect()
    assert conn is fake_conn
    assert conn.autocommit is True


def test_connect_direct_fallback(monkeypatch):
    def fake_pool_err(cfg):
        raise RuntimeError("Pool full")

    fake_conn = DummyConn()
    monkeypatch.setattr("kinetiqo.db.mysql._get_mysql_pool", fake_pool_err)
    monkeypatch.setattr("kinetiqo.db.mysql.mysql.connector.connect", lambda **kw: fake_conn)

    repo = make_repo_with_conn(None)
    conn = repo._connect()
    assert conn is fake_conn
    assert conn.autocommit is True


def test_connect_bad_db_retry(monkeypatch):
    from mysql.connector import errorcode, Error

    def fake_pool_err(cfg):
        raise RuntimeError("No pool")

    calls = []
    fake_conn = DummyConn()

    def fake_connect(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            err = Error(msg="Unknown database", errno=errorcode.ER_BAD_DB_ERROR)
            raise err
        return fake_conn

    monkeypatch.setattr("kinetiqo.db.mysql._get_mysql_pool", fake_pool_err)
    monkeypatch.setattr("kinetiqo.db.mysql.mysql.connector.connect", fake_connect)

    repo = make_repo_with_conn(None)
    conn = repo._connect()
    assert conn is fake_conn
    assert len(calls) == 2
    assert "database" in calls[0]
    assert "database" not in calls[1]


def test_flightcheck_missing_streams_or_logs():
    rows_no_streams = [("activities",), ("logs",)]
    cursor1 = DummyCursor(query_responses={"information_schema.tables": rows_no_streams})
    repo1 = make_repo_with_conn(DummyConn(cursor_obj=cursor1))
    assert repo1.flightcheck() is False

    rows_no_logs = [("activities",), ("streams",)]
    cursor2 = DummyCursor(query_responses={"information_schema.tables": rows_no_logs})
    repo2 = make_repo_with_conn(DummyConn(cursor_obj=cursor2))
    assert repo2.flightcheck() is False


def test_close_handles_exception():
    class BrokenConn(DummyConn):
        def is_connected(self):
            return True
        def close(self):
            raise RuntimeError("close failed")

    repo = make_repo_with_conn(BrokenConn())
    # Should not raise exception
    repo.close()


