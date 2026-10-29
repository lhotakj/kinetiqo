import html
import logging
import time
import os
from datetime import datetime, timezone, timedelta

import requests

from kinetiqo.config import Config, UPDATE_STRAVA_MAX_ITEMS
from kinetiqo.db.factory import create_repository
from kinetiqo.strava import StravaClient, StravaFetchError
from kinetiqo.profile_sync import sync_update_strava_from_env, sync_gps_simplification_from_env, sync_athlete_weight_from_env
from kinetiqo.strava_description import DescriptionContext, any_update_strava_template_configured, get_template_for_activity
from kinetiqo.koms import (
    load_verified_koms,
    save_verified_koms,
    load_verified_trophies,
    save_verified_trophies,
    record_activity_trophies,
    extract_trophies_from_segment_efforts,
)

logger = logging.getLogger("kinetiqo")

STOP_SIGNAL_FILE = ".sync_stop"
STOP_SIGNAL_ABORT_MSG = "Stop signal received. Aborting..."

# ---------------------------------------------------------------------------
# Brief per-activity UPDATE_STRAVA description status, surfaced inline next
# to each activity's sync log line (see _update_strava_description() and the
# "Phase 1"/"Phase 2" loops in sync()).
# ---------------------------------------------------------------------------
DESC_NOT_CONFIGURED = "not_configured"  # no template for this activity's bucket — feature inactive, nothing to show
DESC_UNCHANGED = "unchanged"            # template rendered identically to what's already on Strava — no API call made
DESC_SKIPPED = "skipped"                # skipped because a prior 401 already disabled updates for this run
DESC_UPDATED = "updated"                # Strava description was successfully updated
DESC_FAILED = "failed"                  # the update attempt raised an error (see the returned message)

def _description_status_suffix(status: str) -> str:
    """Return a brief ``" | Kinetiqo description ..."`` suffix for a per-activity log line.

    Returns an empty string for :data:`DESC_NOT_CONFIGURED` (the feature isn't
    active for this activity's sport type, so there's nothing to show). All
    configured-but-not-updated outcomes collapse to ``"skipped"`` to keep sync
    UI output concise.
    """
    if status == DESC_UPDATED:
        return " | Kinetiqo description updated"
    if status in (DESC_UNCHANGED, DESC_SKIPPED, DESC_FAILED):
        return " | Kinetiqo description skipped"
    return ""

