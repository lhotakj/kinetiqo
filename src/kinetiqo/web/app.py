
import hashlib
import logging
import os
import shutil
import mimetypes
import threading
import time as _time
from datetime import datetime
from typing import Dict, List, Optional

import httpx
import requests

import json as json_module
from flask import Flask, g, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_compress import Compress
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from kinetiqo.config import Config
from kinetiqo.db.factory import create_repository
from kinetiqo.db.repository import STRAVA_TYPE_TO_GOAL_TYPE
from kinetiqo.sync import SyncService, STOP_SIGNAL_FILE
from kinetiqo.web.auth import User, users
from kinetiqo.web.fitness import calculate_fitness_freshness
from kinetiqo.web.vo2max import (
    estimate_vo2max, classify_vo2max, smooth_vo2max_history,
    filter_qualifying_rides, MIN_WATTS_SAMPLES,
)
from kinetiqo.web.stats import (
    compute_mega_stats, ACTIVITY_GROUPS, VALID_PERIODS as STATS_PERIODS,
)

"""Web UI for the Kinetiqo application.

This module defines the Flask application, mounts all web routes and JSON
API endpoints used by the browser UI, and provides utility helpers used by
those routes (tile provider configuration, simple caches, Playwright-based
export helpers, etc.). It intentionally keeps the view layer thin — heavy
data processing is delegated to modules under ``kinetiqo.web`` and the
database access is provided via the repository factory ``create_repository``.

Key features implemented here:
  * Flask routes for pages (activities, map, ftp, vo2max, stats, settings)
  * JSON API endpoints for charts and client-side rendering
  * Server-side OSM tile proxy that respects OSM tile usage policy
  * Playwright-driven pixel-perfect PNG/PDF export endpoints
  * Simple in-process TTL cache for expensive power computations

The module is intentionally documented with Google-style docstrings for the
public helpers to satisfy pydocstyle checks and provide richer automated
documentation.
"""

# --- Python version detection ---
import platform


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kinetiqo.web")

app = Flask(__name__, template_folder='./templates',
            static_folder='./static', static_url_path='/static')
app.secret_key = 'super_secret_key_for_demo_only'

# --- Response Compression (gzip / brotli) ---
Compress(app)

# --- Static Files MIME Type Configuration ---
# Add custom MIME types for common files if not already registered
mimetypes.add_type('text/css', '.css')
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('application/json', '.json')
mimetypes.add_type('image/svg+xml', '.svg')
mimetypes.add_type('font/woff2', '.woff2')
mimetypes.add_type('font/woff', '.woff')
mimetypes.add_type('font/ttf', '.ttf')


@app.after_request
def set_static_headers(response):
    """Set proper headers for static content and caching.

    Args:
        response (flask.Response): The response object returned by the
            view. The function mutates headers on this object in-place.

    Returns:
        flask.Response: The mutated response object (returned for Flask
        compatibility with after_request handlers).
    """
    if request.path.startswith('/static/'):
        # Set appropriate Cache-Control headers based on file type
        if request.path.endswith('.css') or request.path.endswith('.js'):
            # CSS and JS: cache for 1 year with immutable. Cache-busting is done
            # via the ?v=<app_version> query parameter appended by templates.
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        elif request.path.endswith(('.woff', '.woff2', '.ttf', '.eot')):
            # Fonts: cache for 1 year
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        elif request.path.endswith(('.jpg', '.jpeg', '.png', '.gif', '.svg', '.ico', '.webp')):
            # Images: cache for 30 days
            response.headers['Cache-Control'] = 'public, max-age=2592000'
        else:
            # Default: cache for 1 hour
            response.headers['Cache-Control'] = 'public, max-age=3600'

        # Ensure Content-Type is set correctly
        if 'Content-Type' not in response.headers:
            content_type, _ = mimetypes.guess_type(request.path)
            if content_type:
                response.headers['Content-Type'] = content_type

        # Add additional security headers for static content
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Access-Control-Allow-Origin'] = '*'

    elif request.path.startswith('/tiles/'):
        # OSM tile proxy responses: let the browser cache tiles for 24 h to
        # avoid redundant round-trips while keeping the map snappy.
        # Do NOT set no-store here — that would defeat the purpose of the proxy.
        response.headers['Cache-Control'] = 'public, max-age=86400'
        response.headers['X-Content-Type-Options'] = 'nosniff'

    else:
        # Prevent browser caching of API responses and dynamic pages.
        # This ensures that data freshly synced (e.g. new activities) is
        # visible immediately without requiring a hard refresh.
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

    # Standard referrer policy for all page responses.
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

    return response


# --- Configuration & Database ---
# Default config, will be overwritten by set_config
config = Config()


def get_db():
    """Return a per-request database repository instance.

    The repository is created via :func:`kinetiqo.db.factory.create_repository`
    on first access and stored on :data:`flask.g` so it is scoped to the
    current request. The :func:`close_db` teardown handler will attempt to
    close the repository at the end of the request (if it exposes ``close``).

    Returns:
        Any: A concrete repository implementing the project's repository API.
    """
    if 'db_repo' not in g:
        g.db_repo = create_repository(config)
    return g.db_repo


@app.teardown_appcontext
def close_db(exception=None):
    """Close and cleanup the per-request repository stored on :data:`flask.g`.

    This function is registered as a Flask ``teardown_appcontext`` handler and
    will be invoked automatically at the end of each request. If the stored
    repository exposes a ``close()`` method it will be called; otherwise the
    repository object is simply discarded.

    Args:
        exception (Optional[BaseException]): Optional exception that caused
            the teardown. It is ignored by this function but included to match
            the Flask teardown handler signature.
    """
    repo = g.pop('db_repo', None)
    if repo is not None:
        try:
            repo.close()
        except Exception as e:
            logger.debug(f"Error closing per-request database connection: {e}", exc_info=True)


def set_config(new_config: Config):
    """Set the global configuration object used by the application.

    Args:
        new_config (Config): A :class:`kinetiqo.config.Config` instance. This
            replaces the module-level ``config`` used when creating
            per-request repositories and resolving API keys/feature flags.
    """
    global config
    config = new_config


# --- Login Configuration ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login ``user_loader`` callback.

    This function is called by Flask-Login to rehydrate a user from the
    session. It should return a :class:`kinetiqo.web.auth.User` instance or
    ``None`` if no matching user exists.

    Args:
        user_id (str): The user identifier stored in the session.

    Returns:
        Optional[User]: A :class:`kinetiqo.web.auth.User` instance or ``None``.
    """
    if user_id in users:
        return User(user_id)
    return None


def describe_cron(expression):
    """Return a human-friendly description for a cron expression.

    Supports simple patterns such as "*/N * * * *" and daily/hourly forms.
    If the expression is unrecognised the original expression is returned.
    """
    if not expression:
        return "Not scheduled"

    parts = expression.strip().split()
    if len(parts) != 5:
        return expression

    minute, hour, day, month, dow = parts

    try:
        if minute.startswith("*/") and hour == "*" and day == "*" and month == "*" and dow == "*":
            interval = minute.split("/")[1]
            return f"Every {interval} minutes"

        if minute == "0" and hour != "*" and day == "*" and month == "*" and dow == "*":
            return f"Daily at {hour}:00"

        if minute != "*" and hour != "*" and day == "*" and month == "*" and dow == "*":
            return f"Daily at {hour}:{minute.zfill(2)}"

    except:
        pass

    return expression


def get_dynamic_limit_days():
    """Calculates dynamic limit days based on current date."""
    today = datetime.now()

    # This Week: Days since Monday (0 = Mon)
    # If today is Mon (0), we want 1 day (today). If Tue (1), 2 days.
    this_week = today.weekday() + 1

    # This Month: Days since 1st of month
    this_month = today.day

    # Helper to get days since start of X months ago
    def days_since_start_of_months_ago(n_months):
        year = today.year
        month = today.month

        target_month = month - n_months
        target_year = year

        while target_month <= 0:
            target_month += 12
            target_year -= 1

        first_of_target = today.replace(year=target_year, month=target_month, day=1)
        return (today - first_of_target).days + 1

    last_month = days_since_start_of_months_ago(1)
    last_2_months = days_since_start_of_months_ago(2)
    last_3_months = days_since_start_of_months_ago(3)
    last_6_months = days_since_start_of_months_ago(6)

    # This Year: Days since Jan 1st
    first_of_year = today.replace(month=1, day=1)
    this_year = (today - first_of_year).days + 1

    # Last Year: This year + Previous year
    first_of_last_year = first_of_year.replace(year=first_of_year.year - 1)
    last_year = (today - first_of_last_year).days + 1

    # Last Two Years: This year + Previous 2 years
    first_of_2_years_ago = first_of_year.replace(year=first_of_year.year - 2)
    last_2_years = (today - first_of_2_years_ago).days + 1

    return {
        'this_week': this_week,
        'this_month': this_month,
        'last_month': last_month,
        'last_2_months': last_2_months,
        'last_3_months': last_3_months,
        'last_6_months': last_6_months,
        'this_year': this_year,
        'last_year': last_year,
        'last_2_years': last_2_years
    }


# --- Routes ---

# Import additional routes from modules
from kinetiqo.web.progress import bp as progress_bp
app.register_blueprint(progress_bp)

@app.route('/')
def index():
    """Root route that redirects authenticated users to the activities page.

    If the current user is authenticated the function redirects to the main
    activities listing. Otherwise it redirects to the login page.

    Returns:
        Response: A Flask redirect response to either ``/activities`` or
        ``/login``.
    """
    if current_user.is_authenticated:
        return redirect(url_for('activities'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Render the login form and authenticate users on POST.

    POST behaviour
    - Expects ``username`` and ``password`` form fields in the request form.
    - On successful authentication the user is logged in via
      :func:`flask_login.login_user` and redirected to the activities page.
    - On failure the login template is rendered again and a flash message is
      shown.

    Returns:
        Response: The rendered login template on GET or on failed login, or a
        redirect to the activities page on successful authentication.
    """
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username in users and users[username]['password'] == password:
            user = User(username)
            login_user(user)
            return redirect(url_for('activities'))
        else:
            flash('Invalid username or password')

    return render_template('login.html', current_year=datetime.now().year)


@app.route('/logout')
@login_required
def logout():
    """Log out the current user and redirect to the login page.

    Returns:
        Response: A Flask redirect response to the login page.
    """
    logout_user()
    return redirect(url_for('login'))


@app.route('/activities')
@login_required
def activities():
    """Render the activities listing page.

    The view attempts to load a recent set of activities from the database
    repository and passes them to the ``activities.html`` template. Errors
    during data loading are caught, logged and surfaced to the user via
    ``flask.flash``.

    Returns:
        Response: The rendered activities page.
    """
    # Load real data from database
    try:
        data = get_db().get_activities(limit=50)
    except Exception as e:
        logger.error(f"Error fetching activities: {e}")
        flash(f"Error fetching activities: {e}")
        data = []

    return render_template('activities.html', title="Activities", activities=data)


