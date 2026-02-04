from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from auth import User, users
from mock_data import get_mock_activities
import time
import random

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_demo_only'

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
    # Load mocked Strava data
    data = get_mock_activities()
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


if __name__ == '__main__':
    app.run(debug=True, port=4444, host='0.0.0.0')
