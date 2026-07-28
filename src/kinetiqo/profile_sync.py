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
    # touches name/weight, sourced from Strava.
    preserved_templates = {field: (existing.get(field, "") if existing else "") for field in UPDATE_STRAVA_FIELDS}
    # Persist whatever refresh token is currently in-memory (which may have
    # just been rotated by the get_athlete() call above — see kinetiqo.strava
    # ._get_access_token). This is what makes the token survive an app
    # restart instead of only living in the shared in-memory Config object.
    current_refresh_token = config.strava_refresh_token or (existing.get("refresh_token", "") if existing else "")
    repo.upsert_profile(athlete_id, first_name, last_name, weight,
                        refresh_token=current_refresh_token, **preserved_templates)

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
    if not existing or not isinstance(existing, dict):
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
        refresh_token=existing.get("refresh_token", "") or "",
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
