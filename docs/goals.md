# Activity Goals & Target Tracking

Kinetiqo enables athletes to define, track, and pacing-forecast distance and elevation training targets across **weekly**, **monthly**, and **yearly** cycles, segmented by sport discipline.

---

## 1. Overview & Capabilities

- 🎯 **Multi-Interval Tracking**: Configure independent targets for:
  - **Weekly Goals**: Short-term consistency (Monday through Sunday).
  - **Monthly Goals**: Mid-term progression (1st through last day of calendar month).
  - **Yearly Goals**: Long-term annual season targets (January 1 through December 31).
- 🚴 **Sport-Specific Segmentation**: Set dedicated goals for:
  - **Cycling**: Road, Gravel, Mountain Bike, Virtual Ride, and E-Bike.
  - **Running**: Road Run, Trail Run, and Track.
  - **Walking & Hiking**: Outdoor walks, treks, and mountaineering.
  - **Swimming**: Pool and open water distance.
  - **Winter Sports**: Cross-country, alpine, and backcountry skiing.
- ⛰️ **Dual Metric Tracking**: Track both **Distance** (km / miles) and cumulative **Elevation Gain** (meters / feet).
- 📊 **Dynamic Pacing & Progress Bars**: Visual completion bars indicating:
  - Percentage achieved to date.
  - Remaining distance and vertical meters required to reach target.
  - Expected pacing vs. elapsed calendar time (ahead or behind schedule).

---

## 2. Web Routes & API Endpoints

| URL Route / Endpoint | Method | Purpose |
|---|---|---|
| `/profile` | GET | View active goals, completion progress bars, and pacing widgets |
| `/api/goals` | GET | Fetch active goal targets and progress statistics |
| `/api/goals` | PUT / POST | Update distance and elevation goals per sport type and timeframe |

---

## 3. Database Schema

Goals are persisted in the `goals` table across all three database backends (PostgreSQL, MySQL, Firebird):
- `goal_id`: Primary key.
- `athlete_id`: Foreign key referencing the athlete.
- `sport_type`: Discipline identifier (`Ride`, `Run`, `Hike`, `Swim`, etc.).
- `period_type`: Target timeframe (`weekly`, `monthly`, `yearly`).
- `target_distance`: Distance in meters.
- `target_elevation`: Elevation in meters.

---

## 4. MCP & AI Integration

The Model Context Protocol server exposes:
- `kinetiqo_get_goals`: Returns active weekly, monthly, and yearly goals, progress percentages, and current pacing status to AI assistants for training advice and motivational check-ins.

---

## 5. Visual Artifacts

- Athlete Profile & Target Goals: `docs/settings.webp`

