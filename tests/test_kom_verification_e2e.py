import os
import sys
import unittest
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from kinetiqo.web.fondo_o_meter import compute_fondo_o_meter
from kinetiqo.koms import (
    save_verified_koms,
    load_verified_koms,
    save_verified_trophies,
    load_verified_trophies,
    extract_trophies_from_segment_efforts,
    record_activity_trophies,
)

class TestKOMCalculationLogic(unittest.TestCase):
    def test_cache_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / 'verified_koms.json'
            sample = {'1001': 2, '1002': 1, '2001': 3}
            save_verified_koms(sample, p)
            loaded = load_verified_koms(p)
            self.assertEqual(loaded, sample)

    def test_trophies_cache_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / 'verified_trophies.json'
            sample = {'1001': {'1': 2, '2': 1, '5': 3}, '1002': {'3': 1}}
            save_verified_trophies(sample, p)
            loaded = load_verified_trophies(p)
            self.assertEqual(loaded, sample)

    def test_record_activity_trophies(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / 'verified_trophies.json'
            efforts = [
                {'kom_rank': 1},
                {'achievements': [{'type': 'overall', 'rank': 2}]},
                {'achievements': [{'type': 'overall', 'rank': 8}]},
            ]
            record_activity_trophies(1001, efforts, p)
            loaded = load_verified_trophies(p)
            self.assertIn('1001', loaded)
            self.assertEqual(loaded['1001']['1'], 1)
            self.assertEqual(loaded['1001']['2'], 1)
            self.assertEqual(loaded['1001']['8'], 1)

    def test_koms_aggregation_by_year_and_sport(self):
        activities = [
            # 2026 rides: 1001 has 2 KOMs, 1002 has 1 KOM, 1003 has 0 KOMs
            {'id': 1001, 'name': '2026 Epic Climb', 'sport_type': 'Ride', 'start_date': '2026-05-10T10:00:00Z', 'distance': 120000, 'pr_count': 3},
            {'id': 1002, 'name': '2026 Sprint', 'sport_type': 'Ride', 'start_date': '2026-06-15T10:00:00Z', 'distance': 60000, 'pr_count': 1},
            {'id': 1003, 'name': '2026 Normal Ride (no KOM)', 'sport_type': 'Ride', 'start_date': '2026-07-20T10:00:00Z', 'distance': 45000, 'pr_count': 2},
            # 2025 ride with 3 KOMs
            {'id': 2001, 'name': '2025 Mountain Pass', 'sport_type': 'Ride', 'start_date': '2025-08-12T10:00:00Z', 'distance': 150000, 'pr_count': 5},
            # 2026 Run (must not count cycling KOMs)
            {'id': 3001, 'name': '2026 Trail Run', 'sport_type': 'Run', 'start_date': '2026-09-01T10:00:00Z', 'distance': 15000, 'pr_count': 1},
        ]
        mock_cache = {'1001': 2, '1002': 1, '2001': 3}

        # 2026 Cycling: 2 + 1 = 3 KOMs
        res_2026 = compute_fondo_o_meter(activities, 2026, 'cycling', verified_koms=mock_cache)
        self.assertEqual(res_2026['koms_count'], 3)

        # 2025 Cycling: 3 KOMs
        res_2025 = compute_fondo_o_meter(activities, 2025, 'cycling', verified_koms=mock_cache)
        self.assertEqual(res_2025['koms_count'], 3)

        # 2026 Running: 0 KOMs
        res_run = compute_fondo_o_meter(activities, 2026, 'running', verified_koms=mock_cache)
        self.assertEqual(res_run['koms_count'], 0)

    def test_sync_phase_3_grouping(self):
        """Simulate Strava API efforts and verify grouping into koms_by_activity."""
        koms_list = [
            {'id': 901, 'name': 'Segment A', 'activity': {'id': 19346164262}},
            {'id': 902, 'name': 'Segment B', 'activity': {'id': 19346164262}},
            {'id': 903, 'name': 'Segment C', 'activity': {'id': 18000000001}},
        ]
        koms_by_activity = {}
        for effort in koms_list:
            act_ref = effort.get('activity') or {}
            act_id = act_ref.get('id')
            if act_id:
                act_id_str = str(act_id)
                koms_by_activity[act_id_str] = koms_by_activity.get(act_id_str, 0) + 1

        self.assertEqual(koms_by_activity, {'19346164262': 2, '18000000001': 1})

    def test_extract_trophies_detailed_edge_cases(self):
        """Test extraction with various Strava payload structures (type_id, string ranks, etc)."""
        efforts = [
            # 1: Direct kom_rank as integer
            {'name': 'Effort 1', 'kom_rank': 1},
            # 2: String rank in kom_rank
            {'name': 'Effort 2', 'kom_rank': '2'},
            # 3: 3rd place podium (e.g. user scenario)
            {'name': 'Effort 3', 'kom_rank': 3, 'achievements': [{'type_id': 1, 'rank': 3, 'type': 'overall'}]},
            # 4: overall_rank field
            {'name': 'Effort 4', 'overall_rank': 4},
            # 5: leaderboard_rank field
            {'name': 'Effort 5', 'leaderboard_rank': 5},
            # 6: achievements with type_id: 1 and no kom_rank
            {'name': 'Effort 6', 'achievements': [{'type_id': 1, 'rank': 6}]},
            # 7: achievements with type: "top10"
            {'name': 'Effort 7', 'achievements': [{'type': 'top10', 'rank': 7}]},
            # 8: achievements with type: "cr"
            {'name': 'Effort 8', 'achievements': [{'type': 'cr', 'rank': 8}]},
            # PR-only efforts that must NOT count as trophies
            {'name': 'Effort PR 1', 'pr_rank': 1, 'achievements': [{'type': 'pr', 'rank': 1, 'type_id': 3}]},
            {'name': 'Effort PR 2', 'pr_rank': 2, 'achievements': [{'type': 'pr', 'rank': 2, 'type_id': 3}]},
            {'name': 'Effort PR 3', 'pr_rank': 3, 'achievements': [{'type': 'year_pr', 'rank': 3}]},
            # Out-of-bounds rank (11th place)
            {'name': 'Effort 11', 'kom_rank': 11},
        ]
        res = extract_trophies_from_segment_efforts(efforts)
        self.assertEqual(res[1], 1)
        self.assertEqual(res[2], 1)
        self.assertEqual(res[3], 1)  # Deduplicated despite appearing in kom_rank and achievements
        self.assertEqual(res[4], 1)
        self.assertEqual(res[5], 1)
        self.assertEqual(res[6], 1)
        self.assertEqual(res[7], 1)
        self.assertEqual(res[8], 1)
        self.assertEqual(res[9], 0)
        self.assertEqual(res[10], 0)
        self.assertEqual(sum(res.values()), 8)

    def test_user_activity_segment_3rd_place_scenario(self):
        """Simulate user activity 19552952131 with segment 3518575221235196116 placing 3rd."""
        efforts = [
            {
                'id': 3518575221235196116,
                'name': 'Famous Hill Climb',
                'kom_rank': 3,
                'pr_rank': 1,
                'achievements': [
                    {'type_id': 1, 'type': 'overall', 'rank': 3},
                    {'type_id': 3, 'type': 'pr', 'rank': 1},
                ],
            }
        ]
        trophies = extract_trophies_from_segment_efforts(efforts)
        self.assertEqual(trophies[3], 1)
        self.assertEqual(trophies[1], 0)
        self.assertEqual(trophies[2], 0)

        # In Fondo-o-meter, verify 3rd place is counted
        activity = {
            'id': 19552952131,
            'name': 'Epic Ride with 3rd place',
            'sport_type': 'Ride',
            'start_date': '2026-08-01T10:00:00Z',
            'distance': 85000,
            'pr_count': 1,
            'achievement_count': 2,
            'segment_efforts': efforts,
        }
        res = compute_fondo_o_meter([activity], 2026, 'cycling')
        self.assertEqual(res['trophies']['ranks']['3'], 1)
        self.assertEqual(res['trophies_count'], 1)
        self.assertEqual(res['prs_count'], 1)

    def test_get_activities_needing_trophies_repositories(self):
        """Verify get_activities_needing_trophies queries for all 3 repository backends."""
        from kinetiqo.db.postgresql import PostgresqlRepository
        from kinetiqo.db.mysql import MySQLRepository
        from kinetiqo.db.firebird import FirebirdRepository

        # 1. PostgreSQL
        class DummyCursorPG:
            def __init__(self):
                self.sql = None
                self.params = None
            def execute(self, sql, params=None):
                self.sql = sql
                self.params = params
            def fetchall(self):
                return [{'id': 19552952131, 'name': 'Ride 1', 'sport': 'Ride', 'achievement_count': 2, 'pr_count': 1, 'start_date': '2026-08-01T10:00:00Z'}]
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        class DummyConnPG:
            def cursor(self, cursor_factory=None):
                return DummyCursorPG()
            def close(self):
                pass

        repo_pg = object.__new__(PostgresqlRepository)
        repo_pg.conn = DummyConnPG()
        repo_pg._ensure_connected = lambda: None
        res_pg = repo_pg.get_activities_needing_trophies(limit=25)
        self.assertEqual(len(res_pg), 1)
        self.assertEqual(res_pg[0]['id'], 19552952131)
        self.assertEqual(res_pg[0]['achievement_count'], 2)

        # 2. MySQL
        class DummyCursorMySQL:
            def __init__(self):
                self.sql = None
                self.params = None
            def execute(self, sql, params=None):
                self.sql = sql
                self.params = params
            def fetchall(self):
                return [{'id': 19552952131, 'name': 'Ride 1', 'sport': 'Ride', 'achievement_count': 2, 'pr_count': 1, 'start_date': '2026-08-01T10:00:00Z'}]
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        class DummyConnMySQL:
            def cursor(self, dictionary=False):
                return DummyCursorMySQL()
            def close(self):
                pass

        repo_my = object.__new__(MySQLRepository)
        repo_my.conn = DummyConnMySQL()
        repo_my._ensure_connected = lambda: None
        res_my = repo_my.get_activities_needing_trophies(limit=25)
        self.assertEqual(len(res_my), 1)
        self.assertEqual(res_my[0]['id'], 19552952131)

        # 3. Firebird
        class DummyCursorFB:
            def __init__(self):
                self.sql = None
                self.params = None
                self.description = [('activity_id',), ('name',), ('sport',), ('start_date',), ('achievement_count',), ('pr_count',), ('trophies',)]
            def execute(self, sql, params=None):
                self.sql = sql
                self.params = params
            def fetchall(self):
                return [(19552952131, 'Ride 1', 'Ride', '2026-08-01T10:00:00Z', 2, 1, None)]
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        class DummyConnFB:
            def cursor(self):
                return DummyCursorFB()
            def close(self):
                pass


        repo_fb = object.__new__(FirebirdRepository)
        repo_fb.conn = DummyConnFB()
        repo_fb._ensure_connected = lambda: None
        res_fb = repo_fb.get_activities_needing_trophies(limit=25)
        self.assertEqual(len(res_fb), 1)
        self.assertEqual(res_fb[0]['id'], 19552952131)

    def test_scan_trophies_cli_command(self):
        """Test the scan-trophies CLI command with mocked StravaClient and DB."""
        from unittest.mock import patch, MagicMock
        from click.testing import CliRunner
        from kinetiqo.cli import cli

        runner = CliRunner()
        mock_db = MagicMock()
        mock_db.get_activities_needing_trophies.return_value = [
            {'id': 19552952131, 'name': 'Ride A', 'sport': 'Ride', 'achievement_count': 2, 'pr_count': 1}
        ]

        mock_client = MagicMock()
        mock_client.get_activity_detail.return_value = {
            'id': 19552952131,
            'segment_efforts': [
                {'kom_rank': 3, 'name': 'Test Climb', 'achievements': [{'rank': 3, 'type': 'overall'}]}
            ]
        }

        with patch('kinetiqo.cli._prepare_db'), \
             patch('kinetiqo.cli.create_repository', return_value=mock_db), \
             patch('kinetiqo.strava.StravaClient', return_value=mock_client), \
             patch('kinetiqo.koms.save_verified_trophies'):
            result = runner.invoke(cli, ['scan-trophies', '--limit', '10'])
            self.assertEqual(result.exit_code, 0)
            mock_db.update_activity_trophies.assert_called_once()
            call_args = mock_db.update_activity_trophies.call_args[0]
            self.assertEqual(call_args[0], '19552952131')
            self.assertEqual(call_args[1][3], 1)




if __name__ == '__main__':
    unittest.main()

