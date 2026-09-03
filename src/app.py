import os

from datetime import datetime

from auth import User, users
from flask import Flask, request, redirect, url_for, flash
from flask import render_template
# Import CSRF protection if available. Production must have Flask-WTF so the
# app never runs with CSRF protection silently disabled.
try:
    from flask_wtf import CSRFProtect
except Exception:
    try:
        from flask_wtf.csrf import CSRFProtect
    except Exception as exc:
        if os.environ.get("FLASK_ENV") == "production" or os.environ.get("KINETIQO_PRODUCTION") == "1":
            raise RuntimeError("Flask-WTF is required in production to enable CSRF protection.") from exc
        logging.getLogger(__name__).warning(
            "flask-wtf not installed; CSRF protection is disabled in this dev/test run."
        )
        CSRFProtect = None

from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from mock_data import get_mock_activities


# --- Flask App & Security Configuration ---
app = Flask(__name__)
csrf = CSRFProtect() if CSRFProtect is not None else None
if csrf is not None:
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
    """Load a user by ID for Flask-Login.

    Args:
        user_id (str): The identifier of the user (as stored in session).

    Returns:
        User | None: A `User` object if the user exists, otherwise `None`.
    """
    if user_id in users:
        return User(user_id)
    return None


# --- Routes ---

@app.route('/', methods=['GET'])
def index():
    """Root route: redirect authenticated users to activities, others to login.

    Returns:
        Response: A Flask redirect response to the appropriate page.
    """
    if current_user.is_authenticated:
        return redirect(url_for('activities'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle login form display and submission.

    GET: render the login form.
    POST: validate credentials and log the user in (demo plaintext check).

    Returns:
        Response: Rendered template or redirect on successful login.
    """
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
    """Log out the current user and redirect to the login page.

    Returns:
        Response: A Flask redirect response to the login page.
    """
    logout_user()
    return redirect(url_for('login'))


@app.route('/activities', methods=['GET'])
@login_required
def activities():
    """Render the activities page using mocked Strava data.

    Returns:
        Response: Rendered activities template populated with activity data.
    """
    # Load mocked Strava data
    data = get_mock_activities()
    return render_template('activities.html', title="Activities", activities=data)


@app.route('/fullsync', methods=['GET'])
@login_required
def fullsync():
    """Render the full-sync page.

    Returns:
        Response: Rendered sync template for a full synchronization.
    """
    return render_template('sync.html', title="Full Sync", sync_type="full")


@app.route('/fastsync', methods=['GET'])
@login_required
def fastsync():
    """Render the fast-sync page.

    Returns:
        Response: Rendered sync template for a fast synchronization.
    """
    return render_template('sync.html', title="Fast Sync", sync_type="fast")


# --- Main Entrypoint ---
if __name__ == '__main__':
    # For development only! Use Gunicorn or another WSGI server in production.
    app.run(debug=True, port=4444, host='0.0.0.0')
