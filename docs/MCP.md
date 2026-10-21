# Model Context Protocol (MCP) User Guide

**Kinetiqo MCP** connects your self-hosted fitness data warehouse directly to modern AI assistants—such as **Google Antigravity IDE**, **Claude Desktop**, **Cursor**, **Windsurf**, and **OpenClaw**—via the open [Model Context Protocol (MCP)](https://modelcontextprotocol.io/).

With Kinetiqo MCP, your AI assistant transforms into an evidence-based personal endurance coach, telemetry analyst, and creative director with direct access to your activities, sensor streams, power curves, and milestones.

---

## 1. Why Use Kinetiqo with MCP?

- 🔒 **Privacy-First & Local**: Your raw sensor streams, GPS coordinates, and heart rates remain completely on your machine. AI assistants query your local SQLite/PostgreSQL/MySQL/Firebird database through standard STDIO JSON-RPC frames.
- ⚡ **Zero Cloud Leak**: No third-party servers or fitness aggregators sit between your AI and your data.
- 🛡️ **Read-Only by Default**: The MCP server is strictly read-only out of the box. Mutating actions (triggering syncs, editing athlete FTP, publishing Strava descriptions) are completely hidden from the AI tool catalog unless explicitly enabled by you.
- 📊 **33 Evidence-Based Tools**: Comprehensive access to historical workouts, continuous Mean Maximal Power (MMP), Normalized Power (NP), aerobic decoupling, suffer-score fitness (CTL/ATL/TSB), and Playwright visual poster exports.

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
python -m pytest -o pythonpath=src tests/test_mcp_contracts.py tests/test_mcp_tools.py tests/test_mcp_server.py -v
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

---

## 5. Pre-Packaged Coaching Prompts

Kinetiqo includes pre-configured coaching workflows that you can invoke directly in supported clients (such as Claude Desktop):

1. **`post_ride_debrief`**: A structured post-workout session debrief. Checks sensor coverage, evaluates Normalized Power and intensity factor, reviews heart-rate decoupling, checks freshness fatigue, and offers to render an activity art poster.
2. **`race_readiness_assessment`**: An objective readiness check prior to an upcoming target event. Evaluates your current TSB form, acute:chronic workload ratio, and 5-minute / 20-minute power breakthroughs.
3. **`poster_creative_director`**: Recommends typography, aspect ratios, and map tile layers (Mapy.cz Outdoor, Thunderforest, CARTO Dark Matter) to best showcase an epic route.

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
