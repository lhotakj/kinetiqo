"""Mocked unit tests for kinetiqo.profile_sync.sync_update_strava_from_env().

Follows the mocked-unit-test style of tests/test_sync_logic.py: the database
repository is a plain MagicMock (never a live connection), so these tests run
fully in isolation.
"""

import unittest
from unittest.mock import MagicMock, patch

from kinetiqo.db.repository import UPDATE_STRAVA_FIELDS
from kinetiqo.profile_sync import (
    sync_update_strava_from_env,
    resolve_refresh_token_from_db,
    persist_refresh_token,
    wire_refresh_token_persistence,
)


def _make_config(**overrides):
    config = MagicMock()
    for field in UPDATE_STRAVA_FIELDS:
        setattr(config, field, "")
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def _make_profile(**overrides):
    profile = {
        "athlete_id": 42,
        "first_name": "Jane",
        "last_name": "Doe",
        "weight": 65.0,
    }
    profile.update({field: "" for field in UPDATE_STRAVA_FIELDS})
    profile.update(overrides)
    return profile


class TestSyncUpdateStravaFromEnv(unittest.TestCase):
    """Unit tests for the "seed once, database wins afterwards" sync behavior."""

    def test_noop_when_no_profile_exists_yet(self):
        repo = MagicMock()
        repo.get_profile.return_value = None
        config = _make_config(update_strava_walking="Year-to-date: {{walking-distance-total-year}}.")

        sync_update_strava_from_env(config, repo)

        repo.upsert_profile.assert_not_called()

    def test_seeds_empty_database_field_from_env(self):
        repo = MagicMock()
        repo.get_profile.return_value = _make_profile()
        config = _make_config(update_strava_walking="Year-to-date: {{walking-distance-total-year}}.")

        sync_update_strava_from_env(config, repo)

        repo.upsert_profile.assert_called_once()
        args, kwargs = repo.upsert_profile.call_args
        self.assertEqual(args, (42, "Jane", "Doe", 65.0))
        self.assertEqual(kwargs["update_strava_walking"], "Year-to-date: {{walking-distance-total-year}}.")
        # All other (still-empty) fields stay empty.
        for field in UPDATE_STRAVA_FIELDS:
            if field != "update_strava_walking":
                self.assertEqual(kwargs[field], "")

    def test_does_not_overwrite_existing_database_value_even_if_env_differs(self):
        repo = MagicMock()
        repo.get_profile.return_value = _make_profile(
            update_strava_walking="Original template, already stored in DB."
        )
        config = _make_config(update_strava_walking="A completely different template now in the env var.")

        sync_update_strava_from_env(config, repo)

        # Database already had a non-empty value for this field — env var is
        # ignored entirely, so no update call should even be made (no other
        # field changed either).
        repo.upsert_profile.assert_not_called()

    def test_mixed_seed_only_empty_fields_left_alone(self):
        repo = MagicMock()
        repo.get_profile.return_value = _make_profile(
            update_strava_walking="Already stored walking template."
        )
        config = _make_config(
            update_strava_walking="Different env value — should be ignored.",
            update_strava_swimming="New swim template from env — DB was empty.",
        )

        sync_update_strava_from_env(config, repo)

        repo.upsert_profile.assert_called_once()
        _, kwargs = repo.upsert_profile.call_args
        # Walking keeps the DB value (env ignored).
        self.assertEqual(kwargs["update_strava_walking"], "Already stored walking template.")
        # Swimming was empty in DB, so it gets seeded from env.
        self.assertEqual(kwargs["update_strava_swimming"], "New swim template from env — DB was empty.")

    def test_noop_when_everything_already_matches_or_stays_empty(self):
        repo = MagicMock()
        repo.get_profile.return_value = _make_profile(
            update_strava_walking="Stored value."
        )
        config = _make_config(update_strava_walking="Stored value.")

        sync_update_strava_from_env(config, repo)

        repo.upsert_profile.assert_not_called()

    def test_empty_env_var_is_a_noop_for_empty_database_field(self):
        repo = MagicMock()
        repo.get_profile.return_value = _make_profile()
        config = _make_config()  # all six env vars empty

        sync_update_strava_from_env(config, repo)

        repo.upsert_profile.assert_not_called()


