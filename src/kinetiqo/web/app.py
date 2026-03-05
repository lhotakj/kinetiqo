import atexit
import logging
import os
import mimetypes
from datetime import datetime

import folium
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from kinetiqo.config import Config
from kinetiqo.db.factory import create_repository
from kinetiqo.sync import SyncService
from kinetiqo.web.auth import User, users

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kinetiqo.web")

app = Flask(__name__, template_folder='./templates',
            static_folder='./static', static_url_path='/static')
app.secret_key = 'super_secret_key_for_demo_only'

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
    # Only apply to static files
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
    else:
        # Prevent browser caching of API responses and dynamic pages.
        # This ensures that data freshly synced (e.g. new activities) is
        # visible immediately without requiring a hard refresh.
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

    return response


# --- Configuration & Database ---
# Default config, will be overwritten by set_config
config = Config()
db_repo = None


def set_config(new_config: Config):
    """Sets the configuration and initializes the repository."""
    global config, db_repo
    config = new_config
    # Initialize the repository immediately with the provided config
    db_repo = create_repository(config)


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
        # Ensure db_repo is initialized if not already (fallback for direct run)
        repo = db_repo
        if repo is None:
            repo = create_repository(config)

        data = repo.get_activities(limit=50)
    except Exception as e:
        logger.error(f"Error fetching activities: {e}")
        flash(f"Error fetching activities: {e}")
        data = []

    return render_template('activities.html', title="Activities", activities=data)


# Available base map tile providers
TILE_PROVIDERS = {
    'openstreetmap': {
        'name': 'OpenStreetMap',
        'tiles': 'OpenStreetMap',
        'attr': '© OpenStreetMap contributors'
    },
    'cartodbpositron': {
        'name': 'CartoDB Positron',
        'tiles': 'CartoDB positron',
        'attr': '© OpenStreetMap contributors, © CartoDB'
    },
    'cartodbdark': {
        'name': 'CartoDB Dark',
        'tiles': 'CartoDB dark_matter',
        'attr': '© OpenStreetMap contributors, © CartoDB'
    },
    'esriworldimagery': {
        'name': 'Esri World Imagery',
        'tiles': 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        'attr': '© Esri, Maxar, Earthstar Geographics'
    }
}


@app.route('/map', methods=['GET', 'POST'])
@login_required
def map_view():
    """Render the map page shell - data is loaded asynchronously."""
    if request.method == 'GET':
        return redirect(url_for('activities'))

    # Get filter parameters to pass to template for the async request
    activity_ids = request.form.getlist('activity_ids[]')

    # Map customization parameters
    color = request.args.get('color', '#FC4C02')  # Strava orange default
    width = request.args.get('width', '2')
    opacity = request.args.get('opacity', '100')
    basemap = request.args.get('basemap', 'openstreetmap')

    return render_template('map.html',
                           title="Activity Map",
                           activity_ids=activity_ids,
                           current_color=color,
                           current_width=width,
                           current_opacity=opacity,
                           current_basemap=basemap,
                           tile_providers=TILE_PROVIDERS)


