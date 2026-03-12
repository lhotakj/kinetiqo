import pandas as pd
import random

def generate_ai_insight(fitness, fatigue, form, trend_fitness):
    """
    Generates a human-readable insight based on the current fitness metrics.
    """
    insight = []
    
    # Form Analysis (TSB)
    if form > 25:
        insight.append("You are in a deep recovery or transition phase. While you are very fresh, your fitness is likely decaying rapidly.")
    elif 5 <= form <= 25:
        insight.append("You are in a peak performance zone! Your freshness is high, making this an ideal time for a race or a breakthrough effort.")
    elif -10 <= form < 5:
        insight.append("You are in a neutral training zone. This is a sustainable state for maintenance or light training blocks.")
    elif -30 <= form < -10:
        insight.append("You are in the optimal training zone. The training load is high enough to stimulate adaptation but manageable.")
    else: # form < -30
        insight.append("⚠️ Warning: High Risk of Overtraining. Your fatigue is significantly outweighing your fitness. Consider a rest day or light recovery ride immediately.")

    # Fitness Trend Analysis (CTL)
    if trend_fitness > 0.5:
        insight.append("Your fitness is on a strong upward trajectory. Keep up the consistent work!")
    elif trend_fitness < -0.5:
        insight.append("Your chronic training load is decreasing. If this isn't a planned taper, consider increasing volume or intensity.")
    else:
        insight.append("Your fitness level has been stable recently.")

    # Fatigue Context (ATL)
    if fatigue > fitness * 1.3:
        insight.append(f"Recent training has been very intense (Fatigue {fatigue:.1f} vs Fitness {fitness:.1f}). Be mindful of burnout.")

    # Add some "AI" flavor
    prefixes = [
        "Based on your recent activity patterns,",
        "Analyzing your training load,",
        "According to the impulse-response model,",
        "My analysis suggests that"
    ]
    
    return f"{random.choice(prefixes)} { ' '.join(insight) }"

def calculate_fitness_freshness(repo, period="14"):
    """
    Calculates Fitness (CTL), Fatigue (ATL), and Form (TSB) from activities.

    :param repo: The database repository instance.
    :param period: The number of days to look back, or "all".
    :return: A dictionary containing the data for the chart.
    """
    if period == "all":
        days = None  # Sentinel for "all time"
    else:
        days = int(period)

    activities = repo.get_activities_with_suffer_score(days=days)

    if not activities:
        return {
            "dates": [],
            "fitness": [],
            "fatigue": [],
            "form": [],
            "insight": "No data available to analyze for the selected period."
        }

    df = pd.DataFrame(activities)
    df['date'] = pd.to_datetime(df['start_date'])
    df = df.set_index('date')

    # Resample to have one entry per day, summing suffer_score
    daily_stress = df[['suffer_score']].resample('D').sum().fillna(0)

    # Calculate Fitness (CTL) - 42-day EWMA
    daily_stress['fitness'] = daily_stress['suffer_score'].ewm(span=42, adjust=False).mean()

    # Calculate Fatigue (ATL) - 7-day EWMA
    daily_stress['fatigue'] = daily_stress['suffer_score'].ewm(span=7, adjust=False).mean()

    # Calculate Form (TSB)
    daily_stress['form'] = daily_stress['fitness'] - daily_stress['fatigue']

    # Filter to dates with activity to avoid long flat lines at the beginning
    first_activity_date = daily_stress[daily_stress['suffer_score'] > 0].index.min()
    if pd.notna(first_activity_date):
        daily_stress = daily_stress[daily_stress.index >= first_activity_date]

    # Calculate insight based on the last available data point
    if not daily_stress.empty:
        last_row = daily_stress.iloc[-1]
        
        # Calculate trend (change in fitness over last 7 days)
        if len(daily_stress) >= 7:
            trend_fitness = last_row['fitness'] - daily_stress.iloc[-7]['fitness']
        else:
            trend_fitness = 0
            
        insight = generate_ai_insight(last_row['fitness'], last_row['fatigue'], last_row['form'], trend_fitness)
    else:
        insight = "Insufficient data for analysis."

    # Format for JSON response
    chart_data = {
        "dates": daily_stress.index.strftime('%Y-%m-%d').tolist(),
        "fitness": daily_stress['fitness'].round(1).tolist(),
        "fatigue": daily_stress['fatigue'].round(1).tolist(),
        "form": daily_stress['form'].round(1).tolist(),
        "insight": insight
    }

    return chart_data
