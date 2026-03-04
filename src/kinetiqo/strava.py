import logging
import time

import requests

from .cache import CacheManager
from .config import Config

logger = logging.getLogger("kinetiqo")


class StravaClient:
    BASE_URL = "https://www.strava.com/api/v3"

    def __init__(self, config: Config):
        self.config = config
        self._access_token = None
        self.cache = CacheManager(config)
        # Network timeout in seconds for (connect, read)
        self.request_timeout = getattr(self.config, 'strava_request_timeout', 15)
        # Simple retry count for transient network errors
        self.request_retries = getattr(self.config, 'strava_request_retries', 2)

    def _get_access_token(self) -> str:
        """Exchange refresh token for a new access token."""
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
            logger.error(f"Token exchange request failed: {e}")
            raise

        if r.status_code != 200:
            logger.error(f"Token exchange failed: {r.status_code}")
            logger.error(f"Response: {r.text}")
            r.raise_for_status()

        data = r.json()
        self._access_token = data["access_token"]
        logger.debug("Access token refreshed successfully.")

        # Strava returns a new refresh token - store it for next time
        new_refresh_token = data.get("refresh_token")
        if new_refresh_token and new_refresh_token != self.config.strava_refresh_token:
            logger.warning(f"⚠ New refresh token issued: {new_refresh_token}")
            logger.warning("Update your STRAVA_REFRESH_TOKEN environment variable!")

        return self._access_token

    def _headers(self) -> dict:
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

            # Try with simple retry logic to avoid long blocking
            attempt = 0
            while True:
                attempt += 1
                try:
                    r = requests.get(url, headers=self._headers(), params=params, timeout=self.request_timeout)
                    r.raise_for_status()
                    break
                except requests.exceptions.RequestException as e:
                    logger.warning(f"Strava request failed (attempt {attempt}): {e}")
                    yield f"Warning: Strava API request failed (attempt {attempt}): {e}"
                    if attempt > self.request_retries:
                        yield f"Error: Failed to fetch activities from Strava after {attempt} attempts: {e}"
                        return
                    # Exponential backoff; honour Retry-After for HTTP 429 responses
                    if isinstance(e, requests.exceptions.HTTPError) and e.response is not None and e.response.status_code == 429:
                        try:
                            retry_after = int(e.response.headers.get("Retry-After", 60))
                        except (ValueError, TypeError):
                            retry_after = 60
                        logger.warning(f"Rate limited (HTTP 429). Waiting {retry_after}s before retry.")
                        time.sleep(retry_after)
                    else:
                        backoff = 2 ** attempt
                        logger.debug(f"Backing off for {backoff}s before retry.")
                        time.sleep(backoff)
            try:
                batch = r.json()
            except Exception as e:
                logger.error(f"Failed to decode Strava response JSON: {e}")
                yield f"Error: Failed to decode Strava response: {e}"
                return

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
                # Exponential backoff; honour Retry-After for HTTP 429 responses
                if isinstance(e, requests.exceptions.HTTPError) and e.response is not None and e.response.status_code == 429:
                    try:
                        retry_after = int(e.response.headers.get("Retry-After", 60))
                    except (ValueError, TypeError):
                        retry_after = 60
                    logger.warning(f"Rate limited (HTTP 429). Waiting {retry_after}s before retry.")
                    time.sleep(retry_after)
                else:
                    backoff = 2 ** attempt
                    logger.debug(f"Backing off for {backoff}s before retry.")
                    time.sleep(backoff)

        streams = r.json()

        # Cache the streams
        self.cache.set(f"streams/{activity_id}", streams)

        return streams
