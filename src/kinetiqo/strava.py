import logging
import time

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
        self.cache = CacheManager(config)
        # Network timeout in seconds for (connect, read)
        self.request_timeout = getattr(self.config, 'strava_request_timeout', 15)
        # Simple retry count for transient network errors
        self.request_retries = getattr(self.config, 'strava_request_retries', 2)

    def _get_access_token(self) -> str:
        """Exchange the refresh token for an access token and cache it.

        Returns:
            str: A valid OAuth2 access token for Strava API calls.
        """
        if self._access_token:
            return self._access_token

        logger.debug("Access token not found or expired. Refreshing...")
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
        new_refresh_token = data.get("refresh_token")
        if new_refresh_token and new_refresh_token != self.config.strava_refresh_token:
            self.config.strava_refresh_token = new_refresh_token
        logger.debug("Access token refreshed successfully.")

        if new_refresh_token:
            logger.debug("New Strava refresh token issued and stored in memory.")

        return self._access_token

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
        new_refresh_token = data.get("refresh_token")
        if new_refresh_token and new_refresh_token != self.config.strava_refresh_token:
            self.config.strava_refresh_token = new_refresh_token
        return data

    def _headers(self) -> dict:
        """Return HTTP headers for authenticated requests.

        Returns:
            dict: Headers with Authorization Bearer token.
        """
        return {"Authorization": f"Bearer {self._get_access_token()}"}

    def get_activities(self, result_container: list, after: int = None):
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

            # Try with simple retry logic and exponential backoff
            attempt = 0
            while True:
                attempt += 1
                try:
                    r = requests.get(url, headers=self._headers(), params=params, timeout=self.request_timeout)
                    r.raise_for_status()
                    break
                except requests.exceptions.HTTPError as e:
                    logger.warning(f"Strava request failed (attempt {attempt}): {e}")
                    yield f"Warning: Strava API request failed (attempt {attempt}): {e}"
                    if attempt > self.request_retries:
                        yield f"Error: Failed to fetch activities from Strava after {attempt} attempts: {e}"
                        # Preserve any complete pages fetched before this failure, but
                        # signal the failure to the caller so it never treats the
                        # (incomplete) result as authoritative for stale-activity deletion.
                        result_container.extend(activities)
                        raise StravaFetchError(str(e)) from e
                    # For HTTP 429 (rate-limited), honour the server's Retry-After header if present
                    if e.response is not None and e.response.status_code == 429:
                        retry_after = e.response.headers.get("Retry-After")
                        sleep_secs = int(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
                        logger.warning(f"Rate-limited by Strava (HTTP 429). Sleeping {sleep_secs}s before retry.")
                    else:
                        sleep_secs = 2 ** attempt
                    time.sleep(sleep_secs)
                except requests.exceptions.RequestException as e:
                    logger.warning(f"Strava request failed (attempt {attempt}): {e}")
                    yield f"Warning: Strava API request failed (attempt {attempt}): {e}"
                    if attempt > self.request_retries:
                        yield f"Error: Failed to fetch activities from Strava after {attempt} attempts: {e}"
                        result_container.extend(activities)
                        raise StravaFetchError(str(e)) from e
                    time.sleep(2 ** attempt)
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

        attempt = 0
        while True:
            attempt += 1
            try:
                r = requests.get(url, headers=self._headers(), timeout=self.request_timeout)
                r.raise_for_status()
                break
            except requests.exceptions.RequestException as e:
                logger.warning(f"Strava athlete request failed (attempt {attempt}): {e}")
                if attempt > self.request_retries:
                    logger.error(f"Failed to fetch athlete profile after {attempt} attempts: {e}")
                    raise
                time.sleep(2 ** attempt)

        data = r.json()
        self.cache.set("athlete", data)
        return data

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

        attempt = 0
        while True:
            attempt += 1
            try:
                r = requests.get(url, headers=self._headers(), params=params, timeout=self.request_timeout)
                r.raise_for_status()
                break
            except requests.exceptions.RequestException as e:
                logger.warning(f"Strava streams request failed (attempt {attempt}): {e}")
                if attempt > self.request_retries:
                    logger.error(f"Failed to fetch streams for {activity_id} after {attempt} attempts: {e}")
                    raise

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

        attempt = 0
        while True:
            attempt += 1
            try:
                r = requests.get(url, headers=self._headers(), timeout=self.request_timeout)
                r.raise_for_status()
                break
            except requests.exceptions.RequestException as e:
                logger.warning(f"Strava activity detail request failed (attempt {attempt}): {e}")
                if attempt > self.request_retries:
                    logger.error(f"Failed to fetch activity detail for {activity_id} after {attempt} attempts: {e}")
                    raise
                time.sleep(2 ** attempt)

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

        attempt = 0
        while True:
            attempt += 1
            try:
                r = requests.put(url, headers=self._headers(), data=payload, timeout=self.request_timeout)
                r.raise_for_status()
                break
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 401:
                    logger.error(
                        "UPDATE_STRAVA: 401 Unauthorized updating description for activity %s — "
                        "the stored Strava refresh token most likely lacks the 'activity:write' scope "
                        "(reads work, writes don't). Reconnect via Settings -> Reconnect with Strava to "
                        "grant it; not retrying since this won't resolve on its own.",
                        activity_id,
                    )
                    raise
                logger.warning(f"Strava update-description request failed (attempt {attempt}): {e}")
                if attempt > self.request_retries:
                    logger.error(f"Failed to update description for {activity_id} after {attempt} attempts: {e}")
                    raise
                time.sleep(2 ** attempt)
            except requests.exceptions.RequestException as e:
                logger.warning(f"Strava update-description request failed (attempt {attempt}): {e}")
                if attempt > self.request_retries:
                    logger.error(f"Failed to update description for {activity_id} after {attempt} attempts: {e}")
                    raise
                time.sleep(2 ** attempt)

        return r.json()
