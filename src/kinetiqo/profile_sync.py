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

    NOTE: When running under Flask testing mode (app.config['TESTING'] == True)
    this function will skip the external Strava call and return None to avoid
    seeding production-like data during unit tests. Tests that require a
    seeded profile should explicitly mock this function or provide a fake repo.
    """
    # Avoid seeding during Flask tests — current_app may not exist outside a
    # request context, so guard access with try/except.
    try:
        from flask import current_app

        if getattr(current_app, "config", {}).get("TESTING", False):
            logger.info("Skipping profile seeding from Strava in TESTING mode.")
            return None
    except Exception:
        # Not running inside Flask request/app context — continue normally
        pass

    from kinetiqo.strava import StravaClient

    existing = repo.get_profile()
    resolve_refresh_token_from_db(config, existing)

    strava = StravaClient(config)
    athlete = strava.get_athlete()

    athlete_id = int(athlete.get("id", 0) or 0)
    if athlete_id <= 0:
        logger.warning("Strava athlete profile has no valid ID — skipping profile seed.")
        return None

    first_name = athlete.get("firstname", "") or ""
    last_name = athlete.get("lastname", "") or ""
    strava_weight = float(athlete.get("weight", 0) or 0)

    if strava_weight > 0:
        weight = strava_weight
    elif existing:
        weight = float(existing.get("weight", 0) or 0)
    else:
        weight = 0.0

    # Preserve the currently-stored UPDATE_STRAVA_* templates — this call only
    # touches name/weight, sourced from Strava. Re-fetch latest DB state to preserve
    # any environment variable updates performed immediately prior to profile seeding.
    latest_existing = repo.get_profile() or existing
    preserved_templates = {field: (latest_existing.get(field, "") if latest_existing else "") for field in UPDATE_STRAVA_FIELDS}
    # Persist whatever refresh token is currently in-memory (which may have
    # just been rotated by the get_athlete() call above — see kinetiqo.strava
    # ._get_access_token). This is what makes the token survive an app
    # restart instead of only living in the shared in-memory Config object.
    current_refresh_token = config.strava_refresh_token or (latest_existing.get("refresh_token", "") if latest_existing else "")
    existing_gps_simp = latest_existing.get("gps_simplification") if latest_existing else None
    effective_gps_simp = existing_gps_simp if existing_gps_simp is not None else getattr(config, "gps_simplification", 0)

    repo.upsert_profile(athlete_id, first_name, last_name, weight,
                        refresh_token=current_refresh_token,
                        gps_simplification=effective_gps_simp,
                        **preserved_templates)

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


def sync_gps_simplification_from_env(config: Config, repo) -> None:
    """Synchronize `gps_simplification` setting between environment variable and DB.

    Precedence Rules:
    1. If `GPS_SIMPLIFICATION` env var is explicitly set in environment:
       - Uses the env var value (0-10).
       - If DB has no stored value yet, or if stored DB value differs from env var, updates DB to match env var.
       - Sets `config.gps_simplification = env_val`.
    2. If `GPS_SIMPLIFICATION` env var is NOT set in environment:
       - If DB has a stored value, uses the stored DB value (`config.gps_simplification = db_val`).
       - If DB has no stored value yet, defaults to 0 and seeds DB with 0.
    """
    existing = repo.get_profile()
    if not existing or not isinstance(existing, dict):
        logger.debug("No athlete profile yet — gps_simplification will sync once profile is seeded.")
        return

    db_val = existing.get("gps_simplification")
    is_env_set = getattr(config, "is_gps_simplification_env_set", False)
    env_val = getattr(config, "gps_simplification", 0)

    if is_env_set:
        if db_val is None or int(db_val) != env_val:
            preserved_templates = {field: (existing.get(field, "") or "") for field in UPDATE_STRAVA_FIELDS}
            repo.upsert_profile(
                existing["athlete_id"], existing["first_name"], existing["last_name"], existing["weight"],
                refresh_token=existing.get("refresh_token", "") or "",
                gps_simplification=env_val,
                **preserved_templates
            )
            config.gps_simplification = env_val
            logger.info("Updated profile gps_simplification in DB from env var: %d (was %s).", env_val, db_val)
        else:
            config.gps_simplification = int(db_val)
    else:
        if db_val is not None:
            config.gps_simplification = int(db_val)
        else:
            preserved_templates = {field: (existing.get(field, "") or "") for field in UPDATE_STRAVA_FIELDS}
            repo.upsert_profile(
                existing["athlete_id"], existing["first_name"], existing["last_name"], existing["weight"],
                refresh_token=existing.get("refresh_token", "") or "",
                gps_simplification=0,
                **preserved_templates
            )
            config.gps_simplification = 0
            logger.info("Initialized profile gps_simplification in DB with default 0.")


def sync_update_strava_from_env(config: Config, repo) -> None:
    """Synchronize ``UPDATE_STRAVA_*`` database fields with environment variables.

    Precedence Rules:
    1. If an env var for a template field IS explicitly set in the environment:
       - Uses the env var template.
       - If DB has no stored value yet, or if DB value differs from env var, updates DB to match env var.
       - Sets `config.<field> = env_value`.
    2. If an env var is NOT set in the environment:
       - If DB has a stored template, uses the stored DB template (`config.<field> = db_value`).
       - If DB has no stored template yet, leaves it empty.
    """
    import os

    existing = repo.get_profile()
    if not existing or not isinstance(existing, dict):
        logger.debug("No athlete profile yet — UPDATE_STRAVA_* will sync once the profile is seeded.")
        return

    new_values = {}
    updated_fields = []
    for field in UPDATE_STRAVA_FIELDS:
        env_var_name = field.upper()
        env_raw = os.getenv(env_var_name)
        db_val = existing.get(field) or ""

        if env_raw is not None and env_raw.strip() != "":
            env_val = env_raw.strip()
            if db_val != env_val:
                new_values[field] = env_val
                updated_fields.append(field)
            else:
                new_values[field] = db_val
            setattr(config, field, new_values[field])
        else:
            new_values[field] = db_val
            setattr(config, field, db_val)

    if updated_fields:
        repo.upsert_profile(
            existing["athlete_id"], existing["first_name"], existing["last_name"], existing["weight"],
            refresh_token=existing.get("refresh_token", "") or "",
            gps_simplification=existing.get("gps_simplification"),
            **new_values,
        )
        logger.info("Updated UPDATE_STRAVA_* template(s) in DB from environment: %s.", ", ".join(updated_fields))


def sync_athlete_weight_from_env(config: Config, repo) -> None:
    """Synchronize `athlete_weight` setting between environment variable and DB.

    Precedence Rules:
    1. If `ATHLETE_WEIGHT` env var is explicitly set in environment:
       - Uses the env var value.
       - Updates DB weight if DB weight is 0 or differs.
       - Sets `config.athlete_weight = env_weight`.
    2. If `ATHLETE_WEIGHT` env var is NOT set:
       - If DB has a stored weight (> 0), uses stored DB weight (`config.athlete_weight = db_weight`).
       - If DB weight is 0, leaves it 0.
    """
    import os

    existing = repo.get_profile()
    if not existing or not isinstance(existing, dict):
        return

    env_weight_raw = os.getenv("ATHLETE_WEIGHT")
    db_weight = float(existing.get("weight", 0) or 0)

    if env_weight_raw is not None and env_weight_raw.strip() != "":
        try:
            env_weight = float(env_weight_raw)
            if env_weight > 0 and abs(db_weight - env_weight) > 0.01:
                preserved_templates = {field: (existing.get(field, "") or "") for field in UPDATE_STRAVA_FIELDS}
                repo.upsert_profile(
                    existing["athlete_id"], existing["first_name"], existing["last_name"], env_weight,
                    refresh_token=existing.get("refresh_token", "") or "",
                    gps_simplification=existing.get("gps_simplification"),
                    **preserved_templates
                )
                config.athlete_weight = env_weight
                logger.info("Updated athlete weight in DB from ATHLETE_WEIGHT env var: %.1f kg (was %.1f kg).", env_weight, db_weight)
            else:
                config.athlete_weight = db_weight if db_weight > 0 else env_weight
        except ValueError:
            pass
    else:
        if db_weight > 0:
            config.athlete_weight = db_weight


def sync_all_profile_env_vars(config: Config, repo) -> None:
    """Synchronize all environment variable configurations to DB profile."""
    sync_update_strava_from_env(config, repo)
    sync_gps_simplification_from_env(config, repo)
    sync_athlete_weight_from_env(config, repo)



# ---------------------------------------------------------------------------
# Strava refresh token persistence
#
# Strava issues a brand-new refresh_token — and permanently invalidates the
# previous one — on *every* OAuth2 token exchange (both the authorization_code
# exchange and later refresh_token grants). If the rotated token only ever
# lives on the shared in-memory Config instance, it is lost the moment the
# process exits, and the *next* startup fails immediately with a
# "RefreshToken invalid" error — even though the previous run ended cleanly.
#
# The fix follows the same "seed once from env, database wins afterwards"
# pattern already used for the UPDATE_STRAVA_* templates above: the
# STRAVA_REFRESH_TOKEN env var only bootstraps the very first run, and from
# then on the database's ``profile.refresh_token`` column is authoritative
# and kept in sync automatically.
# ---------------------------------------------------------------------------

def resolve_refresh_token_from_db(config: Config, existing_profile: Optional[Dict[str, Any]]) -> None:
    """Prefer the refresh token stored in the database over the env var.

    Must be called before the first Strava API call of the process (it
    mutates ``config.strava_refresh_token`` in place). *existing_profile* is
    the current ``repo.get_profile()`` result (or ``None`` if no profile row
    exists yet, in which case the env var is used as-is to bootstrap).
    """
    if not existing_profile or not isinstance(existing_profile, dict):
        return
    db_refresh_token = existing_profile.get("refresh_token") or ""
    if db_refresh_token and db_refresh_token != config.strava_refresh_token:
        logger.info(
            "Using the Strava refresh token stored in the database "
            "(overrides the STRAVA_REFRESH_TOKEN env var, which may be stale)."
        )
        config.strava_refresh_token = db_refresh_token


def persist_refresh_token(repo, refresh_token: str) -> bool:
    """Persist a (possibly rotated) Strava refresh token to the profile row.

    This is a no-op (returns ``False``, with a debug log) if no profile row
    exists yet — the profile must be seeded from Strava first (via
    :func:`seed_profile_from_strava`), since a valid ``athlete_id`` is needed
    to key the update on.

    :param repo: Database repository instance.
    :param refresh_token: The new refresh token to persist.
    :return: ``True`` if the token was persisted (or was already up to date).
    """
    if not refresh_token:
        return False

    existing = repo.get_profile()
    if not existing:
        logger.debug("No athlete profile yet — refresh token will be persisted once the profile is seeded.")
        return False

    if (existing.get("refresh_token") or "") == refresh_token:
        return True  # Already up to date — nothing to write.

    preserved_templates = {field: (existing.get(field, "") or "") for field in UPDATE_STRAVA_FIELDS}
    repo.upsert_profile(
        existing["athlete_id"], existing["first_name"], existing["last_name"], existing["weight"],
        refresh_token=refresh_token, **preserved_templates,
    )
    logger.info("Persisted rotated Strava refresh token to the database.")
    return True


def wire_refresh_token_persistence(config: Config) -> None:
    """Install a callback on *config* that persists rotated refresh tokens.

    Whenever :class:`kinetiqo.strava.StravaClient` receives a new
    refresh_token from Strava — which can happen on every token exchange,
    not just the initial profile seed (e.g. mid-sync, or during an activity
    description update) — the installed callback opens its own short-lived
    repository connection and writes the new token to the database. Using an
    independent connection (rather than relying on a caller-supplied repo)
    means it works no matter which code path or thread triggered the
    rotation.
    """
    from kinetiqo.db.factory import create_repository

    def _on_refresh_token_changed(new_refresh_token: str) -> None:
        repo = None
        try:
            repo = create_repository(config)
            persist_refresh_token(repo, new_refresh_token)
        except Exception as e:
            logger.warning(f"Could not persist rotated Strava refresh token (non-fatal): {e}")
        finally:
            if repo:
                try:
                    repo.close()
                except Exception:
                    pass

    config.on_refresh_token_changed = _on_refresh_token_changed
