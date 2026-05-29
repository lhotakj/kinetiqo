import logging
import time
import os
from datetime import datetime, timezone, timedelta

from kinetiqo.config import Config
from kinetiqo.db.factory import create_repository
from kinetiqo.strava import StravaClient

logger = logging.getLogger("kinetiqo")

STOP_SIGNAL_FILE = ".sync_stop"

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
        self.strava = StravaClient(config)
        self.db = create_repository(config)

    def _check_stop_signal(self):
        """Check for an external stop signal.

        The stop signal is represented by the presence of a file named
        defined by STOP_SIGNAL_FILE; if found, the file is removed and
        the function returns True to indicate the sync should abort.
        """
        if os.path.exists(STOP_SIGNAL_FILE):
            try:
                os.remove(STOP_SIGNAL_FILE)
            except:
                pass
            return True
        return False

    def sync(self, full_sync: bool = True, trigger: str = "unknown", user: str = "-", limit_days: int = 0):
        """
        Perform sync of Strava activities, yielding progress updates.

        Full sync:  fetches activities within the given limit_days window (or all time if 0).
        Fast sync:  fetches activities after the latest activity already in the database.
        """
        self._check_stop_signal()  # clear any leftover stop signal before starting

        log_buffer = []
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
                wrapper_html = f"""<div id="sync-log-area" hx-swap-oob="true">
                    <div class="bg-gray-50 rounded-lg p-4 min-h-[200px] border border-gray-100">
                        <div class="mb-4">{log_content}</div>
                        <div class="text-center pt-4 border-t border-gray-200">
                            <p class="text-sm {status_color} font-medium mb-3">{status_msg}</p>
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
            stop_button_html = f"""<button id="start-sync-btn" 
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
            synced_ids = self.db.get_synced_activity_ids()
            yield yield_log(f"Found {len(synced_ids)} already synced activities in database.")

            if self._check_stop_signal():
                stopped = True
                yield yield_log("Stop signal received. Aborting...", final=True, is_stopped=True)
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
            activities = []
            for item in self.strava.get_activities(activities, after=after):
                if isinstance(item, str):
                    yield yield_log(item)
                else:
                    if self._check_stop_signal():
                        stopped = True
                        yield yield_log("Stop signal received during fetch. Aborting...", final=True, is_stopped=True)
                        return

            yield yield_log(f"Found {len(activities)} activities from Strava.")

            new_activities = [a for a in activities if str(a["id"]) not in synced_ids]
            existing_activities = [a for a in activities if str(a["id"]) in synced_ids]
            yield yield_log(f"Identified {len(new_activities)} new and {len(existing_activities)} existing activities.")

            # --- Identify stale DB entries within the fetched window ---
            strava_ids = {str(a["id"]) for a in activities}
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
                yield yield_log("Stop signal received. Aborting...", final=True, is_stopped=True)
                return

            # --- Phase 1: Update metadata for existing activities ---
            if existing_activities:
                yield yield_log(f"Updating metadata for {len(existing_activities)} existing activities...")
                for activity in existing_activities:
                    try:
                        self.db.write_activity(activity)
                        updated_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to update activity {activity['id']}: {e}")
                yield yield_log(f"Updated {updated_count} existing activities.")

            if self._check_stop_signal():
                stopped = True
                yield yield_log("Stop signal received. Aborting...", final=True, is_stopped=True)
                return

            # --- Phase 2: Sync new activities (metadata + streams) ---
            total_new = len(new_activities)
            for i, activity in enumerate(new_activities, 1):
                if self._check_stop_signal():
                    stopped = True
                    yield yield_log("Stop signal received. Aborting...", final=True, is_stopped=True)
                    return
                activity_id = activity["id"]
                sport = activity["sport_type"]
                name = activity.get("name", "Unknown Activity")
                percent = (i / total_new) * 100 if total_new > 0 else 0
                yield yield_log(f"[{i}/{total_new}] ({percent:.1f}%) Syncing: {name} ({sport})")
                try:
                    self.db.write_activity(activity)
                    streams = self.strava.get_streams(activity_id)
                    point_count = len(streams.get('time', {}).get('data', []))
                    if point_count > 0:
                        self.db.write_activity_streams(activity, streams)
                        added_count += 1
                    else:
                        logger.warning(f"Activity {activity_id} has no stream data.")
                except Exception as e:
                    yield yield_log(f"Error syncing activity {activity_id}: {e}")
                    logger.error(f"Error syncing activity {activity_id}: {e}")
                time.sleep(0.1)

            # --- Phase 3: Delete stale activities ---
            if ids_to_delete:
                try:
                    self.db.delete_activities(list(ids_to_delete))
                    removed_count = len(ids_to_delete)
                    yield yield_log(f"Deleted {removed_count} stale activities from database.")
                except Exception as e:
                    yield yield_log(f"Error deleting stale activities: {e}")

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
