"""Historical route weather fetching and deterministic descriptions."""

from __future__ import annotations

import math
import os
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Sequence

import requests

LOGGER_FIELDS = (
    "datetimeEpoch", "temp", "feelslike", "precip", "snow", "preciptype",
    "conditions", "winddir", "windspeed", "windgust", "source",
)
TIMELINE_URL = "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline"
REQUEST_TIMEOUT_SECONDS = 20
MAX_GPS_BRACKET_SECONDS = 15 * 60
WEATHER_INTERVAL_SECONDS = 60 * 60
QUOTA_WARNING_UNITS = 800
QUOTA_HARD_CAP = 900
PROVIDER_DAILY_LIMIT = 1000
LEDGER_RETENTION_DAYS = 30

HEADWIND_BANDS = (
    (2.7, "Light breeze"),
    (5.4, "Moderate wind"),
    (8.3, "Notable headwind"),
    (12.5, "Strong wind"),
    (math.inf, "Extreme wind"),
)
GUST_BANDS = (
    (7.9, "mild gusts"),
    (10.9, "moderate gusts"),
    (16.9, "notable gusts"),
    (24.9, "severe gusts"),
    (math.inf, "extreme/gale gusts"),
)
COLD_TEMPERATURE_THRESHOLD_C = 5.0
FREEZING_TEMPERATURE_THRESHOLD_C = 0.0


