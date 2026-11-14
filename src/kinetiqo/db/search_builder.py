"""Parameterized keyset search query builder for activities across SQL backends.

Provides dialect-aware SQL query construction, parameter extraction, and cursor
handling for PostgreSQL, MySQL, and Firebird.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional, Tuple

from kinetiqo.db.pagination import decode_cursor, encode_cursor

SORT_FIELD_MAP = {
    "date": "start_date",
    "start_date": "start_date",
    "distance": "distance",
    "elevation": "total_elevation_gain",
    "total_elevation_gain": "total_elevation_gain",
    "moving_time": "moving_time",
    "average_watts": "average_watts",
    "watts": "average_watts",
    "max_watts": "max_watts",
    "speed": "average_speed",
    "average_speed": "average_speed",
    "max_speed": "max_speed",
    "heartrate": "average_heartrate",
    "average_heartrate": "average_heartrate",
    "max_heartrate": "max_heartrate",
    "suffer_score": "suffer_score",
    "calories": "calories",
    "wind_gust": "weather_wind_gust_max",
    "weather_wind_gust": "weather_wind_gust_max",
    "weather_wind_gust_max": "weather_wind_gust_max",
    "wind_speed": "weather_wind_speed",
    "weather_wind_speed": "weather_wind_speed",
    "wind": "weather_wind_speed",
    "temp": "weather_temp_avg",
    "weather_temp": "weather_temp_avg",
    "weather_temp_avg": "weather_temp_avg",
}

COLUMNS = [
    "activity_id", "name", "sport", "athlete_id", "distance", "moving_time", "elapsed_time",
    "total_elevation_gain", "start_date", "average_speed", "max_speed",
    "average_heartrate", "max_heartrate", "average_cadence", "average_watts",
    "max_watts", "weighted_average_watts", "device_watts", "calories",
    "kilojoules", "achievement_count", "pr_count", "suffer_score", "average_temp",
    "gear_id", "has_heartrate", "workout_type", "trophies",
    "weather_temp_min", "weather_temp_max", "weather_temp_avg",
    "weather_condition", "weather_condition_icon",
    "weather_wind_deg", "weather_wind_speed", "weather_wind_gust_max",
    "weather_precipitation"
]


def _quote(col: str, dialect: str) -> str:
    return f'"{col}"' if dialect == "firebird" else col


def build_search_activities_query(
    dialect: str,
    athlete_id: Optional[int] = None,
    filters: Optional[Dict[str, Any]] = None,
    limit: int = 50,
    cursor: Optional[str] = None,
) -> Tuple[str, List[Any], str, int]:
    """Construct dialect-specific parameterized SQL query and arguments.

    :param dialect: 'postgresql', 'mysql', or 'firebird'.
    :param athlete_id: Athlete ID filter.
    :param filters: Search bounds, ranges, keyword, sport types, and sorting.
    :param limit: Page size (1 to 200).
    :param cursor: Keyset pagination cursor string.
    :return: (query_sql, params_list, sort_col, fetch_limit)
    """
    filters = filters or {}
    limit = max(1, min(int(limit), 200))
    fetch_limit = limit + 1
    ph = "?" if dialect == "firebird" else "%s"

    sort_by = filters.get("sort_by", "date")
    sort_col = SORT_FIELD_MAP.get(sort_by, "start_date")
    sort_order = "ASC" if str(filters.get("sort_order", "desc")).lower() == "asc" else "DESC"
    op = ">" if sort_order == "ASC" else "<"

    where_clauses: List[str] = []
    params: List[Any] = []

    if athlete_id:
        where_clauses.append(f"{_quote('athlete_id', dialect)} = {ph}")
        params.append(athlete_id)

    sport_types = filters.get("sport_types")
    if sport_types:
        placeholders = ", ".join([ph] * len(sport_types))
        where_clauses.append(f"{_quote('sport', dialect)} IN ({placeholders})")
        params.extend(sport_types)

    if filters.get("start_date"):
        where_clauses.append(f"{_quote('start_date', dialect)} >= {ph}")
        params.append(filters["start_date"])

    if filters.get("end_date"):
        where_clauses.append(f"{_quote('start_date', dialect)} <= {ph}")
        params.append(filters["end_date"])

    min_dist_km = filters.get("min_distance_km")
    if min_dist_km is None and filters.get("min_distance") is not None:
        min_dist_km = float(filters["min_distance"]) / 1000.0
    if min_dist_km is not None:
        where_clauses.append(f"{_quote('distance', dialect)} >= {ph}")
        params.append(float(min_dist_km) * 1000.0)

    max_dist_km = filters.get("max_distance_km")
    if max_dist_km is None and filters.get("max_distance") is not None:
        max_dist_km = float(filters["max_distance"]) / 1000.0
    if max_dist_km is not None:
        where_clauses.append(f"{_quote('distance', dialect)} <= {ph}")
        params.append(float(max_dist_km) * 1000.0)

    min_elev = filters.get("min_elevation_m") if filters.get("min_elevation_m") is not None else filters.get("min_elevation")
    if min_elev is not None:
        where_clauses.append(f"{_quote('total_elevation_gain', dialect)} >= {ph}")
        params.append(float(min_elev))

    max_elev = filters.get("max_elevation_m") if filters.get("max_elevation_m") is not None else filters.get("max_elevation")
    if max_elev is not None:
        where_clauses.append(f"{_quote('total_elevation_gain', dialect)} <= {ph}")
        params.append(float(max_elev))

    min_mov_s = filters.get("min_moving_time_s")
    if min_mov_s is None and filters.get("min_moving_time") is not None:
        min_mov_s = int(filters["min_moving_time"])
    if min_mov_s is None and filters.get("min_moving_time_min") is not None:
        min_mov_s = int(float(filters["min_moving_time_min"]) * 60)
    if min_mov_s is not None:
        where_clauses.append(f"{_quote('moving_time', dialect)} >= {ph}")
        params.append(int(min_mov_s))

    max_mov_s = filters.get("max_moving_time_s")
    if max_mov_s is None and filters.get("max_moving_time") is not None:
        max_mov_s = int(filters["max_moving_time"])
    if max_mov_s is None and filters.get("max_moving_time_min") is not None:
        max_mov_s = int(float(filters["max_moving_time_min"]) * 60)
    if max_mov_s is not None:
        where_clauses.append(f"{_quote('moving_time', dialect)} <= {ph}")
        params.append(int(max_mov_s))

    if filters.get("min_watts") is not None:
        where_clauses.append(f"{_quote('average_watts', dialect)} >= {ph}")
        params.append(float(filters["min_watts"]))

    if filters.get("max_watts") is not None:
        where_clauses.append(f"{_quote('average_watts', dialect)} <= {ph}")
        params.append(float(filters["max_watts"]))

    if filters.get("min_max_watts") is not None:
        where_clauses.append(f"{_quote('max_watts', dialect)} >= {ph}")
        params.append(float(filters["min_max_watts"]))

    if filters.get("max_max_watts") is not None:
        where_clauses.append(f"{_quote('max_watts', dialect)} <= {ph}")
        params.append(float(filters["max_max_watts"]))

    if filters.get("has_power") is not None:
        dev_watts = _quote("device_watts", dialect)
        avg_watts = _quote("average_watts", dialect)
        if bool(filters["has_power"]):
            where_clauses.append(f"({dev_watts} = TRUE OR {avg_watts} > 0)")
        else:
            where_clauses.append(f"({dev_watts} = FALSE OR {dev_watts} IS NULL)")

    if filters.get("min_heartrate") is not None:
        where_clauses.append(f"{_quote('average_heartrate', dialect)} >= {ph}")
        params.append(float(filters["min_heartrate"]))

    if filters.get("max_heartrate") is not None:
        where_clauses.append(f"{_quote('average_heartrate', dialect)} <= {ph}")
        params.append(float(filters["max_heartrate"]))

    if filters.get("has_heartrate") is not None:
        has_hr = _quote("has_heartrate", dialect)
        avg_hr = _quote("average_heartrate", dialect)
        if bool(filters["has_heartrate"]):
            where_clauses.append(f"({has_hr} = TRUE OR {avg_hr} > 0)")
        else:
            where_clauses.append(f"({has_hr} = FALSE OR {has_hr} IS NULL)")

    if filters.get("min_speed_kmh") is not None:
        where_clauses.append(f"{_quote('average_speed', dialect)} >= {ph}")
        params.append(float(filters["min_speed_kmh"]) / 3.6)

    if filters.get("max_speed_kmh") is not None:
        where_clauses.append(f"{_quote('average_speed', dialect)} <= {ph}")
        params.append(float(filters["max_speed_kmh"]) / 3.6)

    if filters.get("min_suffer_score") is not None:
        where_clauses.append(f"{_quote('suffer_score', dialect)} >= {ph}")
        params.append(int(float(filters["min_suffer_score"])))

    if filters.get("max_suffer_score") is not None:
        where_clauses.append(f"{_quote('suffer_score', dialect)} <= {ph}")
        params.append(int(float(filters["max_suffer_score"])))

    if filters.get("min_pr_count") is not None:
        where_clauses.append(f"{_quote('pr_count', dialect)} >= {ph}")
        params.append(int(filters["min_pr_count"]))

    if filters.get("gear_id"):
        where_clauses.append(f"{_quote('gear_id', dialect)} = {ph}")
        params.append(str(filters["gear_id"]).strip())

    if filters.get("workout_type") is not None:
        where_clauses.append(f"{_quote('workout_type', dialect)} = {ph}")
        params.append(int(filters["workout_type"]))

    if filters.get("has_trophies"):
        trophies_col = _quote("trophies", dialect)
        where_clauses.append(f"({trophies_col} IS NOT NULL AND {trophies_col} != '' AND {trophies_col} != '{{}}')")

    if filters.get("koms_only"):
        where_clauses.append(f"{_quote('trophies', dialect)} LIKE {ph}")
        params.append('%"1":%')

    cond = filters.get("weather_condition")
    if cond:
        w_cond = _quote("weather_condition", dialect)
        w_precip = _quote("weather_precipitation", dialect)
        if dialect == "postgresql":
            where_clauses.append(f"({w_cond} ILIKE %s OR {w_precip} ILIKE %s)")
        elif dialect == "mysql":
            where_clauses.append(f"({w_cond} LIKE %s OR {w_precip} LIKE %s)")
        else:  # firebird
            where_clauses.append(f"(LOWER({w_cond}) LIKE LOWER(?) OR LOWER({w_precip}) LIKE LOWER(?))")
        params.extend([f"%{cond}%", f"%{cond}%"])

    if filters.get("min_temp_c") is not None:
        where_clauses.append(f"{_quote('weather_temp_avg', dialect)} >= {ph}")
        params.append(float(filters["min_temp_c"]))

    if filters.get("max_temp_c") is not None:
        where_clauses.append(f"{_quote('weather_temp_avg', dialect)} <= {ph}")
        params.append(float(filters["max_temp_c"]))

    min_wind_spd = filters.get("min_wind_speed_ms")
    if min_wind_spd is None and filters.get("min_wind_speed_kmh") is not None:
        min_wind_spd = float(filters["min_wind_speed_kmh"]) / 3.6
    if min_wind_spd is not None:
        where_clauses.append(f"{_quote('weather_wind_speed', dialect)} >= {ph}")
        params.append(float(min_wind_spd))

    max_wind_spd = filters.get("max_wind_speed_ms")
    if max_wind_spd is None and filters.get("max_wind_speed_kmh") is not None:
        max_wind_spd = float(filters["max_wind_speed_kmh"]) / 3.6
    if max_wind_spd is not None:
        where_clauses.append(f"{_quote('weather_wind_speed', dialect)} <= {ph}")
        params.append(float(max_wind_spd))

    min_gust = filters.get("min_wind_gust_ms")
    if min_gust is None and filters.get("min_wind_gust_kmh") is not None:
        min_gust = float(filters["min_wind_gust_kmh"]) / 3.6
    if min_gust is not None:
        where_clauses.append(f"{_quote('weather_wind_gust_max', dialect)} >= {ph}")
        params.append(float(min_gust))

    max_gust = filters.get("max_wind_gust_ms")
    if max_gust is None and filters.get("max_wind_gust_kmh") is not None:
        max_gust = float(filters["max_wind_gust_kmh"]) / 3.6
    if max_gust is not None:
        where_clauses.append(f"{_quote('weather_wind_gust_max', dialect)} <= {ph}")
        params.append(float(max_gust))

    if filters.get("has_weather") is not None:
        w_temp = _quote("weather_temp_avg", dialect)
        if bool(filters["has_weather"]):
            where_clauses.append(f"{w_temp} IS NOT NULL")
        else:
            where_clauses.append(f"{w_temp} IS NULL")

    keyword = filters.get("keyword") or filters.get("query")
    if keyword:
        name_col = _quote("name", dialect)
        id_col = _quote("activity_id", dialect)
        w_cond = _quote("weather_condition", dialect)
        w_precip = _quote("weather_precipitation", dialect)
        if dialect == "postgresql":
            where_clauses.append(f"({name_col} ILIKE %s OR CAST({id_col} AS TEXT) LIKE %s OR {w_cond} ILIKE %s OR {w_precip} ILIKE %s)")
        elif dialect == "mysql":
            where_clauses.append(f"({name_col} LIKE %s OR CAST({id_col} AS CHAR) LIKE %s OR {w_cond} LIKE %s OR {w_precip} LIKE %s)")
        else:  # firebird
            where_clauses.append(f"(LOWER({name_col}) LIKE LOWER(?) OR CAST({id_col} AS VARCHAR(20)) LIKE ? OR LOWER({w_cond}) LIKE LOWER(?) OR LOWER({w_precip}) LIKE LOWER(?))")
        params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

    if cursor:
        decoded = decode_cursor(cursor)
        if decoded:
            c_val, c_date, c_id = decoded
            q_sd = _quote("start_date", dialect)
            q_id = _quote("activity_id", dialect)
            q_sc = _quote(sort_col, dialect)
            if sort_col == "start_date":
                where_clauses.append(f"({q_sd} {op} {ph} OR ({q_sd} = {ph} AND {q_id} {op} {ph}))")
                params.extend([c_date, c_date, c_id])
            else:
                where_clauses.append(f"({q_sc} {op} {ph} OR ({q_sc} = {ph} AND ({q_sd} {op} {ph} OR ({q_sd} = {ph} AND {q_id} {op} {ph}))))")
                params.extend([c_val, c_val, c_date, c_date, c_id])

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    q_sd = _quote("start_date", dialect)
    q_id = _quote("activity_id", dialect)
    q_sc = _quote(sort_col, dialect)

    if sort_col == "start_date":
        order_sql = f"ORDER BY {q_sd} {sort_order}, {q_id} {sort_order}"
    elif dialect == "mysql":
        order_sql = f"ORDER BY ({q_sc} IS NULL), {q_sc} {sort_order}, {q_sd} {sort_order}, {q_id} {sort_order}"
    else:  # postgresql and firebird both support NULLS LAST
        order_sql = f"ORDER BY {q_sc} {sort_order} NULLS LAST, {q_sd} {sort_order}, {q_id} {sort_order}"

    quoted_columns = [_quote(col, dialect) for col in COLUMNS]
    cols_sql = ",\n                   ".join(quoted_columns)
    table_name = _quote("activities", dialect)

    if dialect == "firebird":
        query = f"""
            SELECT FIRST {fetch_limit}
                {cols_sql}
            FROM {table_name}
            {where_sql}
            {order_sql}
        """
    else:
        query = f"""
            SELECT {cols_sql}
            FROM {table_name}
            {where_sql}
            {order_sql}
            LIMIT %s
        """
        params.append(fetch_limit)

    return query, params, sort_col, fetch_limit


def process_search_rows(
    rows: List[Dict[str, Any]],
    limit: int,
    sort_col: str,
) -> Tuple[List[Dict[str, Any]], Optional[str], bool]:
    """Normalize row dictionaries (ISO dates, JSON trophies) and compute keyset cursor."""
    processed = []
    for r in rows:
        act = dict(r)
        if isinstance(act.get("start_date"), datetime):
            dt = act["start_date"]
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            act["start_date"] = dt.isoformat()
        if act.get("trophies") and isinstance(act["trophies"], str):
            try:
                act["trophies"] = json.loads(act["trophies"])
            except Exception:
                pass
        processed.append(act)

    has_more = len(processed) > limit
    if has_more:
        activities = processed[:limit]
        last = activities[-1]
        next_cursor = encode_cursor(last.get(sort_col), last["start_date"], last["activity_id"])
    else:
        activities = processed
        next_cursor = None

    return activities, next_cursor, has_more
