"""Road coverage analysis using OpenStreetMap data.

Downloads admin boundaries for the area of the GPS tracks, then downloads
ALL roads within every municipality the user rode through.  This gives
accurate per-municipality coverage percentages (all streets counted, not
just those near the route — matching the Wandrer.earth / RideEveryTile
model).

The pipeline:
1.  Fetch GPS tracks from the database.
2.  Download admin boundaries via a simple bbox query (fast).
3.  Find the finest-level boundaries (municipalities) that intersect the
    GPS tracks and union them into a *coverage polygon*.
4.  Download ALL cyclable roads within that coverage polygon.
5.  Match ridden roads via a tight 15 m buffer around the GPS tracks.
6.  Compute per-boundary coverage stats and build the hierarchy tree.
"""

from typing import List, Dict, Any, Optional

import hashlib
import json as json_module

import geopandas as gpd
import osmnx as ox
import pandas as pd
from loguru import logger
from shapely.geometry import LineString
from shapely.ops import unary_union

from kinetiqo.config import Config
from kinetiqo.db.factory import create_repository

# ---------------------------------------------------------------------------
# Road type configuration
# ---------------------------------------------------------------------------

# Highway types that are ridable by bicycle.
# Motorway, trunk and their links are intentionally excluded — bikes are
# generally prohibited on these high-speed roads.
CYCLABLE_HIGHWAY_TYPES = [
    "primary", "primary_link",
    "secondary", "secondary_link",
    "tertiary", "tertiary_link",
    "residential", "living_street",
    "unclassified",
    "service",
    "cycleway",
    "track",
    "path",
    "bridleway",
    "pedestrian",
]

# Surface values considered "unpaved" — filtered out when *paved_only* is set.
UNPAVED_SURFACES = [
    "unpaved", "dirt", "gravel", "fine_gravel", "sand", "grass",
    "ground", "earth", "mud", "clay", "compacted", "pebblestone",
]

# ---------------------------------------------------------------------------
# Administrative boundary levels (OSM admin_level tag)
# ---------------------------------------------------------------------------

# Ordered from coarsest to finest.  Names are display labels.
ADMIN_LEVELS: List[tuple] = [
    ("country", "2"),
    ("region", "4"),       # Kraj (CZ), Bundesland (DE), Region (FR) …
    ("district", "6"),     # Okres (CZ), Landkreis (DE) …
    ("municipality", "8"), # Obec/Město (CZ), Gemeinde (DE) …
]

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

ROAD_MATCH_BUFFER_M = 15           # metres — tight buffer to snap GPS to road edges
TRACK_ANALYSIS_BUFFER_M = 500      # metres — fallback buffer if no admin boundaries
TRACK_SIMPLIFY_TOLERANCE_M = 50    # metres — simplify polygons for faster Overpass queries
MAX_ANALYSIS_AREA_KM2 = 10_000     # km² — guard against excessively large downloads
MAX_BOUNDARIES_PER_LEVEL = 120     # skip finer admin levels when a coarser one already exceeds this
BBOX_BUFFER_DEG = 0.01             # ~1 km — pad around track bbox for boundary query


def _osm_name(row) -> str | None:
    """Extract a human-readable name from an OSM feature row.

    Prefers ``name:en`` (English), falls back to ``name``.
    Returns ``None`` when neither is available — the caller should
    skip nameless features.

    pandas represents missing tag values as ``float('nan')`` which is
    *truthy* in Python, so a plain ``or`` chain does not work.
    """
    for col in ("name:en", "name"):
        val = row.get(col)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            s = str(val).strip()
            if s:
                return s
    return None