class WeatherProviderError(RuntimeError):
    """A provider failure that can be reported without exposing the API key."""

    def __init__(self, message: str, *, status_code: int | None = None,
                 retry_after: str | None = None, stop_run: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after
        self.stop_run = stop_run


class WeatherQuotaExceeded(RuntimeError):
    """Raised when the local rolling quota guard refuses a reservation."""


def parse_utc(value: Any) -> datetime | None:
    """Parse a database/API timestamp as timezone-aware UTC."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        try:
            parsed = datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def hourly_intervals(start: datetime, end: datetime) -> list[tuple[datetime, int]]:
    """Return each overlapping hourly timestamp and its clipped activity duration."""
    start_utc = parse_utc(start)
    end_utc = parse_utc(end)
    if start_utc is None or end_utc is None or end_utc <= start_utc:
        return []
    cursor = start_utc.replace(minute=0, second=0, microsecond=0)
    intervals: list[tuple[datetime, int]] = []
    while cursor < end_utc:
        overlap = max(
            0,
            int((min(cursor + timedelta(hours=1), end_utc) -
                 max(cursor, start_utc)).total_seconds()),
        )
        if overlap:
            intervals.append((cursor, overlap))
        cursor += timedelta(hours=1)
    return intervals


def _gps_point(point: Mapping[str, Any]) -> tuple[datetime, float, float, float | None] | None:
    timestamp = parse_utc(point.get("ts"))
    try:
        latitude = float(point.get("lat"))
        longitude = float(point.get("lng"))
    except (TypeError, ValueError):
        return None
    if timestamp is None or not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        return None
    distance = _number_or_none(point.get("distance"))
    return timestamp, latitude, longitude, distance


def _bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float | None:
    """Return the initial great-circle bearing from the first point to the second."""
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lon = math.radians(lon2 - lon1)
    y = math.sin(delta_lon) * math.cos(lat2_rad)
    x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(delta_lon)
    if math.isclose(x, 0.0, abs_tol=1e-12) and math.isclose(y, 0.0, abs_tol=1e-12):
        return None
    return math.degrees(math.atan2(y, x)) % 360.0


def _distance_metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance using the haversine formula."""
    earth_radius_m = 6_371_000.0
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    delta_lat = lat2_rad - lat1_rad
    delta_lon = math.radians(lon2 - lon1)
    value = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    return 2 * earth_radius_m * math.asin(min(1.0, math.sqrt(value)))


def interpolate_route_position(
    points: Sequence[Mapping[str, Any]], at: datetime,
) -> dict[str, float] | None:
    """Interpolate a GPS position and segment bearing without extrapolating."""
    target = parse_utc(at)
    if target is None:
        return None
    valid = [item for point in points if (item := _gps_point(point)) is not None]
    valid.sort(key=lambda point: point[0])
    for left, right in zip(valid, valid[1:]):
        gap = (right[0] - left[0]).total_seconds()
        if gap <= 0 or gap > MAX_GPS_BRACKET_SECONDS:
            continue
        if left[0] <= target <= right[0]:
            bearing = _bearing_degrees(left[1], left[2], right[1], right[2])
            if bearing is None:
                return None
            fraction = (target - left[0]).total_seconds() / gap
            distance = (
                left[3] + (right[3] - left[3]) * fraction
                if left[3] is not None and right[3] is not None
                else None
            )
            return {
                "latitude": left[1] + (right[1] - left[1]) * fraction,
                "longitude": left[2] + (right[2] - left[2]) * fraction,
                "bearing_deg": bearing,
                "segment_speed_mps": _distance_metres(left[1], left[2], right[1], right[2]) / gap,
                "distance_m": distance,
            }
    return None


def _weather_hour(response_data: Mapping[str, Any], requested_epoch: int) -> Mapping[str, Any] | None:
    for day in response_data.get("days", []):
        if not isinstance(day, Mapping):
            continue
        for hour in day.get("hours", []):
            if isinstance(hour, Mapping):
                try:
                    if int(hour.get("datetimeEpoch", -1)) == requested_epoch:
                        return hour
                except (TypeError, ValueError):
                    continue
    return None


def fetch_visual_crossing_hour(
    latitude: float,
    longitude: float,
    hour_start: datetime,
    *,
    api_key: str | None = None,
    reserve_quota: Callable[[int], int | None],
    hourly_cache: MutableMapping[tuple[str, str], dict[int, dict[str, Any]]] | None = None,
    get: Callable[..., Any] = requests.get,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[dict[str, Any], int]:
    """Fetch an hourly record, reusing response hours within the current sync."""
    credential = api_key if api_key is not None else os.getenv("VISUAL_CROSSING_API_KEY", "")
    if not credential:
        raise WeatherProviderError("VISUAL_CROSSING_API_KEY is not configured.", stop_run=True)
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Invalid weather coordinate.")
    start = parse_utc(hour_start)
    if start is None or start.minute or start.second or start.microsecond:
        raise ValueError("Weather request time must be an exact UTC hour.")
    end = start + timedelta(hours=1)
    location = f"{latitude:.5f},{longitude:.5f}"
    requested_epoch = int(start.timestamp())
    cache_key = (location, start.date().isoformat())
    if hourly_cache is not None:
        cached_hour = hourly_cache.get(cache_key, {}).get(requested_epoch)
        if cached_hour is not None:
            return dict(cached_hour), 0
    url = f"{TIMELINE_URL}/{location}/{start.strftime('%Y-%m-%dT%H:%M:%S')}/{end.strftime('%Y-%m-%dT%H:%M:%S')}"
    params = {
        "key": credential,
        "unitGroup": "metric",
        "timezone": "Z",
        "include": "hours",
        "lang": "en",
        "elements": ",".join(LOGGER_FIELDS),
        "contentType": "json",
    }

    for attempt in range(2):
        if reserve_quota(1) is None:
            raise WeatherQuotaExceeded(
                f"Weather request quota reached ({QUOTA_HARD_CAP} local requests per rolling 24 hours)."
            )
        try:
            response = get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt == 0:
                sleep(1.0)
                continue
            raise WeatherProviderError("Weather provider request timed out or could not connect.") from exc
        except requests.RequestException as exc:
            raise WeatherProviderError("Weather provider request failed.") from exc

        status_code = int(getattr(response, "status_code", 0))
        if status_code == 429:
            raise WeatherProviderError(
                "Visual Crossing rate limit reached.",
                status_code=429,
                retry_after=getattr(response, "headers", {}).get("Retry-After"),
                stop_run=True,
            )
        if status_code >= 500:
            if attempt == 0:
                sleep(1.0)
                continue
            raise WeatherProviderError("Visual Crossing server error.", status_code=status_code)
        if status_code >= 400:
            raise WeatherProviderError(
                f"Visual Crossing rejected the request (HTTP {status_code}).",
                status_code=status_code,
                stop_run=True,
            )
        try:
            data = response.json()
        except (ValueError, AttributeError) as exc:
            raise WeatherProviderError("Visual Crossing returned invalid JSON.") from exc
        if not isinstance(data, Mapping):
            raise WeatherProviderError("Visual Crossing returned an unexpected response.")
        try:
            query_cost = int(data.get("queryCost", 0))
        except (TypeError, ValueError) as exc:
            raise WeatherProviderError("Visual Crossing returned an invalid query cost.") from exc
        if query_cost < 1:
            raise WeatherProviderError(
                f"Visual Crossing returned an invalid query cost ({query_cost}).",
                stop_run=True,
            )
        if query_cost > 1 and reserve_quota(query_cost - 1) is None:
            raise WeatherQuotaExceeded(
                f"Visual Crossing request cost ({query_cost} records) exceeded the local "
                f"rolling 24-hour quota cap of {QUOTA_HARD_CAP}."
            )
        hour = _weather_hour(data, requested_epoch)
        if hour is None:
            raise WeatherProviderError("Visual Crossing has no record for the requested hour.")
        normalized_hour = normalize_visual_crossing_hour(hour)
        if hourly_cache is not None:
            cached_day = hourly_cache.setdefault(cache_key, {})
            for day in data.get("days", []):
                if not isinstance(day, Mapping):
                    continue
                for returned_hour in day.get("hours", []):
                    if not isinstance(returned_hour, Mapping):
                        continue
                    try:
                        returned_epoch = int(returned_hour.get("datetimeEpoch", -1))
                        returned_date = datetime.fromtimestamp(
                            returned_epoch, tz=timezone.utc,
                        ).date().isoformat()
                    except (OverflowError, OSError, TypeError, ValueError):
                        continue
                    if returned_date == cache_key[1]:
                        cached_day[returned_epoch] = normalize_visual_crossing_hour(returned_hour)
            cached_day[requested_epoch] = normalized_hour
        return normalized_hour, query_cost
    raise WeatherProviderError("Visual Crossing request exhausted retries.")


def _number_or_none(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def normalize_visual_crossing_hour(hour: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize documented provider fields to Kinetiqo's metric contract."""
    wind_kmh = _number_or_none(hour.get("windspeed"))
    gust_kmh = _number_or_none(hour.get("windgust"))
    precip_type = hour.get("preciptype")
    if isinstance(precip_type, str):
        precip_type = [part.strip().lower() for part in precip_type.split(",") if part.strip()]
    elif isinstance(precip_type, list):
        precip_type = [str(part).strip().lower() for part in precip_type if part]
    else:
        precip_type = None
    provider_events = hour.get("events")
    if isinstance(provider_events, str):
        provider_events = [part.strip() for part in provider_events.split(",") if part.strip()]
    elif isinstance(provider_events, list):
        provider_events = [str(part).strip() for part in provider_events if part]
    else:
        provider_events = None
    return {
        "temperature_c": _number_or_none(hour.get("temp")),
        "apparent_temperature_c": _number_or_none(hour.get("feelslike")),
        "precipitation_mm": _number_or_none(hour.get("precip")),
        "snowfall_cm": _number_or_none(hour.get("snow")),
        "precipitation_types": precip_type,
        "conditions": str(hour.get("conditions")).strip() if hour.get("conditions") else None,
        "provider_events": provider_events,
        "wind_direction_deg": _number_or_none(hour.get("winddir")),
        "wind_speed_ms": wind_kmh / 3.6 if wind_kmh is not None else None,
        "wind_gusts_ms": gust_kmh / 3.6 if gust_kmh is not None else None,
        "source": str(hour.get("source")).strip() if hour.get("source") else None,
    }


def build_activity_weather(
    activity: Mapping[str, Any],
    gps_points: Sequence[Mapping[str, Any]],
    fetch_hour: Callable[..., tuple[dict[str, Any], int]],
    reserve_quota: Callable[[int], int | None],
    *,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Fetch one Visual Crossing record per valid route-hour and derive headwind."""
    start = parse_utc(activity.get("start_date") or activity.get("start_date_utc"))
    elapsed = activity.get("elapsed_time")
    if start is None or not isinstance(elapsed, (int, float)) or elapsed <= 0:
        raise ValueError("Activity has no valid start time or elapsed duration.")
    end = start + timedelta(seconds=int(elapsed))
    samples: list[dict[str, Any]] = []
    for hour_start, _ in hourly_intervals(start, end):
        if should_stop and should_stop():
            break
        interval_start = max(start, hour_start)
        interval_end = min(end, hour_start + timedelta(hours=1))
        interval_seconds = int((interval_end - interval_start).total_seconds())
        lookup_time = interval_start + timedelta(seconds=interval_seconds / 2)
        position = interpolate_route_position(gps_points, lookup_time)
        if position is None:
            continue
        distance_start = interpolate_route_position(gps_points, interval_start)
        distance_end = interpolate_route_position(gps_points, interval_end)
        route_distance = None
        if (
            distance_start is not None
            and distance_end is not None
            and distance_start.get("distance_m") is not None
            and distance_end.get("distance_m") is not None
        ):
            route_distance = max(0.0, distance_end["distance_m"] - distance_start["distance_m"])
        values, query_cost = fetch_hour(
            position["latitude"], position["longitude"], hour_start,
            reserve_quota=reserve_quota,
        )
        wind_speed = values.get("wind_speed_ms")
        wind_direction = values.get("wind_direction_deg")
        bearing = position["bearing_deg"]
        headwind = None
        if wind_speed is not None and wind_direction is not None:
            headwind = wind_speed * math.cos(math.radians(wind_direction - bearing))
        samples.append({
            "time_utc": hour_start.isoformat(),
            "interval_seconds": interval_seconds,
            **values,
            "route_bearing_deg": bearing,
            "headwind_component_ms": headwind,
            "route_distance_m": route_distance,
            "query_cost": query_cost,
        })
    return {
        "schema_version": 1,
        "status": "complete" if samples else "deferred_no_route_coverage",
        "provider": "visual-crossing",
        "resolution": "hourly",
        "attribution_url": "https://www.visualcrossing.com/",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "activity": {
            "start_utc": start.isoformat(),
            "end_utc": end.isoformat(),
            "sport_type": str(activity.get("sport_type") or activity.get("sport") or ""),
        },
        "units": {
            "temperature": "°C",
            "precipitation": "mm",
            "snowfall": "cm",
            "wind_speed": "m/s",
            "wind_direction": "degrees",
            "headwind_component": "m/s",
        },
        "samples": samples,
    }


def skipped_activity_weather(activity: Mapping[str, Any], status: str) -> dict[str, Any]:
    """Create a terminal no-request result for an ineligible activity."""
    start = parse_utc(activity.get("start_date") or activity.get("start_date_utc"))
    elapsed = activity.get("elapsed_time")
    end = start + timedelta(seconds=int(elapsed)) if start and isinstance(elapsed, (int, float)) and elapsed > 0 else None
    return {
        "schema_version": 1,
        "status": status,
        "provider": "visual-crossing",
        "resolution": "hourly",
        "attribution_url": "https://www.visualcrossing.com/",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "activity": {
            "start_utc": start.isoformat() if start else None,
            "end_utc": end.isoformat() if end else None,
            "sport_type": str(activity.get("sport_type") or activity.get("sport") or ""),
        },
        "samples": [],
    }


def _weighted_mean(samples: Iterable[Mapping[str, Any]], key: str) -> float | None:
    weighted_sum = 0.0
    weights = 0
    for sample in samples:
        value = _number_or_none(sample.get(key))
        seconds = _number_or_none(sample.get("interval_seconds"))
        if value is not None and seconds is not None and seconds > 0:
            weighted_sum += value * seconds
            weights += int(seconds)
    return weighted_sum / weights if weights else None


def _weighted_wind_direction(samples: Sequence[Mapping[str, Any]]) -> float | None:
    sine = 0.0
    cosine = 0.0
    seconds = 0.0
    valid: list[tuple[float, float]] = []
    for sample in samples:
        direction = _number_or_none(sample.get("wind_direction_deg"))
        speed = _number_or_none(sample.get("wind_speed_ms"))
        duration = _number_or_none(sample.get("interval_seconds"))
        if direction is None or speed is None or duration is None or duration <= 0:
            continue
        angle = math.radians(direction)
        sine += math.sin(angle) * duration
        cosine += math.cos(angle) * duration
        seconds += duration
        valid.append((direction, duration))
    if not seconds or math.isclose(sine, 0.0, abs_tol=1e-12) and math.isclose(cosine, 0.0, abs_tol=1e-12):
        return None
    mean = math.degrees(math.atan2(sine, cosine)) % 360.0
    aligned_seconds = sum(
        duration for direction, duration in valid
        if abs((direction - mean + 180.0) % 360.0 - 180.0) <= 45.0
    )
    return mean if aligned_seconds / seconds >= 0.7 else None


def _classify(value: float, bands: Sequence[tuple[float, str]]) -> str:
    rounded = round(value, 1)
    for ceiling, label in bands:
        if rounded <= ceiling:
            return label
    return bands[-1][1]


def format_weather_placeholders(payload: Any) -> dict[str, str]:
    """Return deterministic concise weather placeholders for a stored payload."""
    empty = {
        "weather-basic": "",
        "weather-start": "",
        "weather-precipitation": "",
        "weather-wind": "",
    }
    if isinstance(payload, str):
        try:
            import json
            payload = json.loads(payload)
        except (TypeError, ValueError):
            return empty
    if not isinstance(payload, Mapping) or payload.get("status") != "complete":
        return empty
    raw_samples = payload.get("samples", [])
    if not isinstance(raw_samples, list):
        return empty
    activity = payload.get("activity")
    activity = activity if isinstance(activity, Mapping) else {}
    activity_start = parse_utc(activity.get("start_utc"))
    activity_end = parse_utc(activity.get("end_utc"))
    samples = [
        sample for sample in raw_samples
        if isinstance(sample, Mapping) and _number_or_none(sample.get("interval_seconds")) is not None
        and _number_or_none(sample.get("interval_seconds")) > 0
        and (
            not sample.get("time_utc")
            or (
                (sample_time := parse_utc(sample.get("time_utc"))) is not None
                and (activity_start is None or sample_time >= activity_start)
                and (activity_end is None or sample_time < activity_end)
            )
        )
    ]
    if not samples:
        return empty

    valid_conditions = [(str(s.get("conditions")).strip(), int(s.get("interval_seconds") or 0))
                        for s in samples if s.get("conditions")]
    dominant_condition = ""
    if valid_conditions:
        condition_weights = Counter()
        for condition, seconds in valid_conditions:
            condition_weights[condition] += seconds
        dominant_condition = condition_weights.most_common(1)[0][0]
    severe_terms = (
        "thunderstorm", "blizzard", "supercell", "tornado", "hail",
        "freezing", "ice storm", "heavy snow", "heavy rain", "squall",
        "hurricane", "tropical storm", "whiteout",
    )
    severe_conditions = []
    provider_events = []
    for sample in samples:
        condition = str(sample.get("conditions") or "").strip()
        if condition and any(term in condition.lower() for term in severe_terms):
            if condition.lower() not in {item.lower() for item in severe_conditions}:
                severe_conditions.append(condition)
        raw_events = sample.get("provider_events") or []
        if isinstance(raw_events, str):
            raw_events = [raw_events]
        if isinstance(raw_events, list):
            for event in raw_events:
                event_text = str(event).strip()
                if event_text and event_text.lower() not in {item.lower() for item in provider_events}:
                    provider_events.append(event_text)
    first_sample = samples[0]
    start_parts = [str(first_sample.get("conditions") or "").strip()]
    if first_sample.get("precipitation_types"):
        start_parts.extend(str(x) for x in first_sample["precipitation_types"])
    temp = _number_or_none(first_sample.get("temperature_c"))
    if temp is not None:
        start_parts.append(f"{round(temp)}°C")
    weather_start = ", ".join(part for part in start_parts if part)

    precip_total = sum(
        (_number_or_none(s.get("precipitation_mm")) or 0.0)
        * min(1.0, int(s.get("interval_seconds") or 0) / WEATHER_INTERVAL_SECONDS)
        for s in samples
    )
    snow_total = sum(
        (_number_or_none(s.get("snowfall_cm")) or 0.0)
        * min(1.0, int(s.get("interval_seconds") or 0) / WEATHER_INTERVAL_SECONDS)
        for s in samples
    )
    precip_types = {
        str(kind).lower()
        for sample in samples
        for kind in (sample.get("precipitation_types") or [])
    }
    precip_parts: list[str] = []
    if precip_total > 0 and "rain" in precip_types:
        rain_word = "trace rain" if round(precip_total, 1) == 0 else f"{precip_total:.1f} mm rain"
        precip_parts.append(rain_word)
    if snow_total > 0 or "snow" in precip_types:
        snow_word = "trace snow" if round(snow_total, 1) == 0 else f"{snow_total:.1f} cm snow"
        precip_parts.append(snow_word)
    if precip_total > 0 and not precip_types:
        precip_parts.append(f"{precip_total:.1f} mm precipitation")
    weather_precipitation = " and ".join(precip_parts)
    precip_sample_indexes = [
        index for index, sample in enumerate(samples)
        if (_number_or_none(sample.get("precipitation_mm")) or 0) > 0
        or (_number_or_none(sample.get("snowfall_cm")) or 0) > 0
    ]
    precipitation_timing = ""
    if precip_sample_indexes:
        first = precip_sample_indexes[0] / max(1, len(samples) - 1)
        last = precip_sample_indexes[-1] / max(1, len(samples) - 1)
        if last < 0.34:
            precipitation_timing = "early in the activity"
        elif first > 0.66:
            precipitation_timing = "late in the activity"
        elif first < 0.34 and last > 0.66:
            precipitation_timing = "throughout the activity"
        else:
            precipitation_timing = "during the activity"

    weighted_temp = _weighted_mean(samples, "temperature_c")
    weighted_feels = _weighted_mean(samples, "apparent_temperature_c")
    peak_feels = max((_number_or_none(s.get("apparent_temperature_c")) for s in samples
                      if _number_or_none(s.get("apparent_temperature_c")) is not None), default=None)
    lowest_air = min((_number_or_none(s.get("temperature_c")) for s in samples
                      if _number_or_none(s.get("temperature_c")) is not None), default=None)
    lowest_feels = min((_number_or_none(s.get("apparent_temperature_c")) for s in samples
                        if _number_or_none(s.get("apparent_temperature_c")) is not None), default=None)
    temp_parts: list[str] = []
    if weighted_temp is not None:
        temp_parts.append(f"around {round(weighted_temp)}°C")
    if weighted_feels is not None:
        temp_parts.append(f"feels like {round(weighted_feels)}°C")
    if peak_feels is not None:
        if peak_feels >= 35:
            temp_parts.append("very hot")
        elif peak_feels >= 30:
            temp_parts.append("hot")
    coldest = min(
        (value for value in (lowest_air, lowest_feels) if value is not None),
        default=None,
    )
    if coldest is not None:
        if coldest <= FREEZING_TEMPERATURE_THRESHOLD_C:
            qualifier = "freezing"
        elif coldest < COLD_TEMPERATURE_THRESHOLD_C:
            qualifier = "cold"
        else:
            qualifier = ""
        if qualifier:
            if lowest_feels is not None and lowest_feels < (lowest_air if lowest_air is not None else math.inf):
                temp_parts.append(f"{qualifier}, feels like as low as {lowest_feels:.1f}°C")
            elif lowest_air is not None:
                temp_parts.append(f"{qualifier}, down to {lowest_air:.1f}°C")
            else:
                temp_parts.append(f"{qualifier}, feels like {lowest_feels:.1f}°C")

    mean_wind = _weighted_mean(samples, "wind_speed_ms")
    gusts = [_number_or_none(s.get("wind_gusts_ms")) for s in samples]
    max_gust = max((value for value in gusts if value is not None), default=None)
    sport_type = str(activity.get("sport_type") or "").lower()
    cycling = any(word in sport_type for word in ("ride", "cycling", "cycle"))
    wind_parts: list[str] = []
    if mean_wind is not None and mean_wind >= 2.8:
        direction = _weighted_wind_direction(samples)
        direction_text = ""
        if direction is not None:
            compass = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
            direction_text = f"{compass[round(direction / 45.0) % 8]} "
        wind_parts.append(f"{direction_text}wind {mean_wind:.1f} m/s")
    if max_gust is not None and max_gust > 0:
        gust_label = _classify(max_gust, GUST_BANDS) if cycling else ""
        if not cycling or max_gust >= 8.0:
            wind_parts.append(f"{gust_label} up to {max_gust:.1f} m/s".strip())
    mean_headwind = _weighted_mean(
        [s for s in samples if (_number_or_none(s.get("headwind_component_ms")) or 0) > 0],
        "headwind_component_ms",
    )
    valid_wind_samples = [
        sample for sample in samples
        if _number_or_none(sample.get("wind_speed_ms")) is not None
        and _number_or_none(sample.get("wind_direction_deg")) is not None
        and _number_or_none(sample.get("headwind_component_ms")) is not None
    ]
    covered = sum(int(sample.get("interval_seconds") or 0) for sample in valid_wind_samples)
    total_activity = (activity_end - activity_start).total_seconds() if activity_start and activity_end else 0
    coverage_sufficient = bool(total_activity and covered >= 0.3 * total_activity)
    if cycling and mean_headwind is not None and mean_headwind >= 2.8 and coverage_sufficient:
        wind_parts.append(
            f"{_classify(mean_headwind, HEADWIND_BANDS).lower()} {mean_headwind:.1f} m/s headwind"
        )
    if cycling:
        positive = [
            s for s in samples if (_number_or_none(s.get("headwind_component_ms")) or 0) > 0
        ]
        if positive:
            positive_seconds = sum(int(s.get("interval_seconds") or 0) for s in positive)
            if covered and coverage_sufficient:
                percent = round(positive_seconds / covered * 100)
                wind_parts.append(f"headwind during {percent}% of covered ride time")
            peak_headwind = max(
                (_number_or_none(s.get("headwind_component_ms")) for s in positive),
                default=None,
            )
            if peak_headwind is not None:
                wind_parts.append(f"peak {peak_headwind:.1f} m/s headwind")
            positive_distance = sum(
                _number_or_none(s.get("route_distance_m")) or 0
                for s in positive
                if _number_or_none(s.get("route_distance_m")) is not None
            )
            if positive_distance > 0:
                wind_parts.append(f"about {positive_distance / 1000:.1f} km into headwinds")

    basic_parts = [dominant_condition] if dominant_condition else []
    for condition in severe_conditions:
        if condition.lower() != dominant_condition.lower():
            basic_parts.append(condition)
    basic_parts.extend(provider_events)
    if weather_precipitation:
        basic_parts.append(" ".join((weather_precipitation, precipitation_timing)).strip())
    basic_parts.extend(temp_parts)
    basic_parts.extend(wind_parts)
    basic = ", ".join(part for part in basic_parts if part).strip()
    if basic:
        basic = basic[0].upper() + basic[1:]
        if not basic.endswith("."):
            basic += "."
    return {
        "weather-basic": basic,
        "weather-start": weather_start,
        "weather-precipitation": weather_precipitation,
        "weather-wind": ", ".join(wind_parts),
    }
