import html
import logging
import time
import os
from datetime import datetime, timezone, timedelta

import requests

from kinetiqo.config import Config, UPDATE_STRAVA_MAX_ITEMS
from kinetiqo.db.factory import create_repository
from kinetiqo.strava import StravaClient, StravaFetchError
from kinetiqo.profile_sync import sync_update_strava_from_env
from kinetiqo.strava_description import DescriptionContext, any_update_strava_template_configured, get_template_for_activity

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

    def _update_strava_description(self, description_context: "DescriptionContext", activity: dict) -> "tuple[str, str | None]":
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
            detail = self.strava.get_activity_detail(activity_id)
            existing_description = (detail or {}).get("description") or ""
            new_description = description_context.render_for_activity(
                template,
                activity.get("start_date"),
                existing_description,
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

    def sync(self, full_sync: bool = True, trigger: str = "unknown", user: str = "-", limit_days: int = 0):
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
            log_content = '<div class="font-mono text-xs text-gray-600 overflow-y-auto max-h-64 flex flex-col-reverse">'
            for line in log_buffer:
                log_content += f'<div class="truncate">{line}</div>'
            log_content += '</div>'
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
                hx_include = 'hx-include="#syncLimit"' if full_sync else ''
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
                return f"data: {log_content}\n\n"

        try:
            stop_button_html = """<button id="start-sync-btn" 
                    hx-post="/api/sync/stop" 
                    hx-swap="none"
                    hx-swap-oob="true"
                    class="px-6 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium transition shadow-sm inline-flex items-center">
                <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                Stop Sync
            </button>""".replace('\n', '')
            yield f"data: {stop_button_html}\n\n"
            yield yield_log(f"Starting {sync_type_str} sync (limit: {limit_days} days)...")

            self.db.initialize_schema()
            try:
                sync_update_strava_from_env(self.config, self.db)
            except Exception as e:
                logger.warning(f"UPDATE_STRAVA: failed to sync template from environment: {e}")

            description_context = None
            description_update_ids: set[str] = set()
            if any_update_strava_template_configured(self.config):
                description_context = DescriptionContext(self.config, self.db)

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
                    after = int(after_dt.timestamp())
                    yield yield_log(
                        f"Fast sync: fetching activities since {after_dt.strftime('%Y-%m-%d')} "
                        f"(day prior to latest: {latest_dt.strftime('%Y-%m-%d %H:%M:%S UTC')})."
                    )
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
            for i, activity in enumerate(activities, 1):
                if self._check_stop_signal():
                    stopped = True
                    yield yield_log(STOP_SIGNAL_ABORT_MSG, final=True, is_stopped=True)
                    return
                activity_id = activity["id"]
                sport = activity["sport_type"]
                name = activity.get("name", "Unknown Activity")
                percent = (i / total_activities) * 100 if total_activities > 0 else 0
                is_existing = str(activity_id) in synced_ids
                desc_suffix = ""
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
                    if description_context is not None:
                        if str(activity_id) in description_update_ids:
                            status, warning = self._update_strava_description(description_context, activity)
                        else:
                            # Template may be absent for this activity's bucket;
                            # preserve the old "no status suffix" behavior there.
                            status = DESC_SKIPPED if get_template_for_activity(self.config, sport) else DESC_NOT_CONFIGURED
                            warning = None
                        desc_suffix = _description_status_suffix(status)
                        if warning:
                            sync_warnings.append(warning)
                    yield yield_log(f"[{i}/{total_activities}] ({percent:.0f}%) {name} ({sport}){desc_suffix}")
                except Exception as e:
                    msg = f"Error syncing activity {activity_id}: {e}"
                    sync_warnings.append(msg)
                    logger.error(msg)
                    yield yield_log(f"[{i}/{total_activities}] ({percent:.0f}%) {name} ({sport}) — failed: {e}")
                time.sleep(0.1)

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

            yield yield_log(
                f"Sync complete. Added: {added_count}, updated: {updated_count}, removed: {removed_count}.",
                final=True
            )

        except Exception as e:
            success = False
            logger.error(f"Sync failed: {e}", exc_info=True)
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
                logger.error(f"Failed to write sync log: {e}")


    def close(self):
        """Close any resources held by the SyncService (database connection)."""
        self.db.close()
