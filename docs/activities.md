# Searchable Activity Grid & Telemetry Explorer

The **Activity Grid** is the central command center of Kinetiqo, powered by **DataTables 2.x** with client-side responsive processing, drag-and-drop column reordering, persistent column visibility controls, bulk data operations, and multi-format data export.

---

## 1. Overview & Capabilities

- 📊 **High-Performance DataTables 2.x**: Client-side rendering of thousands of synchronized workouts with sub-millisecond filtering, multi-column sorting, and responsive pagination.
- 🔄 **Drag-and-Drop Column Reordering (ColReorder)**: Reorganize column sequence according to your athletic preference; positions persist across browser sessions in `localStorage`.
- 👁️ **Persistent Column Visibility Picker**: Toggle visible metrics across 25+ telemetry columns, including power, cadence, heart rate, suffer score, weather conditions, and segment trophies.
- ⚡ **Bulk Operations & Selection Engine**: Interactive checkbox selection supporting single rows, entire current page selection, or full-dataset bulk selection for batch deletion with audit logging.
- 💾 **Export Multi-Format**: Direct client-side export to CSV, Excel (XLSX via JSZip), and PNG screenshot summaries without server round-trips.
- 🌦️ **Integrated Weather Telemetry**: Inline display of temperature range (`min-max°C`), weather condition icon, wind direction vector with cardinal tooltip, wind gusts, and precipitation amount.
- 🏆 **Segment Trophies & Achievements**: Visual badges indicating King of the Mountains (KOM), Personal Records (PRs), and top-10 segment leaderboard ribbons.

---

## 2. Telemetry Columns Reference

| Column | Data Field | Sort Type | Description |
|---|---|---|---|
| **Selection** | `activity_id` | Boolean | Checkbox for individual and bulk row selection |
| **Date** | `start_date_local` | Timestamp | Formatted activity start date and time |
| **Name** | `name` | String | Activity title with direct links to [Activity Detail Infographic](activity-detail.md) (`/activity/<id>`), Strava, and Poster Generator |
| **Type** | `type` | String | Discipline badge (Ride, Run, Swim, Walk, Hike, VirtualRide, AlpineSki, etc.) |
| **Distance** | `distance` | Numeric (m) | Total distance formatted in km (or miles) with 1 decimal precision |
| **Moving Time** | `moving_time` | Seconds | Net active time formatted as `HH:MM:SS` |
| **Elapsed Time** | `elapsed_time` | Seconds | Total time including pauses |
| **Elevation Gain** | `total_elevation_gain` | Meters | Cumulative vertical ascent |
| **Avg Speed** | `average_speed` | m/s | Average velocity formatted in km/h or pace (min/km) |
| **Max Speed** | `max_speed` | m/s | Peak velocity recorded by sensor/GPS |
| **Avg Power** | `average_watts` | Watts | Arithmetic average power output |
| **Max Power** | `max_watts` | Watts | Peak instantaneous wattage recorded |
| **Weighted Power (NP)** | `weighted_average_watts` | Watts | Normalized Power (NP) calculated across 30-second rolling averages |
| **Avg HR** | `average_heartrate` | bpm | Average heart rate |
| **Max HR** | `max_heartrate` | bpm | Peak heart rate recorded |
| **Avg Cadence** | `average_cadence` | rpm | Crank or stride cadence |
| **Suffer Score** | `suffer_score` | Numeric | Strava Relative Effort / Suffer Score |
| **Kilojoules** | `kilojoules` | kJ | Total mechanical work performed |
| **Calories** | `calories` | kcal | Estimated metabolic energy expenditure |
| **Weather** | `weather` | Numeric (`temp_avg`) | Monochromatic thermometer icon, temperature range, condition icon, wind vector, gusts, and rain |
| **Trophies** | `trophies` | Numeric | Breakdown of KOMs, PRs, and 1st–10th place segment effort achievements |
| **Gear** | `gear_id` | String | Bike or shoe identifier assigned to workout |

---

## 3. Web Routes & API Endpoints

| URL Route / Endpoint | Method | Purpose |
|---|---|---|
| `/activities` | GET | Render the full interactive DataTables 2.x activity grid |
| `/activity/<id>` | GET | Comprehensive single-workout analytical showcase (see [docs/activity-detail.md](activity-detail.md)) |
| `/api/activities` | GET | JSON data provider supporting sorting, filtering by sport type, date ranges, and pagination |
| `/api/activities` | DELETE | Bulk delete activities by ID list with CSRF protection |
| `/api/activities/<id>` | DELETE | Delete single activity by ID |

---

## 4. UI Controls & State Persistence

All UI configurations are automatically persisted in browser `localStorage` using version-safe schema keys:
- `activities_table_state`: Saves visible columns, column sequence order, and page size (10, 25, 50, 100 rows).
- Quick Filter shortcuts: Filter instantly by discipline (Cycling, Running, Swimming, Winter Sports).
- Date Range Picker: Filter by custom date intervals, Current Year, Last Year, or All Time.

---

## 5. Visual Artifacts

- Activity Grid Dark Mode: `docs/grid-dark.webp`
- Column Visibility & Reorder: `docs/activities-colums-dark.webp`
- Activity Sync Progress: `docs/activities-sync.webp`

