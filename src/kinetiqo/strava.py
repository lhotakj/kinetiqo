import json
import logging
from pathlib import Path
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Mapping, Any, Optional

import requests

from .cache import CacheManager
from .config import Config

logger = logging.getLogger("kinetiqo")

_MAX_ERROR_BODY_LEN = 300


class StravaFetchError(RuntimeError):
    """Raised when fetching activities from Strava fails after all retries.

    Callers (see :class:`kinetiqo.sync.SyncService`) must treat this as a
    signal that the fetched activity set is incomplete/unreliable and must
    **not** infer that any activity missing from it was deleted on Strava —
    doing so would wrongly delete local data during an outage or an expired
    token, rather than only when Strava genuinely no longer has the activity.
    """


class StravaAuthError(requests.exceptions.HTTPError):
    """Raised when Strava authentication fails (HTTP 401 Unauthorized) and cannot
    be recovered by refreshing the OAuth access token.
    """


class StravaRateLimitError(requests.exceptions.HTTPError):
    """Raised when Strava API rate limit is exceeded (HTTP 429 Too Many Requests)."""


def parse_rate_limit_header(header_val: Any) -> tuple[int, int] | None:
    """Parse comma-separated pair '<15_min>, <daily>' from a Strava rate limit header.

    Examples:
        '100,1000' -> (100, 1000)
        '200, 2000' -> (200, 2000)
        ' 90 , 450 ' -> (90, 450)
    """
    if not header_val:
        return None
    try:
        parts = [p.strip() for p in str(header_val).split(",")]
        if len(parts) >= 2:
            return int(parts[0]), int(parts[1])
        if len(parts) == 1 and parts[0].isdigit():
            val = int(parts[0])
            return val, val
    except (ValueError, TypeError):
        pass
    return None


