import json
import time
import types
from datetime import datetime, timezone
from unittest import mock

import pytest

from kinetiqo.db.firebird import FirebirdRepository


class DummyCursor:
    def __init__(self, query_responses=None, default_rows=None, default_fetchone=None, description=None):
        self.query_responses = query_responses or {}
        self.default_rows = default_rows or []
        self.default_fetchone = default_fetchone
        self.description = description or []
        self.prefetch = 0
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
        self._closed = closed
        self._cursor_obj = cursor_obj or DummyCursor()
        self._cursor_factory = cursor_factory
        self.committed = False
        self.rolled_back = False
        self.main_transaction = types.SimpleNamespace(default_tpb=None)

    def cursor(self):
        if self._cursor_factory:
            return self._cursor_factory()
        return self._cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self._closed = True

    def is_closed(self):
        return self._closed


def make_repo_with_conn(conn, verify_interval=30.0):
    repo = object.__new__(FirebirdRepository)
    repo.config = types.SimpleNamespace(
        firebird_database="db.fdb",
        firebird_host="localhost",
        firebird_port=3050,
        firebird_user="sysdba",
        firebird_password="masterkey",
    )
    repo.conn = conn
    repo._last_verified = time.monotonic()
    repo._VERIFY_INTERVAL = verify_interval
    return repo


def make_activity_row(
    id=1,
    name="Test Ride",
    sport="Ride",
    distance=45000.0,
    moving_time=5400,
    elevation=450.0,
    start_date=None,
    trophies='{"koms": 1}',
    include_max_speed=False,
):
    dt = start_date or datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    base = [
        id, name, sport, distance, moving_time, elevation, dt,
        30.0, 145, 85, 220.0, 480.0, 230.0, 1, 750, 700, 2, 1, 65,
        22.0, 500.0, 100.0, "gear_id", 1, "default"
    ]
    if include_max_speed:
        base.append(48.0)
    base.append(trophies)
    return tuple(base)


# ---------------------------------------------------------------------------
# Health checks and connection management
# ---------------------------------------------------------------------------

def test_flightcheck_success():
    cursor = DummyCursor(query_responses={"RDB$RELATIONS": [(1,)]})
    conn = DummyConn(closed=False, cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    assert repo.flightcheck() is True


def test_flightcheck_missing_table():
    cursor = DummyCursor(query_responses={"RDB$RELATIONS": [(0,)]})
    conn = DummyConn(closed=False, cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    assert repo.flightcheck() is False


def test_flightcheck_exception():
    cursor = DummyCursor()
    def failing_execute(sql, params=None):
        raise RuntimeError("Database unavailable")
    cursor.execute = failing_execute

    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))
    assert repo.flightcheck() is False


def test_ensure_connected_skips_within_interval():
    cursor = DummyCursor()
    conn = DummyConn(closed=False, cursor_obj=cursor)
    repo = make_repo_with_conn(conn, verify_interval=60.0)
    repo._last_verified = time.monotonic()

    repo._ensure_connected()
    assert len(cursor.executed) == 0


def test_ensure_connected_probes_when_interval_expired():
    cursor = DummyCursor()
    conn = DummyConn(closed=False, cursor_obj=cursor)
    repo = make_repo_with_conn(conn, verify_interval=0.01)
    repo._last_verified = time.monotonic() - 100.0

    repo._ensure_connected()
    assert len(cursor.executed) == 1
    assert "SELECT 1 FROM RDB$DATABASE" in cursor.executed[0][0]


def test_ensure_connected_reconnects_when_closed(monkeypatch):
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