class TestResolveRefreshTokenFromDb(unittest.TestCase):
    """Unit tests for resolve_refresh_token_from_db().

    Strava rotates and invalidates the previous refresh token on every token
    exchange, so the database copy (once a profile row exists) must win over
    the — possibly stale — STRAVA_REFRESH_TOKEN env var.
    """

    def test_noop_when_no_profile_exists_yet(self):
        config = _make_config(strava_refresh_token="env-token")

        resolve_refresh_token_from_db(config, None)

        self.assertEqual(config.strava_refresh_token, "env-token")

    def test_database_token_overrides_env_var(self):
        config = _make_config(strava_refresh_token="stale-env-token")
        existing = _make_profile(refresh_token="fresh-db-token")

        resolve_refresh_token_from_db(config, existing)

        self.assertEqual(config.strava_refresh_token, "fresh-db-token")

    def test_noop_when_database_token_is_empty(self):
        config = _make_config(strava_refresh_token="env-token")
        existing = _make_profile(refresh_token="")

        resolve_refresh_token_from_db(config, existing)

        self.assertEqual(config.strava_refresh_token, "env-token")

    def test_noop_when_database_token_already_matches(self):
        config = _make_config(strava_refresh_token="same-token")
        existing = _make_profile(refresh_token="same-token")

        resolve_refresh_token_from_db(config, existing)

        self.assertEqual(config.strava_refresh_token, "same-token")


class TestPersistRefreshToken(unittest.TestCase):
    """Unit tests for persist_refresh_token()."""

    def test_noop_when_no_profile_exists_yet(self):
        repo = MagicMock()
        repo.get_profile.return_value = None

        result = persist_refresh_token(repo, "new-token")

        self.assertFalse(result)
        repo.upsert_profile.assert_not_called()

    def test_noop_when_token_unchanged(self):
        repo = MagicMock()
        repo.get_profile.return_value = _make_profile(refresh_token="same-token")

        result = persist_refresh_token(repo, "same-token")

        self.assertTrue(result)
        repo.upsert_profile.assert_not_called()

    def test_noop_for_empty_token(self):
        repo = MagicMock()

        result = persist_refresh_token(repo, "")

        self.assertFalse(result)
        repo.get_profile.assert_not_called()
        repo.upsert_profile.assert_not_called()

    def test_persists_rotated_token_and_preserves_other_fields(self):
        repo = MagicMock()
        repo.get_profile.return_value = _make_profile(
            refresh_token="old-token", update_strava_walking="Keep me."
        )

        result = persist_refresh_token(repo, "new-token")

        self.assertTrue(result)
        repo.upsert_profile.assert_called_once_with(
            42, "Jane", "Doe", 65.0,
            refresh_token="new-token",
            **{field: ("Keep me." if field == "update_strava_walking" else "") for field in UPDATE_STRAVA_FIELDS},
        )


class TestWireRefreshTokenPersistence(unittest.TestCase):
    """Unit tests for wire_refresh_token_persistence()."""

    @patch("kinetiqo.db.factory.create_repository")
    def test_callback_persists_token_via_its_own_repo(self, mock_create_repo):
        repo = MagicMock()
        repo.get_profile.return_value = _make_profile(refresh_token="old-token")
        mock_create_repo.return_value = repo
        config = _make_config()

        wire_refresh_token_persistence(config)
        config.on_refresh_token_changed("rotated-token")

        mock_create_repo.assert_called_once_with(config)
        repo.upsert_profile.assert_called_once()
        repo.close.assert_called_once()

    @patch("kinetiqo.db.factory.create_repository")
    def test_callback_swallows_errors_and_still_closes_repo(self, mock_create_repo):
        repo = MagicMock()
        repo.get_profile.side_effect = RuntimeError("db down")
        mock_create_repo.return_value = repo
        config = _make_config()

        wire_refresh_token_persistence(config)
        # Must not raise even though persisting failed.
        config.on_refresh_token_changed("rotated-token")

        repo.close.assert_called_once()

    @patch("kinetiqo.db.factory.create_repository")
    def test_callback_handles_repo_creation_failure(self, mock_create_repo):
        mock_create_repo.side_effect = RuntimeError("cannot connect")
        config = _make_config()

        wire_refresh_token_persistence(config)
        # Must not raise even though repo creation failed.
        config.on_refresh_token_changed("rotated-token")


if __name__ == "__main__":
    unittest.main()