# Available base map tile providers with Leaflet-compatible URL templates.
# Mapy.cz providers are always listed so the dropdown can show them as
# disabled when no MAPY_API_KEY is configured (free key from
# https://developer.mapy.cz).  Tiles are loaded directly by the browser.
def _build_tile_providers() -> dict:
    """Return the configured tile providers for the map dropdown.

    The returned mapping is Leaflet-compatible and includes provider names,
    URL templates and attribution strings. Some entries may be marked
    ``disabled`` when the project configuration lacks the required API key so
    the frontend can render them greyed-out.

    Returns:
        dict: Mapping provider_key -> provider metadata dict.
    """
    providers = {
        'openstreetmap': {
            'name': 'OpenStreetMap',
            # Tiles are fetched through our own proxy so the server can attach a
            # valid Referer and User-Agent header as required by OSM's tile usage
            # policy (https://operations.osmfoundation.org/policies/tiles/).
            'url': '/tiles/osm/{z}/{x}/{y}.png',
            'attr': '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            'maxZoom': 19
        },
    }

    # Mapy.cz – use the official public API (no proxy required).
    # The API key is appended as a query-string parameter; Leaflet's
    # L.tileLayer() passes the URL through verbatim.
    api_key = config.mapy_api_key
    mapy_attr = ('&copy; <a href="https://www.seznam.cz/">Seznam.cz, a.s.</a>, '
                 '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>')
    if api_key:
        providers['mapy_basic'] = {
            'name': 'Mapy.cz (Basic)',
            'url': f'https://api.mapy.cz/v1/maptiles/basic/256/{{z}}/{{x}}/{{y}}?apikey={api_key}',
            'attr': mapy_attr,
            'maxZoom': 19
        }
        providers['mapy_outdoor'] = {
            'name': 'Mapy.cz (Outdoor)',
            'url': f'https://api.mapy.cz/v1/maptiles/outdoor/256/{{z}}/{{x}}/{{y}}?apikey={api_key}',
            'attr': mapy_attr,
            'maxZoom': 19
        }
    else:
        # No API key — include entries as disabled so the UI can show them
        # greyed-out with a hint that a key is needed.
        providers['mapy_basic'] = {
            'name': 'Mapy.cz (Basic)',
            'disabled': True,
            'url': '',
            'attr': mapy_attr,
            'maxZoom': 19
        }
        providers['mapy_outdoor'] = {
            'name': 'Mapy.cz (Outdoor)',
            'disabled': True,
            'url': '',
            'attr': mapy_attr,
            'maxZoom': 19
        }

    # Thunderforest – use the official tile API (no proxy required).
    # Free tier key from https://manage.thunderforest.com
    tf_key = config.thunderforest_api_key
    tf_attr = ('Maps &copy; <a href="https://www.thunderforest.com/">Thunderforest</a>, '
               'Data &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors')
    if tf_key:
        providers['thunderforest_cycle'] = {
            'name': 'Thunderforest (OpenCycleMap)',
            'url': f'https://tile.thunderforest.com/cycle/{{z}}/{{x}}/{{y}}.png?apikey={tf_key}',
            'attr': tf_attr,
            'maxZoom': 22
        }
        providers['thunderforest_outdoors'] = {
            'name': 'Thunderforest (Outdoors)',
            'url': f'https://tile.thunderforest.com/outdoors/{{z}}/{{x}}/{{y}}.png?apikey={tf_key}',
            'attr': tf_attr,
            'maxZoom': 22
        }
    else:
        providers['thunderforest_cycle'] = {
            'name': 'Thunderforest (OpenCycleMap)',
            'disabled': True,
            'url': '',
            'attr': tf_attr,
            'maxZoom': 22
        }
        providers['thunderforest_outdoors'] = {
            'name': 'Thunderforest (Outdoors)',
            'disabled': True,
            'url': '',
            'attr': tf_attr,
            'maxZoom': 22
        }

    providers.update({
        'cartodbpositron': {
            'name': 'CartoDB Positron',
            'url': 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
            'attr': '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
            'maxZoom': 20
        },
        'cartodbdark': {
            'name': 'CartoDB Dark',
            'url': 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
            'attr': '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
            'maxZoom': 20
        },
        'esriworldimagery': {
            'name': 'Esri World Imagery',
            'url': 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            'attr': '&copy; Esri, Maxar, Earthstar Geographics',
            'maxZoom': 18
        }
    })

    return providers

# OSM tile subdomain pool — distribute load across a/b/c as recommended.
_OSM_SUBDOMAINS = ('a', 'b', 'c')


@app.route('/tiles/osm/<int:z>/<int:x>/<int:y>.png')
@login_required
async def osm_tile_proxy(z: int, x: int, y: int):
    """Server-side proxy for OpenStreetMap raster tiles.

    Args:
        z (int): Tile zoom level.
        x (int): Tile X coordinate.
        y (int): Tile Y coordinate.

    Returns:
        flask.Response: The raw tile bytes proxied from the OSM tile server
        with an appropriate content-type, or an error status on failure.

    The proxy sets a responsible ``User-Agent`` and ``Referer`` header when
    fetching tiles to comply with OSM tile usage policy.
    """
    if not (0 <= z <= 19):
        return Response('', status=400)

    # Distribute requests across the a/b/c OSM subdomains
    subdomain = _OSM_SUBDOMAINS[(x + y + z) % 3]
    tile_url = f"https://{subdomain}.tile.openstreetmap.org/{z}/{x}/{y}.png"

    # Identify ourselves to OSM as required by their policy
    app_referer = request.host_url.rstrip('/')
    user_agent = 'Kinetiqo/1.0 (personal fitness dashboard; +https://github.com/kinetiqo/kinetiqo)'

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            osm_resp = await client.get(
                tile_url,
                headers={
                    'User-Agent': user_agent,
                    'Referer': app_referer,
                },
                follow_redirects=True,
            )

        # Forward the tile (or the error status) straight to the browser.
        # The after_request hook will add Cache-Control: public, max-age=86400.
        return Response(
            osm_resp.content,
            status=osm_resp.status_code,
            mimetype=osm_resp.headers.get('content-type', 'image/png'),
        )

    except httpx.TimeoutException:
        logger.warning(f"OSM tile proxy timeout: z={z} x={x} y={y}")
        return Response('', status=504)
    except Exception as e:
        logger.error(f"OSM tile proxy error for z={z} x={x} y={y}: {e}")
        return Response('', status=502)


@app.route('/map', methods=['GET', 'POST'])
@login_required
def map_view():
    """Render the map page shell.

    The page itself is a thin shell; actual track geometry is loaded
    asynchronously by the browser via the ``/api/map/data`` endpoint. The
    view accepts optional form/query parameters to pre-select activities and
    rendering options.

    Returns:
        Response: The rendered map template or a redirect back to
        ``/activities`` for GET requests.
    """
    if request.method == 'GET':
        return redirect(url_for('activities'))

    # Get filter parameters
    activity_ids = request.form.getlist('activity_ids[]')

    # Map customization parameters
    color = request.args.get('color', '#FC4C02')
    width = request.args.get('width', '2')
    opacity = request.args.get('opacity', '100')
    basemap = request.args.get('basemap', 'openstreetmap')

    # Just render the template with IDs, don't generate map yet
    return render_template('map.html',
                           title="Activity Map",
                           activity_ids=activity_ids,
                           current_color=color,
                           current_width=width,
                           current_opacity=opacity,
                           current_basemap=basemap,
                           tile_providers=_build_tile_providers())