class StravaRateLimitTracker:
    """Thread-safe tracker for Strava API rate limits.

    Monitors 15-minute and daily rate limits and usage reported by Strava headers:
      - X-RateLimit-Limit & X-RateLimit-Usage
      - X-ReadRateLimit-Limit & X-ReadRateLimit-Usage
      - X-RateLimit-Remaining (fallback)

    When usage reaches >= 90% of any limit, records an active warning message.
    The warning automatically expires when the corresponding window resets:
      - 15-minute window resets at :00, :15, :30, :45 of each hour.
      - Daily window resets at 00:00 UTC.
    """

    def __init__(self, cache_file: Path | None = None) -> None:
        self._lock = threading.Lock()
        self.cache_file = cache_file
        self.active_warning: str | None = None
        self.warning_expires_at: float = 0.0
        self.last_short_limit: int = 0
        self.last_short_usage: int = 0
        self.last_daily_limit: int = 0
        self.last_daily_usage: int = 0
        self.updated_at: float = 0.0

    @staticmethod
    def next_15m_reset(now_ts: float) -> float:
        return float(((int(now_ts) // 900) + 1) * 900)

    @staticmethod
    def next_daily_reset(now_utc: datetime) -> float:
        tomorrow = (now_utc + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return tomorrow.timestamp()

    def observe(self, headers: Mapping[str, Any] | None, now_ts: float | None = None) -> str | None:
        """Inspect HTTP response headers for Strava rate limits and usage.

        Returns:
            str | None: A warning message if >= 90% of any limit has been reached,
            or None otherwise.
        """
        if not isinstance(headers, Mapping) or not headers:
            return None

        def _get_h(target_name: str) -> str | None:
            t = target_name.lower()
            for k, v in headers.items():
                if str(k).lower() == t:
                    return str(v)
            return None

        limit_val = parse_rate_limit_header(_get_h("X-RateLimit-Limit"))
        usage_val = parse_rate_limit_header(_get_h("X-RateLimit-Usage"))
        read_limit_val = parse_rate_limit_header(_get_h("X-ReadRateLimit-Limit"))
        read_usage_val = parse_rate_limit_header(_get_h("X-ReadRateLimit-Usage"))

        # Fallback to X-RateLimit-Remaining if usage is missing
        if limit_val and not usage_val:
            rem_val = parse_rate_limit_header(_get_h("X-RateLimit-Remaining"))
            if rem_val:
                usage_val = (max(0, limit_val[0] - rem_val[0]), max(0, limit_val[1] - rem_val[1]))

        if not limit_val and not read_limit_val:
            return None

        now = now_ts or time.time()
        now_dt = datetime.fromtimestamp(now, tz=timezone.utc)
        reset_15m = self.next_15m_reset(now)
        reset_daily = self.next_daily_reset(now_dt)

        windows: list[tuple[str, int, int, bool]] = []
        # (label, limit, usage, is_daily)
        if limit_val and usage_val and limit_val[0] > 0:
            windows.append(("15-minute", limit_val[0], usage_val[0], False))
        if limit_val and usage_val and limit_val[1] > 0:
            windows.append(("daily", limit_val[1], usage_val[1], True))
        if read_limit_val and read_usage_val and read_limit_val[0] > 0:
            windows.append(("15-minute read", read_limit_val[0], read_usage_val[0], False))
        if read_limit_val and read_usage_val and read_limit_val[1] > 0:
            windows.append(("daily read", read_limit_val[1], read_usage_val[1], True))

        if not windows:
            return None

        exceeded_windows: list[str] = []
        max_expiry: float = 0.0

        for label, lim, use, is_daily in windows:
            ratio = use / lim
            if ratio >= 0.90:
                rem = max(0, lim - use)
                exceeded_windows.append(f"{label}: {use}/{lim} requests used, {rem} remaining")
                expiry = reset_daily if is_daily else reset_15m
                if expiry > max_expiry:
                    max_expiry = expiry

        with self._lock:
            self.updated_at = now
            if limit_val and usage_val:
                self.last_short_limit = limit_val[0]
                self.last_short_usage = usage_val[0]
                self.last_daily_limit = limit_val[1]
                self.last_daily_usage = usage_val[1]

            if exceeded_windows:
                detail_str = "; ".join(exceeded_windows)
                self.active_warning = f"Strava API rate limit warning: 90% limit has been reached ({detail_str})."
                self.warning_expires_at = max_expiry
            else:
                self.active_warning = None
                self.warning_expires_at = 0.0

            result = self.active_warning

            if self.cache_file:
                try:
                    self.cache_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.cache_file, "w") as f:
                        json.dump({
                            "active_warning": self.active_warning,
                            "warning_expires_at": self.warning_expires_at,
                            "updated_at": self.updated_at,
                            "short_limit": self.last_short_limit,
                            "short_usage": self.last_short_usage,
                            "daily_limit": self.last_daily_limit,
                            "daily_usage": self.last_daily_usage,
                        }, f)
                except Exception:
                    pass

            return result

    def get_active_warning(self, now_ts: float | None = None) -> str | None:
        """Return the active rate limit warning message if valid, else None."""
        now = now_ts or time.time()
        with self._lock:
            if self.active_warning:
                if now < self.warning_expires_at:
                    return self.active_warning
                self.active_warning = None
                self.warning_expires_at = 0.0

            if self.cache_file and self.cache_file.exists():
                try:
                    with open(self.cache_file, "r") as f:
                        data = json.load(f)
                    expires_at = float(data.get("warning_expires_at", 0.0))
                    if now < expires_at:
                        self.active_warning = data.get("active_warning")
                        self.warning_expires_at = expires_at
                        return self.active_warning
                except Exception:
                    pass
            return None

    def reset(self) -> None:
        with self._lock:
            self.active_warning = None
            self.warning_expires_at = 0.0
            self.updated_at = 0.0
            if self.cache_file and self.cache_file.exists():
                try:
                    self.cache_file.unlink()
                except Exception:
                    pass


DEFAULT_STRAVA_RATE_LIMIT_CACHE = Path(".cache/strava_rate_limits.json")
GLOBAL_RATE_LIMIT_TRACKER = StravaRateLimitTracker(DEFAULT_STRAVA_RATE_LIMIT_CACHE)


def get_active_rate_limit_warning() -> str | None:
    """Return the active Strava rate limit warning message if 90% limit has been reached,
    or None if within normal limits or window has reset.
    """
    return GLOBAL_RATE_LIMIT_TRACKER.get_active_warning()


def reset_rate_limits() -> None:
    """Reset the global rate limit tracker state (primarily for tests)."""
    GLOBAL_RATE_LIMIT_TRACKER.reset()



def _summarise_error_body(response: requests.Response) -> str:
    """Return a concise single-line summary of an error response body.

    Strava returns a full HTML maintenance page (several KB) on outages.
    Logging the raw body fills the log with noise.  This helper detects HTML
    and replaces it with a brief description; JSON bodies are truncated.
    """
    content_type = response.headers.get("Content-Type", "")
    body = response.text or ""
    if "text/html" in content_type or body.lstrip().startswith("<!"):
        title = ""
        import re
        m = re.search(r"<title>([^<]+)</title>", body, re.IGNORECASE)
        if m:
            title = f": {m.group(1).strip()}"
        return f"[HTML response{title}]"
    if len(body) > _MAX_ERROR_BODY_LEN:
        return body[:_MAX_ERROR_BODY_LEN] + "…"
    return body


class StravaClient:
    """Simple Strava API client used by Kinetiqo for fetching activities,
    athlete profile and activity streams. Supports basic retry logic and
    optional file-based caching via CacheManager.
    """

    BASE_URL = "https://www.strava.com/api/v3"

    def __init__(self, config: Config):
        """Initialize the Strava client.

        Args:
            config (Config): Application configuration with Strava credentials
                and optional client settings (timeouts, retries).
        """
        self.config = config
        self._access_token = None
        self._expires_at = None
        self.cache = CacheManager(config)
        # Network timeout in seconds for (connect, read)
        self.request_timeout = getattr(self.config, 'strava_request_timeout', 15)
        # Simple retry count for transient network errors
        self.request_retries = getattr(self.config, 'strava_request_retries', 2)
        self.rate_limit_tracker = GLOBAL_RATE_LIMIT_TRACKER
        if hasattr(self.config, 'cache_dir') and self.config.cache_dir:
            try:
                self.rate_limit_tracker.cache_file = Path(self.config.cache_dir) / "strava_rate_limits.json"
            except Exception:
                pass
        self._rate_limit_warning_callback = None
        self._rate_limit_warnings: list[str] = []
        self._last_logged_rate_limit_warning: str | None = None

    def set_rate_limit_warning_callback(self, callback: Any) -> None:
        """Register a callback to be invoked whenever a 90% rate limit warning is detected."""
        self._rate_limit_warning_callback = callback

    def pop_rate_limit_warnings(self) -> list[str]:
        """Drain and return queued rate limit warnings from this client instance."""
        warnings = list(self._rate_limit_warnings)
        self._rate_limit_warnings.clear()
        return warnings

    def get_active_rate_limit_warning(self) -> str | None:
        """Return the current active rate limit warning message, or None."""
        return self.rate_limit_tracker.get_active_warning()

    def _observe_rate_limits(self, headers: Mapping[str, Any] | None) -> str | None:
        """Inspect HTTP response headers for Strava rate limits.

        If 90% of any limit has been reached, logs a warning, updates the tracker,
        and invokes any registered callback.
        """
        warning_msg = self.rate_limit_tracker.observe(headers)
        if warning_msg:
            if warning_msg != self._last_logged_rate_limit_warning:
                self._last_logged_rate_limit_warning = warning_msg
                logger.warning(warning_msg)

            if warning_msg not in self._rate_limit_warnings:
                self._rate_limit_warnings.append(warning_msg)

            if self._rate_limit_warning_callback:
                try:
                    self._rate_limit_warning_callback(warning_msg)
                except Exception as cb_err:
                    logger.debug(f"Rate limit callback error: {cb_err}")
            return warning_msg
        else:
            self._last_logged_rate_limit_warning = None
            return None

    def _get_access_token(self, force_refresh: bool = False) -> str:
        """Exchange the refresh token for an access token and cache it.

        Auto-refreshes if the cached access token is expired or within 2 minutes
        of expiration, or if force_refresh is True.

        Returns:
            str: A valid OAuth2 access token for Strava API calls.
        """
        now = time.time()
        if not force_refresh and self._access_token:
            if self._expires_at is None or now < (self._expires_at - 120):
                return self._access_token
            logger.info("Strava access token has expired or is nearing expiration. Refreshing...")

        logger.debug("Access token not found, expired, or refresh requested. Refreshing...")
        url = "https://www.strava.com/oauth/token"
        payload = {
            "client_id": self.config.strava_client_id,
            "client_secret": self.config.strava_client_secret,
            "refresh_token": self.config.strava_refresh_token,
            "grant_type": "refresh_token"
        }

        logger.debug(f"POST {url}")
        try:
            r = requests.post(url, data=payload, timeout=self.request_timeout)
        except Exception as e:
            logger.exception(f"Token exchange request failed: {e}")
            raise

        if r.status_code != 200:
            logger.error("Token exchange failed: %s — %s", r.status_code, _summarise_error_body(r))
            r.raise_for_status()

        data = r.json()
        self._access_token = data["access_token"]
        self._expires_at = data.get("expires_at")
        if not self._expires_at and "expires_in" in data:
            self._expires_at = int(time.time()) + int(data["expires_in"])
        new_refresh_token = data.get("refresh_token")
        if new_refresh_token and new_refresh_token != self.config.strava_refresh_token:
            self.config.strava_refresh_token = new_refresh_token
            self._notify_refresh_token_changed(new_refresh_token)
        logger.debug("Access token refreshed successfully.")

        if new_refresh_token:
            logger.debug("New Strava refresh token issued and stored in memory.")

        return self._access_token

    def _notify_refresh_token_changed(self, new_refresh_token: str) -> None:
        """Invoke the configured callback so the rotated token can be persisted.

        Strava issues a new refresh token — and invalidates the previous one
        — on every token exchange. If the rotated token is only kept on the
        in-memory ``Config`` instance, it is lost when the process exits,
        which then makes the *next* startup fail immediately with an
        "invalid" refresh_token error (even though the previous run ended
        cleanly). See :mod:`kinetiqo.profile_sync` for the callback that
        persists it to the database.
        """
        callback = getattr(self.config, "on_refresh_token_changed", None)
        if not callback:
            return
        try:
            callback(new_refresh_token)
        except Exception:
            logger.exception("Failed to persist rotated Strava refresh token.")

    def exchange_authorization_code(self, code: str) -> dict:
        """Exchange an OAuth authorization code for tokens."""
        url = "https://www.strava.com/oauth/token"
        payload = {
            "client_id": self.config.strava_client_id,
            "client_secret": self.config.strava_client_secret,
            "code": code,
            "grant_type": "authorization_code",
        }

        logger.debug(f"POST {url} (authorization_code exchange)")
        try:
            r = requests.post(url, data=payload, timeout=self.request_timeout)
        except Exception as e:
            logger.exception(f"Authorization code exchange failed: {e}")
            raise

        if r.status_code != 200:
            logger.error("Authorization code exchange failed: %s — %s", r.status_code, _summarise_error_body(r))
            r.raise_for_status()

        data = r.json()
        self._access_token = data.get("access_token")
        self._expires_at = data.get("expires_at")
        if not self._expires_at and "expires_in" in data:
            self._expires_at = int(time.time()) + int(data["expires_in"])
        new_refresh_token = data.get("refresh_token")
        if new_refresh_token and new_refresh_token != self.config.strava_refresh_token:
            self.config.strava_refresh_token = new_refresh_token
            self._notify_refresh_token_changed(new_refresh_token)
        return data

    def _headers(self) -> dict:
        """Return HTTP headers for authenticated requests.

        Returns:
            dict: Headers with Authorization Bearer token.
        """
        return {"Authorization": f"Bearer {self._get_access_token()}"}

    def _request(self, method: str, url: str, refresh_on_401: bool = True, **kwargs) -> requests.Response:
        """Execute an authenticated HTTP request against Strava API with error handling,
        automatic token refresh on 401, rate-limiting detection, and transient retries.
        """
        attempt = 0
        token_refreshed_on_401 = False

        while True:
            attempt += 1
            headers = dict(kwargs.pop("headers", None) or self._headers())
            if "Authorization" not in headers:
                headers.update(self._headers())

            req_kwargs = dict(kwargs)
            req_kwargs["headers"] = headers
            if "timeout" not in req_kwargs:
                req_kwargs["timeout"] = self.request_timeout

            try:
                meth = method.upper()
                if meth == "GET":
                    r = requests.get(url, **req_kwargs)
                elif meth == "PUT":
                    r = requests.put(url, **req_kwargs)
                elif meth == "POST":
                    r = requests.post(url, **req_kwargs)
                elif meth == "DELETE":
                    r = requests.delete(url, **req_kwargs)
                else:
                    r = requests.request(method, url, **req_kwargs)

                self._observe_rate_limits(getattr(r, "headers", None))
                r.raise_for_status()
                return r
            except requests.exceptions.HTTPError as e:
                if getattr(e, "response", None) is not None:
                    self._observe_rate_limits(getattr(e.response, "headers", None))
                status_code = e.response.status_code if e.response is not None else None
                if status_code == 401:
                    if refresh_on_401 and not token_refreshed_on_401:
                        logger.warning(
                            f"Strava {method} {url} returned 401 Unauthorized. "
                            "Invalidating access token and attempting refresh..."
                        )
                        token_refreshed_on_401 = True
                        try:
                            self._access_token = None
                            self._expires_at = None
                            self._get_access_token(force_refresh=True)
                            continue
                        except Exception as refresh_err:
                            logger.error(f"Failed to refresh Strava token after 401: {refresh_err}")
                            raise StravaAuthError(
                                f"Strava authentication failed (401 Unauthorized) and token refresh failed: {refresh_err}",
                                response=e.response,
                            ) from refresh_err

                    logger.error(
                        f"Strava {method} {url} returned 401 Unauthorized"
                        + (" even after refreshing token." if token_refreshed_on_401 else ".")
                        + " Stopping retries."
                    )
                    raise StravaAuthError(
                        f"Strava authentication failed: 401 Client Error: Unauthorized for url: {url}",
                        response=e.response,
                    ) from e

                if status_code == 429:
                    logger.warning(f"Strava rate limit exceeded (HTTP 429) on {method} {url}.")
                    retry_after = e.response.headers.get("Retry-After") if e.response is not None else None
                    if retry_after and retry_after.isdigit() and int(retry_after) <= 60 and attempt <= self.request_retries:
                        sleep_secs = int(retry_after)
                        logger.warning(f"Waiting {sleep_secs}s as requested by Strava Retry-After header...")
                        time.sleep(sleep_secs)
                        continue
                    raise StravaRateLimitError(
                        f"Strava rate limit exceeded (HTTP 429) for url: {url}",
                        response=e.response,
                    ) from e

                # For client errors (4xx) other than 401/429, do not retry
                if status_code and 400 <= status_code < 500:
                    logger.warning(f"Strava client error (HTTP {status_code}) on {method} {url}: {e}")
                    raise

                # Transient server errors (5xx)
                logger.warning(f"Strava request failed (attempt {attempt}): {e}")
                if attempt > self.request_retries:
                    logger.exception(f"Failed {method} {url} after {attempt} attempts: {e}")
                    raise
                time.sleep(2 ** attempt)

            except requests.exceptions.RequestException as e:
                # Network-level exceptions (timeouts, connection resets)
                logger.warning(f"Strava request failed (attempt {attempt}): {e}")
                if attempt > self.request_retries:
                    logger.exception(f"Failed {method} {url} after {attempt} attempts: {e}")
                    raise
                time.sleep(2 ** attempt)

    def get_activities(self, result_container: list, after: int | None = None):
        """
        Fetch activities, optionally after a given Unix timestamp.
        Yields progress messages.
        Populates result_container with the fetched activities.
        """
        # Check cache first
        cache_params = {"after": after} if after else {}
        cached_activities = self.cache.get("activities", cache_params)
        if cached_activities is not None:
            logger.info(f"Using cached activities list ({len(cached_activities)} activities)")
            yield f"Using cached activities list ({len(cached_activities)} activities)"
            result_container.extend(cached_activities)
            return

        page = 1
        per_page = 200
        activities = []

        logger.info(f"Fetching activities list from Strava (after={after})...")
        yield "Fetching data from Strava ..."

        while True:
            url = f"{self.BASE_URL}/athlete/activities"
            params = {"page": page, "per_page": per_page}
            if after:
                params["after"] = after

            logger.debug(f"GET {url} | params={params}")

            try:
                r = self._request("GET", url, params=params)
            except (StravaAuthError, StravaRateLimitError) as e:
                msg = f"Strava API error on activities page {page}: {e}"
                logger.error(msg)
                yield f"Error: {msg}"
                result_container.extend(activities)
                raise StravaFetchError(str(e)) from e
            except requests.exceptions.RequestException as e:
                msg = f"Failed to fetch activities from Strava after retries: {e}"
                logger.error(msg)
                yield f"Error: {msg}"
                result_container.extend(activities)
                raise StravaFetchError(str(e)) from e

            try:
                batch = r.json()
            except Exception as e:
                logger.exception(f"Failed to decode Strava response JSON: {e}")
                yield f"Error: Failed to decode Strava response: {e}"
                result_container.extend(activities)
                raise StravaFetchError(str(e)) from e

            msg = f"Page {page}: Found {len(batch)} activities."
            logger.debug(msg)
            yield msg

            if batch:
                activities.extend(batch)

            # If the batch is empty or we received fewer activities than we asked for,
            # it means we have reached the end.
            if not batch or len(batch) < per_page:
                logger.debug(f"Reached end of activities on page {page}.")
                break

            page += 1

        # Cache the results
        self.cache.set("activities", activities, cache_params)

        result_container.extend(activities)

    def get_athlete(self) -> dict:
        """Fetch the authenticated athlete's profile from Strava.

        The returned dict includes fields such as ``weight`` (kg),
        ``firstname``, ``lastname``, etc.

        :return: Athlete profile dictionary.
        """
        cached = self.cache.get("athlete")
        if cached is not None:
            logger.debug("Using cached athlete profile")
            return cached

        url = f"{self.BASE_URL}/athlete"
        logger.debug(f"GET {url}")
        r = self._request("GET", url)
        data = r.json()
        self.cache.set("athlete", data)
        return data

    def get_athlete_koms(self, athlete_id: int | str, page: int = 1, per_page: int = 200) -> list[dict]:
        """Fetch the athlete's King of the Mountain (KOM/QOM/CR) efforts from Strava.

        Calls ``GET /api/v3/athletes/{athlete_id}/koms`` to retrieve all segment efforts
        where the athlete currently holds the #1 ranking.

        :param athlete_id: Strava athlete ID.
        :param page: Starting page number (1-indexed).
        :param per_page: Items per page (up to 200).
        :return: List of segment effort dictionaries.
        """
        all_koms = []
        current_page = page

        while True:
            url = f"{self.BASE_URL}/athletes/{athlete_id}/koms"
            params = {"page": current_page, "per_page": per_page}
            logger.debug(f"GET {url} | params={params}")

            r = self._request("GET", url, params=params)
            batch = r.json()
            if not isinstance(batch, list):
                break
            all_koms.extend(batch)
            if len(batch) < per_page:
                break
            current_page += 1

        return all_koms

    def get_streams(self, activity_id: int) -> dict:
        """Fetch detailed streams for an activity."""
        # Check cache first
        cached_streams = self.cache.get(f"streams/{activity_id}")
        if cached_streams is not None:
            logger.debug(f"Using cached streams for activity {activity_id}")
            return cached_streams

        url = f"{self.BASE_URL}/activities/{activity_id}/streams"
        params = {
            "keys": "time,latlng,altitude,heartrate,cadence,velocity_smooth,distance,watts,temp,grade_smooth,moving",
            "key_by_type": "true"
        }
        logger.debug(f"GET {url} | params={params}")

        r = self._request("GET", url, params=params)
        streams = r.json()

        # Cache the streams
        self.cache.set(f"streams/{activity_id}", streams)

        return streams

    def get_activity_detail(self, activity_id) -> dict:
        """Fetch the full (detailed) activity representation from Strava.

        Unlike the summary activities returned by :meth:`get_activities`, the
        detailed representation includes the ``description`` field, which is
        required by the ``UPDATE_STRAVA`` description-update feature. This call
        always hits the network (never cached) so the description we read is
        never stale relative to our own prior updates.

        :param activity_id: Strava activity ID.
        :return: Detailed activity dictionary (includes ``description``).
        """
        url = f"{self.BASE_URL}/activities/{activity_id}"
        logger.debug(f"GET {url}")
        r = self._request("GET", url)
        return r.json()

    def update_activity_description(self, activity_id, description: str) -> dict:
        """Update an activity's description on Strava.

        Note that this endpoint requires the ``activity:write`` OAuth scope
        in addition to the read scopes used everywhere else in this client.
        A ``401 Unauthorized`` here — even though reads (activity list,
        streams, activity detail) succeed fine — almost always means the
        stored refresh token was never authorized with ``activity:write``.
        This is a permanent condition (not a transient auth glitch), so it is
        **not retried**: retrying would just burn the same 401 three times
        with exponential backoff for every single activity in the sync,
        which for e.g. 50+ activities in one run can add several minutes of
        pure waiting for a call that can never succeed until the token is
        reauthorized (Settings → Reconnect with Strava, which now requests
        ``activity:write``).

        :param activity_id: Strava activity ID.
        :param description: New full description text to store.
        :return: The updated activity dictionary as returned by Strava.
        """
        url = f"{self.BASE_URL}/activities/{activity_id}"
        payload = {"description": description}
        logger.debug(f"PUT {url} (updating description)")

        try:
            r = self._request("PUT", url, refresh_on_401=False, data=payload)
            return r.json()
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 401:
                logger.exception(
                    "UPDATE_STRAVA: 401 Unauthorized updating description for activity %s — "
                    "the stored Strava refresh token most likely lacks the 'activity:write' scope "
                    "(reads work, writes don't). Reconnect via Settings -> Reconnect with Strava to "
                    "grant it; not retrying since this won't resolve on its own.",
                    activity_id,
                )
            raise