def test_ensure_database_creates_on_failure(monkeypatch):
    cursor = DummyCursor()
    conn = DummyConn(closed=False, cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    def bad_execute(sql, params=None):
        raise RuntimeError("db missing")

    cursor.execute = bad_execute
    created = {}

    def fake_create_db(sql):
        created["ok"] = True

    monkeypatch.setattr(
        "kinetiqo.db.firebird.firebird",
        types.SimpleNamespace(driver=types.SimpleNamespace(create_database=fake_create_db)),
        raising=False,
    )
    new_conn = DummyConn(closed=False, cursor_obj=cursor)
    monkeypatch.setattr(repo, "_connect", lambda: new_conn)

    repo._ensure_database()
    assert created.get("ok") is True
    assert repo.conn is new_conn


def test_get_firebird_version():
    cursor = DummyCursor(default_fetchone=("LI-V5.0.0.1306 Firebird 5.0",))
    conn = DummyConn(cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    assert repo.get_firebird_version() == "LI-V5.0.0.1306 Firebird 5.0"


def test_migrate_blob_columns_skips_non_blob():
    # RDB$FIELD_TYPE = 14 (VARCHAR, not 261)
    cursor = DummyCursor(default_fetchone=(14,))
    conn = DummyConn(cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    repo._migrate_blob_columns()
    assert len(cursor.executed) == 1
    assert "RDB$RELATION_FIELDS" in cursor.executed[0][0]


def test_migrate_blob_columns_migrates_blob():
    # RDB$FIELD_TYPE = 261 (BLOB)
    cursor = DummyCursor(default_fetchone=(261,))
    conn = DummyConn(cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    repo._migrate_blob_columns()
    # Should execute check, add tmp, update cast, drop, and alter
    assert len(cursor.executed) >= 5
    assert conn.committed is True


def test_initialize_schema(monkeypatch):
    cursor = DummyCursor()
    conn = DummyConn(cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    called = {}
    class FakeSchemaManager:
        def __init__(self, conn, db_type):
            called["db_type"] = db_type
        def ensure_schema(self):
            called["ensured"] = True

    monkeypatch.setattr("kinetiqo.db.firebird.SchemaManager", FakeSchemaManager)
    repo.initialize_schema()
    assert called["db_type"] == "firebird"
    assert called["ensured"] is True


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
    cursor = DummyCursor(default_rows=[(1001,), (1002,)])
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))
    ids = repo.get_synced_activity_ids()
    assert ids == {"1001", "1002"}


def test_get_synced_activity_ids_since():
    cursor = DummyCursor(default_rows=[(2001,)])
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))
    ids = repo.get_synced_activity_ids_since(1700000000)
    assert ids == {"2001"}
    assert '"start_date" >= ?' in cursor.executed[0][0]


def test_get_activities():
    row = make_activity_row()
    cursor = DummyCursor(default_rows=[row])
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    res = repo.get_activities(limit=10)
    assert len(res) == 1
    assert res[0]["id"] == 1
    assert res[0]["name"] == "Test Ride"
    assert res[0]["trophies"] == {"koms": 1}


def test_get_activities_web_pagination_and_sorting():
    cursor = DummyCursor(default_rows=[])
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    repo.get_activities_web(limit=25, offset=50, sort_by="distance", sort_order="ASC")
    sql, params = cursor.executed[0]
    assert 'FIRST 25 SKIP 50' in sql
    assert 'ORDER BY "distance" ASC' in sql

    # Column fallback
    cursor.executed.clear()
    repo.get_activities_web(limit=10, sort_by="malicious_col", sort_order="xyz")
    sql, params = cursor.executed[0]
    assert 'ORDER BY "start_date" ASC' in sql


def test_get_activities_web_filters():
    cursor = DummyCursor(default_rows=[])
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    repo.get_activities_web(
        types=["Ride", "Run"],
        start_date="2026-01-01T00:00:00",
        end_date="2026-01-31",
    )
    sql, params = cursor.executed[0]
    assert '"sport" IN (?, ?)' in sql
    assert '"start_date" >= ?' in sql
    assert '"start_date" <= ?' in sql
    assert params[0] == "Ride"
    assert params[1] == "Run"


def test_get_activities_by_ids():
    repo = make_repo_with_conn(DummyConn())
    assert repo.get_activities_by_ids([]) == []

    row = make_activity_row(id=123)
    cursor = DummyCursor(default_rows=[row])
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    res = repo.get_activities_by_ids(["123", "456"])
    assert len(res) == 1
    assert res[0]["id"] == 123
    assert '"activity_id" IN (?, ?)' in cursor.executed[0][0]


def test_get_activities_totals():
    cursor = DummyCursor(default_fetchone=(120000.0, 1500.0, 18000))
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    res = repo.get_activities_totals(types=["Ride"], start_date="2026-01-01", end_date="2026-01-10")
    assert res["total_distance"] == 120000.0
    sql, params = cursor.executed[0]
    assert 'COALESCE(SUM("distance"), 0)' in sql
    assert '"sport" IN (?)' in sql


def test_count_activities():
    cursor = DummyCursor(default_fetchone=(42,))
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    count = repo.count_activities(types=["Ride"], start_date="2026-01-01", end_date="2026-01-31")
    assert count == 42
    sql, params = cursor.executed[0]
    assert 'SELECT COUNT(*) FROM "activities"' in sql


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
    }

    repo.write_activity(activity)
    assert len(cursor.executed) == 1
    sql, params = cursor.executed[0]
    assert 'UPDATE OR INSERT INTO "activities"' in sql
    assert 'MATCHING ("activity_id")' in sql
    assert params[1] == 99999


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
    assert 'UPDATE "activities" SET "trophies" = ? WHERE "activity_id" = ?' in sql
    assert json.loads(params[0]) == {"rank_1": 2}
    assert params[1] == 12345
    assert conn.committed is True


