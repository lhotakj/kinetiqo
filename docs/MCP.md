# Model Context Protocol (MCP) User Guide

**Kinetiqo MCP** connects your self-hosted fitness data warehouse directly to modern AI assistants—such as **Google Antigravity IDE**, **Claude Desktop**, **Cursor**, **Windsurf**, and **OpenClaw**—via the open [Model Context Protocol (MCP)](https://modelcontextprotocol.io/).

With Kinetiqo MCP, your AI assistant transforms into an evidence-based personal endurance coach, telemetry analyst, and creative director with direct access to your activities, sensor streams, power curves, and milestones.

---

## 1. Why Use Kinetiqo with MCP?

- 🔒 **Privacy-First & Local**: Your raw sensor streams, GPS coordinates, and heart rates remain completely on your machine. AI assistants query your local PostgreSQL/MySQL/Firebird database through standard STDIO JSON-RPC frames.
- ⚡ **Zero Cloud Leak**: No third-party servers or fitness aggregators sit between your AI and your data.
- 🛡️ **Read-Only by Default**: The MCP server is strictly read-only out of the box. Mutating actions (triggering syncs, editing athlete FTP, publishing Strava descriptions) are completely hidden from the AI tool catalog unless explicitly enabled by you.
- 📊 **35 Evidence-Based Tools**: Comprehensive access to historical workouts, continuous Mean Maximal Power (MMP), Normalized Power (NP), aerobic decoupling, suffer-score fitness (CTL/ATL/TSB), weekly power profiles, recovery turnaround, and Playwright visual poster exports.

---

## 2. Quick Testing & Verification

Before connecting an AI desktop client, you can quickly verify that the MCP server is working in under 5 seconds.

### Fast Smoke Test
Run this command from your Kinetiqo directory to confirm tool registration and schema integrity:

**Windows (PowerShell):**
```powershell
& .\.venv_win\Scripts\python.exe -c "import sys; sys.path.insert(0, 'src'); import asyncio; from kinetiqo.config import Config; from kinetiqo.mcp.server import create_mcp_server; s = create_mcp_server(Config()); print('✓ MCP Ready! Tools registered:', len(asyncio.run(s.list_tools())))"
```

**Linux / macOS:**
```bash
./.venv/bin/python -c "import sys; sys.path.insert(0, 'src'); import asyncio; from kinetiqo.config import Config; from kinetiqo.mcp.server import create_mcp_server; s = create_mcp_server(Config()); print('✓ MCP Ready! Tools registered:', len(asyncio.run(s.list_tools())))"
```

### Interactive Testing with MCP Inspector
The easiest and most visual way to test tools, pass arguments, and inspect JSON responses is with the official MCP Inspector web UI:

```bash
# Windows
npx @modelcontextprotocol/inspector .\.venv_win\Scripts\python.exe src/kinetiqo.py mcp

# Linux / macOS
npx @modelcontextprotocol/inspector ./.venv/bin/python src/kinetiqo.py mcp
```
Open `http://localhost:5173` in your browser, click **Connect**, select any tool (such as `kinetiqo_search_activities`), and click **Run Tool**.

### Automated Pytest Suite
Run the dedicated isolated unit test suite covering contracts, tools, and server security:

```bash
python -m pytest -o pythonpath=src tests/test_mcp_contracts.py tests/test_mcp_tools.py tests/test_mcp_server.py tests/test_cli_mcp.py tests/test_mcp_sse.py -v
```

---

## 3. Connecting Your AI Assistant

To connect your AI client, add Kinetiqo to your client's MCP configuration file.

### 1. Claude Desktop

**Configuration File Location:**
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

**Example Configuration (`claude_desktop_config.json`):**

```json
{
  "mcpServers": {
    "kinetiqo": {
      "command": "C:\\path\\to\\kinetiqo\\.venv_win\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\kinetiqo\\src\\kinetiqo.py", "mcp"],
      "cwd": "C:\\path\\to\\kinetiqo",
      "env": {
        "DATABASE_TYPE": "postgresql",
        "POSTGRESQL_HOST": "localhost",
        "POSTGRESQL_USER": "athlete",
        "POSTGRESQL_PASSWORD": "your_db_password",
        "POSTGRESQL_DATABASE": "kinetiqo",
        "POSTGRESQL_PORT": "5432"
      }
    }
  }
}
```

*(On macOS/Linux, replace `command` with `/path/to/kinetiqo/.venv/bin/python` and use Unix paths).*

---

### 2. Google Antigravity IDE

**Configuration File Location:**
- Workspace root or global: `mcp_config.json`

**Example Configuration:**

```json
{
  "mcpServers": {
    "kinetiqo": {
      "command": "python",
      "args": ["src/kinetiqo.py", "mcp"],
      "cwd": "H:/WORKING/kinetiqo",
      "env": {
        "DATABASE_TYPE": "postgresql",
        "POSTGRESQL_HOST": "localhost",
        "POSTGRESQL_USER": "athlete",
        "POSTGRESQL_PASSWORD": "your_db_password",
        "POSTGRESQL_DATABASE": "kinetiqo",
        "POSTGRESQL_PORT": "5432"
      }
    }
  }
}
```

---

### 3. Cursor

**Configuration File Location:**
- Project directory: `.cursor/mcp.json`

**Example Configuration:**

```json
{
  "mcpServers": {
    "kinetiqo": {
      "command": "python",
      "args": ["src/kinetiqo.py", "mcp"],
      "cwd": "${workspaceFolder}",
      "env": {
        "DATABASE_TYPE": "mysql",
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_USER": "athlete",
        "MYSQL_PASSWORD": "your_db_password",
        "MYSQL_DATABASE": "kinetiqo",
        "MYSQL_PORT": "3306"
      }
    }
  }
}
```

---

### 4. OpenClaw CLI

Register Kinetiqo directly into your OpenClaw tool registry:

```bash
openclaw mcp add kinetiqo \
  --command /path/to/kinetiqo/.venv/bin/python \
  --arg /path/to/kinetiqo/src/kinetiqo.py \
  --arg mcp \
  --cwd /path/to/kinetiqo

# Verify connectivity:
openclaw mcp doctor kinetiqo --probe
```

---

### 5. Running via Docker (Web UI + Concurrent MCP SSE Server)

Kinetiqo publishes two official Docker variants:
- **`kinetiqo/web:latest` (Standalone)**: Runs the Web Dashboard on port `4444` and the background Cron sync daemon. MCP is disabled by default (`ENABLE_MCP=0`).
- **`kinetiqo/web-mcp:latest` (Kinetiqo + MCP)**: Runs the Web Dashboard on port `4444`, the Cron sync daemon, and the **FastMCP SSE Server on standard port `8000`** in parallel (`ENABLE_MCP=1`).

Both variants include full system Chromium and Playwright, supporting all 35 MCP tools including Group E visual poster and infographic exports.

#### A. Docker Run with Embedded FastMCP (All Options)

```bash
docker run -d \
  --name kinetiqo \
  --restart unless-stopped \
  -p 4444:4444 \
  -p 8000:8000 \
  -e ENABLE_MCP=1 \
  -e MCP_PORT=8000 \
  -e MCP_HOST="0.0.0.0" \
  -e MCP_TRANSPORT="sse" \
  -e KINETIQO_MCP_ALLOW_SYNC=0 \
  -e KINETIQO_MCP_ALLOW_PROFILE_WRITE=0 \
  -e KINETIQO_MCP_ALLOW_STRAVA_WRITE=0 \
  -e STRAVA_CLIENT_ID="your_strava_client_id" \
  -e STRAVA_CLIENT_SECRET="your_strava_client_secret" \
  -e STRAVA_REFRESH_TOKEN="your_strava_refresh_token" \
  -e SECRET_KEY="replace_with_output_from_openssl_rand_hex_32" \
  -e KINETIQO_PRODUCTION=1 \
  -e WEB_LOGIN="admin" \
  -e WEB_PASSWORD="securepassword13" \
  -e DATABASE_TYPE="postgresql" \
  -e POSTGRESQL_HOST="host.docker.internal" \
  -e POSTGRESQL_PORT=5432 \
  -e POSTGRESQL_USER="postgres" \
  -e POSTGRESQL_PASSWORD="your_database_password" \
  -e POSTGRESQL_DATABASE="kinetiqo" \
  -e POSTGRESQL_SSL_MODE="disable" \
  -e FAST_SYNC="*/15 * * * *" \
  -e FULL_SYNC="0 3 * * *" \
  -e VISUAL_CROSSING_API_KEY="your_visual_crossing_api_key" \
  -e ATHLETE_WEIGHT="75" \
  -e DATE_FORMAT="%b %d, %Y" \
  -e GPS_SIMPLIFICATION="0" \
  -e LOG_LEVEL="INFO" \
  -e MAPY_API_KEY="" \
  -e THUNDERFOREST_API_KEY="" \
  -e MAPTILER_API_KEY="" \
  -e GEOAPIFY_API_KEY="" \
  -e CARTO_API_KEY="" \
  -e UPDATE_STRAVA_PLACEMENT="end" \
  -e WORKOUT_SUMMARY_PEAK_THRESHOLD_W="300" \
  kinetiqo/web-mcp:latest
```

- Web UI: **http://localhost:4444**
- FastMCP SSE Endpoint: **http://localhost:8000/sse**

#### B. Docker Compose with Embedded FastMCP (All Options)

**`docker-compose.yml`:**
```yaml
services:
  kinetiqo:
    image: kinetiqo/web-mcp:latest
    container_name: kinetiqo
    restart: unless-stopped
    ports:
      - "4444:4444"   # Web UI
      - "8000:8000"   # FastMCP SSE
    env_file:
      - .env
    environment:
      - ENABLE_MCP=1
      - MCP_PORT=8000
      - MCP_HOST=0.0.0.0
      - MCP_TRANSPORT=sse
      - KINETIQO_MCP_ALLOW_SYNC=${KINETIQO_MCP_ALLOW_SYNC:-0}
      - KINETIQO_MCP_ALLOW_PROFILE_WRITE=${KINETIQO_MCP_ALLOW_PROFILE_WRITE:-0}
      - KINETIQO_MCP_ALLOW_STRAVA_WRITE=${KINETIQO_MCP_ALLOW_STRAVA_WRITE:-0}
      - VISUAL_CROSSING_API_KEY=${VISUAL_CROSSING_API_KEY:-}
    depends_on:
      postgresql:
        condition: service_healthy

  postgresql:
    image: postgres:16-alpine
    container_name: postgresql
    restart: unless-stopped
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=${POSTGRESQL_PASSWORD}
      - POSTGRES_DB=kinetiqo
    volumes:
      - postgresql_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d kinetiqo"]
      interval: 5s
      timeout: 5s
      retries: 5

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}
    depends_on:
      - postgresql

volumes:
  postgresql_data:
```

#### Method A: Connect via FastMCP SSE URL (Recommended)

When Kinetiqo is running as a Docker daemon on your computer or local network, configure Claude Desktop, Cursor, or Antigravity IDE with the direct SSE URL:

```json
{
  "mcpServers": {
    "kinetiqo": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

#### Method B: Ephemeral Execution via STDIO

If you prefer to run an on-demand container without keeping Kinetiqo running as a persistent daemon:

```json
{
  "mcpServers": {
    "kinetiqo": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e", "DATABASE_TYPE=postgresql",
        "-e", "POSTGRESQL_HOST=host.docker.internal",
        "-e", "POSTGRESQL_PORT=5432",
        "-e", "POSTGRESQL_USER=postgres",
        "-e", "POSTGRESQL_PASSWORD=your_password",
        "-e", "POSTGRESQL_DATABASE=kinetiqo",
        "kinetiqo/web-mcp:latest",
        "python", "kinetiqo.py", "mcp"
      ]
    }
  }
}
```

---

## 4. What Can You Ask Your AI? (Real-World Examples)

Once connected, your AI assistant automatically discovers Kinetiqo's tools. Here are example conversations you can start:

### A. Deep Workout & Telemetry Analysis
> **You:** *"Analyze my ride from yesterday. Did I pace the climbs well, and was there noticeable aerobic decoupling (cardiac drift) during the second half?"*
- **What the AI does:** Calls `kinetiqo_get_activity_details`, fetches the aligned telemetry stream with `kinetiqo_get_activity_streams`, and runs `kinetiqo_analyze_pacing` to compare heart-rate-to-power ratios in the first half vs second half.

### B. Route Matching & Historical Effort Comparison
> **You:** *"I rode the mountain pass route this morning. How does my effort compare to my previous 3 attempts this season?"*
- **What the AI does:** Executes `kinetiqo_find_similar_routes` to match activities sharing the GPS track, then calls `kinetiqo_compare_route_attempts` to show speed, power, and elapsed time side by side.

### C. Training Fatigue & Race Readiness
> **You:** *"Check my fitness and freshness form. Am I fresh or fatigued for my 100km Gran Fondo this Sunday?"*
- **What the AI does:** Calls `kinetiqo_get_fitness_and_freshness` to inspect Chronic Training Load (CTL), Acute Training Load (ATL), and Training Stress Balance (TSB), providing an evidence-based recommendation on whether to taper or rest.

### D. Finding Specific Workouts
> **You:** *"Find all outdoor gravel rides over 80km with at least 1,200 meters of climbing done between May and September."*
- **What the AI does:** Calls `kinetiqo_search_activities` with `sport_types=["GravelRide", "Ride"]`, `min_distance_km=80`, `min_elevation_m=1200`, and the specified date range.

### E. Power Curve & Personal Records
> **You:** *"Calculate my power curve for the last 90 days. What were my peak 5-second, 1-minute, 5-minute, and 20-minute power efforts?"*
- **What the AI does:** Calls `kinetiqo_calculate_power_curve` and `kinetiqo_get_personal_records` to report exact wattage and watts-per-kilogram values.

### F. Generating Visual Posters & Infographics
> **You:** *"Generate a minimalist art poster of my latest 120km ride with an elevation profile and OpenCycleMap basemap."*
- **What the AI does:** Executes `kinetiqo_generate_activity_poster` with your desired aspect ratio, basemap, and color theme, returning the rendered image artifact.

### G. Weekly Volume, Habits & Best Power Weeks
> **You:** *"What was my best week of 2026 in terms of power output, and what does my usual week look like for kilometers and climbing?"*
- **What the AI does:** Calls `kinetiqo_get_weekly_training_profile` with `year=2026`, returning the peak week by average watts and total kilojoules (kJ), alongside your typical weekly median distance, elevation gain, and day-of-week ride distribution.

### H. 100km+ Endurance Recovery Turnaround
> **You:** *"What is my usual recovery time after doing a 100km+ ride?"*
- **What the AI does:** Calls `kinetiqo_analyze_recovery_turnaround` with `min_distance_km=100.0`, calculating the median rest days taken before your next workout, and how many days it typically takes for your Training Stress Balance (TSB Form) to rebound to fresh baseline.

---

## 5. Pre-Packaged Coaching Prompts

Kinetiqo includes pre-configured coaching workflows that you can invoke directly in supported clients (such as Claude Desktop):

1. **`post_ride_debrief`**: A structured post-workout session debrief. Checks sensor coverage, evaluates Normalized Power and intensity factor, reviews heart-rate decoupling, checks freshness fatigue, and offers to render an activity art poster.
2. **`race_readiness_assessment`**: An objective readiness check prior to an upcoming target event. Evaluates your current TSB form, acute:chronic workload ratio, and 5-minute / 20-minute power breakthroughs.
3. **`poster_creative_director`**: Recommends typography, aspect ratios, and map tile layers (Mapy.cz Outdoor, Thunderforest, CARTO Dark Matter) to best showcase an epic route.
4. **`weekly_training_review`**: Multi-week review of training volume (km, elevation), mechanical work (kJ, average watts, NP), goal pacing, and Acute:Chronic Workload Ratio (ACWR).
5. **`endurance_recovery_advisor`**: Deep recovery analysis following 100km+ rides, evaluating your median turnaround rest days, days until your next hard ride, and TSB form rebound duration.
6. **`season_power_audit`**: Comprehensive performance review tracking your standout power week of the year, Mean Maximal Power (MMP) curve, FTP breakthrough history, and benchmark PRs.
7. **`training_habit_and_volume_profile`**: Behavioral audit of typical weekly kilometers, elevation gain, ride frequency, and preferred days of the week (Monday through Sunday).

---

## 6. Security & Mutation Permissions

To guarantee total peace of mind, all mutating operations are **100% disabled by default**. The tools are completely excluded from the tool catalog:

| Environment Variable | Default | What it Enables |
|---|---|---|
| `KINETIQO_MCP_ALLOW_SYNC` | `0` | If set to `1`, registers `kinetiqo_trigger_sync` (allows the AI to launch background syncs). |
| `KINETIQO_MCP_ALLOW_PROFILE_WRITE` | `0` | If set to `1`, registers `kinetiqo_update_athlete_profile` and `kinetiqo_update_training_goals`. |
| `KINETIQO_MCP_ALLOW_STRAVA_WRITE` | `0` | If set to `1`, registers `kinetiqo_update_strava_description` (requires `activity:write` OAuth scope). |

To grant write permission, simply add the variable to the `"env"` block of your client's JSON configuration (e.g., `"KINETIQO_MCP_ALLOW_PROFILE_WRITE": "1"`).

---

## 7. Troubleshooting & FAQs

### AI client says "Connection refused" or fails immediately
- Verify that the `command` points to the exact Python binary inside your virtual environment (`.\.venv_win\Scripts\python.exe` on Windows or `.venv/bin/python` on Linux/macOS).
- Run the **Fast Smoke Test** in Section 2 to verify all dependencies (`mcp`, `pydantic`) are installed in that environment.

### Are my logs breaking the protocol?
- No. Kinetiqo redirects all logging strictly to `stderr`. `stdout` carries only pure JSON-RPC protocol messages, preventing parser crashes.

### How does request logging work?
- Just like in the web app, Kinetiqo MCP logs incoming requests and responses at default `INFO` level to `stderr` with timestamps, tool names, parameters, result status, and execution duration (e.g., `MCP Request: kinetiqo_search_activities(...) -> complete (0.015s)`).

### How to stop the server?
- Press `Ctrl+C`. Kinetiqo MCP catches SIGINT/KeyboardInterrupt and exits immediately and cleanly without tracebacks or thread shutdown errors.

### Mutating tools do not appear in the tool list
- By default, all write tools are hidden. Set `KINETIQO_MCP_ALLOW_SYNC=1` or `KINETIQO_MCP_ALLOW_PROFILE_WRITE=1` in your configuration `env` block.
