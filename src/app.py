import random
import time
import os

from datetime import datetime

from auth import User, users
from flask import Flask, request, redirect, url_for, flash
from flask import render_template
# Import CSRFProtect with robust fallbacks so the app can run in dev without
# Flask-WTF installed. In production, ensure Flask-WTF is installed and
# enabled to provide CSRF protection.
try:
    from flask_wtf import CSRFProtect
except Exception:
    try:
        from flask_wtf.csrf import CSRFProtect
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "flask-wtf not installed; CSRF protection disabled. "
            "Install Flask-WTF in production!"
        )

        class CSRFProtect:  # no-op fallback for development/test environments
            def init_app(self):
                return None

from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from mock_data import get_mock_activities


# --- Flask App & Security Configuration ---
app = Flask(__name__)
csrf = CSRFProtect()
csrf.init_app(app) # Compliant

# Enforce SECRET_KEY in production
secret = os.environ.get("SECRET_KEY")
if not secret:
    import logging
    logging.getLogger(__name__).warning(
        "SECRET_KEY environment variable not set - using a generated key. "
        "This is fine for development but MUST be set in production."
    )
    # Use a randomly generated key (bytes); Flask accepts bytes or str.
    secret = os.urandom(24)
app.secret_key = secret

# Secure session cookie settings (adjust as needed for your deployment)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # Consider "Strict" for extra protection
# Only set SESSION_COOKIE_SECURE if running behind HTTPS
if os.environ.get("FLASK_ENV") == "production" or os.environ.get("KINETIQO_PRODUCTION") == "1":
    app.config["SESSION_COOKIE_SECURE"] = True
    if not os.environ.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY must be set in production!")

# Warn if running in debug mode in production
if app.debug or os.environ.get("FLASK_ENV") == "development":
    import logging
    logging.getLogger(__name__).warning(
        "Flask is running in debug mode. Do NOT use debug mode in production!"
    )

# --- Password Security Note ---
# WARNING: This mock app uses plaintext passwords for demonstration only.
# In production, always store password hashes (e.g., with bcrypt or argon2).
# Never store or compare plaintext passwords.

# --- Production Deployment Note ---
# For production, use a WSGI server like Gunicorn behind HTTPS (e.g., via nginx or Caddy).
# Do NOT use Flask's built-in server in production.


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

@app.route('/', methods=['GET'])
def index():
    if current_user.is_authenticated:
        return redirect(url_for('activities'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')


        # WARNING: Plaintext password check for mock/demo only!
        # Replace with password hash check in production.
        if username in users and users[username]['password'] == password:
            user = User(username)
            login_user(user)
            return redirect(url_for('activities'))
        else:
            flash('Invalid username or password')

    return render_template('login.html', current_year=datetime.now().year)


@app.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/activities', methods=['GET'])
@login_required
def activities():
    # Load mocked Strava data
    data = get_mock_activities()
    return render_template('activities.html', title="Activities", activities=data)


@app.route('/fullsync', methods=['GET'])
@login_required
def fullsync():
    return render_template('sync.html', title="Full Sync", sync_type="full")


@app.route('/fastsync', methods=['GET'])
@login_required
def fastsync():
    return render_template('sync.html', title="Fast Sync", sync_type="fast")


# --- HTMX / Reactive API Endpoints ---

@app.route('/api/sync/<type>', methods=['POST'])
@login_required
def run_sync(type):
    """
    This endpoint is called by HTMX. It simulates a backend process
    and returns an HTML snippet to update the UI without a page reload.
    """
    # Simulate processing delay
    time.sleep(1.5)

    if type == 'full':
        count = random.randint(1000, 2000)
        msg = f"Full synchronization completed. {count} historical items processed."
        color_class = "green"
    else:
        count = random.randint(0, 15)
        msg = f"Fast sync completed. {count} new activities found."
        color_class = "blue"

    # Return HTML snippet for HTMX injection
    return f'''
        <div class="p-4 bg-{color_class}-50 border border-{color_class}-200 rounded-md text-{color_class}-800 animate-fade-in">
            <div class="flex items-center">
                <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                <span class="font-medium">{msg}</span>
            </div>
            <div class="mt-2 text-xs text-{color_class}-600 opacity-75">
                Database connection: Active | Strava API: OK
            </div>
        </div>
    '''



# --- Main Entrypoint ---
if __name__ == '__main__':
    # For development only! Use Gunicorn or another WSGI server in production.
    app.run(debug=True, port=4444, host='0.0.0.0')
