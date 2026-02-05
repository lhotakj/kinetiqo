import logging
import time
from datetime import datetime, timezone
from kinetiqo.config import Config
from kinetiqo.strava import StravaClient
from kinetiqo.db.factory import create_repository

logger = logging.getLogger("kinetiqo")

class SyncService:
    def __init__(self, config: Config):
        self.strava = StravaClient(config)
        self.db = create_repository(config)

    def sync(self, full_sync: bool = True):
        """
        Perform sync of Strava activities.

        :param full_sync: If True, fetches ALL activities from Strava and checks for deletions.
                          If False, fetches only activities newer than the latest one in the database.
        """
        logger.info(f"Starting sync process (Mode: {'FULL' if full_sync else 'FAST'})...")

        # 0. Initialize database schema
        self.db.initialize_schema()

        # 1. Get already synced activity IDs
        synced_ids = self.db.get_synced_activity_ids()
        logger.info(f"Found {len(synced_ids)} already synced activities in database.")

        # 2. Determine fetch strategy
        after = None
        if not full_sync:
            latest_ts = self.db.get_latest_activity_time()
            if latest_ts:
                after = latest_ts - 86400  # Go back 1 day
                logger.info(f"Fast sync: Fetching activities after {datetime.fromtimestamp(after, tz=timezone.utc)}")
            else:
                logger.info("Fast sync: No previous data found, falling back to full fetch.")

        # 3. Fetch activities from Strava
        activities = self.strava.get_activities(after=after)
        logger.info(f"Found {len(activities)} activities from Strava.")

        # 4. Identify new activities to sync
        new_activities = [a for a in activities if str(a["id"]) not in synced_ids]
        logger.info(f"Identified {len(new_activities)} new activities to sync.")

        # 5. Identify deleted activities (ONLY in Full Sync mode)
        ids_to_delete = set()
        if full_sync:
            strava_ids = set(str(a["id"]) for a in activities)
            ids_to_delete = synced_ids - strava_ids
            if ids_to_delete:
                logger.info(f"Found {len(ids_to_delete)} activities in database that are missing from Strava.")
            else:
                logger.info("No activities to delete.")
        else:
            logger.info("Fast sync: Skipping deletion check.")

        # 6. Sync new activities
        total_new = len(new_activities)
        for i, activity in enumerate(new_activities, 1):
            activity_id = activity["id"]
            sport = activity["sport_type"]
            name = activity.get("name", "Unknown Activity")
            percent = (i / total_new) * 100

            logger.info(f"[{i}/{total_new}] ({percent:.1f}%) Syncing activity {activity_id}: '{name}' ({sport})...")

            try:
                # Write activity metadata
                self.db.write_activity(activity)

                # Fetch and write streams
                streams = self.strava.get_streams(activity_id)
                point_count = len(streams.get('time', {}).get('data', []))

                if point_count > 0:
                    self.db.write_activity_streams(activity, streams)
                    logger.info(f"  ✓ Synced {point_count} data points for activity {activity_id}.")
                else:
                    logger.warning(f"  ⚠ Activity {activity_id} has no stream data.")

            except Exception as e:
                logger.error(f"  ✗ Error syncing activity {activity_id}: {e}")

            time.sleep(1)  # Respect rate limits

        # 7. Delete removed activities
        if ids_to_delete:
            total_del = len(ids_to_delete)
            for i, act_id in enumerate(ids_to_delete, 1):
                logger.info(f"[{i}/{total_del}] Deleting activity {act_id} from database...")
                try:
                    self.db.delete_activity(act_id)
                    logger.info(f"  ✓ Deleted activity {act_id}.")
                except Exception as e:
                    logger.error(f"  ✗ Error deleting activity {act_id}: {e}")

        logger.info("Sync complete.")

    def close(self):
        self.db.close()
