from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from kinetiqo.config import Config
from kinetiqo.db.factory import create_repository
from kinetiqo.sync import SyncService
from kinetiqo.web.auth import User, users
import time
import random
import logging
import threading
from datetime import datetime
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kinetiqo.web")

app = Flask(__name__, template_folder='./templates')
app.secret_key = 'super_secret_key_for_demo_only'

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

@app.route('/logs')
@login_required
def logs():
    try:
        # Ensure db_repo is initialized
        repo = db_repo
        if repo is None:
            repo = create_repository(config)
            
        # Commit to ensure fresh data
        if hasattr(repo, 'conn') and repo.conn:
            repo.conn.commit()
            
        logs_data = repo.get_logs(limit=50)
        
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
    
    return jsonify({
        'full_sync': {
            'expression': full_sync,
            'description': describe_cron(full_sync)
        },
        'fast_sync': {
            'expression': fast_sync,
            'description': describe_cron(fast_sync)
        }
    })

@app.route('/api/activities', methods=['GET'])
def get_activities_api():
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
            repo.conn.commit()

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
                'name': a['name'],
                'type': a['type'],
                'date': {
                    'display': formatted_date,
                    'timestamp': timestamp
                },
                'distance': float(a['distance']),
                'elevation': float(a['total_elevation_gain']),
                'moving_time': a['moving_time'],
                'average_speed': float(a['average_speed']) if a.get('average_speed') is not None else 0.0,
                'average_heartrate': int(a['average_heartrate']) if a.get('average_heartrate') is not None else 0
            })

        return jsonify({
            'data': data,
            'recordsTotal': len(data), # This might be inaccurate if paginated, but for client-side it's fine. 
                                       # For server-side, we should use count_activities.
                                       # But here we are mixing modes. 
                                       # If per_page is set, we are doing server-side pagination.
                                       # recordsTotal should be total in DB.
                                       # recordsFiltered should be total matching filters.
            'recordsFiltered': repo.count_activities(types=types), # This is approximate as it doesn't count date filter
            # Actually, count_activities needs to support date filter too if we want accurate pagination.
            # But for now, let's just return the totals.
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


@app.route('/fullsync')
@login_required
def fullsync():
    return render_template('sync.html', title="Full Sync", sync_type="full")


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
    return f'''
    <div id="sync-log-area">
        <div sse-connect="/api/sync/stream/{type}">
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
    
    def generate():
        sync_service = SyncService(config)
        try:
            for progress in sync_service.sync(full_sync=is_full_sync, trigger="web", user=user_id):
                yield progress
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            yield f"data: <strong>Error:</strong> {str(e)}\n\n"
        finally:
            sync_service.close()

    return Response(generate(), mimetype='text/event-stream')


def run_app():
    app.run(debug=True, port=4444, host='0.0.0.0')

if __name__ == '__main__':
    run_app()
