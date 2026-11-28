# Fitness & Freshness (CTL / ATL / TSB)

The **Fitness & Freshness** module models training load, physical fatigue, and race readiness using the classic **Banister Impulse-Response Model** powered by high-performance **pandas** time-series calculations.

---

## 1. Overview & Capabilities

- 📈 **Banister Impulse-Response Engine**: Tracks your fitness trajectory across seasons using daily training impulse derived from Strava Suffer Scores (Relative Effort) or heart rate/power metrics.
- 🏋️ **Chronic Training Load (CTL / Fitness)**: 42-day exponentially weighted moving average reflecting long-term aerobic conditioning and training volume.
- ⚡ **Acute Training Load (ATL / Fatigue)**: 7-day exponentially weighted moving average reflecting short-term fatigue and recent hard efforts.
- 🎯 **Training Stress Balance (TSB / Form)**: The mathematical difference ($\text{CTL} - \text{ATL}$) determining whether your body is fatigued, primed for racing, or detraining.
- 📊 **Interactive Chart.js Visualization**: Zoomable, pannable multi-axis timeline with color-coded form zones, daily workout markers, and moving averages.
- 🤖 **AI Coach Integration**: AI assistants can query your active CTL, ATL, and TSB via MCP to diagnose overreaching, evaluate taper quality, or recommend rest days.

---

## 2. Mathematical Modeling & Formulas

Training load accumulation follows the standard exponential impulse-response equations:

$$\text{CTL}_t = \text{CTL}_{t-1} + (\text{Load}_t - \text{CTL}_{t-1}) \times \left(1 - e^{-1 / \tau_{\text{CTL}}}\right)$$

$$\text{ATL}_t = \text{ATL}_{t-1} + (\text{Load}_t - \text{ATL}_{t-1}) \times \left(1 - e^{-1 / \tau_{\text{ATL}}}\right)$$

$$\text{TSB}_t = \text{CTL}_t - \text{ATL}_t$$

### Default Time Constants:
- **$\tau_{\text{CTL}} = 42$ days**: Represents the rate of adaptation and aerobic fitness decay.
- **$\tau_{\text{ATL}} = 7$ days**: Represents rapid fatigue accumulation and recovery kinetics.

---

## 3. Training Form Zones & Interpretation

| Form (TSB) Range | Zone State | Interpretation & Coaching Recommendations |
|---|---|---|
| **$> +25$** | **Transition / Detraining** | Extended rest or illness. High freshness, but aerobic fitness (CTL) is actively decaying. |
| **$+5$ to $+25$** | **Peak Race Form** | **Optimal performance window**. Freshness is maximized while preserving high base fitness. Ideal for goal events. |
| **$-10$ to $+5$** | **Maintenance / Neutral** | Steady-state training. Balanced fatigue and fitness; good for regular group rides or tempo workouts. |
| **$-30$ to $-10$** | **Productive Overreaching** | **Optimal training stimulation**. High stimulus builds long-term fitness. Sustainable for 2–3 week blocks before deloading. |
| **$< -30$** | **Excessive Fatigue** | **High injury & illness risk**. Severe physical strain; prioritize sleep, active recovery, or full rest days immediately. |

---

## 4. Web Routes & API Endpoints

| URL Route / Endpoint | Method | Purpose |
|---|---|---|
| `/fitness` | GET | Render the interactive Chart.js Fitness & Freshness dashboard |
| `/api/fitness_data` | GET | Fetch daily CTL, ATL, TSB time series with start/end date filter parameters |

---

## 5. MCP & AI Integration

The Model Context Protocol server exposes:
- `kinetiqo_get_fitness_and_freshness`: Returns current and historical CTL, ATL, and TSB values, training impulse sums, and physiological form interpretations.

---

## 6. Visual Artifacts

- Fitness & Freshness Timeline: `docs/chart-dark.webp`
- Fitness Overview Widget: `docs/fitness.webp`

