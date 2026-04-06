from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required

# Create a Blueprint
bp = Blueprint('progress', __name__)

@bp.route('/progress')
@login_required
def progress_page():
    # Render the template initially. Data will be fetched via AJAX.
    return render_template('progress.html', title="Progress")


def _aggregate_activity(activity, day_map):
    """Add a single activity's distance and elevation to *day_map*.

    Returns without side-effects when the activity lacks a usable date or
    its date falls outside the map.
    """
    start_date_val = activity.get('start_date')
    if not start_date_val:
        return

    d_str = str(start_date_val)[:10]
    if d_str not in day_map:
        return

    dist_m = float(activity.get('distance') or 0)
    elev_m = float(activity.get('total_elevation_gain') or 0)
    day_map[d_str]['dist'] += dist_m / 1000.0
    day_map[d_str]['elev'] += elev_m


@bp.route('/api/progress_data')
@login_required
def progress_data_api():
    from kinetiqo.web.app import get_db
    
    repo = get_db()
    today = datetime.now()

    # Get filters from request
    types = request.args.getlist('types[]')
    # Sentinel value sent by the UI when nothing is selected — return empty data immediately.
    if types == ['_NO_MATCH_']:
        return jsonify({
            'week':  {'dates': [], 'distance': [], 'elevation': []},
            'month': {'dates': [], 'distance': [], 'elevation': []},
            'year':  {'dates': [], 'distance': [], 'elevation': []}
        })
    # No types param at all → treat as "all types" (should not normally happen)
    if not types:
        types = None

    def get_range_data(start_dt, end_dt):
        """
        Fetch activities for range and aggregate by day.
        Returns dict with parallel lists: { 'dates': [], 'distance': [], 'elevation': [] }
        Distance in km, Elevation in meters.
        """
        # 1. Initialize map for all dates in range with 0.0
        day_map = {}
        curr = start_dt
        while curr <= end_dt:
            day_str = curr.strftime('%Y-%m-%d')
            day_map[day_str] = {'dist': 0.0, 'elev': 0.0}
            curr += timedelta(days=1)

        s_str = start_dt.strftime('%Y-%m-%d')
        e_str = end_dt.strftime('%Y-%m-%d')
        
        try:
            acts = repo.get_activities_web(
                limit=100000, 
                start_date=s_str, 
                end_date=e_str,
                types=types
            )
        except Exception:
            acts = []

        # Aggregate each activity into the day map
        for a in acts:
            try:
                _aggregate_activity(a, day_map)
            except Exception:
                pass

        sorted_keys = sorted(day_map.keys())
        
        return {
            'dates': sorted_keys,
            'distance': [day_map[k]['dist'] for k in sorted_keys],
            'elevation': [day_map[k]['elev'] for k in sorted_keys]
        }

    # --- Ranges ---
    
    # This Week (Monday - Today)
    start_week = today - timedelta(days=today.weekday())
    data_week = get_range_data(start_week, today)

    # This Month (1st - Today)
    start_month = today.replace(day=1)
    data_month = get_range_data(start_month, today)

    # This Year (Jan 1 - Today)
    start_year = today.replace(month=1, day=1)
    data_year = get_range_data(start_year, today)

    return jsonify({
        'week': data_week,
        'month': data_month,
        'year': data_year
    })