class PathfinderService:
    """Analyse road coverage from cycling activities against OSM data."""

    def __init__(self, config: Config):
        self.config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_ridden_roads_stats(
        self, activity_ids: List[str], paved_only: bool = False,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Compute road-coverage statistics for the given activities.

        Results are cached in the database.  On subsequent calls with the
        same activities and paved_only flag the cached JSON is returned
        instantly unless the cache entry is older than
        ``config.pathfinder_cache_ttl_days`` or *force_refresh* is set.

        :param activity_ids: Strava activity IDs whose GPS tracks to analyse.
        :param paved_only:   If ``True``, exclude unpaved road surfaces.
        :param force_refresh: If ``True``, ignore any cached result and
                              re-download from OpenStreetMap.
        :return: A dict with *summary*, *hierarchy*, and *cached* keys,
                 or an *error* key.
        """
        repo = create_repository(self.config)
        try:
            cache_key = self._cache_key(activity_ids, paved_only)
            ttl_days = self.config.pathfinder_cache_ttl_days

            # --- try cache (unless disabled or forced refresh) ---------------
            if ttl_days > 0 and not force_refresh:
                try:
                    hit = repo.get_pathfinder_cache(cache_key)
                    if hit is not None:
                        from datetime import datetime, timezone, timedelta
                        created = hit["created_at"]
                        if hasattr(created, "tzinfo") and created.tzinfo is None:
                            created = created.replace(tzinfo=timezone.utc)
                        age = datetime.now(timezone.utc) - created
                        if age < timedelta(days=ttl_days):
                            logger.info(
                                f"Pathfinder: cache hit (age {age.days}d, "
                                f"TTL {ttl_days}d)"
                            )
                            result = json_module.loads(hit["result_json"])
                            result["cached"] = True
                            return result
                        else:
                            logger.info(
                                f"Pathfinder: cache stale (age {age.days}d, "
                                f"TTL {ttl_days}d) — recomputing"
                            )
                except Exception as exc:
                    logger.warning(f"Pathfinder: cache read failed, computing fresh: {exc}")

            # --- compute fresh -----------------------------------------------
            result = self._analyse(repo, activity_ids, paved_only)

            # --- store in cache (only successful results) --------------------
            if "error" not in result and ttl_days > 0:
                try:
                    repo.set_pathfinder_cache(
                        cache_key,
                        json_module.dumps(sorted(activity_ids)),
                        paved_only,
                        json_module.dumps(result),
                    )
                    logger.info("Pathfinder: result cached")
                except Exception as exc:
                    logger.warning(f"Pathfinder: failed to write cache: {exc}")

            result["cached"] = False
            return result

        except Exception as e:
            logger.error(f"Pathfinder error: {e}", exc_info=True)
            return {"error": str(e)}
        finally:
            repo.close()

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_key(activity_ids: List[str], paved_only: bool) -> str:
        """Deterministic SHA-256 cache key from activity IDs + paved flag."""
        payload = json_module.dumps(sorted(activity_ids)) + "|" + str(paved_only)
        return hashlib.sha256(payload.encode()).hexdigest()

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------

    def _analyse(
        self, repo, activity_ids: List[str], paved_only: bool
    ) -> Dict[str, Any]:
        # 1. Fetch GPS tracks from the database --------------------------------
        activity_coords = repo.get_streams_coords_for_activities(activity_ids)
        if not activity_coords:
            return {"error": "No GPS data found for selected activities."}

        lines = []
        for coords in activity_coords.values():
            if len(coords) > 1:
                # DB stores [lat, lng]; Shapely expects (lng, lat)
                xy = [(p[1], p[0]) for p in coords]
                lines.append(LineString(xy))

        if not lines:
            return {"error": "No valid GPS tracks found."}

        ridden_gdf = gpd.GeoDataFrame(geometry=lines, crs="EPSG:4326")
        utm_crs = ridden_gdf.estimate_utm_crs()

        # 2. Download admin boundaries (single Overpass query) -----------------
        minx, miny, maxx, maxy = ridden_gdf.total_bounds
        north = maxy + BBOX_BUFFER_DEG
        south = miny - BBOX_BUFFER_DEG
        east  = maxx + BBOX_BUFFER_DEG
        west  = minx - BBOX_BUFFER_DEG

        boundaries_gdf = self._fetch_boundaries(north, south, east, west)

        # 3. Build coverage polygon --------------------------------------------
        #    = union of finest-level boundaries that intersect the GPS tracks.
        #    This ensures we download ALL roads in every municipality touched,
        #    giving accurate per-municipality percentages.
        #    Falls back to a 500 m buffer around tracks if boundaries fail.
        coverage_polygon, area_km2 = self._build_coverage_polygon(
            ridden_gdf, boundaries_gdf, utm_crs,
        )

        if area_km2 > MAX_ANALYSIS_AREA_KM2:
            return {
                "error": (
                    f"Analysis area is too large ({area_km2:,.0f} km², "
                    f"max {MAX_ANALYSIS_AREA_KM2:,} km²). "
                    "Please select fewer activities."
                )
            }

        logger.info(
            f"Pathfinder: {len(activity_ids)} activities, "
            f"coverage area {area_km2:,.1f} km²"
        )

        # 4. Download OSM road graph within the coverage polygon ---------------
        highway_re = "|".join(CYCLABLE_HIGHWAY_TYPES)
        custom_filter = f'["highway"~"{highway_re}"]'
        if paved_only:
            unpaved_re = "|".join(UNPAVED_SURFACES)
            custom_filter += f'["surface"!~"{unpaved_re}"]'

        try:
            G = ox.graph_from_polygon(
                coverage_polygon,
                custom_filter=custom_filter,
                simplify=True,
            )
        except Exception as e:
            logger.error(f"OSMnx graph download failed: {e}")
            return {"error": f"Failed to download road data: {e}"}

        if not G or len(G.nodes) == 0:
            return {"error": "No cyclable roads found in the selected area."}

        try:
            G_undir = ox.convert.to_undirected(G)
        except AttributeError:
            G_undir = ox.utils_graph.get_undirected(G)
        G_proj = ox.project_graph(G_undir)
        _, edges_proj = ox.graph_to_gdfs(G_proj, nodes=True, edges=True)

        # 5. Match ridden tracks to road edges ---------------------------------
        #    Instead of marking entire edges as ridden (which inflates the
        #    distance when a GPS track only clips the corner of a long edge),
        #    we geometrically clip each edge to the GPS buffer and measure
        #    only the portion that was actually ridden.
        ridden_proj  = ridden_gdf.to_crs(edges_proj.crs)
        ridden_union = unary_union(ridden_proj.buffer(ROAD_MATCH_BUFFER_M))

        edges_proj = edges_proj.copy()
        edges_proj["length_m"]        = edges_proj.geometry.length
        edges_proj["ridden_length_m"] = 0.0
        edges_proj["is_ridden"]       = False

        sindex = edges_proj.sindex
        candidates_idx = list(sindex.intersection(ridden_union.bounds))
        if candidates_idx:
            candidates  = edges_proj.iloc[candidates_idx]
            touching    = candidates[candidates.intersects(ridden_union)]
            if not touching.empty:
                # Clip edge geometries to the ridden buffer → precise overlap
                clipped = touching.geometry.intersection(ridden_union)
                edges_proj.loc[touching.index, "ridden_length_m"] = clipped.length
                edges_proj.loc[touching.index, "is_ridden"] = clipped.length > 0

        total_m  = edges_proj["length_m"].sum()
        ridden_m = edges_proj["ridden_length_m"].sum()
        pct      = (ridden_m / total_m * 100) if total_m > 0 else 0

        logger.info(
            f"Pathfinder: {ridden_m / 1000:.1f} km ridden / "
            f"{total_m / 1000:.1f} km total = {pct:.1f}%"
        )

        # 6. Build hierarchy from pre-fetched boundaries -----------------------
        hierarchy = self._build_hierarchy_from_gdf(boundaries_gdf, edges_proj)

        return {
            "summary": {
                "total_road_length_km":   round(total_m  / 1000, 2),
                "ridden_road_length_km":  round(ridden_m / 1000, 2),
                "coverage_percentage":    round(pct, 2),
            },
            "hierarchy": hierarchy,
        }

    # ------------------------------------------------------------------
    # Boundary fetching
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_boundaries(
        north: float, south: float, east: float, west: float,
    ) -> Optional[gpd.GeoDataFrame]:
        """Download all admin boundaries in the bbox.  Returns *None* on failure."""
        try:
            gdf = ox.features_from_bbox(
                north, south, east, west,
                tags={"boundary": "administrative"},
            )
            # Keep only relation features (full assembled boundaries)
            if hasattr(gdf.index, "get_level_values"):
                try:
                    gdf = gdf[gdf.index.get_level_values(0) == "relation"]
                except Exception:
                    pass
            gdf = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])]
            if gdf.empty or "admin_level" not in gdf.columns:
                return None
            gdf["_admin_level_str"] = gdf["admin_level"].astype(str).str.strip()
            return gdf
        except Exception as e:
            logger.warning(f"Could not fetch admin boundaries: {e}")
            return None

    # ------------------------------------------------------------------
    # Coverage polygon
    # ------------------------------------------------------------------

    def _build_coverage_polygon(
        self,
        ridden_gdf: gpd.GeoDataFrame,
        boundaries_gdf: Optional[gpd.GeoDataFrame],
        utm_crs,
    ) -> tuple:
        """Build the polygon used to download roads.

        If admin boundaries are available, returns the **union of the
        finest-level boundaries that the GPS tracks cross**.  This
        captures ALL roads in every municipality the user rode through.

        Falls back to a 500 m buffer around the GPS tracks when boundaries
        are not available.

        :return: ``(polygon_wgs84, area_km2)``
        """
        ridden_utm = ridden_gdf.to_crs(utm_crs)
        tracks_union = unary_union(ridden_utm.geometry)

        if boundaries_gdf is not None:
            # Find the finest admin level that has a manageable number of
            # boundaries intersecting the tracks.
            for _, target_level in reversed(ADMIN_LEVELS):
                level_gdf = boundaries_gdf[
                    boundaries_gdf["_admin_level_str"] == target_level
                ]
                if level_gdf.empty:
                    continue

                level_utm = level_gdf.to_crs(utm_crs)
                touching = level_utm[level_utm.intersects(tracks_union)]

                if touching.empty:
                    continue

                if len(touching) > MAX_BOUNDARIES_PER_LEVEL:
                    # Too many at this level — try the next coarser level
                    logger.info(
                        f"Pathfinder: {len(touching)} boundaries at "
                        f"admin_level={target_level} — trying coarser level"
                    )
                    continue

                coverage = unary_union(touching.geometry)
                area_km2 = coverage.area / 1_000_000
                simplified = coverage.simplify(
                    TRACK_SIMPLIFY_TOLERANCE_M
                ).buffer(0)
                polygon = (
                    gpd.GeoSeries([simplified], crs=utm_crs)
                    .to_crs("EPSG:4326")
                    .iloc[0]
                )
                logger.info(
                    f"Pathfinder: coverage polygon from {len(touching)} "
                    f"admin_level={target_level} boundaries "
                    f"({area_km2:,.1f} km²)"
                )
                return polygon, area_km2

        # Fallback: buffer tracks by TRACK_ANALYSIS_BUFFER_M
        logger.info("Pathfinder: falling back to track buffer for coverage")
        buffered = unary_union(ridden_utm.buffer(TRACK_ANALYSIS_BUFFER_M))
        area_km2 = buffered.area / 1_000_000
        simplified = buffered.simplify(TRACK_SIMPLIFY_TOLERANCE_M).buffer(0)
        polygon = (
            gpd.GeoSeries([simplified], crs=utm_crs)
            .to_crs("EPSG:4326")
            .iloc[0]
        )
        return polygon, area_km2

    # ------------------------------------------------------------------
    # Hierarchy from pre-fetched boundaries
    # ------------------------------------------------------------------

    def _build_hierarchy_from_gdf(
        self,
        boundaries_gdf: Optional[gpd.GeoDataFrame],
        edges: gpd.GeoDataFrame,
    ) -> List[Dict[str, Any]]:
        """Build the country→region→district→municipality tree.

        Re-uses a pre-fetched boundaries GeoDataFrame (already filtered
        to relations + polygons) so there is no second Overpass download.
        """
        if boundaries_gdf is None:
            return self._fallback_flat(edges)

        boundaries_gdf = boundaries_gdf.to_crs(edges.crs)
        if "_admin_level_str" not in boundaries_gdf.columns:
            boundaries_gdf["_admin_level_str"] = (
                boundaries_gdf["admin_level"].astype(str).str.strip()
            )

        edge_sindex = edges.sindex
        level_entries: Dict[str, list] = {}

        for level_name, target_level in ADMIN_LEVELS:
            level_gdf = boundaries_gdf[
                boundaries_gdf["_admin_level_str"] == target_level
            ]
            if level_gdf.empty:
                continue

            seen_names: set = set()
            entries = []

            for _, row in level_gdf.iterrows():
                name = _osm_name(row)
                if name is None or name in seen_names:
                    continue
                seen_names.add(name)

                geom = row.geometry
                candidate_idx = list(edge_sindex.intersection(geom.bounds))
                if not candidate_idx:
                    continue
                candidates = edges.iloc[candidate_idx]
                local = candidates[candidates.intersects(geom)]
                if local.empty:
                    continue

                total_m  = local["length_m"].sum()
                ridden_m = local["ridden_length_m"].sum()
                pct      = (ridden_m / total_m * 100) if total_m > 0 else 0

                entries.append({
                    "name":       name,
                    "level":      level_name,
                    "geom":       geom,
                    "rep_point":  geom.representative_point(),
                    "total_km":   round(total_m  / 1000, 2),
                    "ridden_km":  round(ridden_m / 1000, 2),
                    "percentage": round(pct, 2),
                    "children":   [],
                })

            if entries:
                level_entries[level_name] = entries
                logger.info(
                    f"Pathfinder: {len(entries)} {level_name} "
                    f"boundaries with data"
                )
                if len(entries) > MAX_BOUNDARIES_PER_LEVEL:
                    logger.info(
                        f"Pathfinder: skipping finer admin levels "
                        f"(>{MAX_BOUNDARIES_PER_LEVEL} {level_name} entries)"
                    )
                    break

        if not level_entries:
            return self._fallback_flat(edges)

        # ---- nest children into parents (finest → coarsest) -----------------
        available = [name for name, _ in ADMIN_LEVELS if name in level_entries]

        for i in range(len(available) - 1, 0, -1):
            child_level  = available[i]
            parent_level = available[i - 1]

            for child in level_entries[child_level]:
                for parent in level_entries[parent_level]:
                    try:
                        if parent["geom"].contains(child["rep_point"]):
                            parent["children"].append(child)
                            child["_assigned"] = True
                            break
                    except Exception:
                        continue

        # ---- assemble root list ---------------------------------------------
        root = list(level_entries[available[0]])

        for level_name in available[1:]:
            for entry in level_entries[level_name]:
                if not entry.get("_assigned"):
                    root.append(entry)

        return self._clean_tree(root)

    # ------------------------------------------------------------------

    @staticmethod
    def _fallback_flat(edges: gpd.GeoDataFrame) -> List[Dict[str, Any]]:
        """Single "Selected Area" node when no admin boundaries are found."""
        total_km  = edges["length_m"].sum() / 1000
        ridden_km = edges["ridden_length_m"].sum() / 1000
        pct = (ridden_km / total_km * 100) if total_km > 0 else 0
        return [{
            "name":       "Selected Area",
            "level":      "area",
            "total_km":   round(total_km, 2),
            "ridden_km":  round(ridden_km, 2),
            "percentage": round(pct, 2),
            "children":   [],
        }]

    def _clean_tree(self, nodes: list) -> List[Dict[str, Any]]:
        """Strip internal geometry fields and sort recursively."""
        result = []
        for n in nodes:
            result.append({
                "name":       n["name"],
                "level":      n["level"],
                "total_km":   n["total_km"],
                "ridden_km":  n["ridden_km"],
                "percentage": n["percentage"],
                "children":   self._clean_tree(n.get("children", [])),
            })
        result.sort(key=lambda x: x["name"])
        return result