@app.route('/api/map/data', methods=['POST'])
@login_required
def map_data_api():
    """API endpoint returning raw coordinate arrays as JSON.

    The server sends only compact [lat, lng] arrays and SQL-computed bounds;
    the client renders polylines directly with Leaflet's Canvas renderer.
    Response compression is handled automatically by flask-compress.

    Request JSON body::

        {
            "activity_ids": ["123", "456", ...]
        }

    Response JSON::

        {
            "activities": {
                "<id>": {"name": "...", "coords": [[lat, lng], ...]},
                ...
            },
            "bounds": [min_lat, min_lng, max_lat, max_lng],
            "activity_count": <int>,
            "point_count": <int>
        }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid request body'}), 400

        activity_ids = data.get('activity_ids', [])
        if not activity_ids:
            return jsonify({'error': 'No activity IDs provided'}), 400

        repo = get_db()

        # Step 1: Get activity names
        activities_data = repo.get_activities_by_ids(activity_ids)
        if not activities_data:
            return jsonify({'error': 'No activities found matching the filter criteria.'}), 404

        activity_names = {str(a['id']): a.get('name', f"Activity {a['id']}") for a in activities_data}

        # Step 2: Get compact coordinate arrays — [[lat, lng], ...] per activity
        streams_data = repo.get_streams_coords_for_activities(activity_ids)
        if not streams_data:
            return jsonify({'error': 'No GPS data found for the selected activities.'}), 404

        # Step 3: Get bounds via SQL aggregation (much faster than Python iteration)
        bounds = repo.get_streams_bounds_for_activities(activity_ids)
        if bounds is None:
            return jsonify({'error': 'No valid GPS coordinates found.'}), 404

        # Step 4: Build compact response
        total_points = 0
        activities_payload = {}
        for aid, coords in streams_data.items():
            if len(coords) < 2:
                continue
            total_points += len(coords)
            activities_payload[aid] = {
                'name': activity_names.get(aid, f"Activity {aid}"),
                'coords': coords
            }

        if not activities_payload:
            return jsonify({'error': 'No valid GPS tracks found.'}), 404

        payload = {
            'activities': activities_payload,
            'bounds': list(bounds),  # [min_lat, min_lng, max_lat, max_lng]
            'activity_count': len(activities_payload),
            'point_count': total_points
        }

        # Serialize to compact JSON; flask-compress handles gzip/brotli
        # automatically so we no longer compress manually here.
        json_bytes = json_module.dumps(payload, separators=(',', ':')).encode('utf-8')
        uncompressed_len = len(json_bytes)

        response = Response(json_bytes, mimetype='application/json')
        response.headers['Content-Length'] = uncompressed_len

        # Custom header for client-side download progress tracking.
        # Browsers strip Content-Length when transparently decompressing gzip,
        # so the client reads this to know the final decompressed size.
        response.headers['X-Uncompressed-Length'] = uncompressed_len

        return response

    except Exception as e:
        logger.error(f"Error generating map data: {e}")
        return jsonify({'error': str(e)}), 500


def _compute_best_average_power(watts_series: list, duration_seconds: int) -> float:
    """Compute the best (maximum) average power over a sliding window.

    This function delegates to the canonical O(N) implementation in
    :mod:`kinetiqo.db.repository` so the algorithm is implemented in a
    central place and can be unit-tested independently of the web layer.

    Args:
        watts_series (list[float]): Sequence of power samples (typically
            sampled at 1 Hz).
        duration_seconds (int): Sliding window size in seconds to compute the
            average over (e.g. 300 for 5 minutes).

    Returns:
        float: Best (maximum) average power found for the given window size,
        or 0.0 if the input series is too short.
    """
    from kinetiqo.db.repository import compute_best_average_power
    return compute_best_average_power(watts_series, duration_seconds)


# Power Skills durations matching Strava's spider chart
POWER_SKILLS_DURATIONS = [
    {"label": "5s", "seconds": 5},
    {"label": "15s", "seconds": 15},
    {"label": "30s", "seconds": 30},
    {"label": "1m", "seconds": 60},
    {"label": "2m", "seconds": 120},
    {"label": "3m", "seconds": 180},
    {"label": "5m", "seconds": 300},
    {"label": "10m", "seconds": 600},
    {"label": "15m", "seconds": 900},
    {"label": "20m", "seconds": 1200},
    {"label": "30m", "seconds": 1800},
    {"label": "45m", "seconds": 2700},
    {"label": "60m", "seconds": 3600},
]


@app.route('/powerskills', methods=['GET', 'POST'])
@login_required
def powerskills():
    """Render the Power Skills spider chart for selected activities.

    The view accepts activity IDs either via POST form field
    ``activity_ids[]`` or via GET query string ``ids`` (comma-separated).
    It computes the best average power for a set of standard durations and
    passes the results to the template.

    Returns:
        Response: The rendered ``powerskills.html`` template.
    """
    # Accept activity IDs from POST (form) or GET (query string)
    if request.method == 'POST':
        activity_ids = request.form.getlist('activity_ids[]')
    else:
        # Fallback for GET, though not recommended for large selections
        ids_param = request.args.get('ids', '')
        activity_ids = [aid.strip() for aid in ids_param.split(',') if aid.strip()]

    if not activity_ids:
        flash("No activities selected.", "warning")
        return redirect(url_for('activities'))

    try:
        repo = get_db()

        # Fetch activity metadata for names and dates
        activities_meta = repo.get_activities_by_ids(activity_ids)
        activity_map = {}
        for a in activities_meta:
            # Format date nicely
            try:
                dt = datetime.fromisoformat(a['start_date'].replace('Z', '+00:00'))
                date_str = dt.strftime(config.date_format)
            except:
                date_str = a['start_date']
            
            activity_map[str(a['id'])] = {
                'name': a.get('name', f"Activity {a['id']}"),
                'date': date_str
            }

        # Fetch watts stream data for selected activities
        watts_data = repo.get_watts_streams_for_activities(activity_ids)

        # Compute best average power for each duration across all activities
        power_data = []
        for d in POWER_SKILLS_DURATIONS:
            best_power = 0.0
            best_activity_id = None
            
            for aid, watts_list in watts_data.items():
                avg = _compute_best_average_power(watts_list, d["seconds"])
                if avg > best_power:
                    best_power = avg
                    best_activity_id = aid
            
            # Get details for the best activity
            activity_name = None
            activity_date = None
            if best_activity_id and best_activity_id in activity_map:
                activity_name = activity_map[best_activity_id]['name']
                activity_date = activity_map[best_activity_id]['date']

            power_data.append({
                "label": d["label"],
                "seconds": d["seconds"],
                "watts": int(round(best_power)),
                "activity_id": best_activity_id,
                "activity_name": activity_name,
                "activity_date": activity_date
            })

    except Exception as e:
        logger.error(f"Error computing power skills: {e}")
        flash(f"An error occurred while computing power skills: {e}", "error")
        power_data = [{"label": d["label"], "seconds": d["seconds"], "watts": 0} for d in POWER_SKILLS_DURATIONS]

    return render_template(
        'powerskills.html',
        title="Power Skills",
        power_data=power_data,
        activity_count=len(activity_ids),
        power_data_json=json_module.dumps(power_data),
    )


# Ordered list of activity-goal categories surfaced in the Settings / Progress UI.
# Extend this list to support additional sport categories.
ACTIVITY_GOALS_TYPES = {
    1: {
        "name": "Cycling",
        "icon": "🚴",
        "strava_types": [
            "Ride", "VirtualRide", "EBikeRide", "EMountainBikeRide",
            "GravelRide", "MountainBikeRide", "Velomobile", "Handcycle",
        ],
    },
    2: {
        "name": "Walking",
        "icon": "🥾",
        "strava_types": ["Walk", "Hike"],
    },
}

# Period options shared across pages with a history chart
SUPPORTED_PERIODS = ["14", "30", "60", "90", "120", "365", "all"]

# Strava sport types considered as cycling
CYCLING_SPORT_TYPES = [
    'Ride', 'VirtualRide', 'EBikeRide', 'EMountainBikeRide',
    'GravelRide', 'MountainBikeRide', 'Velomobile', 'Handcycle',
]

# FTP is estimated as 95 % of the best 20-minute average power (the standard
# "20-Minute Test" protocol).
FTP_DURATION_SECONDS = 1200  # 20 minutes
FTP_FACTOR = 0.95

# VO2max MAP (Maximal Aerobic Power) is approximated from the best 5-minute
# average power — the same sliding-window function used by Power Skills.
VO2MAX_MAP_DURATION_SECONDS = 300  # 5 minutes


def _build_activity_map(cycling_activities):
    """Build a lightweight lookup map for activities.

    Args:
        cycling_activities (list[dict]): List of raw activity rows as returned
            by the repository. Each row is expected to contain at least
            ``id`` and ``start_date`` keys and may include ``name``.

    Returns:
        dict[str, dict]: Mapping of activity id (string) to a small dict with
        keys ``name``, ``date`` (formatted for display) and ``start_date_iso``.
    """
    activity_map = {}
    for a in cycling_activities:
        try:
            dt = datetime.fromisoformat(a['start_date'].replace('Z', '+00:00'))
            date_str = dt.strftime(config.date_format)
        except Exception:
            date_str = a['start_date']
        activity_map[str(a['id'])] = {
            'name': a.get('name', f"Activity {a['id']}"),
            'date': date_str,
            'start_date_iso': a['start_date'],
        }
    return activity_map


def _get_athlete_weight() -> tuple[float, str]:
    """Resolve athlete weight from the profile table or configured fallback.

    The resolution order is:
      1. Value from ``profile`` table (if present and > 0)
      2. ``config.athlete_weight`` from environment/config

    Returns:
        tuple[float, str]: ``(weight_kg, source)`` where *source* is a
        human-friendly label such as ``"profile"`` or ``"ATHLETE_WEIGHT env var"``.
    """
    try:
        profile = get_db().get_profile()
        if profile:
            w = float(profile.get("weight", 0) or 0)
            if w > 0:
                return w, "profile"
    except Exception as e:
        logger.warning(f"Could not read athlete weight from profile table: {e}")

    # Fall back to env-var / config value
    if config.athlete_weight > 0:
        return config.athlete_weight, "ATHLETE_WEIGHT env var"

    return 0.0, ""



# --- Detect Playwright Chromium Version at Startup ---
try:
    from playwright.sync_api import sync_playwright
    
    def _find_system_chromium() -> Optional[str]:
        """
        Try to find a system-installed Chromium executable.
        
        Searches in this order:
        1. PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH environment variable
        2. System PATH locations (varies by OS)
        3. Common installation paths
        
        Returns:
            Full path to chromium executable if found, None otherwise
        """
        # Priority 1: Check environment variable
        exe_path = os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH')
        if exe_path and os.path.isfile(exe_path) and os.access(exe_path, os.X_OK):
            return exe_path
        
        # Priority 2: Try to find in system PATH
        # Common executable names across platforms
        executable_names = [
            'chromium',              # Linux (common package name)
            'chromium-browser',      # Debian/Ubuntu variant
            'chromium-headless-shell',  # Playwright headless variant
            'google-chrome',         # Google Chrome (if installed as Chrome)
            'google-chrome-stable',  # Chrome stable variant
            'chrome',                # Windows/macOS
        ]
        
        for name in executable_names:
            exe = shutil.which(name)
            if exe:
                logger.info(f"Found Chromium via PATH: {exe} (name: {name})")
                return exe
        
        # Priority 3: Check common installation paths (Windows)
        if os.name == 'nt':  # Windows
            common_paths = [
                r'C:\Program Files\Chromium\Application\chrome.exe',
                r'C:\Program Files (x86)\Chromium\Application\chrome.exe',
                r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
            ]
            for path in common_paths:
                if os.path.isfile(path):
                    logger.info(f"Found Chromium at common Windows path: {path}")
                    return path
        
        # Priority 4: Check common installation paths (Unix/Linux/macOS)
        else:
            common_paths = [
                '/usr/bin/chromium',
                '/usr/bin/chromium-browser',
                '/snap/bin/chromium',
                '/opt/chromium/chrome',
                '/Applications/Chromium.app/Contents/MacOS/Chromium',
                '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            ]
            for path in common_paths:
                if os.path.isfile(path) and os.access(path, os.X_OK):
                    logger.info(f"Found Chromium at common path: {path}")
                    return path
        
        return None
    
    def detect_chromium_version() -> Optional[str]:
        """
        Detect Chromium version using available Chromium installation.
        
        Tries the following in order:
        1. System-installed Chromium (via _find_system_chromium)
        2. Playwright-bundled Chromium (default)
        
        Returns:
            Version string if successful, None otherwise
        """
        try:
            with sync_playwright() as p:
                launch_kwargs = {'headless': True}
                
                # Try to find system Chromium first
                exe_path = _find_system_chromium()
                if exe_path:
                    launch_kwargs['executable_path'] = exe_path
                    logger.info(f"Using system Chromium: {exe_path}")
                else:
                    logger.info("Using Playwright's bundled Chromium")
                
                browser = p.chromium.launch(**launch_kwargs)
                version = browser.version
                browser.close()
                logger.info(f"Detected Chromium version: {version}")
                return version
        except Exception as e:
            logger.warning(f"Could not detect Chromium version: {e}")
            return None
    
    CHROMIUM_VERSION = detect_chromium_version()
except ImportError:
    CHROMIUM_VERSION = None

# --- Detect Python version at startup ---
PYTHON_VERSION = platform.python_version()


# ---------------------------------------------------------------------------
# In-memory TTL cache for expensive power computations
# ---------------------------------------------------------------------------
# The FTP / VO₂max pages and their chart-data API endpoints both call
# ``repo.get_best_power_per_activity()`` with the *same* parameters within
# seconds of each other (page render, then AJAX chart load).  On Firebird
# this query takes ~5 s because the pure-Python driver must transfer ~1.8 M
# raw watts rows.
#
# The cache stores the result keyed by ``(activity_ids_hash, duration,
# min_total_samples)`` with a configurable TTL (default 5 min).  This means:
#   • The chart API reuses the result the page just computed → 0 s.
#   • Navigating back to the page within the TTL is instant.
#   • After a sync adds new activities the cache expires naturally.
# ---------------------------------------------------------------------------

class _PowerCache:
    """Process-level TTL cache for best-power-per-activity results.

    This lightweight in-memory cache stores the result of
    ``repo.get_best_power_per_activity(activity_ids, duration, min_total)``
    keyed by a hash of the activity id list and the query parameters. It is
    intended to dramatically speed up round-trip scenarios where the page
    render triggers the same expensive query twice within a short interval
    (for example the initial page render followed immediately by an AJAX
    chart data request).

    Attributes:
        _DEFAULT_TTL (int): Default time-to-live for cache entries in seconds.
        _store (Dict[str, tuple]): Internal mapping key -> (timestamp, result).
        _lock (threading.Lock): Protects concurrent access to the store.
        _ttl (int): Effective TTL; can be adjusted on the instance.
    """

    _DEFAULT_TTL: int = 300          # 5 minutes

    def __init__(self) -> None:
        self._store: Dict[str, tuple] = {}   # key → (timestamp, result)
        self._lock = threading.Lock()
        self._ttl = self._DEFAULT_TTL

    # -- public API ----------------------------------------------------------

    def get_best_power(
        self,
        repo,
        activity_ids: List[str],
        duration_seconds: int,
        min_total_samples: int = 0,
    ) -> Dict[str, float]:
        """Return cached best-power-per-activity result or compute and cache it.

        The method first checks an in-process TTL cache and returns the cached
        result if it is still fresh. On a cache miss it calls
        ``repo.get_best_power_per_activity(...)`` to fetch the data and stores
        the result in the cache.

        Args:
            repo: Repository instance implementing ``get_best_power_per_activity``.
            activity_ids (List[str]): List of activity id strings to query.
            duration_seconds (int): Duration window in seconds (e.g. 1200 for 20m).
            min_total_samples (int, optional): Minimum number of samples required
                for an activity to be considered. Defaults to 0.

        Returns:
            Dict[str, float]: Mapping activity_id -> best average watts.
        """
        key = self._make_key(activity_ids, duration_seconds, min_total_samples)
        now = _time.monotonic()

        with self._lock:
            entry = self._store.get(key)
            if entry is not None:
                ts, result = entry
                if (now - ts) < self._ttl:
                    logger.debug("PowerCache HIT  (dur=%d, min=%d)", duration_seconds, min_total_samples)
                    return result

        # Cache miss — compute (outside the lock so other threads aren't blocked)
        result = repo.get_best_power_per_activity(
            activity_ids, duration_seconds, min_total_samples,
        )

        with self._lock:
            self._store[key] = (_time.monotonic(), result)
            # Lazy eviction: drop stale entries when the cache grows
            if len(self._store) > 50:
                self._evict(now)

        logger.debug("PowerCache MISS (dur=%d, min=%d, results=%d)", duration_seconds, min_total_samples, len(result))
        return result

    def invalidate(self) -> None:
        """Drop all cached entries (e.g. after a sync)."""
        with self._lock:
            self._store.clear()

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _make_key(activity_ids: List[str], duration: int, min_total: int) -> str:
        """Create a stable cache key for the given query parameters.

        Args:
            activity_ids (List[str]): Activity id strings.
            duration (int): Duration seconds.
            min_total (int): Minimum total samples parameter.

        Returns:
            str: Deterministic string key used to lookup cache entries.
        """
        ids_hash = hashlib.md5(",".join(sorted(activity_ids)).encode()).hexdigest()
        return f"{ids_hash}:{duration}:{min_total}"

    def _evict(self, now: float) -> None:
        """Remove entries older than TTL. Caller must hold ``_lock``.

        Args:
            now (float): Current monotonic timestamp used to compare entry ages.
        """
        stale = [k for k, (ts, _) in self._store.items() if (now - ts) >= self._ttl]
        for k in stale:
            del self._store[k]


_power_cache = _PowerCache()


@app.route('/ftp')
@login_required
def ftp():
    """Estimate FTP as 95% of the best 20-minute average power.

    The view computes the best 20-minute average power across cycling
    activities (optionally restricted by a period) and applies the configured
    FTP factor to produce the final estimate. Results and contextual
    information are rendered into ``ftp.html``.

    Returns:
        Response: The rendered FTP estimate page.
    """
    period = request.args.get('period', 'all')
    if period not in SUPPORTED_PERIODS:
        period = "all"

    ftp_watts = 0
    best_20min_watts = 0
    activity_name = None
    activity_date = None
    activity_id = None
    activity_count = 0
    error_message = None

    try:
        repo = get_db()

        # Push the date cut-off to SQL so the DB returns only the relevant rows.
        # The composite index idx_activities_sport_start_date (sport, start_date DESC)
        # covers both the sport filter and the date predicate efficiently.
        from datetime import timedelta, timezone as tz

        # Fetch cycling activities first (we'll compute an anchor date from the
        # returned rows and apply the period filter relative to the most
        # recent activity). This makes the period filter deterministic during
        # tests that use fixed activity timestamps.
        cycling_activities = repo.get_activity_ids_by_types(
            CYCLING_SPORT_TYPES, since_date=None, watts_only=True,
        )

        if period != 'all' and cycling_activities:
            # Compute anchor as the latest activity start_date and filter
            # activities relative to that anchor. This matches the user's
            # expectation of 'last N days' relative to recent data rather
            # than the current wall-clock time which may differ in CI.
            try:
                anchor = max(datetime.fromisoformat(a['start_date'].replace('Z', '+00:00')) for a in cycling_activities)
                since_cutoff = anchor - timedelta(days=int(period))
            except Exception:
                since_cutoff = None

            if since_cutoff is not None:
                filtered = []
                for a in cycling_activities:
                    try:
                        dt = datetime.fromisoformat(a['start_date'].replace('Z', '+00:00'))
                        if dt >= since_cutoff:
                            filtered.append(a)
                    except Exception:
                        continue
                cycling_activities = filtered

        activity_count = len(cycling_activities)

        if cycling_activities:
            activity_ids = [str(a['id']) for a in cycling_activities]
            activity_map = _build_activity_map(cycling_activities)

            # Compute best 20-min power.  The result is cached so the
            # subsequent /api/ftp_history AJAX call is instant.
            best_power = _power_cache.get_best_power(
                repo, activity_ids, FTP_DURATION_SECONDS,
            )

            for aid, avg in best_power.items():
                if avg > best_20min_watts:
                    best_20min_watts = avg
                    activity_id = aid
                    if aid in activity_map:
                        activity_name = activity_map[aid]['name']
                        activity_date = activity_map[aid]['date']

            ftp_watts = int(round(best_20min_watts * FTP_FACTOR))

    except Exception as e:
        logger.error(f"Error computing FTP: {e}")
        error_message = str(e)

    return render_template(
        'ftp.html',
        title="FTP Estimate",
        ftp_watts=ftp_watts,
        activity_name=activity_name,
        activity_date=activity_date,
        activity_id=activity_id,
        activity_count=activity_count,
        error_message=error_message,
        current_period=period,
    )


@app.route('/api/ftp_history')
@login_required
def ftp_history():
    """Return per-ride FTP estimates as JSON for charting purposes.

    Query parameters:
        period (str): Time window to include (see ``SUPPORTED_PERIODS``).

    Returns:
        flask.Response: JSON payload with ``dates``, ``ftp_values`` and
        ``activity_names`` arrays, or an error payload on failure.
    """
    try:
        period = request.args.get('period', 'all')
        if period not in SUPPORTED_PERIODS:
            period = "all"

        repo = get_db()

        # Push the date cut-off to SQL — avoids loading the full activity list
        # into Python just to discard old rows.
        from datetime import timedelta, timezone as tz

        # Fetch cycling activities first and then apply a period filter
        # relative to the latest activity. This ensures deterministic
        # behaviour for unit tests that use fixed timestamps.
        cycling_activities = repo.get_activity_ids_by_types(
            CYCLING_SPORT_TYPES, since_date=None, watts_only=True,
        )

        if not cycling_activities:
            return jsonify({'dates': [], 'ftp_values': [], 'activity_names': []})

        if period != 'all':
            try:
                anchor = max(datetime.fromisoformat(a['start_date'].replace('Z', '+00:00')) for a in cycling_activities)
                since_cutoff = anchor - timedelta(days=int(period))
            except Exception:
                since_cutoff = None

            if since_cutoff is not None:
                filtered = []
                for a in cycling_activities:
                    try:
                        dt = datetime.fromisoformat(a['start_date'].replace('Z', '+00:00'))
                        if dt >= since_cutoff:
                            filtered.append(a)
                    except Exception:
                        continue
                cycling_activities = filtered

        activity_map = _build_activity_map(cycling_activities)
        filtered_ids = list(activity_map.keys())

        if not filtered_ids:
            return jsonify({'dates': [], 'ftp_values': [], 'activity_names': []})

        # Compute per-ride FTP — typically a cache HIT from the /ftp page
        # render that fired moments ago with the same activity IDs.
        best_power = _power_cache.get_best_power(
            repo, filtered_ids, FTP_DURATION_SECONDS,
        )

        results = []
        for aid, avg in best_power.items():
            if avg > 0 and aid in activity_map:
                ftp_val = round(avg * FTP_FACTOR, 1)
                results.append({
                    'date': activity_map[aid]['start_date_iso'][:10],
                    'ftp': ftp_val,
                    'name': activity_map[aid]['name'],
                })

        # Sort chronologically
        results.sort(key=lambda r: r['date'])

        return jsonify({
            'dates': [r['date'] for r in results],
            'ftp_values': [r['ftp'] for r in results],
            'activity_names': [r['name'] for r in results],
        })

    except Exception as e:
        logger.error(f"Error computing FTP history: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/fitness')
@login_required
def fitness():
    """Render the Fitness & Freshness chart page.

    Returns:
        Response: The rendered fitness page template.
    """
    period = request.args.get('period', '14')
    if period not in SUPPORTED_PERIODS:
        period = "14"
        
    return render_template('fitness.html', title="Fitness & Freshness", current_period=period)


@app.route('/api/fitness_data')
@login_required
def fitness_data():
    """API endpoint to compute and return fitness/freshness (CTL/ATL/TSB).

    Query parameters:
        period (str): Period length in days (defaults to '14').

    Returns:
        flask.Response: JSON payload produced by
        :func:`kinetiqo.web.fitness.calculate_fitness_freshness` or an error
        payload on failure.
    """
    try:
        period = request.args.get('period', '14')
        if period not in SUPPORTED_PERIODS:
            period = "14"
        
        data = calculate_fitness_freshness(get_db(), period)
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error calculating fitness data: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/vo2max')
@login_required
def vo2max():
    """Render the VO₂max estimation page.

    The view obtains athlete weight, computes the best 5-minute power per
    activity, estimates VO₂max using the Townsend method and passes the
    results to the template for display.

    Returns:
        Response: The rendered VO₂max page.
    """
    period = request.args.get('period', 'all')
    if period not in SUPPORTED_PERIODS:
        period = "all"

    vo2max_value = 0.0
    classification = "N/A"
    best_5min_watts = 0.0
    activity_name = None
    activity_date = None
    activity_id = None
    activity_count = 0
    error_message = None
    weight, weight_source = _get_athlete_weight()
    logger.info(f"VO2max page: athlete weight={weight}, source='{weight_source}'")

    if weight <= 0:
        error_message = (
            "Athlete weight is not configured. "
            "Go to Settings → Athlete to set your weight, "
            "or set the ATHLETE_WEIGHT environment variable (in kg)."
        )
    else:
        try:
            repo = get_db()

            # Push the date cut-off to SQL — the idx_activities_sport_start_date
            # index covers the combined (sport, start_date) predicate efficiently.
            from datetime import timedelta, timezone as tz
            since_date = None if period == 'all' else datetime.now(tz.utc) - timedelta(days=int(period))

            cycling_activities = repo.get_activity_ids_by_types(
                CYCLING_SPORT_TYPES, since_date=since_date, watts_only=True,
            )
            activity_count = len(cycling_activities)

            if cycling_activities:
                activity_ids = [str(a['id']) for a in cycling_activities]
                activity_map = _build_activity_map(cycling_activities)

                # Compute best 5-min power.  The result is cached so the
                # subsequent /api/vo2max_history AJAX call is instant.
                best_power = _power_cache.get_best_power(
                    repo, activity_ids, VO2MAX_MAP_DURATION_SECONDS,
                )

                for aid, avg in best_power.items():
                    if avg > best_5min_watts:
                        best_5min_watts = avg
                        activity_id = aid
                        if aid in activity_map:
                            activity_name = activity_map[aid]['name']
                            activity_date = activity_map[aid]['date']

                vo2max_value = round(estimate_vo2max(best_5min_watts, weight), 1)
                classification = classify_vo2max(vo2max_value)


        except Exception as e:
            logger.error(f"Error computing VO2max: {e}")
            error_message = str(e)

    return render_template(
        'vo2max.html',
        title="VO₂max Estimate",
        vo2max_value=vo2max_value,
        classification=classification,
        best_5min_watts=int(round(best_5min_watts)),
        athlete_weight=weight,
        weight_source=weight_source,
        activity_name=activity_name,
        activity_date=activity_date,
        activity_id=activity_id,
        activity_count=activity_count,
        error_message=error_message,
        current_period=period,
    )


@app.route('/api/vo2max_history')
@login_required
def vo2max_history():
    """Return per-ride VO₂max estimates as a JSON time-series for the chart.

    Query parameters:
        period (str): Period filter for included rides.

    Returns:
        flask.Response: JSON payload with dates, vo2max values and activity
        names, or an error payload on failure.
    """
    try:
        period = request.args.get('period', 'all')
        if period not in SUPPORTED_PERIODS:
            period = "all"

        weight, _ = _get_athlete_weight()
        if weight <= 0:
            return jsonify({'error': 'Athlete weight not configured. Set it in Settings → Athlete or via ATHLETE_WEIGHT env var.'}), 400

        repo = get_db()

        # Push the date cut-off to SQL — avoids loading the full activity list
        # into Python just to discard old rows.
        from datetime import timedelta, timezone as tz
        since_date = None if period == 'all' else datetime.now(tz.utc) - timedelta(days=int(period))

        cycling_activities = repo.get_activity_ids_by_types(
            CYCLING_SPORT_TYPES, since_date=since_date, watts_only=True,
        )

        if not cycling_activities:
            return jsonify({'dates': [], 'vo2max_values': [], 'activity_names': []})

        activity_map = _build_activity_map(cycling_activities)
        filtered_ids = list(activity_map.keys())

        if not filtered_ids:
            return jsonify({'dates': [], 'vo2max_values': [], 'activity_names': []})

        # Compute best 5-min power per activity.
        # min_total_samples=MIN_WATTS_SAMPLES requires ≥20 min of power data
        # per activity so that short / incomplete rides are excluded.
        best_power = _power_cache.get_best_power(
            repo, filtered_ids, VO2MAX_MAP_DURATION_SECONDS,
            min_total_samples=MIN_WATTS_SAMPLES,
        )

        results = []
        for aid, best_5min in best_power.items():
            if best_5min > 0 and aid in activity_map:
                vo2 = round(estimate_vo2max(best_5min, weight), 1)
                results.append({
                    'date': activity_map[aid]['start_date_iso'][:10],
                    'vo2max': vo2,
                    'name': activity_map[aid]['name'],
                })

        results.sort(key=lambda r: r['date'])

        # Filter to qualifying rides (best per day, outlier rejection)
        qualified = filter_qualifying_rides(results)

        # Apply Firstbeat-style asymmetric EWMA smoothing
        smoothed = smooth_vo2max_history(qualified)

        return jsonify({
            'dates': [r['date'] for r in qualified],
            'vo2max_values': smoothed,
            'vo2max_raw': [r['vo2max'] for r in qualified],
            'activity_names': [r['name'] for r in qualified],
        })

    except Exception as e:
        logger.error(f"Error computing VO2max history: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/stats')
@login_required
def stats():
    """Render the Mega Stats infographic page.

    The view determines an appropriate year range and athlete name (from the
    profile) and renders the stats infographic shell. Heavy aggregation is
    performed by the JSON API endpoint ``/api/stats_data`` which the page
    uses to populate charts.

    Returns:
        Response: The rendered stats page.
    """
    # Determine the year range from the earliest activity
    min_year = datetime.now().year
    try:
        repo = get_db()
        oldest = repo.get_activities_web(limit=1, sort_by='start_date', sort_order='ASC')
        if oldest:
            from kinetiqo.web.stats import parse_activity_date
            d = parse_activity_date(oldest[0].get('start_date'))
            if d:
                min_year = d.year
    except Exception as e:
        logger.warning(f"Could not determine earliest activity year: {e}")

    current_year = datetime.now().year

    # Get athlete profile for the infographic header
    athlete_name = ''
    try:
        profile = get_db().get_profile()
        if profile:
            first = profile.get('first_name', '') or ''
            last = profile.get('last_name', '') or ''
            athlete_name = f"{first} {last}".strip()
    except Exception:
        pass

    return render_template(
        'stats.html',
        title="Mega Stats",
        min_year=min_year,
        current_year=current_year,
        athlete_name=athlete_name,
        activity_groups=ACTIVITY_GROUPS,
    )


@app.route('/api/stats_data')
@login_required
def stats_data_api():
    """Return computed Mega Stats as JSON for the infographic.

    Query parameters:
        year (int): Target year to compute stats for.
        period (str): Period selection (e.g. 'year').
        group (str): Activity group key.

    Returns:
        flask.Response: JSON object with computed statistics and metadata, or
        an error payload on failure.
    """
    try:
        year = request.args.get('year', default=datetime.now().year, type=int)
        period = request.args.get('period', 'year')
        if period not in STATS_PERIODS:
            period = 'year'
        group = request.args.get('group', 'walking')

        # Resolve activity types from the selected group
        group_info = ACTIVITY_GROUPS.get(group)
        if not group_info:
            return jsonify({'error': f'Unknown activity group: {group}'}), 400

        types = group_info['types']

        repo = get_db()

        # Fetch activities for the entire year (compute_mega_stats filters by period)
        start_date_str = f'{year}-01-01'
        end_date_str = f'{year}-12-31'

        activities = repo.get_activities_web(
            limit=100000,
            sort_by='start_date',
            sort_order='ASC',
            types=types,
            start_date=start_date_str,
            end_date=end_date_str,
        )

        stats = compute_mega_stats(activities, year, period)

        # Attach group metadata
        stats['group_key'] = group
        stats['group_name'] = group_info['name']
        stats['group_icon'] = group_info['icon']
        stats['group_noun'] = group_info['noun']

        # Attach athlete profile
        athlete_name = ''
        try:
            profile = repo.get_profile()
            if profile:
                first = profile.get('first_name', '') or ''
                last = profile.get('last_name', '') or ''
                athlete_name = f"{first} {last}".strip()
        except Exception:
            pass
        stats['athlete_name'] = athlete_name

        return jsonify(stats)

    except Exception as e:
        logger.error(f"Error computing mega stats: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/logs')
def logs():
    """Render the sync logs page showing recent sync actions.

    The view fetches recent log rows from the repository and formats them
    into a monospaced text block that the template shows.

    Returns:
        Response: The rendered logs page.
    """
    try:
        logs_data = get_db().get_logs(limit=25)

        # Format logs as text
        log_text = f"{'DATETIME':<25} {'ACTION':<12} {'ADDED':<8} {'REMOVED':<8} {'TRIGGER':<10} {'USER':<10} {'RESULT':<10}\n"
        log_text += "-" * 95 + "\n"

        for log in logs_data:
            ts = log['timestamp']
            # Try to format timestamp nicely if it's a string
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                ts_str = dt.strftime("%b %d, %Y %H:%M")
            except:
                ts_str = str(ts)[:20]

            status = "success" if log['success'] else "failed"
            action = log.get('action', 'unknown') or 'unknown'
            user = log.get('user', '-') or '-'

            log_text += f"{ts_str:<25} {action:<12} {log['added']:<8} {log['removed']:<8} {log['trigger_source']:<10} {user:<10} {status:<10}\n"

    except Exception as e:
        logger.error(f"Error fetching logs: {e}")
        log_text = f"Error fetching logs: {e}"
        if "doesn't exist" in str(e) or "does not exist" in str(e):
            log_text = "Table logs doesn't exist or is inaccessible"

    return render_template('logs.html', title="Sync Logs", log_text=log_text)


@app.route('/settings')
@login_required
def settings():
    """Render the Settings page shell.

    Returns:
        Response: The rendered settings template.
    """
    return render_template('settings.html', title="Settings")



@app.route('/license', methods=['GET'])
@login_required
def license_page():
    """Render the License & Credits page and inject diagnostic info.

    Injects detected Chromium and Python versions into the template for
    debugging and compatibility information.

    Returns:
        Response: The rendered license and credits page.
    """
    return render_template(
        'license.html',
        title="License & Credits",
        chromium_version=CHROMIUM_VERSION,
        python_version=PYTHON_VERSION
    )


@app.route('/api/settings')
@login_required
def get_settings():
    """Return runtime and database settings as JSON for the UI settings panel.

    The endpoint reads environment and repository-derived configuration and
    returns a JSON object used by the settings UI to display runtime status.

    Returns:
        flask.Response: JSON payload describing runtime and database settings.
    """
    full_sync = os.environ.get('FULL_SYNC', '')
    fast_sync = os.environ.get('FAST_SYNC', '')

    repo = get_db()
    db_type = config.database_type or 'unknown'
    db_host = None
    db_port = None

    # Prefer the repository's config if available, otherwise fall back to the global config
    db_config = getattr(repo, 'config', config)

    if db_type == 'mysql':
        db_host = config.mysql_host or getattr(db_config, 'mysql_host', 'unknown')
        db_port = config.mysql_port or getattr(db_config, 'mysql_port', 'unknown')
    elif db_type == 'postgresql':
        db_host = config.postgresql_host or getattr(db_config, 'postgresql_host', 'unknown')
        db_port = config.postgresql_port or getattr(db_config, 'postgresql_port', 'unknown')
    elif db_type == 'firebird':
        db_host = config.firebird_host or getattr(db_config, 'firebird_host', 'unknown')
        db_port = config.firebird_port or getattr(db_config, 'firebird_port', 'unknown')
    else:
        db_host = 'unknown'
        db_port = 'unknown'

    table_counts = repo.get_table_record_counts()

    return jsonify({
        'full_sync': {
            'expression': full_sync,
            'description': describe_cron(full_sync)
        },
        'fast_sync': {
            'expression': fast_sync,
            'description': describe_cron(fast_sync)
        },
        'database': {
            'type': db_type,
            'host': db_host,
            'port': db_port,
            'table_counts': table_counts
        }
    })


@app.route('/api/profile', methods=['GET'])
@login_required
def get_profile_api():
    """Return the athlete profile as JSON.

    Returns:
        flask.Response: The athlete profile as stored in the repository or a
        default empty profile if none exists. On error returns a 500 error
        payload.
    """
    try:
        profile = get_db().get_profile()
        if not profile:
            return jsonify({'athlete_id': 0, 'first_name': '', 'last_name': '', 'weight': 0})
        return jsonify(profile)
    except Exception as e:
        logger.error(f"Error fetching profile: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/profile', methods=['PUT'])
@login_required
def update_profile_api():
    """Update individual profile fields and validate inputs.

    Expects a JSON body with optional ``first_name``, ``last_name`` and
    ``weight``. ``weight`` must be a numeric value >= 0.

    Returns:
        flask.Response: The updated profile on success, or an error payload
        with a suitable HTTP status code on validation/database failure.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid request body'}), 400

        repo = get_db()
        existing = repo.get_profile()
        if not existing:
            return jsonify({'error': 'No profile exists yet — sync from Strava first.'}), 404

        first_name = data.get('first_name', existing['first_name'])
        last_name = data.get('last_name', existing['last_name'])

        # Validate weight: must be a positive number (allow 0 to clear)
        if 'weight' in data:
            try:
                weight = float(data['weight'])
            except (TypeError, ValueError):
                return jsonify({'error': 'Weight must be a number.'}), 422
            if weight < 0:
                return jsonify({'error': 'Weight must be zero or positive.'}), 422
        else:
            weight = existing['weight']

        repo.upsert_profile(existing['athlete_id'], first_name, last_name, weight)

        return jsonify({
            'athlete_id': existing['athlete_id'],
            'first_name': first_name,
            'last_name': last_name,
            'weight': weight,
        })
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Activity Goals API
# ---------------------------------------------------------------------------

