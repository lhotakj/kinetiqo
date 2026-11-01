# Power Skills Analysis & Mean Maximal Power (MMP)

The **Power Skills** module evaluates your physiological capabilities and energy systems across standard benchmark durations from 5 seconds to 1 hour, visualized via an interactive **Radar / Spider Chart** and comprehensive **Mean Maximal Power (MMP)** curves.

---

## 1. Overview & Capabilities

- 🕸️ **Interactive Radar / Spider Chart**: Visualizes your power profile across 7 standard physiological durations (5s, 30s, 1m, 5m, 10m, 20m, 1h).
- ⚡ **Energy System Mapping**: Identifies your athletic archetype (Sprint Specialist, Puncheur, Time Trialist, Climber, All-Rounder).
- ⚖️ **Absolute Watts & Relative Watts per Kilogram (W/kg)**: Instant toggle between absolute mechanical wattage and weight-adjusted power based on your athlete profile weight.
- 🔄 **Per-Activity vs. Season Bests**: Compare the power profile of any individual workout directly against your all-time career or current season power curve.
- 📈 **Continuous Mean Maximal Power (MMP)**: Calculates the highest average power sustained for every single duration from 1 second to the total elapsed time of the ride.
- ⚡ **Normalized Power (NP) Engine**: Calculates physiological cost using Coggan's 4th-power weighting of 30-second rolling power averages.

---

## 2. Physiological Durations & Energy Systems

| Duration | Energy System | Athletic Role / Physiological Significance |
|---|---|---|
| **5 seconds** | **Neuromuscular (ATP-PCr)** | Peak sprint power, out-of-saddle acceleration, closing a gap |
| **30 seconds** | **Anaerobic Capacity** | Short steep hill sprint, launching a decisive breakaway |
| **1 minute** | **Anaerobic / Aerobic Crossover** | Sustained high-intensity surge, bridging to a lead group |
| **5 minutes** | **Maximal Aerobic Power ($\text{VO}_2\max$)** | Hard climb effort, attacking on a climb, critical aerobic capacity |
| **10 minutes** | **Lactate Tolerance / Supra-Threshold** | Long climb tempo, sustained time-trial pacing |
| **20 minutes** | **Threshold Power (FTP Benchmark)** | Used to calculate estimated Functional Threshold Power ($0.95 \times \text{P}_{20}$) |
| **1 hour** | **Aerobic Endurance / Critical Power** | True steady-state hour threshold power and fatigue resistance |

---

## 3. Mathematical Calculations

### 3.1 Mean Maximal Power (MMP)
For an activity with power stream $P = [p_1, p_2, \dots, p_N]$ recorded at 1-second intervals, the peak power for duration $d$ is:

$$\text{MMP}(d) = \max_{k=1}^{N - d + 1} \left( \frac{1}{d} \sum_{i=k}^{k + d - 1} p_i \right)$$

### 3.2 Normalized Power (NP)
Normalized Power accounts for the non-linear physiological stress of stochastic efforts:

1. Compute 30-second rolling average power:
   $$\bar{P}_{30, i} = \frac{1}{30} \sum_{j=i-29}^{i} p_j$$
2. Raise each value to the 4th power, take the mean, and extract the 4th root:
   $$\text{NP} = \left( \frac{1}{M} \sum_{i=30}^{N} (\bar{P}_{30, i})^4 \right)^{1/4}$$

---

## 4. Web Routes & API Endpoints

| URL Route / Endpoint | Method | Purpose |
|---|---|---|
| `/powerskills` | GET | Render the Power Skills radar chart dashboard |
| `/api/activities` | GET | Provides best efforts and power averages for individual workouts |

---

## 5. MCP & AI Integration

The Model Context Protocol server exposes:
- `kinetiqo_get_power_curve`: Returns high-resolution MMP curve points across benchmark intervals.
- `kinetiqo_get_weekly_power_profile`: Aggregates peak sprint, VO₂max, and threshold wattage across weekly training blocks.
- `kinetiqo_analyze_workout_efforts`: Detects sustained hard efforts, surge counts (≥1000W), and normalized power metrics.

---

## 6. Visual Artifacts

- Power Skills Spider Chart: `docs/power-dark.webp`