@app.route('/api/map/generate')
@login_required
def generate_map_api():
    """API endpoint to generate map HTML with SSE progress updates."""

    # Get filter parameters
    activity_ids = request.args.getlist('activity_ids[]')

    # Map customization parameters
    color = request.args.get('color', '#FC4C02')
    width = request.args.get('width', '2')
    try:
        width = int(width)
        if width < 1:
            width = 1
        if width > 20:
            width = 20
    except:
        width = 2

    opacity = request.args.get('opacity', '100')
    try:
        opacity = int(opacity)
        if opacity < 0:
            opacity = 0
        if opacity > 100:
            opacity = 100
    except:
        opacity = 100
    opacity_float = opacity / 100.0

    basemap = request.args.get('basemap', 'openstreetmap')
    if basemap not in TILE_PROVIDERS:
        basemap = 'openstreetmap'

    def generate():
        import json
        import base64

        try:
            repo = db_repo
            if repo is None:
                repo = create_repository(config)

            # Step 1: Get activities
            yield f"data: {json.dumps({'type': 'progress', 'step': 'activities', 'message': 'Fetching activities...'})}\n\n"

            activities_data = repo.get_activities_by_ids(activity_ids)

            if not activities_data:
                yield f"data: {json.dumps({'type': 'error', 'error': 'No activities found matching the filter criteria.'})}\n\n"
                return

            total_activities = len(activities_data)
            yield f"data: {json.dumps({'type': 'progress', 'step': 'activities', 'message': f'Found {total_activities} activities', 'total': total_activities})}\n\n"

            # Step 2: Get stream data
            yield f"data: {json.dumps({'type': 'progress', 'step': 'streams', 'message': 'Loading GPS data...', 'total': total_activities, 'current': 0})}\n\n"

            streams_data = repo.get_streams_for_activities(activity_ids)

            if not streams_data:
                yield f"data: {json.dumps({'type': 'error', 'error': 'No GPS data found for the selected activities.'})}\n\n"
                return

            activities_with_gps = len(streams_data)
            yield f"data: {json.dumps({'type': 'progress', 'step': 'streams', 'message': f'Loaded GPS data for {activities_with_gps} activities', 'total': total_activities, 'current': activities_with_gps})}\n\n"

            # Create activity name map
            activity_names = {str(a['id']): a['name'] for a in activities_data}

            # Calculate bounds
            yield f"data: {json.dumps({'type': 'progress', 'step': 'processing', 'message': 'Processing coordinates...'})}\n\n"

            all_lats = []
            all_lngs = []
            for aid, points in streams_data.items():
                for p in points:
                    all_lats.append(p['lat'])
                    all_lngs.append(p['lng'])

            if not all_lats or not all_lngs:
                yield f"data: {json.dumps({'type': 'error', 'error': 'No valid GPS coordinates found.'})}\n\n"
                return

            total_points = len(all_lats)
            yield f"data: {json.dumps({'type': 'progress', 'step': 'processing', 'message': f'Processing {total_points:,} GPS points...'})}\n\n"

            # Step 3: Create map
            yield f"data: {json.dumps({'type': 'progress', 'step': 'rendering', 'message': 'Creating map...', 'total': activities_with_gps, 'current': 0})}\n\n"

            center_lat = sum(all_lats) / len(all_lats)
            center_lng = sum(all_lngs) / len(all_lngs)

            tile_config = TILE_PROVIDERS[basemap]

            if tile_config['tiles'].startswith('http'):
                m = folium.Map(location=[center_lat, center_lng], zoom_start=10, tiles=None)
                folium.TileLayer(
                    tiles=tile_config['tiles'],
                    attr=tile_config['attr'],
                    name=tile_config['name']
                ).add_to(m)
            else:
                m = folium.Map(location=[center_lat, center_lng], zoom_start=10, tiles=tile_config['tiles'])

            # Add polylines with progress updates
            activity_count = 0
            for aid, points in streams_data.items():
                if len(points) < 2:
                    continue

                coords = [[p['lat'], p['lng']] for p in points]
                name = activity_names.get(aid, f'Activity {aid}')

                folium.PolyLine(
                    coords,
                    color=color,
                    weight=width,
                    opacity=opacity_float,
                    tooltip=name
                ).add_to(m)
                activity_count += 1

                # Send progress every 10 activities or at the end
                if activity_count % 10 == 0 or activity_count == activities_with_gps:
                    yield f"data: {json.dumps({'type': 'progress', 'step': 'rendering', 'message': f'Rendering activity {activity_count} of {activities_with_gps}...', 'total': activities_with_gps, 'current': activity_count})}\n\n"

            # Fit bounds
            m.fit_bounds([[min(all_lats), min(all_lngs)], [max(all_lats), max(all_lngs)]])

            # Generate HTML
            yield f"data: {json.dumps({'type': 'progress', 'step': 'finalizing', 'message': 'Finalizing map...'})}\n\n"

            map_html = m._repr_html_()
            map_html_b64 = base64.b64encode(map_html.encode("utf-8")).decode("ascii")

            # Send final result
            yield f"data: {json.dumps({'type': 'complete', 'html_b64': map_html_b64, 'activity_count': activity_count, 'point_count': total_points})}\n\n"

        except Exception as e:
            logger.error(f"Error generating map: {e}")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return Response(generate(), mimetype='text/event-stream')


@app.route('/logs')
def logs():
    try:
        # Ensure db_repo is initialized
        repo = db_repo
        if repo is None:
            repo = create_repository(config)

        # Commit to ensure fresh data
        if hasattr(repo, 'conn') and repo.conn:
            try:
                repo.conn.commit()
            except Exception as e:
                logger.warning(f"Failed to commit transaction in logs: {e}")

        logs_data = repo.get_logs(limit=25)

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


@app.route('/api/settings')
@login_required
def get_settings():
    full_sync = os.environ.get('FULL_SYNC', '')
    fast_sync = os.environ.get('FAST_SYNC', '')

    global db_repo
    if db_repo is None:
        db_repo = create_repository(config)

    db_type = config.database_type or 'unknown'
    db_host = None
    db_port = None

    # Prefer the repository's config if available, otherwise fall back to the global config
    db_config = getattr(db_repo, 'config', config)

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

    table_counts = db_repo.get_table_record_counts() if db_repo else {}

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
        # Ensure db_repo is initialized
        repo = db_repo
        if repo is None:
            repo = create_repository(config)

        # Commit the transaction to ensure we see the latest data
        if hasattr(repo, 'conn') and repo.conn:
            try:
                repo.conn.commit()
            except Exception as e:
                logger.warning(f"Failed to commit transaction in get_activities_api: {e}")

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
        # Ensure db_repo is initialized
        repo = db_repo
        if repo is None:
            repo = create_repository(config)

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
        repo = db_repo
        if repo is None:
            repo = create_repository(config)

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

    return Response(generate(), mimetype='text/event-stream')


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


def close_db_connection():
    """Closes the database connection if it's open."""
    global db_repo
    if db_repo:
        try:
            db_repo.close()
            logger.info("Database connection closed.")
        except Exception:
            pass


atexit.register(close_db_connection)


def run_app():
    app.run(debug=True, port=4444, host='0.0.0.0')


if __name__ == '__main__':
    run_app()