def _build_goals_response(goals_rows: list) -> dict:
    """Merge DB goal rows with the activity goals catalogue for the UI.

    Args:
        goals_rows (list[dict]): Rows returned from the repository containing
            persisted goal values (may be empty).

    Returns:
        dict: Mapping string(activity_type_id) -> combined goal metadata and
        persisted values suitable for JSON serialization.
    """
    goals_by_type = {int(g['activity_type_id']): g for g in goals_rows}
    result = {}
    for type_id, meta in ACTIVITY_GOALS_TYPES.items():
        row = goals_by_type.get(type_id, {})
        result[str(type_id)] = {
            'activity_type_id': type_id,
            'name':             meta['name'],
            'icon':             meta['icon'],
            'strava_types':     meta['strava_types'],   # needed by client pill/filter logic
            'weekly_distance_goal':  row.get('weekly_distance_goal'),
            'monthly_distance_goal': row.get('monthly_distance_goal'),
            'yearly_distance_goal':  row.get('yearly_distance_goal'),
            'weekly_elevation_goal':  row.get('weekly_elevation_goal'),
            'monthly_elevation_goal': row.get('monthly_elevation_goal'),
            'yearly_elevation_goal':  row.get('yearly_elevation_goal'),
        }
    return result


@app.route('/api/goals', methods=['GET'])
@login_required
def get_goals_api():
    """Return activity goals for the authenticated athlete.

    Returns:
        flask.Response: JSON mapping of activity goal configuration for the
        logged-in athlete or an error payload on failure.
    """
    try:
        profile = get_db().get_profile()
        if not profile:
            return jsonify(_build_goals_response([]))
        return jsonify(_build_goals_response(get_db().get_goals(profile['athlete_id'])))
    except Exception as e:
        logger.error(f"Error fetching goals: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/goals', methods=['PUT'])
@login_required
def update_goals_api():
    """Upsert activity goals for the authenticated athlete.

    Expects a JSON array of goal objects describing targets per activity type.

    Returns:
        flask.Response: ``{'success': True}`` on success or an error payload on
        failure.
    """
    try:
        data = request.get_json()
        if not data or not isinstance(data, list):
            return jsonify({'error': 'Expected a JSON array of goal objects'}), 400

        profile = get_db().get_profile()
        if not profile:
            return jsonify({'error': 'No profile exists yet — sync from Strava first.'}), 404

        athlete_id = profile['athlete_id']

        def _parse(val):
            """Convert user input to a positive float or None (= unset)."""
            if val is None or val == '':
                return None
            try:
                v = float(val)
                return v if v > 0 else None
            except (TypeError, ValueError):
                return None

        repo = get_db()
        for item in data:
            type_id = int(item.get('activity_type_id', 0))
            if type_id not in ACTIVITY_GOALS_TYPES:
                continue
            repo.upsert_goal(
                athlete_id=athlete_id,
                activity_type_id=type_id,
                weekly_distance_goal=_parse(item.get('weekly_distance_goal')),
                monthly_distance_goal=_parse(item.get('monthly_distance_goal')),
                yearly_distance_goal=_parse(item.get('yearly_distance_goal')),
                weekly_elevation_goal=_parse(item.get('weekly_elevation_goal')),
                monthly_elevation_goal=_parse(item.get('monthly_elevation_goal')),
                yearly_elevation_goal=_parse(item.get('yearly_elevation_goal')),
            )

        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error updating goals: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/activities', methods=['GET', 'DELETE'])
def get_activities_api():
    """API endpoint to list activities (GET) or delete activities (DELETE).

    GET behaviour:
      - Supports pagination parameters ``page`` and ``per_page`` for server-side mode.
      - Supports filtering by ``types[]``, ``startDate`` and ``endDate``.

    DELETE behaviour:
      - Expects JSON body containing ``activity_ids`` and delegates to the
        bulk delete handler.

    Returns:
        flask.Response: JSON payload containing activity rows and aggregated
        totals in the ``data`` and ``totals`` keys respectively.
    """
    if request.method == 'DELETE':
        return delete_activities_api()

    # Check if pagination parameters are provided
    page = request.args.get('page', type=int)
    per_page = request.args.get('per_page', type=int)

    sort_column = request.args.get('sortColumn', 'start_date')
    sort_dir = request.args.get('sortDir', 'DESC')

    # Handle types filtering
    types = request.args.getlist('types[]')
    if not types:
        types = None

    # Handle date filtering
    start_date = request.args.get('startDate')
    end_date = request.args.get('endDate')

    if per_page is None:
        # Client-side processing mode: return all data
        # We use a very high limit to effectively fetch "all"
        limit = 100000
        offset = 0
    else:
        # Server-side processing mode
        if page is None: page = 1
        limit = per_page
        offset = (page - 1) * per_page

    try:
        repo = get_db()

        # Fetch activities directly from database
        activities = repo.get_activities_web(
            limit=limit,
            offset=offset,
            sort_by=sort_column,
            sort_order=sort_dir,
            types=types,
            start_date=start_date,
            end_date=end_date
        )

        # Calculate totals for the filtered dataset
        totals = repo.get_activities_totals(
            types=types,
            start_date=start_date,
            end_date=end_date
        )

        data = []
        for a in activities:
            # Format date
            try:
                # Parse ISO format (e.g., 2023-05-15T10:30:00Z)
                dt = datetime.fromisoformat(a['start_date'].replace('Z', '+00:00'))
                formatted_date = dt.strftime(config.date_format)
                # Keep original timestamp for sorting
                timestamp = int(dt.timestamp())
            except Exception as e:
                logger.warning(f"Could not parse date {a['start_date']}: {e}")
                formatted_date = a['start_date']
                timestamp = 0

            data.append({
                'id': a['id'],
                'name': a.get('name') or '',
                'type': a.get('type') or '',
                'date': {
                    'display': formatted_date,
                    'timestamp': timestamp
                },
                'distance': float(a.get('distance') or 0.0),
                'elevation': float(a.get('total_elevation_gain') or 0.0),
                'moving_time': int(a.get('moving_time') or 0),
                'average_speed': float(a.get('average_speed') or 0.0),
                'average_heartrate': int(a.get('average_heartrate') or 0),
                'average_watts': float(a.get('average_watts') or 0.0),
                'max_watts': float(a.get('max_watts') or 0.0),
                'weighted_average_watts': float(a.get('weighted_average_watts') or 0.0),
                'device_watts': int(a.get('device_watts')) if a.get('device_watts') is not None else None,
                'calories': float(a.get('calories')) if a.get('calories') is not None else None,
                'kilojoules': float(a.get('kilojoules')) if a.get('kilojoules') is not None else None,
                'achievement_count': int(a.get('achievement_count') or 0),
                'pr_count': int(a.get('pr_count') or 0),
                'suffer_score': int(a.get('suffer_score') or 0),
                'average_temp': float(a.get('average_temp')) if a.get('average_temp') is not None else None,
                'elev_high': float(a.get('elev_high')) if a.get('elev_high') is not None else None,
                'elev_low': float(a.get('elev_low')) if a.get('elev_low') is not None else None,
                'gear_id': a.get('gear_id') or None,
                'has_heartrate': bool(a.get('has_heartrate')) if a.get('has_heartrate') is not None else False,
                'workout_type': int(a.get('workout_type')) if a.get('workout_type') is not None else None
            })

        return jsonify({
            'data': data,
            'recordsTotal': len(data),  # This might be inaccurate if paginated, but for client-side it's fine.
            # For server-side, we should use count_activities.
            # But here we are mixing modes.
            # If per_page is set, we are doing server-side pagination.
            # recordsTotal should be total in DB.
            # recordsFiltered should be total matching filters.
            'totals': totals
        })
    except Exception as e:
        logger.error(f"Error fetching activities: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/activities/<activity_id>', methods=['DELETE'])
@login_required
def delete_activity_api(activity_id):
    """Delete a single activity by its id.

    Args:
        activity_id (str): Identifier of the activity to delete.

    Returns:
        flask.Response: JSON success or error payload.
    """
    try:
        repo = get_db()

        repo.delete_activity(activity_id)

        # Log the deletion
        try:
            repo.log_sync(added=0, removed=1, trigger="web", success=True, action="delete", user=current_user.id)
        except Exception as log_err:
            logger.error(f"Failed to log deletion: {log_err}")

        return jsonify({'success': True, 'message': f'Activity {activity_id} deleted successfully'})
    except Exception as e:
        logger.error(f"Error deleting activity {activity_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@login_required
def delete_activities_api():
    """Delete multiple activities provided in the request JSON.

    Expects a JSON body: {"activity_ids": ["123", "456", ...]}.

    Returns:
        flask.Response: JSON success or error payload.
    """
    activity_ids = request.json.get('activity_ids', [])
    if not activity_ids:
        return jsonify({'success': False, 'error': 'No activity IDs provided'}), 400

    try:
        repo = get_db()

        repo.delete_activities(activity_ids)

        try:
            repo.log_sync(added=0, removed=len(activity_ids), trigger="web", success=True, action="delete_bulk",
                          user=current_user.id)
        except Exception as log_err:
            logger.error(f"Failed to log bulk deletion: {log_err}")

        return jsonify({'success': True, 'message': f'{len(activity_ids)} activities deleted successfully'})
    except Exception as e:
        logger.error(f"Error deleting activities: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/fullsync')
@login_required
def fullsync():
    """Render the Full Sync UI page which triggers a full Strava sync.

    Returns:
        Response: The rendered sync UI page configured for a full sync.
    """
    return render_template('sync.html', title="Full Sync", sync_type="full", limits=get_dynamic_limit_days())


@app.route('/fastsync')
@login_required
def fastsync():
    """Render the Fast Sync UI page for incremental syncs.

    Returns:
        Response: The rendered sync UI page configured for a fast/incremental sync.
    """
    return render_template('sync.html', title="Fast Sync", sync_type="fast")


# --- HTMX / Reactive API Endpoints ---

@app.route('/sync/start/<type>')
@login_required
def start_sync_ui(type):
    """Return an HTML snippet that connects the client to the SSE sync stream.

    Args:
        type (str): Sync type string (e.g. 'full' or 'fast').

    Returns:
        str: HTML fragment used by the HTMX UI to initialise the SSE connection.
    """
    limit_days = request.args.get('limit_days', '0')
    sse_url = f"/api/sync/stream/{type}?limit_days={limit_days}"

    return f'''
    <div id="sync-log-area">
        <div sse-connect="{sse_url}">
            <div id="sync-result" sse-swap="message" class="bg-gray-50 rounded-lg p-4 min-h-[200px] border border-gray-100">
                <p class="text-sm text-gray-500 italic">Initializing sync...</p>
            </div>
        </div>
    </div>
    
    <button id="start-sync-btn" hx-swap-oob="true" disabled
            class="px-6 py-2.5 bg-gray-400 text-white rounded-lg text-sm font-medium transition shadow-sm inline-flex items-center cursor-not-allowed">
        <svg class="animate-spin -ml-1 mr-3 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        Syncing...
    </button>
    '''


@app.route('/api/sync/stream/<type>')
@login_required
def sync_stream(type):
    """Stream synchronization progress via Server-Sent Events (SSE).

    Args:
        type (str): 'full' or 'fast' indicating the sync mode.

    Returns:
        Response: A text/event-stream response streaming progress events.
    """
    is_full_sync = (type == 'full')
    user_id = current_user.id
    limit_days = request.args.get('limit_days', default=0, type=int)

    logger.info(f"Starting sync stream: type={type}, limit_days={limit_days}")

    def generate():
        sync_service = SyncService(config)
        try:
            for progress in sync_service.sync(full_sync=is_full_sync, trigger="web", user=user_id,
                                              limit_days=limit_days):
                yield progress
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            yield f"data: <strong>Error:</strong> {str(e)}\n\n"
        finally:
            sync_service.close()
            # Invalidate the power cache so that FTP / VO₂max pages
            # reflect any newly synced activities immediately.
            _power_cache.invalidate()

    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/sync/stop', methods=['POST'])
@login_required
def stop_sync():
    """Signal the long-running sync process to stop via a filesystem flag.

    Returns:
        flask.Response: Empty 204 response on success or a JSON error payload
        on failure.
    """
    try:
        with open(STOP_SIGNAL_FILE, 'w') as f:
            f.write('stop')
        logger.info("Stop signal created.")
        return '', 204
    except Exception as e:
        logger.error(f"Failed to create stop signal: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/poster/<activity_id>')
@login_required
def poster(activity_id):
    """Render the poster page for a given activity id.

    Args:
        activity_id (str): Activity identifier to render the poster for.

    Returns:
        Response: The rendered poster page or a redirect to activities if the
        activity cannot be found.
    """
    repo = get_db()
    # Fetch basic activity info from DB
    activities = repo.get_activities_by_ids([activity_id])
    activity = activities[0] if activities else None
    if not activity:
        flash("Activity not found.")
        return redirect(url_for('activities'))

    return render_template('poster.html', title="Activity Poster", activity=activity)


@app.route('/api/poster/photo/<activity_id>', methods=['GET'])
@login_required
def poster_photo_get(activity_id):
    """Serve a cached poster photo or fetch it from Strava and cache it.

    Args:
        activity_id (str): Activity identifier for which to serve the poster photo.

    Returns:
        Response: PNG bytes with mimetype 'image/png' on success, or an empty
        404 response on failure.
    """
    import pathlib
    cache_dir = pathlib.Path(os.path.dirname(os.path.abspath(__file__))) / 'posters-cache'
    cache_dir.mkdir(exist_ok=True)
    cached = cache_dir / f"{activity_id}.png"
    if cached.exists():
        return Response(cached.read_bytes(), mimetype='image/png')
    # Try to fetch from Strava
    try:
        photo_url = _fetch_strava_activity_photo(activity_id)
        if photo_url:
            img_data = _download_and_convert_to_png(photo_url)
            if img_data:
                cached.write_bytes(img_data)
                return Response(img_data, mimetype='image/png')
    except Exception as e:
        logger.error(f"Failed to fetch poster photo for {activity_id}: {e}")
    return '', 404


@app.route('/api/poster/photo/<activity_id>', methods=['POST'])
@login_required
def poster_photo_reload(activity_id):
    """Force re-download of the activity photo from Strava and cache it.

    Args:
        activity_id (str): Activity identifier whose photo should be reloaded.

    Returns:
        Response: PNG bytes on success or a JSON error payload on failure.
    """
    import pathlib
    cache_dir = pathlib.Path(os.path.dirname(os.path.abspath(__file__))) / 'posters-cache'
    cache_dir.mkdir(exist_ok=True)
    cached = cache_dir / f"{activity_id}.png"
    try:
        photo_url = _fetch_strava_activity_photo(activity_id)
        if photo_url:
            img_data = _download_and_convert_to_png(photo_url)
            if img_data:
                cached.write_bytes(img_data)
                return Response(img_data, mimetype='image/png')
        return jsonify({'error': 'No photo found on Strava'}), 404
    except Exception as e:
        logger.error(f"Failed to reload poster photo for {activity_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/poster/upload/<activity_id>', methods=['POST'])
@login_required
def poster_photo_upload(activity_id):
    """Upload and store a custom image for an activity poster.

    The endpoint accepts common image formats and converts them to PNG for
    consistent use in the poster generator.

    Args:
        activity_id (str): Activity identifier to attach the uploaded image to.

    Returns:
        Response: PNG bytes of the converted image or a JSON error payload on
        failure.
    """
    import pathlib
    from PIL import Image
    import io

    cache_dir = pathlib.Path(os.path.dirname(os.path.abspath(__file__))) / 'posters-cache'
    cache_dir.mkdir(exist_ok=True)

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    filename = file.filename.lower() if file.filename else ''
    allowed = ('.png', '.jpg', '.jpeg', '.heic', '.heif')
    if not any(filename.endswith(ext) for ext in allowed):
        return jsonify({'error': 'Invalid file type. Allowed: PNG, JPG, HEIC'}), 400

    try:
        raw = file.read()
        # Convert to PNG
        if filename.endswith(('.heic', '.heif')):
            try:
                import pillow_heif
                pillow_heif.register_heif_opener()
            except ImportError:
                return jsonify({'error': 'HEIC support not available (pillow-heif not installed)'}), 500
        img = Image.open(io.BytesIO(raw))
        img = img.convert('RGB')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        png_data = buf.getvalue()
        cached = cache_dir / f"{activity_id}.png"
        cached.write_bytes(png_data)
        return Response(png_data, mimetype='image/png')
    except Exception as e:
        logger.error(f"Failed to process uploaded image for {activity_id}: {e}")
        return jsonify({'error': f'Failed to process image: {e}'}), 500


@app.route('/api/poster/elevation/<activity_id>')
@login_required
def poster_elevation_data(activity_id):
    """Return elevation profile data (distance and altitude arrays) for an activity.

    Args:
        activity_id (str): Activity identifier whose streams to fetch.

    Returns:
        flask.Response: JSON object with ``distance`` and ``altitude`` arrays or
        empty arrays if unavailable.
    """
    from kinetiqo.strava import StravaClient
    try:
        client = StravaClient(config)
        streams = client.get_streams(int(activity_id))
        distance_data = streams.get('distance', {}).get('data', [])
        altitude_data = streams.get('altitude', {}).get('data', [])
        if not distance_data or not altitude_data:
            return jsonify({'distance': [], 'altitude': []})
        return jsonify({
            'distance': distance_data,
            'altitude': altitude_data
        })
    except Exception as e:
        logger.error(f"Failed to get elevation data for {activity_id}: {e}")
        return jsonify({'distance': [], 'altitude': []})


@app.route('/api/poster/export/<activity_id>', methods=['POST'])
@login_required
def poster_export(activity_id):
    """Export the activity poster as a pixel-perfect PNG using Playwright.

    The client POSTs the current poster settings as a JSON body.  This
    endpoint launches a headless Chromium, navigates to the poster page
    with those settings pre-loaded into localStorage (so ``renderPoster()``
    picks them up on the first paint), waits for every async element to
    finish rendering, then screenshots the ``#posterContainer`` element and
    streams the PNG bytes back to the browser as a file download.

    Chromium selection
    ------------------
    * In Docker / Production: system Chromium from ``chromium`` apt package,
      configured via ``PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium``
      in the base image.
    * In local development: Playwright's bundled Chromium installed via
      ``playwright install chromium``.
    """
    import json as _json
    import shutil

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error('playwright package is not installed')
        return jsonify({'error': 'playwright is not installed on the server. '
                                 'Run: pip install playwright && playwright install chromium'}), 500

    settings_payload = request.get_json(silent=True) or {}
    # Support both legacy payload (settings directly) and new payload
    # { settings: {...}, positions: {...} }
    settings_obj = settings_payload.get('settings', settings_payload)
    positions_payload = settings_payload.get('positions', {}) if isinstance(settings_payload, dict) else {}
    logger.info(f"Poster export request: activity={activity_id}, settings_keys={list(settings_obj.keys()) if isinstance(settings_obj, dict) else 'N/A'}, positions_provided={len(positions_payload) if isinstance(positions_payload, dict) else 0}")

    # ── Determine poster dimensions from settings ─────────────────────────
    poster_width = int(settings_obj.get('posterSize', 1280))
    # Clamp to a sensible range to prevent abuse
    poster_width = max(800, min(poster_width, 2048))

    # Parse the aspect ratio string (e.g. "4/3", "16/9", "1/1) to compute
    # the poster container's rendered height so the viewport is tall enough.
    ratio_str = settings_obj.get('ratio', '4/3')
    try:
        rw, rh = (int(x) for x in ratio_str.split('/'))
        poster_height = int(poster_width * rh / rw)
    except (ValueError, ZeroDivisionError):
        poster_height = int(poster_width * 3 / 4)  # fallback to 4:3

    # Viewport must be large enough for the poster to render at its full
    # requested size.  The page has a 256 px sidebar, a 320 px controls
    # panel, and ~48 px of padding/gaps.  We inject CSS later to force the
    # exact size, but the viewport still needs to be at least as large.
    viewport_width = poster_width + 700   # sidebar + controls + margin
    viewport_height = poster_height + 300  # nav bar + padding

    # ── Determine the URL Playwright should navigate to ──────────────────────
    # Always hit the local address so we bypass any external reverse-proxy
    # TLS termination.  The Flask dev server and gunicorn both bind on 4444;
    # fall back to the port embedded in request.host if different.
    host_header = request.host  # e.g. "localhost:4444" or "kinetiqo.example.com"
    host_domain = host_header.split(':')[0]  # strip port for cookie domain
    port = host_header.split(':')[1] if ':' in host_header else '4444'
    internal_url = f"http://127.0.0.1:{port}/poster/{activity_id}"

    # ── Replay Flask session cookies so the protected route doesn't redirect ─
    cookies_for_playwright = []
    for name, value in request.cookies.items():
        cookies_for_playwright.append({
            'name': name,
            'value': value,
            'domain': '127.0.0.1',
            'path': '/'
        })

    # ── Resolve Chromium executable ────────────────────────────────────────
    # Try to find system Chromium first, then fall back to Playwright's
    # bundled Chromium.
    chromium_exe = _find_system_chromium()
    if chromium_exe:
        logger.info(f"Poster export will use: {chromium_exe}")
    else:
        logger.info("Poster export will use Playwright's bundled Chromium")

    try:
        with sync_playwright() as p:
            launch_kwargs: dict = {
                'headless': True,
                'args': [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',  # avoids /dev/shm exhaustion in Docker
                    '--disable-gpu',
                    '--font-render-hinting=none',  # crisper font rendering
                ],
            }
            if chromium_exe:
                launch_kwargs['executable_path'] = chromium_exe

            browser = p.chromium.launch(**launch_kwargs)

            context = browser.new_context(
                # Viewport sized to fit the poster container at its full
                # configured width plus room for the controls panel.
                viewport={'width': viewport_width, 'height': viewport_height},
                # 1:1 device pixel ratio so the exported PNG matches the
                # exact pixel dimensions chosen by the user (no scaling).
                device_scale_factor=1,
                # Declare support for web fonts loaded from fonts.googleapis.com
                # (the CSP on the page already allows them).
                ignore_https_errors=True,
            )

            # Replay session cookies (Flask-Login auth)
            if cookies_for_playwright:
                context.add_cookies(cookies_for_playwright)

            # Pre-populate localStorage BEFORE the page script runs so that
            # loadSettings() picks up the user's settings and saved positions
            # on the very first renderPoster() call — no need for a second
            # reload or manual injection. Both `settings` and `positions` are
            # optional in the payload; fall back to empty objects when missing.
            context.add_init_script(f"""
                (function() {{
                    try {{
                        window.localStorage.setItem(
                            'poster_settings_v2',
                            JSON.stringify({_json.dumps(settings_payload.get('settings', {}))})
                        );
                        window.localStorage.setItem(
                            'posterPositions_{activity_id}',
                            JSON.stringify({_json.dumps(settings_payload.get('positions', {}))})
                        );
                    }} catch(e) {{}}
                }})();
            """)

            page = context.new_page()

            # ── Navigate and wait for the network to settle ───────────────────
            # 'networkidle' fires once there are no in-flight requests for
            # 500 ms — covers the photo, SVG icons, elevation API call, and
            # all CDN assets (Chart.js, Google Fonts, Tailwind).
            page.goto(internal_url, wait_until='networkidle', timeout=30_000)

            # ── Wait for web fonts to be measured ─────────────────────────────
            # document.fonts.ready resolves after the browser has loaded every
            # font used on the page and updated all text layout boxes.
            page.wait_for_function('document.fonts.ready', timeout=10_000)

            # ── Wait for inline SVG icons ──────────────────────────────────────
            # loadInlineSvgs() fetches each icon via XHR and injects the <svg>
            # element into the DOM; check that the stat-icon spans have their
            # <svg> children inlined (distance, elevation, speed, time, cadence).
            # Require >=5 so the poster export waits for the cadence crank icon too.
            page.wait_for_function(
                "document.querySelectorAll('.stat-icon svg').length >= 5",
                timeout=10_000
            )

            # ── Wait for the elevation Chart.js canvas to be painted ───────────
            # Chart.js renders synchronously once data arrives, but the canvas
            # element gets a non-zero width only after the first paint cycle.
            page.wait_for_function(
                "(function() {"
                "  var c = document.getElementById('elevationChart');"
                "  return c && c.width > 0;"
                "})()",
                timeout=15_000
            )

            # ── Wait for the background photo ─────────────────────────────────
            # The img is hidden (display:none) until onload fires and the JS
            # sets display:block.  If no photo is cached the src returns 404
            # and the element stays hidden — both states are terminal.
            page.wait_for_function(
                "(function() {"
                "  var img = document.getElementById('posterBg');"
                "  if (!img) return true;"
                "  return img.complete;"  # true for both loaded and errored
                "})()",
                timeout=15_000
            )

            # Short settle: allow Chart.js entrance animations and any
            # micro-task queues to fully drain before we screenshot.
            page.wait_for_timeout(400)

            # ── Force exact poster dimensions ─────────────────────────────────
            # The page layout (sidebar + flex + controls panel) may constrain
            # the poster container to less than the requested width.  Override
            # all layout constraints so the container renders at pixel-perfect
            # dimensions matching the user's Poster Size × Ratio settings.
            page.evaluate(f"""
                (function() {{
                    var c = document.getElementById('posterContainer');
                    c.style.width    = '{poster_width}px';
                    c.style.maxWidth = '{poster_width}px';
                    c.style.minWidth = '{poster_width}px';
                    c.style.height   = '{poster_height}px';
                    c.style.flex     = 'none';
                    c.style.position = 'relative';
                    c.style.overflow = 'hidden';
                }})();
            """)

            # Let the browser re-layout and Chart.js resize after the
            # dimension override, then wait for a
            #
            page.wait_for_timeout(500)

            # Re-trigger Chart.js resize so the elevation chart fills the
            # new container dimensions.
            page.evaluate("""
                (function() {
                    var canvas = document.getElementById('elevationChart');
                    if (canvas && canvas.__chartjs_instance) {
                        canvas.__chartjs_instance.resize();
                    }
                    // Chart.js 4.x stores the instance on Chart.instances
                    if (typeof Chart !== 'undefined' && Chart.instances) {
                        Object.values(Chart.instances).forEach(function(c) { c.resize(); });
                    }
                })();
            """)
            page.wait_for_timeout(200)

            # ── Ensure drag UI is hidden in the headless page so the resize
            # handles (blue boxes) are not visible in the exported PNG.
            page.evaluate("(function(){ var o = document.getElementById('posterOverlay'); if (o) o.classList.add('hide-drag-ui'); })();")
            page.wait_for_timeout(80)

            # ── Screenshot only the poster container ──────────────────────────
            # element.screenshot() crops to the element's bounding box,
            # ignoring the rest of the page (nav, controls, etc.).
            container = page.locator('#posterContainer')
            png_bytes = container.screenshot()

            context.close()
            browser.close()

        logger.info(
            f"Poster export OK: activity={activity_id}, "
            f"size={len(png_bytes)//1024} KB"
        )
        return Response(
            png_bytes,
            mimetype='image/png',
            headers={
                'Content-Disposition':
                    f'attachment; filename="poster_{activity_id}.png"',
                'Content-Length': str(len(png_bytes)),
            }
        )

    except Exception as e:
        logger.error(
            f"Playwright poster export failed for {activity_id}: {e}",
            exc_info=True
        )
        return jsonify({'error': str(e)}), 500


@app.route('/api/stats/export', methods=['POST'])
@login_required
def stats_export():
    """Export the Mega Stats infographic as a pixel-perfect PNG using Playwright.

    The client POSTs the current infographic settings (year, period, group, bg,
    width, height) as a JSON body.  Playwright loads /stats, injects the correct
    settings into the form controls, waits for the calendar to render, then
    repositions the #infographic-wrapper to (0,0) with no scale transform so the
    page screenshot captures exactly width×height pixels of the infographic.
    """
    import json as _json
    import os
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error('playwright package is not installed')
        return jsonify({'error': 'playwright is not installed on the server. '
                                  'Run: pip install playwright && playwright install chromium'}), 500

    payload = request.get_json(silent=True) or {}
    logger.info(f"Stats export request: {list(payload.keys()) if isinstance(payload, dict) else 'N/A'}")

    year   = str(payload.get('year',   ''))
    period = str(payload.get('period', 'year'))
    group  = str(payload.get('group',  'walking'))
    bg     = str(payload.get('bg',     '#4a4a4a'))
    width  = max(800,  min(int(payload.get('width',  1280)), 2048))
    height = max(600,  min(int(payload.get('height',  960)), 1600))
    font_size = str(payload.get('fontSize', '24'))
    stats_column_width = str(payload.get('statsColumnWidth', '20'))
    export_format = str(payload.get('format', 'png')).lower()

    host_header = request.host
    port = host_header.split(':')[1] if ':' in host_header else '4444'
    internal_url = f"http://127.0.0.1:{port}/stats"

    cookies_for_playwright = [
        {'name': n, 'value': v, 'domain': '127.0.0.1', 'path': '/'}
        for n, v in request.cookies.items()
    ]
    chromium_exe = _find_system_chromium()
    if chromium_exe:
        logger.info(f"Stats export will use: {chromium_exe}")
    else:
        logger.info("Stats export will use Playwright's bundled Chromium")

    try:
        from flask import Response
        with sync_playwright() as p:
            launch_kwargs = {
                'headless': True,
                'args': [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--font-render-hinting=none',
                ],
            }
            if chromium_exe:
                launch_kwargs['executable_path'] = chromium_exe

            browser = p.chromium.launch(**launch_kwargs)
            # Viewport must be at least as large as the infographic so that the
            # fixed-position element is fully painted by the GPU compositor.
            context = browser.new_context(
                viewport={'width': width, 'height': height},
                device_scale_factor=1,
                ignore_https_errors=True,
            )
            if cookies_for_playwright:
                context.add_cookies(cookies_for_playwright)

            page = context.new_page()
            page.goto(internal_url, wait_until='networkidle', timeout=30_000)
            page.wait_for_function('document.fonts.ready', timeout=10_000)
            page.wait_for_selector('#infographic-wrapper', state='visible', timeout=10_000)

            # ── Step 1: inject the correct settings into the form controls and
            #           trigger a re-fetch so the right year/period/group/bg is shown.
            font_size_js = _json.dumps(font_size)
            js_code = f"""
                (function() {{
                    function setVal(id, val) {{
                        var el = document.getElementById(id);
                        if (el) el.value = val;
                    }}
                    setVal('stats-year',   {_json.dumps(year)});
                    setVal('stats-period', {_json.dumps(period)});
                    setVal('stats-group',  {_json.dumps(group)});
                    setVal('stats-size',   'M');  // size only affects layout, handled below
                    var bg = document.getElementById('stats-bg');
                    if (bg) bg.value = {_json.dumps(bg)};
                    var ig = document.getElementById('infographic');
                    if (ig) ig.style.backgroundColor = {_json.dumps(bg)};
                    var statsWidthSlider = document.getElementById('stats-column-width');
                    if (statsWidthSlider) {{
                        statsWidthSlider.value = {_json.dumps(stats_column_width)};
                        statsWidthSlider.dispatchEvent(new Event('input'));
                    }}
                    // Set font size slider and update
                    var fontSlider = document.getElementById('stats-title-font-size');
                    if (fontSlider) {{
                        fontSlider.value = {_json.dumps(font_size)};
                        updateStatsFontSize({_json.dumps(font_size)});
                    }}
                    var sel = document.getElementById('stats-year');
                    if (sel) sel.dispatchEvent(new Event('change'));
                }})();
            """
            page.evaluate(js_code)

            # ── Step 2: wait for the calendar to finish rendering.
            #            #ig-body goes from display:none → display:flex when data arrives.
            page.wait_for_function(
                "document.getElementById('ig-body') && "
                "document.getElementById('ig-body').style.display !== 'none'",
                timeout=20_000,
            )
            # Give the calendar dots an extra tick to paint
            page.wait_for_timeout(600)

            # ── Step 3: reset the infographic to exact export dimensions and
            #            detach it from the flex layout so it covers the full
            #            viewport with no CSS transform applied.
            #            We move #infographic-wrapper to the body root and fix it
            #            at (0,0) so page.screenshot() captures exactly W×H px.
            page.evaluate(f"""
                (function() {{
                    try {{
                        var w = document.getElementById('infographic-wrapper');
                        if (!w) return;
                        // Move wrapper to body root to escape any parent clipping/transform
                        document.body.appendChild(w);
                        // Hide every other body child so nothing shows behind the infographic
                        Array.from(document.body.children).forEach(function(el) {{
                            if (el !== w) el.style.visibility = 'hidden';
                        }});
                        document.body.style.cssText = 'margin:0;padding:0;overflow:hidden;background:#000;';
                        // Apply exact pixel size with no transform
                        w.style.cssText = [
                            'display:block',
                            'position:fixed',
                            'top:0', 'left:0',
                            'width:{width}px',
                            'height:{height}px',
                            'transform:none',
                            'transform-origin:top left',
                            'border-radius:0',
                            'box-shadow:none',
                            'overflow:hidden',
                            'z-index:99999'
                        ].join(';') + ';';
                        // Ensure the infographic div inside fills completely
                        var ig = document.getElementById('infographic');
                        if (ig) {{
                            ig.style.width  = '100%';
                            ig.style.height = '100%';
                        }}
                    }} catch(e) {{ console.error('Stats export prep failed', e); }}
                }})();
            """)
            # Short pause so the browser repaints after the DOM changes
            page.wait_for_timeout(300)

            # ── Step 4: export as PNG or PDF
            if export_format == 'pdf':
                pdf_bytes = page.pdf(
                    width=f'{width}px',
                    height=f'{height}px',
                    print_background=True,
                    margin={'top': '0', 'right': '0', 'bottom': '0', 'left': '0'},
                    page_ranges=None,
                    display_header_footer=False
                )
                context.close()
                browser.close()
                logger.info(f"Stats PDF export OK: {width}x{height}, size={len(pdf_bytes)//1024} KB")
                return Response(
                    pdf_bytes,
                    mimetype='application/pdf',
                    headers={
                        'Content-Disposition': 'attachment; filename="kinetiqo-megastats.pdf"',
                        'Content-Length': str(len(pdf_bytes)),
                    }
                )
            else:
                png_bytes = page.screenshot(
                    clip={'x': 0, 'y': 0, 'width': width, 'height': height}
                )
                context.close()
                browser.close()
                logger.info(f"Stats PNG export OK: {width}x{height}, size={len(png_bytes)//1024} KB")
                return Response(
                    png_bytes,
                    mimetype='image/png',
                    headers={
                        'Content-Disposition': 'attachment; filename="kinetiqo-megastats.png"',
                        'Content-Length': str(len(png_bytes)),
                    }
                )
    except Exception as e:
        logger.error(f"Playwright stats export failed: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


def _fetch_strava_activity_photo(activity_id: str) -> str | None:
    """Fetch the primary photo URL for a Strava activity (highest resolution).

    Args:
        activity_id (str): Strava activity identifier.

    Returns:
        Optional[str]: URL of the best available photo size or ``None`` when
        no photo is available.
    """
    from kinetiqo.strava import StravaClient
    client = StravaClient(config)
    token = client._get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    # First try the activity photos endpoint which gives full-size URLs
    try:
        photos_url = f"https://www.strava.com/api/v3/activities/{activity_id}/photos?size=5000"
        r = requests.get(photos_url, headers=headers, timeout=15)
        r.raise_for_status()
        photos_list = r.json()
        if photos_list and len(photos_list) > 0:
            # Get the first (primary) photo
            photo = photos_list[0]
            urls = photo.get('urls', {})
            # size=5000 returns the largest available in the '5000' key
            return urls.get('5000') or urls.get('2048') or urls.get('1800') or urls.get('600') or None
    except Exception:
        pass

    # Fallback: activity detail endpoint
    url = f"https://www.strava.com/api/v3/activities/{activity_id}"
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()
    photos = data.get('photos', {}).get('primary', {})
    if photos:
        urls = photos.get('urls', {})
        return urls.get('600') or urls.get('100') or None
    return None


def _download_and_convert_to_png(url: str) -> bytes | None:
    """Download an image URL and convert to PNG bytes."""
    from PIL import Image
    import io
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content))
    img = img.convert('RGB')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


@app.route('/latest-version')
async def latest_version():
    """Return an asynchronous message indicating whether a newer release exists.

    This endpoint delegates to :mod:`kinetiqo.version_check` and is safe to
    call from the web UI; the check is cached and non-blocking.
    """
    from kinetiqo.version_check import check_for_new_version
    message = await check_for_new_version()
    return jsonify({'message': message})


# Context processor to inject version into all templates
@app.context_processor
def inject_version():
    version = "dev"
    try:
        # Look for version.txt in the package root or project root
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # Check current dir (kinetiqo/web/) -> ../../version.txt
        version_path = os.path.join(os.path.dirname(os.path.dirname(base_dir)), "version.txt")

        if os.path.exists(version_path):
            with open(version_path, "r") as vf:
                version = vf.read().strip()
    except:
        pass
    return dict(app_version=version)


def run_app():
    """Run the Flask development server (for local testing only)."""
    app.run(debug=True, port=4444, host='0.0.0.0')


if __name__ == '__main__':
    run_app()
