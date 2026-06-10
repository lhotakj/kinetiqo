import logging
from typing import Any, Dict, Optional

from kinetiqo.config import Config

logger = logging.getLogger("kinetiqo")


def seed_profile_from_strava(config: Config, repo) -> Optional[Dict[str, Any]]:
    """Fetch the athlete profile from Strava and persist it in *repo*.

    The helper keeps the existing database weight when Strava returns no weight
    or ``0``.  It returns the persisted profile dict, or ``None`` if Strava did
    not return a valid athlete id.
    """
    from kinetiqo.strava import StravaClient

    strava = StravaClient(config)
    athlete = strava.get_athlete()

    athlete_id = int(athlete.get("id", 0) or 0)
    if athlete_id <= 0:
        logger.warning("Strava athlete profile has no valid ID — skipping profile seed.")
        return None

    first_name = athlete.get("firstname", "") or ""
    last_name = athlete.get("lastname", "") or ""
    strava_weight = float(athlete.get("weight", 0) or 0)

    existing = repo.get_profile()
    if strava_weight > 0:
        weight = strava_weight
    elif existing:
        weight = float(existing.get("weight", 0) or 0)
    else:
        weight = 0.0

    repo.upsert_profile(athlete_id, first_name, last_name, weight)

    if strava_weight <= 0:
        logger.warning(
            "Strava athlete weight came back as 0. "
            "Make sure the refresh token was authorized with profile:read_all, "
            "or set ATHLETE_WEIGHT / update the profile manually."
        )

    logger.info(
        f"Profile seeded from Strava: {first_name} {last_name}, {weight} kg"
        + (" (weight kept from DB — Strava returned 0)" if strava_weight <= 0 and weight > 0 else "")
    )
    return {
        "athlete_id": athlete_id,
        "first_name": first_name,
        "last_name": last_name,
        "weight": weight,
    }
