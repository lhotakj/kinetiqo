# FTP & VO₂max Estimation

Kinetiqo automatically computes, logs, and visualizes your **Functional Threshold Power (FTP)** history and **Maximal Oxygen Uptake ($\text{VO}_2\max$)** trends across seasons using evidence-based exercise physiology formulas.

---

## 1. Functional Threshold Power (FTP)

### 1.1 Estimation Methodology
FTP represents the highest sustained power output an athlete can maintain in a quasi-steady state for approximately one hour.

Kinetiqo continuously analyzes every synchronized workout containing power sensor streams:
1. Computes the highest rolling 20-minute average power ($\text{MMP}_{20\text{min}}$).
2. Calculates estimated FTP using the standard Coggan formula:
   $$\text{Estimated FTP} = 0.95 \times \text{MMP}_{20\text{min}}$$
3. Plots the per-ride estimation history to demonstrate aerobic power improvements, seasonal peaks, and recovery plateaus.

### 1.2 Athlete Profile & Validation
- Athletes can set their active FTP in **Settings / Profile** to drive power zones and normalized power percentages (`% FTP`).
- Enforces strict server-side validation bounds ($0 < \text{FTP} \le 1000\text{ W}$) with theme-aware input highlighting.

---

## 2. VO₂max Estimation & Classification

$\text{VO}_2\max$ measures the maximum volume of oxygen (in $\text{ml/kg/min}$) your body can utilize during exhaustive exercise.

### 2.1 Estimation Models
Kinetiqo calculates $\text{VO}_2\max$ using two complementary physiological models:

1. **Townsend / Storer-Davis 5-Minute MAP Model**:
   Derived from your best 5-minute Maximal Aerobic Power ($\text{MAP}_{5\text{min}}$):
   $$\text{VO}_2\max = \frac{10.8 \times \text{MAP}_{5\text{min}} (\text{W})}{\text{Weight} (\text{kg})} + 7.0$$

2. **Coggan FTP Ratio Model**:
   Derived assuming threshold power equals approximately 80% of Maximal Aerobic Power:
   $$\text{VO}_2\max = \frac{10.8 \times (\text{FTP} / 0.80)}{\text{Weight} (\text{kg})} + 7.0$$

### 2.2 Aerobic Fitness Classification Bands

| Classification Band | Men ($\text{ml/kg/min}$) | Women ($\text{ml/kg/min}$) | Cycling Category / Level |
|---|---|---|---|
| **World-Class** | $> 75.0$ | $> 65.0$ | Professional / UCI WorldTour |
| **Superior** | $65.0 - 75.0$ | $55.0 - 65.0$ | Cat 1 / Elite Amateur |
| **Excellent** | $55.0 - 65.0$ | $45.0 - 55.0$ | Cat 2–3 / Strong Competitive |
| **Good** | $45.0 - 55.0$ | $35.0 - 45.0$ | Cat 4–5 / Enthusiast |
| **Fair / Moderate** | $35.0 - 45.0$ | $28.0 - 35.0$ | Recreational / Active |
| **Untrained** | $< 35.0$ | $< 28.0$ | Sedentary Baseline |

---

## 3. Web Routes & API Endpoints

| URL Route / Endpoint | Method | Purpose |
|---|---|---|
| `/ftp` | GET | Render the interactive FTP historical trend dashboard |
| `/vo2max` | GET | Render the interactive $\text{VO}_2\max$ trend chart with classification bands |
| `/api/ftp_history` | GET | JSON time-series of per-ride 20-min best efforts and 95% FTP estimates |
| `/api/vo2max_history` | GET | JSON time-series of 5-min MAP and FTP-based $\text{VO}_2\max$ calculations |
| `/api/profile` | GET / POST | View and update athlete FTP and body weight |

---

## 4. MCP & AI Integration

The Model Context Protocol server exposes:
- `kinetiqo_get_ftp_history`: Retrieves historical 20-minute power milestones and threshold progression.
- `kinetiqo_get_vo2max_trend`: Fetches time-series VO₂max estimates and current physiological fitness classification.

---

## 5. Visual Artifacts

- FTP Estimation History: `docs/ftp.webp`
- VO₂max Trends & Classification: `docs/vo2.webp`

