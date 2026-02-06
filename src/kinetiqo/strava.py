import requests
import logging
from .config import Config
from .cache import CacheManager

logger = logging.getLogger("kinetiqo")

class StravaClient:
    BASE_URL = "https://www.strava.com/api/v3"

    def __init__(self, config: Config):
        self.config = config
        self._access_token = None
        self.cache = CacheManager(config)

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
        r = requests.post(url, data=payload)

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

    def get_activities(self, after: int = None) -> list:
        """Fetch activities, optionally after a given Unix timestamp."""
        # Check cache first
        cache_params = {"after": after} if after else {}
        cached_activities = self.cache.get("activities", cache_params)
        if cached_activities is not None:
            logger.info(f"Using cached activities list ({len(cached_activities)} activities)")
            return cached_activities

        page = 1
        per_page = 200
        activities = []

        logger.info(f"Fetching activities list from Strava (after={after})...")

        while True:
            url = f"{self.BASE_URL}/athlete/activities"
            params = {"page": page, "per_page": per_page}
            if after:
                params["after"] = after

            logger.debug(f"GET {url} | params={params}")
            r = requests.get(url, headers=self._headers(), params=params)
            r.raise_for_status()
            batch = r.json()

            if not batch:
                logger.debug(f"Page {page} is empty. Reached end of activities.")
                break

            logger.debug(f"Page {page}: Found {len(batch)} activities.")
            activities.extend(batch)
            page += 1

        # Cache the results
        self.cache.set("activities", activities, cache_params)

        return activities

    def get_streams(self, activity_id: int) -> dict:
        """Fetch detailed streams for an activity."""
        # Check cache first
        cached_streams = self.cache.get(f"streams/{activity_id}")
        if cached_streams is not None:
            logger.debug(f"Using cached streams for activity {activity_id}")
            return cached_streams

        url = f"{self.BASE_URL}/activities/{activity_id}/streams"
        params = {
            "keys": "time,latlng,altitude,heartrate,cadence,velocity_smooth,distance",
            "key_by_type": "true"
        }
        logger.debug(f"GET {url} | params={params}")
        r = requests.get(url, headers=self._headers(), params=params)
        r.raise_for_status()
        streams = r.json()

        # Cache the streams
        self.cache.set(f"streams/{activity_id}", streams)

        return streams
