"""Mocked unit tests for the Map Explorer feature (geo.py).

Follows the canonical test structure from test_sync_logic.py:
- Class-level patches for external dependencies (DB, OSMnx)
- Isolated, fast tests — no real database or network calls
"""

import json
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, PropertyMock

from kinetiqo.config import Config
from kinetiqo.geo import MapExplorerService

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

# Simulates get_streams_coords_for_activities → {id: [[lat, lng], ...]}
MOCK_COORDS = {
    "100": [
        [50.0, 14.0],
        [50.001, 14.001],
        [50.002, 14.002],
    ],
    "101": [
        [50.010, 14.010],
        [50.011, 14.011],
    ],
}

MOCK_COORDS_SINGLE_POINT = {
    "200": [[50.0, 14.0]],  # Only 1 point — too short for a LineString
}


class TestMapExplorerService(unittest.TestCase):
    """Mocked unit tests for MapExplorerService.get_ridden_roads_stats()."""

    def _make_config(self) -> Config:
        return Config(
            database_type="postgresql",
            postgresql_host="localhost",
            postgresql_port=5432,
            postgresql_user="test",
            postgresql_password="test",
            postgresql_database="test_db",
        )

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    @patch("kinetiqo.geo.ox")
    @patch("kinetiqo.geo.create_repository")
    def test_returns_summary_and_hierarchy(self, mock_create_repo, mock_ox):
        """Happy path: valid GPS data → summary + hierarchy returned."""
        mock_repo = MagicMock()
        mock_repo.get_streams_coords_for_activities.return_value = MOCK_COORDS
        mock_create_repo.return_value = mock_repo

        # Stub osmnx calls
        mock_graph = MagicMock()
        mock_graph.__len__ = lambda self: 1  # non-empty graph
        type(mock_graph).nodes = PropertyMock(return_value={1: {}, 2: {}})
        mock_ox.graph_from_polygon.return_value = mock_graph

        mock_undir = MagicMock()
        mock_ox.utils_graph.get_undirected.return_value = mock_undir
        mock_proj = MagicMock()
        mock_ox.project_graph.return_value = mock_proj

        # Minimal GeoDataFrame stub for edges
        import geopandas as gpd
        from shapely.geometry import LineString
        edge_line = LineString([(0, 0), (100, 0)])
        edges = gpd.GeoDataFrame(geometry=[edge_line], crs="EPSG:32633")
        mock_ox.graph_to_gdfs.return_value = (MagicMock(), edges)

        # Admin boundaries: simulate empty results (fallback to flat)
        empty_gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        mock_ox.features_from_bbox.return_value = empty_gdf

        config = self._make_config()
        service = MapExplorerService(config)
        result = service.get_ridden_roads_stats(["100", "101"])

        # Verify structure
        self.assertIn("summary", result)
        self.assertIn("hierarchy", result)
        self.assertIn("total_road_length_km", result["summary"])
        self.assertIn("ridden_road_length_km", result["summary"])
        self.assertIn("coverage_percentage", result["summary"])
        self.assertIsInstance(result["hierarchy"], list)

        # Verify repo was used and closed
        mock_repo.get_streams_coords_for_activities.assert_called_once_with(["100", "101"])
        mock_repo.close.assert_called_once()

    # ------------------------------------------------------------------
    # Error cases
    # ------------------------------------------------------------------

    @patch("kinetiqo.geo.ox")
    @patch("kinetiqo.geo.create_repository")
    def test_no_gps_data_returns_error(self, mock_create_repo, mock_ox):
        """Empty GPS data should return an error dict."""
        mock_repo = MagicMock()
        mock_repo.get_streams_coords_for_activities.return_value = {}
        mock_create_repo.return_value = mock_repo

        config = self._make_config()
        service = MapExplorerService(config)
        result = service.get_ridden_roads_stats(["999"])

        self.assertIn("error", result)
        self.assertIn("No GPS data", result["error"])
        mock_repo.close.assert_called_once()

    @patch("kinetiqo.geo.ox")
    @patch("kinetiqo.geo.create_repository")
    def test_single_point_tracks_returns_error(self, mock_create_repo, mock_ox):
        """Tracks with only 1 point cannot form a LineString → error."""
        mock_repo = MagicMock()
        mock_repo.get_streams_coords_for_activities.return_value = MOCK_COORDS_SINGLE_POINT
        mock_create_repo.return_value = mock_repo

        config = self._make_config()
        service = MapExplorerService(config)
        result = service.get_ridden_roads_stats(["200"])

        self.assertIn("error", result)
        self.assertIn("No valid GPS tracks", result["error"])
        mock_repo.close.assert_called_once()

    @patch("kinetiqo.geo.MAX_ANALYSIS_AREA_KM2", 0.0001)
    @patch("kinetiqo.geo.ox")
    @patch("kinetiqo.geo.create_repository")
    def test_area_too_large_returns_error(self, mock_create_repo, mock_ox):
        """Buffered track area exceeding MAX_ANALYSIS_AREA_KM2 should be rejected."""
        mock_repo = MagicMock()
        mock_repo.get_streams_coords_for_activities.return_value = MOCK_COORDS
        mock_create_repo.return_value = mock_repo

        config = self._make_config()
        service = MapExplorerService(config)
        result = service.get_ridden_roads_stats(["100", "101"])

        self.assertIn("error", result)
        self.assertIn("too large", result["error"])
        mock_repo.close.assert_called_once()

    @patch("kinetiqo.geo.ox")
    @patch("kinetiqo.geo.create_repository")
    def test_osmnx_download_failure_returns_error(self, mock_create_repo, mock_ox):
        """OSMnx network error should be caught and returned as error."""
        mock_repo = MagicMock()
        mock_repo.get_streams_coords_for_activities.return_value = MOCK_COORDS
        mock_create_repo.return_value = mock_repo

        mock_ox.graph_from_polygon.side_effect = Exception("Overpass server timeout")

        config = self._make_config()
        service = MapExplorerService(config)
        result = service.get_ridden_roads_stats(["100", "101"])

        self.assertIn("error", result)
        self.assertIn("Failed to download road data", result["error"])
        mock_repo.close.assert_called_once()

    # ------------------------------------------------------------------
    # paved_only filter
    # ------------------------------------------------------------------

    @patch("kinetiqo.geo.ox")
    @patch("kinetiqo.geo.create_repository")
    def test_paved_only_passes_surface_filter(self, mock_create_repo, mock_ox):
        """When paved_only=True, the custom_filter must include a surface exclusion."""
        mock_repo = MagicMock()
        mock_repo.get_streams_coords_for_activities.return_value = MOCK_COORDS
        mock_create_repo.return_value = mock_repo

        # Let graph_from_polygon succeed then return an empty graph to trigger
        # "No cyclable roads" error — we only care about the filter argument.
        mock_graph = MagicMock()
        type(mock_graph).nodes = PropertyMock(return_value={})
        mock_ox.graph_from_polygon.return_value = mock_graph

        config = self._make_config()
        service = MapExplorerService(config)
        service.get_ridden_roads_stats(["100"], paved_only=True)

        # Inspect the custom_filter kwarg
        call_kwargs = mock_ox.graph_from_polygon.call_args
        custom_filter = call_kwargs.kwargs.get("custom_filter") or call_kwargs[1].get("custom_filter", "")
        self.assertIn('["surface"!~"', custom_filter)
        self.assertIn("unpaved", custom_filter)

    @patch("kinetiqo.geo.ox")
    @patch("kinetiqo.geo.create_repository")
    def test_paved_false_no_surface_filter(self, mock_create_repo, mock_ox):
        """When paved_only=False, the custom_filter should NOT include surface exclusion."""
        mock_repo = MagicMock()
        mock_repo.get_streams_coords_for_activities.return_value = MOCK_COORDS
        mock_create_repo.return_value = mock_repo

        mock_graph = MagicMock()
        type(mock_graph).nodes = PropertyMock(return_value={})
        mock_ox.graph_from_polygon.return_value = mock_graph

        config = self._make_config()
        service = MapExplorerService(config)
        service.get_ridden_roads_stats(["100"], paved_only=False)

        call_kwargs = mock_ox.graph_from_polygon.call_args
        custom_filter = call_kwargs.kwargs.get("custom_filter") or call_kwargs[1].get("custom_filter", "")
        self.assertNotIn("surface", custom_filter)

    # ------------------------------------------------------------------
    # Highway exclusion
    # ------------------------------------------------------------------

    @patch("kinetiqo.geo.ox")
    @patch("kinetiqo.geo.create_repository")
    def test_motorway_excluded_from_filter(self, mock_create_repo, mock_ox):
        """The custom_filter must NOT include motorway or trunk road types."""
        mock_repo = MagicMock()
        mock_repo.get_streams_coords_for_activities.return_value = MOCK_COORDS
        mock_create_repo.return_value = mock_repo

        mock_graph = MagicMock()
        type(mock_graph).nodes = PropertyMock(return_value={})
        mock_ox.graph_from_polygon.return_value = mock_graph

        config = self._make_config()
        service = MapExplorerService(config)
        service.get_ridden_roads_stats(["100"])

        call_kwargs = mock_ox.graph_from_polygon.call_args
        custom_filter = call_kwargs.kwargs.get("custom_filter") or call_kwargs[1].get("custom_filter", "")

        # These should NOT appear in the highway regex
        for excluded in ["motorway", "trunk"]:
            self.assertNotIn(excluded, custom_filter,
                             f"'{excluded}' must be excluded from bike-ridable roads")

        # These SHOULD appear
        for included in ["cycleway", "residential", "secondary"]:
            self.assertIn(included, custom_filter,
                          f"'{included}' must be included in bike-ridable roads")

    # ------------------------------------------------------------------
    # Database caching
    # ------------------------------------------------------------------

    @patch("kinetiqo.geo.ox")
    @patch("kinetiqo.geo.create_repository")
    def test_cache_hit_returns_cached_result(self, mock_create_repo, mock_ox):
        """A fresh cache entry should be returned without calling _analyse."""
        cached_result = {
            "summary": {"total_road_length_km": 10, "ridden_road_length_km": 5, "coverage_percentage": 50},
            "hierarchy": [{"name": "Test Area", "level": "area", "total_km": 10, "ridden_km": 5,
                           "percentage": 50, "children": []}],
        }
        mock_repo = MagicMock()
        mock_repo.get_mapexplorer_cache.return_value = {
            "result_json": json.dumps(cached_result),
            "created_at": datetime.now(timezone.utc) - timedelta(days=1),  # 1 day old
        }
        mock_create_repo.return_value = mock_repo

        config = self._make_config()
        service = MapExplorerService(config)
        result = service.get_ridden_roads_stats(["100", "101"])

        self.assertEqual(result["summary"]["coverage_percentage"], 50)
        self.assertTrue(result["cached"])
        # _analyse should not have been called → no graph download
        mock_ox.graph_from_polygon.assert_not_called()
        mock_repo.close.assert_called_once()

    @patch("kinetiqo.geo.ox")
    @patch("kinetiqo.geo.create_repository")
    def test_cache_miss_computes_and_stores(self, mock_create_repo, mock_ox):
        """On cache miss, _analyse runs and the result is stored in cache."""
        mock_repo = MagicMock()
        mock_repo.get_mapexplorer_cache.return_value = None  # cache miss
        mock_repo.get_streams_coords_for_activities.return_value = MOCK_COORDS
        mock_create_repo.return_value = mock_repo

        # Stub a minimal successful graph download
        mock_graph = MagicMock()
        type(mock_graph).nodes = PropertyMock(return_value={1: {}, 2: {}})
        mock_ox.graph_from_polygon.return_value = mock_graph
        mock_ox.utils_graph.get_undirected.return_value = MagicMock()
        mock_ox.project_graph.return_value = MagicMock()

        import geopandas as gpd
        from shapely.geometry import LineString
        edges = gpd.GeoDataFrame(geometry=[LineString([(0, 0), (100, 0)])], crs="EPSG:32633")
        mock_ox.graph_to_gdfs.return_value = (MagicMock(), edges)

        empty_gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        mock_ox.features_from_bbox.return_value = empty_gdf

        config = self._make_config()
        service = MapExplorerService(config)
        result = service.get_ridden_roads_stats(["100", "101"])

        self.assertIn("summary", result)
        self.assertFalse(result["cached"])
        # Verify the result was stored in cache
        mock_repo.set_mapexplorer_cache.assert_called_once()
        mock_repo.close.assert_called_once()

    @patch("kinetiqo.geo.ox")
    @patch("kinetiqo.geo.create_repository")
    def test_stale_cache_triggers_recomputation(self, mock_create_repo, mock_ox):
        """A cache entry older than TTL should trigger a fresh computation."""
        cached_result = {
            "summary": {"total_road_length_km": 10, "ridden_road_length_km": 5, "coverage_percentage": 50},
            "hierarchy": [],
        }
        mock_repo = MagicMock()
        mock_repo.get_mapexplorer_cache.return_value = {
            "result_json": json.dumps(cached_result),
            "created_at": datetime.now(timezone.utc) - timedelta(days=999),  # very old
        }
        mock_repo.get_streams_coords_for_activities.return_value = MOCK_COORDS
        mock_create_repo.return_value = mock_repo

        # Stub graph download
        mock_graph = MagicMock()
        type(mock_graph).nodes = PropertyMock(return_value={1: {}})
        mock_ox.graph_from_polygon.return_value = mock_graph
        mock_ox.utils_graph.get_undirected.return_value = MagicMock()
        mock_ox.project_graph.return_value = MagicMock()

        import geopandas as gpd
        from shapely.geometry import LineString
        edges = gpd.GeoDataFrame(geometry=[LineString([(0, 0), (50, 0)])], crs="EPSG:32633")
        mock_ox.graph_to_gdfs.return_value = (MagicMock(), edges)
        mock_ox.features_from_bbox.return_value = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

        config = self._make_config()
        service = MapExplorerService(config)
        result = service.get_ridden_roads_stats(["100"])

        # Should have recomputed (not returned cached 50%)
        self.assertFalse(result["cached"])
        # Graph was downloaded → _analyse ran
        mock_ox.graph_from_polygon.assert_called_once()
        # Updated cache was written
        mock_repo.set_mapexplorer_cache.assert_called_once()
        mock_repo.close.assert_called_once()

    @patch("kinetiqo.geo.ox")
    @patch("kinetiqo.geo.create_repository")
    def test_force_refresh_ignores_cache(self, mock_create_repo, mock_ox):
        """force_refresh=True should skip the cache entirely."""
        mock_repo = MagicMock()
        mock_repo.get_streams_coords_for_activities.return_value = MOCK_COORDS
        mock_create_repo.return_value = mock_repo

        mock_graph = MagicMock()
        type(mock_graph).nodes = PropertyMock(return_value={1: {}})
        mock_ox.graph_from_polygon.return_value = mock_graph
        mock_ox.utils_graph.get_undirected.return_value = MagicMock()
        mock_ox.project_graph.return_value = MagicMock()

        import geopandas as gpd
        from shapely.geometry import LineString
        edges = gpd.GeoDataFrame(geometry=[LineString([(0, 0), (50, 0)])], crs="EPSG:32633")
        mock_ox.graph_to_gdfs.return_value = (MagicMock(), edges)
        mock_ox.features_from_bbox.return_value = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

        config = self._make_config()
        service = MapExplorerService(config)
        result = service.get_ridden_roads_stats(["100"], force_refresh=True)

        # Cache read should NOT have been called
        mock_repo.get_mapexplorer_cache.assert_not_called()
        # But cache write should have been called
        mock_repo.set_mapexplorer_cache.assert_called_once()
        self.assertFalse(result["cached"])


if __name__ == "__main__":
    unittest.main()

