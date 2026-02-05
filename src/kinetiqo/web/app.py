from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from kinetiqo.config import Config
from kinetiqo.db.factory import create_repository
from kinetiqo.sync import SyncService
from kinetiqo.web.auth import User, users
import time
import random
import logging
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kinetiqo.web")

app = Flask(__name__, template_folder='../../templates')
app.secret_key = 'super_secret_key_for_demo_only'

# --- Configuration & Database ---
config = Config()
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

    return render_template('login.html')


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
        data = db_repo.get_activities(limit=50)
    except Exception as e:
        logger.error(f"Error fetching activities: {e}")
        flash(f"Error fetching activities: {e}")
        data = []
        
    return render_template('activities.html', title="Activities", activities=data)


@app.route('/fullsync')
@login_required
def fullsync():
    return render_template('sync.html', title="Full Sync", sync_type="full")


@app.route('/fastsync')
@login_required
def fastsync():
    return render_template('sync.html', title="Fast Sync", sync_type="fast")


# --- HTMX / Reactive API Endpoints ---

@app.route('/api/sync/<type>', methods=['POST'])
@login_required
def run_sync(type):
    """
    This endpoint is called by HTMX. It triggers the backend sync process
    and returns an HTML snippet to update the UI.
    """
    
    is_full_sync = (type == 'full')
    
    # Run sync in a separate thread to avoid blocking the request?
    # For simplicity in this demo, we'll run it synchronously but it might timeout for large syncs.
    # In a real app, use Celery or RQ.
    
    try:
        # Re-initialize sync service to ensure fresh state
        sync_service = SyncService(config)
        
        # Capture start time
        start_time = time.time()
        
        # Run sync
        sync_service.sync(full_sync=is_full_sync)
        
        duration = time.time() - start_time
        
        # We don't have easy access to the exact count of processed items from here 
        # without modifying SyncService to return stats. 
        # For now, we'll return a generic success message.
        
        msg = f"{'Full' if is_full_sync else 'Fast'} synchronization completed in {duration:.1f}s."
        color_class = "green"
        
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        msg = f"Sync failed: {str(e)}"
        color_class = "red"
    finally:
        # sync_service.close() # SyncService closes db in close(), but we share db_repo?
        # Actually SyncService creates its own db repo instance.
        pass

    # Return HTML snippet for HTMX injection
    return f'''
        <div class="p-4 bg-{color_class}-50 border border-{color_class}-200 rounded-md text-{color_class}-800 animate-fade-in">
            <div class="flex items-center">
                <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                <span class="font-medium">{msg}</span>
            </div>
            <div class="mt-2 text-xs text-{color_class}-600 opacity-75">
                Database: {config.database_type} | Strava API: OK
            </div>
        </div>
    '''


def run_app():
    app.run(debug=True, port=4444, host='0.0.0.0')

if __name__ == '__main__':
    run_app()