def test_get_activities_needing_trophies():
    dt = datetime(2026, 3, 1, tzinfo=timezone.utc)
    desc = [("activity_id",), ("name",), ("sport",), ("start_date",), ("achievement_count",), ("pr_count",), ("trophies",)]
    rows = [(1, "Race", "Ride", dt, 5, 2, None)]
    cursor = DummyCursor(default_rows=rows, description=desc)
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    res = repo.get_activities_needing_trophies(limit=25)
    assert len(res) == 1
    assert res[0]["id"] == 1
    assert res[0]["start_date"] == dt.isoformat()
    assert 'WHERE "achievement_count" > 0' in cursor.executed[0][0]


def test_delete_activity():
    cursor = DummyCursor()
    conn = DummyConn(cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    repo.delete_activity("54321")
    sql, params = cursor.executed[0]
    assert 'DELETE FROM "activities" WHERE "activity_id" = ?' in sql
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
    assert 'DELETE FROM "activities" WHERE "activity_id" IN (?,?)' in sql
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
    assert 'DELETE FROM "streams" WHERE "activity_id" = ?' in cursor.executed[0][0]
    assert len(cursor.executed_many) == 1
    assert 'INSERT INTO "streams"' in cursor.executed_many[0][0]
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
        (100, 50.0, 14.0),
        (100, 50.1, 14.1),
        (200, 51.0, 15.0),
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
    assert cursor.prefetch == 10000


def test_get_best_power_per_activity():
    cursor = DummyCursor(default_rows=[(1, 200.0), (1, 300.0), (1, 400.0)])
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    powers = repo.get_best_power_per_activity(["1"], duration_seconds=2)
    assert "1" in powers
    assert powers["1"] == 350.0


def test_get_activity_ids_by_types():
    repo = make_repo_with_conn(DummyConn())
    assert repo.get_activity_ids_by_types([]) == []

    dt = datetime(2026, 6, 1, tzinfo=timezone.utc)
    cursor = DummyCursor(default_rows=[(1, "Morning Ride", dt)])
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    res = repo.get_activity_ids_by_types(["Ride"], since_date="2026-01-01", watts_only=True)
    assert len(res) == 1
    assert res[0]["start_date"] == dt.isoformat()
    sql, params = cursor.executed[0]
    assert '"average_watts" IS NOT NULL' in sql
    assert '"start_date" >= ?' in sql


def test_get_table_record_counts():
    cursor = DummyCursor(default_fetchone=(150,))
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))
    counts = repo.get_table_record_counts()
    assert counts == {"activities": 150, "streams": 150, "logs": 150}


