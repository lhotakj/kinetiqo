import logging
from typing import Any, Dict, Optional

from kinetiqo.config import Config
from kinetiqo.db.repository import UPDATE_STRAVA_FIELDS

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

    # Preserve the currently-stored UPDATE_STRAVA_* templates — this call only
    # touches name/weight, sourced from Strava.
    preserved_templates = {field: (existing.get(field, "") if existing else "") for field in UPDATE_STRAVA_FIELDS}
    repo.upsert_profile(athlete_id, first_name, last_name, weight, **preserved_templates)

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


def sync_update_strava_from_env(config: Config, repo) -> None:
    """Seed empty ``UPDATE_STRAVA_*`` database fields from their env vars.

    There are six independent templates — one per activity-type/scope bucket
    (see :mod:`kinetiqo.strava_description`):

        UPDATE_STRAVA_CYCLING_INDOOR, UPDATE_STRAVA_CYCLING_OUTDOOR,
        UPDATE_STRAVA_RUNNING_INDOOR, UPDATE_STRAVA_RUNNING_OUTDOOR,
        UPDATE_STRAVA_WALKING, UPDATE_STRAVA_SWIMMING

    The database value is authoritative once set: for each field, if the
    ``profile`` table already stores a non-empty value, it is left completely
    untouched — the corresponding env var is ignored, even if it now differs.
    Only a field that is currently **empty in the database** gets seeded from
    its env var (which may itself be empty, i.e. a no-op). This runs on every
    application start (web server boot and CLI ``sync`` invocation) so a
    freshly-created profile picks up whatever templates are configured via
    the environment, without env var changes silently clobbering a value that
    was already synced (e.g. after a template's env var is edited or removed
    later, the previously-synced database value keeps being used).

    This is a no-op (with a debug log) if no athlete profile row exists yet —
    the profile must be seeded from Strava first (requires a known
    ``athlete_id``). See :mod:`kinetiqo.strava_description` for how the
    templates are actually rendered into activity descriptions during sync.
    """
    env_values = {field: (getattr(config, field, "") or "") for field in UPDATE_STRAVA_FIELDS}

    existing = repo.get_profile()
    if not existing:
        logger.debug("No athlete profile yet — UPDATE_STRAVA_* will sync once the profile is seeded.")
        return

    new_values = {}
    newly_seeded = []
    ignored_env_diff = []
    for field in UPDATE_STRAVA_FIELDS:
        existing_value = existing.get(field) or ""
        if existing_value:
            # Database already has a value for this field — it's authoritative
            # from now on, regardless of what the env var currently says.
            new_values[field] = existing_value
            if env_values[field] and env_values[field] != existing_value:
                ignored_env_diff.append(field)
        else:
            # Database field is empty — seed it from the env var (a no-op if
            # the env var is also empty).
            new_values[field] = env_values[field]
            if env_values[field]:
                newly_seeded.append(field)

    if not newly_seeded:
        if ignored_env_diff:
            logger.debug(
                "UPDATE_STRAVA_*: %d field(s) already set in the database differ from their "
                "current env var value and were left unchanged (db value wins): %s.",
                len(ignored_env_diff), ", ".join(ignored_env_diff),
            )
        return

    repo.upsert_profile(
        existing["athlete_id"], existing["first_name"], existing["last_name"], existing["weight"],
        **new_values,
    )
    logger.info(
        "UPDATE_STRAVA_* templates seeded from environment for %d previously-empty field(s): %s.",
        len(newly_seeded), ", ".join(newly_seeded),
    )
    if ignored_env_diff:
        logger.debug(
            "UPDATE_STRAVA_*: %d field(s) already set in the database differ from their "
            "current env var value and were left unchanged (db value wins): %s.",
            len(ignored_env_diff), ", ".join(ignored_env_diff),
        )
