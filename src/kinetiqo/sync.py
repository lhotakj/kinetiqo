import logging
import time
from datetime import datetime, timezone, timedelta

from kinetiqo.config import Config
from kinetiqo.db.factory import create_repository
from kinetiqo.strava import StravaClient

logger = logging.getLogger("kinetiqo")

class SyncService:
    def __init__(self, config: Config):
        self.strava = StravaClient(config)
        self.db = create_repository(config)

    def sync(self, full_sync: bool = True, trigger: str = "unknown", user: str = "-", limit_days: int = 0):
        """
        Perform sync of Strava activities, yielding progress updates.

        :param full_sync: If True, fetches ALL activities from Strava and checks for deletions.
                          If False, fetches only activities newer than the latest one in the database.
        :param trigger: Source of the sync trigger (e.g., "cli", "web").
        :param user: User who initiated the sync.
        :param limit_days: If > 0, limits the sync to the last N days.
        """
        log_buffer = []
        sync_type_str = 'full' if full_sync else 'fast'
        action = 'full-sync' if full_sync else 'fast-sync'
        added_count = 0
        removed_count = 0
        success = True

        def yield_log(msg, final=False):
            # Sanitize message to ensure it doesn't break SSE format (no newlines)
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
                # OOB Swap to replace the log area (stopping SSE) and re-enable the button
                
                # 1. Replace wrapper to remove sse-connect but keep log
                wrapper_html = f"""<div id="sync-log-area" hx-swap-oob="true">
                    <div class="bg-gray-50 rounded-lg p-4 min-h-[200px] border border-gray-100">
                        <div class="mb-4">
                            {log_content}
                        </div>
                        <div class="text-center pt-4 border-t border-gray-200">
                            <p class="text-sm text-green-600 font-medium mb-3">Sync completed successfully.</p>
                        </div>
                    </div>
                </div>"""

                # 2. Re-enable the button
                # We need to conditionally add hx-include only for full sync, but since we are in sync() method,
                # we know if it's full sync.
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

                # Combine into a single SSE message and strip newlines from HTML
                combined_html = (wrapper_html + button_html).replace('\n', '')
                return f"data: {combined_html}\n\n"
            else:
                # Normal update targets #sync-result (implied by sse-swap="message" in the client)
                return f"data: {log_content}\n\n"

        try:
            yield yield_log(f"Starting sync process (Mode: {'FULL' if full_sync else 'FAST'}, Limit: {limit_days} days)...")

            # 0. Initialize database schema
            self.db.initialize_schema()

            # 1. Get already synced activity IDs
            synced_ids = self.db.get_synced_activity_ids()
            yield yield_log(f"Found {len(synced_ids)} already synced activities in database.")

            # 2. Determine fetch strategy
            after = None
            if limit_days > 0:
                after = int((datetime.now(timezone.utc) - timedelta(days=limit_days)).timestamp())
                yield yield_log(f"Full sync limited to last {limit_days} days. Fetching activities after {datetime.fromtimestamp(after, tz=timezone.utc)} (timestamp: {after})")
            elif not full_sync:
                latest_ts = self.db.get_latest_activity_time()
                if latest_ts:
                    after = latest_ts - 86400  # Go back 1 day
                    yield yield_log(f"Fast sync: Fetching activities after {datetime.fromtimestamp(after, tz=timezone.utc)}")
                else:
                    yield yield_log("Fast sync: No previous data found, falling back to full fetch.")

            # 3. Fetch activities from Strava
            activities = []
            for progress_msg in self.strava.get_activities(activities, after=after):
                yield yield_log(progress_msg)
                
            yield yield_log(f"Found {len(activities)} activities from Strava.")

            # 4. Identify new activities to sync
            new_activities = [a for a in activities if str(a["id"]) not in synced_ids]
            yield yield_log(f"Identified {len(new_activities)} new activities to sync.")

            # 5. Identify deleted activities (ONLY in Full Sync mode)
            ids_to_delete = set()
            if full_sync and limit_days == 0:
                strava_ids = set(str(a["id"]) for a in activities)
                ids_to_delete = synced_ids - strava_ids
                if ids_to_delete:
                    yield yield_log(f"Found {len(ids_to_delete)} activities in database that are missing from Strava.")
                else:
                    yield yield_log("No activities to delete.")
            else:
                yield yield_log("Skipping deletion check (not in unlimited full sync mode).")

            # 6. Sync new activities
            total_new = len(new_activities)
            for i, activity in enumerate(new_activities, 1):
                activity_id = activity["id"]
                sport = activity["sport_type"]
                name = activity.get("name", "Unknown Activity")
                percent = (i / total_new) * 100 if total_new > 0 else 0

                yield yield_log(f"[{i}/{total_new}] ({percent:.1f}%) Syncing: {name} ({sport})")

                try:
                    # Write activity metadata
                    self.db.write_activity(activity)

                    # Fetch and write streams
                    streams = self.strava.get_streams(activity_id)
                    point_count = len(streams.get('time', {}).get('data', []))

                    if point_count > 0:
                        self.db.write_activity_streams(activity, streams)
                        added_count += 1
                    else:
                        logger.warning(f"  ⚠ Activity {activity_id} has no stream data.")

                except Exception as e:
                    yield yield_log(f"Error syncing activity {activity_id}: {e}")
                    logger.error(f"  ✗ Error syncing activity {activity_id}: {e}")

                time.sleep(1)  # Respect rate limits

            # 7. Delete removed activities
            if ids_to_delete:
                total_del = len(ids_to_delete)
                for i, act_id in enumerate(ids_to_delete, 1):
                    yield yield_log(f"[{i}/{total_del}] Deleting activity {act_id} from database...")
                    try:
                        self.db.delete_activity(act_id)
                        removed_count += 1
                    except Exception as e:
                        yield yield_log(f"Error deleting activity {act_id}: {e}")

            yield yield_log("Sync complete.", final=True)

        except Exception as e:
            success = False
            logger.error(f"Sync failed: {e}")
            yield yield_log(f"Sync failed: {e}", final=True)
            raise e
        finally:
            try:
                self.db.log_sync(added_count, removed_count, trigger, success, action, user)
            except Exception as e:
                logger.error(f"Failed to write sync log: {e}")

    def close(self):
        self.db.close()