def test_get_activities_with_suffer_score():
    dt = datetime(2026, 7, 1, tzinfo=timezone.utc)
    cursor = DummyCursor(default_rows=[(dt, 85)])
    repo = make_repo_with_conn(DummyConn(cursor_obj=cursor))

    res = repo.get_activities_with_suffer_score(days=30)
    assert len(res) == 1
    assert res[0]["start_date"] == dt.isoformat()
    assert '"start_date" >= ?' in cursor.executed[0][0]

    cursor.executed.clear()
    repo.get_activities_with_suffer_score(days=None)
    assert '"start_date" >= ?' not in cursor.executed[0][0]


# ---------------------------------------------------------------------------
# Athlete Profile & Goals
# ---------------------------------------------------------------------------

def test_profile_operations():
    cursor = DummyCursor(default_fetchone=(
        1234, "Test", "Rider", 70.5, 280.0, "", "", "", "", "", "", "tok", 1
    ))
    conn = DummyConn(cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    profile = repo.get_profile()
    assert profile["athlete_id"] == 1234
    assert profile["weight"] == 70.5

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
    assert 'UPDATE OR INSERT INTO "profile"' in sql
    assert 'MATCHING ("athlete_id")' in sql
    assert params[0] == 1234
    assert params[3] == 71.0
    assert params[4] == 285.0
    assert params[12] == 2
    assert conn.committed is True


def test_goals_operations():
    cursor = DummyCursor(default_rows=[(
        "Ride", 200.0, 800.0, 10000.0, 2000.0, 8000.0, 100000.0
    )])
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
    assert 'UPDATE OR INSERT INTO "activity_goals"' in sql
    assert 'MATCHING ("athlete_id", "activity_type_id")' in sql
    assert params[0] == 1234
    assert params[1] == "Ride"
    assert params[2] == 250.0
    assert conn.committed is True


# ---------------------------------------------------------------------------
# Sync Logs & Benchmarks
# ---------------------------------------------------------------------------

def test_sync_logs():
    cursor = DummyCursor()
    conn = DummyConn(cursor_obj=cursor)
    repo = make_repo_with_conn(conn)

    repo.log_sync(added=5, removed=1, trigger="manual", success=True, action="sync", user="admin")
    sql, params = cursor.executed[0]
    assert 'INSERT INTO "logs"' in sql
    assert params == (5, 1, "manual", 1, "sync", "admin")
    assert conn.committed is True

    dt = datetime(2026, 8, 1, tzinfo=timezone.utc)
    cursor_logs = DummyCursor(default_rows=[(dt, 5, 1, "manual", 1, "sync", "admin")])
    repo_logs = make_repo_with_conn(DummyConn(cursor_obj=cursor_logs))
    logs = repo_logs.get_logs(limit=10)
    assert len(logs) == 1
    assert logs[0]["timestamp"] == dt.isoformat()
    assert logs[0]["success"] is True


def test_run_benchmarks():
    row = make_activity_row(include_max_speed=True)
    cursor = DummyCursor(
        query_responses={
            'JOIN "streams"': [(1, 50.0, 14.0)],
        },
        default_rows=[row],
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
        assert not conn.is_closed()

    assert conn.is_closed()


def test_connect_resolves_connect_callable(monkeypatch):
    called = {}
    fake_conn = DummyConn()

    def fake_connect(database, user, password, charset):
        called["args"] = (database, user, password, charset)
        return fake_conn

    fake_firebird = types.SimpleNamespace(
        driver=types.SimpleNamespace(connect=fake_connect)
    )
    monkeypatch.setattr("kinetiqo.db.firebird.firebird", fake_firebird)

    repo = make_repo_with_conn(None)
    conn = repo._connect()
    assert conn is fake_conn
    assert "db.fdb" in called["args"][0]
    assert called["args"][1] == "sysdba"