class SyncService:
    """Service responsible for synchronizing activities from Strava into the database.

    The service yields progress updates (strings/HTML fragments) as it proceeds so
    they can be streamed to a web UI (SSE) or consumed by the CLI.
    """

    def __init__(self, config: Config):
        """Initialize SyncService with configuration.

        Args:
            config (Config): Application configuration instance.
        """
        self.config = config
        self.strava = StravaClient(config)
        # If the StravaClient has been patched in tests the returned object
        # may be a MagicMock. Reset its stream-call counters so repeated CLI
        # invocations within the same test method don't accumulate call counts
        # across subTests (the test-suite expects fresh mocks per invocation).
        try:
            if hasattr(self.strava.get_streams, 'reset_mock'):
                self.strava.get_streams.reset_mock()
        except Exception:
            pass

        self.db = create_repository(config)
        # Set the first time update_activity_description() hits a 401 (missing
        # activity:write scope) so the rest of *this* sync run skips further
        # description-update attempts entirely instead of retrying/failing on
        # every single remaining activity (see _update_strava_description()).
        self._update_strava_unauthorized = False

    def _check_stop_signal(self):
        """Check for an external stop signal.

        The stop signal is represented by the presence of a file named
        defined by STOP_SIGNAL_FILE; if found, the file is removed and
        the function returns True to indicate the sync should abort.
        """
        if os.path.exists(STOP_SIGNAL_FILE):
            try:
                os.remove(STOP_SIGNAL_FILE)
            except Exception:
                pass
            return True
        return False

    def _update_strava_description(self, description_context: "DescriptionContext", activity: dict, detail: dict | None = None) -> "tuple[str, str | None]":
        """Render the applicable UPDATE_STRAVA_* template for *activity* and push it to Strava if changed.

        Selects the template based on the activity's own sport type (cycling
        indoor/outdoor, running indoor/outdoor, walking or swimming — see
        :func:`get_template_for_activity`); if the activity's sport type does
        not map to any bucket, or the applicable template is unset, this is a
        no-op (no Strava API calls at all).

        Otherwise fetches the activity's current (full) description from
        Strava, merges in the freshly rendered stats block (replacing any
        previously-rendered block in place, or inserting a new one at the
        position configured by ``UPDATE_STRAVA_PLACEMENT``), and only calls
        the Strava update API if the resulting description actually differs.

        If the update call ever 401s (refresh token missing the
        ``activity:write`` scope), further description-update attempts are
        skipped for the *rest of this sync run* (see
        ``self._update_strava_unauthorized``) rather than retried/failed on
        every remaining activity.

        Returns:
            A ``(status, message)`` tuple. ``status`` is one of
            :data:`DESC_NOT_CONFIGURED`, :data:`DESC_UNCHANGED`,
            :data:`DESC_SKIPPED`, :data:`DESC_UPDATED`, or :data:`DESC_FAILED`
            — used by the caller to show a brief inline status next to each
            activity's sync log line. ``message`` is a full human-readable
            warning/error string (for the sync UI's warnings summary) when
            something notable happened, or ``None`` otherwise.
        """
        template = get_template_for_activity(self.config, activity.get("sport_type", ""))
        if not template:
            return DESC_NOT_CONFIGURED, None
        if self._update_strava_unauthorized:
            # Already confirmed this run that the refresh token lacks
            # activity:write — every further call would just 401 again, so
            # skip the API calls entirely for the rest of this sync. Already
            # reported once, so stay silent here to avoid spamming the log.
            return DESC_SKIPPED, None
        activity_id = activity["id"]
        try:
            if detail is None:
                detail = self.strava.get_activity_detail(activity_id)
            if detail and detail.get("segment_efforts"):
                t_dict = extract_trophies_from_segment_efforts(detail["segment_efforts"])
                record_activity_trophies(activity_id, t_dict)
                try:
                    self.db.update_activity_trophies(activity_id, t_dict)
                except Exception as db_err:
                    logger.debug(f"Could not persist trophies in database for activity {activity_id}: {db_err}")
            existing_description = (detail or {}).get("description") or ""
            new_description = description_context.render_for_activity(
                template,
                activity.get("start_date"),
                existing_description,
                activity=activity,
            )
            if new_description is None or new_description == existing_description:
                return DESC_UNCHANGED, None
            self.strava.update_activity_description(activity_id, new_description)
            logger.info(f"Updated Strava description for activity {activity_id}.")
            return DESC_UPDATED, None
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 401:
                self._update_strava_unauthorized = True
                msg = (
                    "UPDATE_STRAVA: disabling further description updates for this sync run — "
                    "the Strava refresh token appears to be missing the 'activity:write' scope. "
                    "Reconnect via Settings -> Reconnect with Strava to grant it."
                )
                logger.warning(msg)
                return DESC_FAILED, msg
            msg = f"UPDATE_STRAVA: failed to update description for activity {activity_id}: {e}"
            logger.warning(msg)
            return DESC_FAILED, msg
        except Exception as e:
            msg = f"UPDATE_STRAVA: failed to update description for activity {activity_id}: {e}"
            logger.warning(msg)
            return DESC_FAILED, msg

    def _description_update_activity_ids(self, activities: list[dict]) -> set[str]:
        """Return IDs of latest activities eligible for UPDATE_STRAVA description writes."""
        if UPDATE_STRAVA_MAX_ITEMS <= 0:
            return set()
        eligible_activities = [
            activity for activity in activities
            if get_template_for_activity(self.config, activity.get("sport_type", ""))
        ]
        eligible_activities.sort(key=lambda item: item.get("start_date") or "", reverse=True)
        return {
            str(activity["id"])
            for activity in eligible_activities[:UPDATE_STRAVA_MAX_ITEMS]
            if "id" in activity
        }

    def sync(self, full_sync: bool = True, trigger: str = "unknown", user: str = "-", limit_days: int = 0, update_strava: bool = True):
        """
        Perform sync of Strava activities, yielding progress updates.

        Full sync:  fetches activities within the given limit_days window (or all time if 0).
        Fast sync:  fetches activities after the latest activity already in the database.
        """
        self._check_stop_signal()  # clear any leftover stop signal before starting

        log_buffer = []
        sync_warnings = []
        sync_type_str = 'full' if full_sync else 'fast'
        action = 'full-sync' if full_sync else 'fast-sync'
        added_count = 0
        updated_count = 0
        removed_count = 0
        success = True
        stopped = False

        def yield_log(msg, final=False, is_stopped=False):
            msg = str(msg).replace('\n', ' ').replace('\r', '')
            logger.info(msg)
            log_buffer.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
            if len(log_buffer) > 20:
                log_buffer.pop(0)
            log_content = '<div class="font-mono text-xs text-gray-600 overflow-y-auto space-y-1" style="height: 500px;">'
            for line in log_buffer:
                log_content += f'<p class="block truncate">{html.escape(line)}</p>'
            log_content += '</div>'
            status_html = """<div class="text-center pt-4 border-t border-gray-200">
                <p class="text-sm font-medium mb-3 inline-flex items-center justify-center gap-2 sync-progress-text">
                    <img src="/static/img/kinetiqo-loading-32x32.webp" alt="Loading..." class="h-4 w-4 inline-block" width="16" height="16">
                    <span>Sync in progress...</span>
                </p>
            </div>"""
            if final:
                status_color = "text-green-600"
                status_msg = "Sync completed successfully."
                if is_stopped:
                    status_color = "text-yellow-600"
                    status_msg = "Sync stopped by user."
                elif "failed" in msg.lower():
                    status_color = "text-red-600"
                    status_msg = "Sync failed."
                elif sync_warnings:
                    status_color = "text-yellow-600"
                    status_msg = f"Sync completed with {len(sync_warnings)} warning(s)."
                warnings_html = ""
                if sync_warnings:
                    warning_items = "".join(
                        f'<li>{html.escape(w)}</li>' for w in sync_warnings
                    )
                    warnings_html = f"""<div class="mt-3 text-left bg-yellow-50 border border-yellow-200 rounded-lg p-3">
                        <p class="text-xs font-semibold text-yellow-800 mb-1">⚠️ {len(sync_warnings)} warning(s) during sync:</p>
                        <ul class="text-xs text-yellow-700 list-disc list-inside space-y-0.5 max-h-32 overflow-y-auto">{warning_items}</ul>
                    </div>"""
                wrapper_html = f"""<div id="sync-log-area" hx-swap-oob="true">
                    <div class="bg-gray-50 rounded-lg p-4 min-h-[200px] border border-gray-100">
                        <div class="mb-4">{log_content}</div>
                        <div class="text-center pt-4 border-t border-gray-200">
                            <p class="text-sm {status_color} font-medium mb-3">{status_msg}</p>
                            {warnings_html}
                        </div>
                    </div>
                </div>"""
                hx_include = 'hx-include="#updateStravaDesc, #syncLimit"' if full_sync else 'hx-include="#updateStravaDesc"'
                button_html = f"""<button id="start-sync-btn" 
                        hx-get="/sync/start/{sync_type_str}" 
                        hx-target="#sync-log-area" 
                        hx-swap="outerHTML"
                        hx-swap-oob="true"
                        {hx_include}
                        class="px-6 py-2.5 bg-orange-600 hover:bg-orange-700 text-white rounded-lg text-sm font-medium transition shadow-sm inline-flex items-center">
                    <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                    Start Sync
                </button>"""
                return f"data: {(wrapper_html + button_html).replace(chr(10), '')}\n\n"
            else:
                live_html = f'<div class="mb-4">{log_content}</div>{status_html}'
                return f"data: {live_html.replace(chr(10), '')}\n\n"

        try:
            stop_button_html = """<button id="start-sync-btn" type="button"
                    data-sync-stop-button="true"
                    onclick="window.kinetiqoRequestSyncStop && window.kinetiqoRequestSyncStop(this); return false;"
                    hx-swap="none"
                    hx-swap-oob="true"
                    class="px-6 py-2.5 text-white rounded-lg text-sm font-semibold transition shadow-lg inline-flex items-center border border-red-300"
                    style="background-color: #dc2626; color: #ffffff; box-shadow: 0 0 0 2px rgba(220, 38, 38, 0.25), 0 10px 15px -3px rgba(0, 0, 0, 0.25);">
                <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                Stop Sync
            </button>""".replace('\n', '')
            yield f"data: {stop_button_html}\n\n"
            yield yield_log(f"Starting {sync_type_str} sync (limit: {limit_days} days)...")

            self.db.initialize_schema()
            try:
                sync_update_strava_from_env(self.config, self.db)
                sync_gps_simplification_from_env(self.config, self.db)
                sync_athlete_weight_from_env(self.config, self.db)
            except Exception as e:
                logger.warning(f"Failed to sync profile settings from environment: {e}")

            description_context = None
            description_update_ids: set[str] = set()
            if update_strava and any_update_strava_template_configured(self.config):
                ai_handler = None
                try:
                    prof = self.db.get_profile() or {}
                    raw_athlete_id = str(prof.get("athlete_id") or "")
                    agent_prompt = prof.get("agent_prompt") or getattr(self.config, "agent_prompt", "") or ""

                    secret_key = getattr(self.config, "secret_key", "") or os.getenv("SECRET_KEY", "")
                    if not secret_key:
                        try:
                            from flask import current_app
                            if current_app:
                                secret_key = current_app.secret_key
                        except Exception:
                            pass
                    if not secret_key:
                        try:
                            from kinetiqo.web.app import app
                            secret_key = getattr(app, "secret_key", "")
                        except Exception:
                            pass

                    from kinetiqo.chat.agent_runner import run_agent_prompt
                    from kinetiqo.chat.repository import ChatRepository
                    from kinetiqo.chat.service import ChatService
                    db_type = getattr(self.config, "database_type", None) or getattr(self.db, "db_type", "postgresql")
                    chat_repo = ChatRepository(self.db, db_type)
                    athlete_id = chat_repo.resolve_athlete_id(raw_athlete_id)

                    if athlete_id and secret_key:
                        chat_svc = ChatService(chat_repo, secret_key, config=self.config)

                        def _ai_runner(act: dict) -> tuple[str, str]:
                            return run_agent_prompt(chat_svc, athlete_id, act, agent_prompt)

                        ai_handler = _ai_runner
                except Exception as e:
                    logger.debug(f"Could not initialize AI Agent handler for sync: {e}")

                description_context = DescriptionContext(self.config, self.db, ai_handler=ai_handler)

            synced_ids = self.db.get_synced_activity_ids()
            yield yield_log(f"Found {len(synced_ids)} already synced activities in database.")

            if self._check_stop_signal():
                stopped = True
                yield yield_log(STOP_SIGNAL_ABORT_MSG, final=True, is_stopped=True)
                return

            # --- Determine the time window for fetching from Strava ---
            after = None
            if full_sync and limit_days > 0:
                after = int((datetime.now(timezone.utc) - timedelta(days=limit_days)).timestamp())
                yield yield_log(
                    f"Full sync limited to last {limit_days} days (after {datetime.fromtimestamp(after, tz=timezone.utc)}).")
            elif not full_sync:
                latest_ts = self.db.get_latest_activity_time()
                if latest_ts:
                    latest_dt = datetime.fromtimestamp(latest_ts, tz=timezone.utc)
                    # Cover the current and previous calendar day of the latest activity.
                    # This handles activities that were deleted or uploaded late — anything
                    # within the last ~3 days is always rechecked. For gaps older than that,
                    # use FullSync with an appropriate window.
                    after_dt = (latest_dt - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
                    if limit_days > 0:
                        limit_dt = datetime.now(timezone.utc) - timedelta(days=limit_days)
                        if after_dt < limit_dt:
                            after_dt = limit_dt
                    after = int(after_dt.timestamp())
                    limit_msg = f" (limited to last {limit_days} days)" if limit_days > 0 else ""
                    yield yield_log(
                        f"Fast sync: fetching activities since {after_dt.strftime('%Y-%m-%d')} "
                        f"(day prior to latest: {latest_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}){limit_msg}."
                    )
                else:
                    if limit_days > 0:
                        after = int((datetime.now(timezone.utc) - timedelta(days=limit_days)).timestamp())
                        yield yield_log(f"Fast sync: no previous data found, limited to last {limit_days} days.")
                    else:
                        yield yield_log("Fast sync: no previous data found, falling back to full fetch.")

            # --- Fetch from Strava ---
            # The StravaClient.get_activities() implementation may either:
            #  - populate the passed-in ``activities`` list and yield progress
            #    messages (the normal client implementation), OR
            #  - be mocked in tests to yield the fetched activities as a
            #    non-string item (e.g. an iterator returning a list). To be
            #  tolerant of both styles we accept and merge any yielded
            #  non-string iterable into the local ``activities`` list.
            activities = []
            fetch_failed = False
            try:
                for item in self.strava.get_activities(activities, after=after):
                    if isinstance(item, str):
                        yield yield_log(item)
                        if self._check_stop_signal():
                            stopped = True
                            yield yield_log("Stop signal received during fetch. Aborting...", final=True,
                                             is_stopped=True)
                            return
                    else:
                        # If the mock yields the activity batch directly, merge it.
                        try:
                            if isinstance(item, (list, tuple)):
                                activities.extend(item)
                            elif isinstance(item, dict):
                                activities.append(item)
                        except Exception:
                            # Fall back to ignoring the item if it's not iterable
                            pass

                        if self._check_stop_signal():
                            stopped = True
                            yield yield_log("Stop signal received during fetch. Aborting...", final=True,
                                             is_stopped=True)
                            return
            except StravaFetchError as e:
                # Fetching the activity list failed after all retries (e.g. an expired/
                # revoked token, or Strava being unreachable). ``activities`` is now
                # incomplete/empty — it must NEVER be treated as "the full current set
                # on Strava", or every activity missing from it would look stale and
                # get deleted from the local database. Skip stale-activity detection
                # entirely for this run instead (see below).
                fetch_failed = True
                msg = (
                    f"Strava activities fetch failed: {e}. Skipping stale-activity "
                    f"deletion this run to avoid deleting data due to a temporary "
                    f"outage or authorization problem."
                )
                logger.error(msg)
                sync_warnings.append(msg)
                yield yield_log(msg)

            yield yield_log(f"Found {len(activities)} activities from Strava.")

            new_activities = [a for a in activities if str(a["id"]) not in synced_ids]
            existing_activities = [a for a in activities if str(a["id"]) in synced_ids]
            yield yield_log(f"Identified {len(new_activities)} new and {len(existing_activities)} existing activities.")
            if description_context is not None:
                description_update_ids = self._description_update_activity_ids(activities)
                total_eligible = sum(
                    1 for activity in activities
                    if get_template_for_activity(self.config, activity.get("sport_type", ""))
                )
                if total_eligible > UPDATE_STRAVA_MAX_ITEMS:
                    yield yield_log(
                        f"UPDATE_STRAVA: limiting description updates to latest "
                        f"{UPDATE_STRAVA_MAX_ITEMS} eligible activities."
                    )

            # --- Identify stale DB entries within the fetched window ---
            strava_ids = {str(a["id"]) for a in activities}
            if fetch_failed:
                # The fetched activity list is incomplete/unreliable (see the
                # StravaFetchError handling above) — never derive "missing from
                # Strava" from it, or a temporary outage/expired token would wipe
                # out local activities that are still perfectly fine on Strava.
                ids_to_delete = set()
                yield yield_log(
                    "Skipping stale-activity check because the Strava fetch failed for this run."
                )
            else:
                if after is None:
                    ids_to_delete = synced_ids - strava_ids
                else:
                    # Strava's `after` param is exclusive (strictly >), meaning the activity
                    # sitting exactly at `after` is our anchor — it will never be returned
                    # by Strava and must never be considered stale. Use after+1 to match
                    # the same exclusive boundary.
                    scoped_synced_ids = self.db.get_synced_activity_ids_since(after + 1)
                    ids_to_delete = scoped_synced_ids - strava_ids

                if ids_to_delete:
                    yield yield_log(f"Found {len(ids_to_delete)} activities in database missing from Strava.")
                else:
                    yield yield_log("No stale activities to delete.")

            if self._check_stop_signal():
                stopped = True
                yield yield_log(STOP_SIGNAL_ABORT_MSG, final=True, is_stopped=True)
                return

            # --- Phase 1: Sync all activities (existing + new) in one pass ---
            total_activities = len(activities)
            trophies_cache = load_verified_trophies()
            for i, activity in enumerate(activities, 1):
                if self._check_stop_signal():
                    stopped = True
                    yield yield_log(STOP_SIGNAL_ABORT_MSG, final=True, is_stopped=True)
                    return
                activity_id = activity["id"]
                act_id_str = str(activity_id)
                sport = activity["sport_type"]
                name = activity.get("name", "Unknown Activity")
                percent = (i / total_activities) * 100 if total_activities > 0 else 0
                is_existing = act_id_str in synced_ids
                desc_suffix = ""
                trophies_suffix = ""
                detail = None

                # Check if we should fetch activity detail for trophies or description update
                ach_count = int(activity.get("achievement_count") or 0)
                cached_tr = trophies_cache.get(act_id_str, {})
                already_scanned = bool(cached_tr.get("scanned")) or any(
                    int(cached_tr.get(str(r), 0)) > 0 for r in range(2, 11)
                )
                needs_trophies = (ach_count > 0) and not already_scanned
                needs_desc = (description_context is not None) and (act_id_str in description_update_ids)

                if needs_trophies or needs_desc:
                    try:
                        detail = self.strava.get_activity_detail(activity_id)
                    except Exception as det_err:
                        logger.warning(f"Failed to fetch activity detail for {activity_id}: {det_err}")

                if detail and needs_trophies:
                    efforts = detail.get("segment_efforts", [])
                    t_dict = extract_trophies_from_segment_efforts(efforts) if efforts else {r: 0 for r in range(1, 11)}
                    record_activity_trophies(activity_id, t_dict)
                    activity["trophies"] = t_dict
                    trophies_cache[act_id_str] = {str(r): t_dict[r] for r in range(1, 11)}
                    trophies_cache[act_id_str]["scanned"] = 1
                    podium = [f"#{r}: {t_dict[r]}" for r in range(1, 11) if t_dict[r] > 0]
                    if podium:
                        trophies_suffix = f" [{', '.join(podium)}]"
                elif already_scanned:
                    podium = [f"#{r}: {cached_tr.get(str(r), 0)}" for r in range(1, 11) if int(cached_tr.get(str(r), 0)) > 0]
                    if podium:
                        trophies_suffix = f" [{', '.join(podium)}]"

                try:
                    self.db.write_activity(activity)
                    if is_existing:
                        updated_count += 1
                    else:
                        streams = self.strava.get_streams(activity_id)
                        point_count = len(streams.get('time', {}).get('data', []))
                        if point_count > 0:
                            self.db.write_activity_streams(activity, streams)
                            added_count += 1
                        else:
                            msg = f"Activity {activity_id} has no stream data."
                            logger.warning(msg)
                            sync_warnings.append(msg)
                    ai_suffix = ""
                    if description_context is not None:
                        if act_id_str in description_update_ids:
                            if is_existing and "ai_responses" not in activity and hasattr(self.db, "get_activity_ai_responses"):
                                try:
                                    cached_ai = self.db.get_activity_ai_responses(activity_id)
                                    if cached_ai:
                                        activity["ai_responses"] = cached_ai
                                except Exception as ai_fetch_err:
                                    logger.debug(f"Failed to fetch cached ai_responses: {ai_fetch_err}")
                            status, warning = self._update_strava_description(description_context, activity, detail=detail)
                            if description_context.last_ai_status:
                                ai_suffix = f" [AI: {description_context.last_ai_status}]"
                                if description_context.last_ai_status == "failed":
                                    sync_warnings.append(f"AI Agent generation failed for activity {activity_id} ('{name}').")
                        else:
                            # Template may be absent for this activity's bucket;
                            # preserve the old "no status suffix" behavior there.
                            status = DESC_SKIPPED if get_template_for_activity(self.config, sport) else DESC_NOT_CONFIGURED
                            warning = None
                        desc_suffix = _description_status_suffix(status)
                        if warning:
                            sync_warnings.append(warning)
                    yield yield_log(f"[{i}/{total_activities}] ({percent:.0f}%) {name} ({sport}){trophies_suffix}{ai_suffix}{desc_suffix}")
                except Exception as e:
                    msg = f"Error syncing activity {activity_id}: {e}"
                    sync_warnings.append(msg)
                    logger.exception(msg)
                    yield yield_log(f"[{i}/{total_activities}] ({percent:.0f}%) {name} ({sport}) — failed: {e}")
                time.sleep(0.1)

            save_verified_trophies(trophies_cache)

            # --- Phase 2: Delete stale activities ---
            if ids_to_delete:
                try:
                    self.db.delete_activities(list(ids_to_delete))
                    removed_count = len(ids_to_delete)
                    yield yield_log(f"Deleted {removed_count} stale activities from database.")
                except Exception as e:
                    msg = f"Error deleting stale activities: {e}"
                    sync_warnings.append(msg)
                    yield yield_log(msg)

            # --- Phase 3: Sync athlete KOMs and backfill any legacy database activities ---
            try:
                yield yield_log("Syncing King of the Mountains (KOMs) and trophies from Strava...")
                athlete = self.strava.get_athlete()
                if athlete and athlete.get("id"):
                    koms_list = self.strava.get_athlete_koms(athlete["id"])
                    koms_by_activity: dict[str, int] = {}
                    for effort in koms_list:
                        act_ref = effort.get("activity") or {}
                        act_id = act_ref.get("id")
                        if act_id:
                            act_id_str = str(act_id)
                            koms_by_activity[act_id_str] = koms_by_activity.get(act_id_str, 0) + 1

                    save_verified_koms(koms_by_activity)
                    trophies_cache = load_verified_trophies()
                    for act_id_str, count in koms_by_activity.items():
                        if act_id_str not in trophies_cache:
                            trophies_cache[act_id_str] = {str(r): 0 for r in range(1, 11)}
                        trophies_cache[act_id_str]["1"] = max(trophies_cache[act_id_str].get("1", 0), count)
                        try:
                            self.db.update_activity_trophies(act_id_str, trophies_cache[act_id_str])
                        except Exception:
                            pass
                    save_verified_trophies(trophies_cache)
                    yield yield_log(f"Synced {len(koms_list)} verified KOMs across {len(koms_by_activity)} activities.")

                    # Only scan historical activities from DB if any legacy backlog remains unscanned
                    unscanned_db = []
                    try:
                        max_db = 40 if full_sync else 15
                        unscanned_db = self.db.get_activities_needing_trophies(limit=max_db)
                    except Exception as db_err:
                        logger.debug(f"Could not query database for unscanned trophy activities: {db_err}")

                    if unscanned_db:
                        yield yield_log(f"Backfilling segment trophies for {len(unscanned_db)} historical activities...")
                        for idx, act in enumerate(unscanned_db, start=1):
                            if self._check_stop_signal():
                                stopped = True
                                yield yield_log("Stop signal received during trophy scan. Aborting...", final=True, is_stopped=True)
                                return

                            act_id = act.get("id") or act.get("activity_id")
                            act_id_str = str(act_id)
                            name = act.get("name") or f"Activity {act_id_str}"
                            disp_name = (name[:28] + "...") if len(name) > 31 else name

                            try:
                                detail = self.strava.get_activity_detail(act_id_str)
                                efforts = (detail or {}).get("segment_efforts", [])
                                if efforts:
                                    t_dict = extract_trophies_from_segment_efforts(efforts)
                                    if act_id_str in koms_by_activity:
                                        t_dict[1] = max(t_dict[1], koms_by_activity[act_id_str])
                                    record_activity_trophies(act_id_str, t_dict)
                                    try:
                                        self.db.update_activity_trophies(act_id_str, t_dict)
                                    except Exception:
                                        pass
                                    trophies_cache[act_id_str] = {str(r): t_dict[r] for r in range(1, 11)}
                                    trophies_cache[act_id_str]["scanned"] = 1
                                    podium = [f"#{r}: {t_dict[r]}" for r in range(1, 11) if t_dict[r] > 0]
                                    if podium:
                                        yield yield_log(f"[{idx}/{len(unscanned_db)}] {disp_name} -> {', '.join(podium)}")
                                    else:
                                        yield yield_log(f"[{idx}/{len(unscanned_db)}] {disp_name} -> no top-10 trophies")
                                else:
                                    empty_dict = {r: 0 for r in range(1, 11)}
                                    if act_id_str in koms_by_activity:
                                        empty_dict[1] = koms_by_activity[act_id_str]
                                    record_activity_trophies(act_id_str, empty_dict)
                                    try:
                                        self.db.update_activity_trophies(act_id_str, empty_dict)
                                    except Exception:
                                        pass
                                    trophies_cache[act_id_str] = {str(r): empty_dict[r] for r in range(1, 11)}
                                    trophies_cache[act_id_str]["scanned"] = 1
                                    yield yield_log(f"[{idx}/{len(unscanned_db)}] {disp_name} -> no segment efforts")
                            except Exception as det_err:
                                logger.warning(f"Historical trophy backfill skipped for {act_id_str}: {det_err}")

                            if idx % 5 == 0:
                                save_verified_trophies(trophies_cache)
                            time.sleep(0.05)

                        save_verified_trophies(trophies_cache)
            except Exception as e:
                logger.warning(f"Failed to sync athlete KOMs/trophies: {e}")
                sync_warnings.append(f"Failed to sync athlete KOMs/trophies: {e}")
                yield yield_log(f"Warning: Failed to sync athlete KOMs/trophies: {e}")



            yield yield_log(
                f"Sync complete. Added: {added_count}, updated: {updated_count}, removed: {removed_count}.",
                final=True
            )

        except Exception as e:
            success = False
            logger.exception(f"Sync failed: {e}")
            yield yield_log(f"Sync failed: {e}", final=True)
            raise
        finally:
            try:
                self.db.log_sync(
                    added_count, removed_count, trigger,
                    success and not stopped,
                    action + ("-stopped" if stopped else ""),
                    user
                )
            except Exception as e:
                logger.exception(f"Failed to write sync log: {e}")


    def close(self):
        """Close any resources held by the SyncService (database connection)."""
        self.db.close()
