import hashlib
import logging
import os
import mimetypes
import threading
import time as _time
from datetime import datetime
from typing import Dict, List

import httpx

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
    """Set proper headers for static content and caching."""
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
    """Returns a per-request database repository, creating one if needed.

    The repository is stored in Flask's ``g`` object so it is scoped to the
    current request and automatically closed by :func:`close_db` at the end
    of the application context.

    :return: A database repository instance for the current request.
    """
    if 'db_repo' not in g:
        g.db_repo = create_repository(config)
    return g.db_repo


@app.teardown_appcontext
def close_db(exception=None):
    """Closes the per-request database connection after each request.

    :param exception: Any exception that caused the context to be torn down.
    """
    repo = g.pop('db_repo', None)
    if repo is not None:
        try:
            repo.close()
        except Exception as e:
            logger.debug(f"Error closing per-request database connection: {e}", exc_info=True)


def set_config(new_config: Config):
    """Sets the configuration used by the application.

    :param new_config: The configuration instance to use.
    """
    global config
    config = new_config


# --- Login Configuration ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    if user_id in users:
        return User(user_id)
    return None


def describe_cron(expression):
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
    if current_user.is_authenticated:
        return redirect(url_for('activities'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
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
    logout_user()
    return redirect(url_for('login'))


@app.route('/activities')
@login_required
def activities():
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

    Fetches tiles from tile.openstreetmap.org with a proper ``Referer`` and
    ``User-Agent`` header, satisfying OSM's tile usage policy:
    https://operations.osmfoundation.org/policies/tiles/

    Because the browser requests tiles from our own origin the
    ``Referer`` the browser sends is irrelevant — our server controls what
    OSM actually sees, completely eliminating the 403r "Access blocked" tile.
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
    """Render the map page shell. Data is loaded asynchronously via /api/map/data."""
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
    """Compute the best (max) average power over a sliding window for a single activity.

    Delegates to the canonical O(N) implementation in ``kinetiqo.db.repository``.

    :param watts_series: List of float watts values (1 sample/sec).
    :param duration_seconds: Window size in seconds.
    :return: Best average power as float, or 0.0 if insufficient data.
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
    """Render the Power Skills spider chart for selected activities."""
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
    """Build a lightweight lookup {activity_id_str → {name, date, start_date_iso}} from raw activity rows."""
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
    """Resolve athlete weight from the ``profile`` database table.

    Returns a ``(weight_kg, source)`` tuple.  *source* is a human-readable
    label such as ``"profile"`` or ``"ATHLETE_WEIGHT env var"``.
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
    """Process-level TTL cache for ``get_best_power_per_activity`` results."""

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
        """Return cached result or compute, cache, and return."""
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
        ids_hash = hashlib.md5(",".join(sorted(activity_ids)).encode()).hexdigest()
        return f"{ids_hash}:{duration}:{min_total}"

    def _evict(self, now: float) -> None:
        """Remove entries older than TTL.  Caller must hold ``_lock``."""
        stale = [k for k, (ts, _) in self._store.items() if (now - ts) >= self._ttl]
        for k in stale:
            del self._store[k]


_power_cache = _PowerCache()


@app.route('/ftp')
@login_required
def ftp():
    """Estimate FTP as 95 % of the best 20-minute average power across all cycling activities."""
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
        since_date = None if period == 'all' else datetime.now(tz.utc) - timedelta(days=int(period))

        # Get cycling activity IDs (filtered at DB level when period != 'all').
        # watts_only=True restricts to activities that actually have power-meter
        # data, which can be a 5-10× reduction vs. all cycling activities and
        # dramatically cuts the number of stream rows loaded next.
        cycling_activities = repo.get_activity_ids_by_types(
            CYCLING_SPORT_TYPES, since_date=since_date, watts_only=True,
        )
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
    """Return per-ride FTP estimates as a JSON time-series for the chart."""
    try:
        period = request.args.get('period', 'all')
        if period not in SUPPORTED_PERIODS:
            period = "all"

        repo = get_db()

        # Push the date cut-off to SQL — avoids loading the full activity list
        # into Python just to discard old rows.
        from datetime import timedelta, timezone as tz
        since_date = None if period == 'all' else datetime.now(tz.utc) - timedelta(days=int(period))

        cycling_activities = repo.get_activity_ids_by_types(
            CYCLING_SPORT_TYPES, since_date=since_date, watts_only=True,
        )

        if not cycling_activities:
            return jsonify({'dates': [], 'ftp_values': [], 'activity_names': []})

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
    """Render the Fitness & Freshness chart page."""
    period = request.args.get('period', '14')
    if period not in SUPPORTED_PERIODS:
        period = "14"
        
    return render_template('fitness.html', title="Fitness & Freshness", current_period=period)


@app.route('/api/fitness_data')
@login_required
def fitness_data():
    """API endpoint to get fitness, fatigue, and form data."""
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
    """Render the VO2max estimation page."""
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
    """Return per-ride VO2max estimates as a JSON time-series for the chart."""
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


@app.route('/logs')
def logs():
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
    return render_template('settings.html', title="Settings")


@app.route('/license', methods=['GET'])
@login_required
def license_page():
    return render_template('license.html', title="License & Credits")


@app.route('/api/settings')
@login_required
def get_settings():
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
    """Return the athlete profile as JSON."""
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
    """Update individual profile fields.  Validates that *weight* is a positive number."""
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
    """Merge DB rows with the ACTIVITY_GOALS_TYPES catalogue into a JSON-ready dict.

    Each entry includes ``strava_types`` so the client can drive Select2
    filtering without maintaining a duplicate mapping.
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
    """Return activity goals for the authenticated athlete."""
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
    """Upsert activity goals. Request body: list of goal objects."""
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
    return render_template('sync.html', title="Full Sync", sync_type="full", limits=get_dynamic_limit_days())


@app.route('/fastsync')
@login_required
def fastsync():
    return render_template('sync.html', title="Fast Sync", sync_type="fast")


# --- HTMX / Reactive API Endpoints ---

@app.route('/sync/start/<type>')
@login_required
def start_sync_ui(type):
    """
    Returns the HTML snippet to connect to the SSE stream.
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
    """
    This endpoint uses Server-Sent Events (SSE) to stream sync progress.
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
    """Endpoint to signal the sync process to stop."""
    try:
        with open(STOP_SIGNAL_FILE, 'w') as f:
            f.write('stop')
        logger.info("Stop signal created.")
        return '', 204
    except Exception as e:
        logger.error(f"Failed to create stop signal: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/latest-version')
async def latest_version():
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
    app.run(debug=True, port=4444, host='0.0.0.0')


if __name__ == '__main__':
    run_app()
