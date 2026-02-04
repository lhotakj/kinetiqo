import random
from datetime import datetime, timedelta


def get_mock_activities():
    activities = []
    types = ['Run', 'Ride', 'Hike', 'Swim', 'Alpine Ski']
    names = ['Morning Loop', 'Evening Commute', 'Weekend Long Haul', 'Interval Session', 'Recovery', 'Lunch Break']

    base_date = datetime.now()

    for i in range(1, 51):
        act_type = random.choice(types)

        # Logic to make data look realistic
        if act_type == 'Ride':
            distance = round(random.uniform(20.0, 80.0), 2)
            elevation = random.randint(100, 1500)
        elif act_type == 'Run':
            distance = round(random.uniform(5.0, 21.0), 2)
            elevation = random.randint(10, 300)
        elif act_type == 'Swim':
            distance = round(random.uniform(1.0, 4.0), 2)
            elevation = 0
        else:
            distance = round(random.uniform(3.0, 10.0), 2)
            elevation = random.randint(100, 500)

        activities.append({
            "id": 1000 + i,
            "name": f"{random.choice(names)}",
            "type": act_type,
            "date": (base_date - timedelta(days=i)).strftime('%Y-%m-%d'),
            "distance": distance,
            "elevation": elevation
        })

    return activities
