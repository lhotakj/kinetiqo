# Kinetiqo AI Chat — Feature & Telemetry Guide

> **Version:** 3.0  
> **Status:** Active / Production Ready  
> **Primary Interfaces:** `/chat`, `/settings`, FastMCP tools layer  
> **Supported Providers:** Google Gemini, OpenRouter AI, Vercel AI Gateway, Kilo AI Gateway, Ollama (Local AI)  
> **Database Compatibility:** PostgreSQL, MySQL, Firebird (100% Parameterized Raw SQL)

---

## 1. Overview

**Kinetiqo AI Chat** brings conversational intelligence directly to self-hosted endurance telemetry. Instead of relying on generic public fitness models with hypothetical training numbers, Kinetiqo connects language models directly to your real activity history, power duration curves, Banister impulse-response freshness models, and athlete milestones through a strictly gated, read-only **Model Context Protocol (MCP)** tool layer.

Athletes can ask nuanced training questions in plain language:
- *"What are my Z1, Z2, Z3 ... power and heart rate zones?"*
- *"When did I really do VO2max training?"*
- *"What does VO2max training mean for me and how should I train for best VO2max?"*
- *"In three consecutive biking activities find same/peak wattage output."*
- *"In the last 2 weeks what was my average cadence?"*
- *"What is my usual warm up time before I hit max watts in the last year?"*
- *"Analyze my fatigue over the last 3 weeks — am I digging a hole or over-reaching productively?"*
- *"What is my current VO₂max trend based on 5-minute MAP power intervals?"*
- *"Compare my aerobic decoupling and cadence between indoor turbo trainer sessions and outdoor road rides."*
- *"What are my benchmark power records across 5s, 1m, 5m, and 20m, and when were they set?"*
- *"Did I pace my Gran Fondo climb efficiently yesterday based on my FTP?"*

---

## 2. Core Capabilities

### 2.1 Direct Grounding via 31 Read-Only MCP Tools
The assistant does not guess or hallucinate metrics. When asked a training question, it autonomously discovers and calls in-process read-only tools:
- **Activity Discovery & Streams**: `kinetiqo_get_activities`, `kinetiqo_get_activity_details`, `kinetiqo_get_activity_streams`, `kinetiqo_get_activity_totals`.
- **Power & Performance**: `kinetiqo_get_power_skills`, `kinetiqo_get_personal_records`, `kinetiqo_get_ftp_history`, `kinetiqo_get_vo2max_trend`.
- **Fitness & Freshness**: `kinetiqo_get_fitness_freshness` (computing daily CTL, ATL, and TSB form using athlete-specific exponential moving averages).
- **Milestones & Trophies**: `kinetiqo_get_trophy_stats`, `kinetiqo_get_milestones`, `kinetiqo_get_training_goals`.
- **Visual Artifacts**: `kinetiqo_generate_poster_preview`, `kinetiqo_export_infographic`.

### 2.2 Transparent Data Provenance ("Data used")
Every assistant answer that queries athlete telemetry features a prominent, interactive **"Data used (X local queries)"** toggle in the message footer. Clicking it exposes the exact underlying analytical tools and execution latency (e.g., `get fitness freshness (18ms)`, `get personal records (24ms)`).

### 2.3 Pre-Built Athlete Coaching & Operations Workflows
Integrated prompt workflows in `src/kinetiqo/mcp/prompts.py` equip the AI with structured evaluation frameworks:
1. **Post-Ride Debrief (`post_ride_debrief`)**: Analyzes sensor coverage, sustained power blocks, sprint surges, pacing splits, and offers commemorative poster generation or Strava description updates.
2. **Sync & Strava Update Workflow (`sync_and_update_strava`)**: Initiates fast or full sync with customizable time limits (`limit_days`), validates imported telemetry, formulates custom workout summaries, and publishes updated descriptions to Strava.
3. **Recovery & Freshness Audit (`endurance_recovery_advisor`)**: Evaluates TSB (Form) vs ATL (Fatigue) and CTL (Fitness) after major endurance milestones.
4. **VO₂max & FTP Progression (`ftp_breakthrough_and_power_zones_audit`)**: Analyzes 5-min MAP power trend lines, 95% 20-min FTP steps, and Coggan power training zones.
5. **Race Readiness Assessment (`race_readiness_assessment`)**: Evaluates athlete form, peak power skills, and acute:chronic training workload prior to target events.
6. **Training Stress & Overreaching Check (`training_stress_and_overreaching_check`)**: Audits ACWR ratios, CTL ramp rates, and fatigue accumulation to prevent overtraining.

---

## 3. Privacy, Isolation & Security

1. **100% Self-Hosted & Scoped**: All telemetry queries execute against the local database, strictly isolated to the authenticated athlete (`athlete_id = current_user.id`).
2. **Encrypted Provider Keys**: External API keys are encrypted at rest using **AES-256-GCM** with an envelope key derived via HKDF-SHA256. API keys are never rendered in HTML, logged, or sent to the browser.
3. **Hard Read-Only Safety Gates in Web Chat**: Mutating actions (triggering Strava sync, updating Strava activity descriptions, altering athlete FTP/weight) are **strictly forbidden** from the web chat tool allowlist. The chat interface cannot modify athlete records.
4. **Gated MCP Mutating Tools for External Agents**: When running the standalone FastMCP server (`kinetiqo mcp`) for external AI agents (Claude Desktop, Antigravity IDE, Cursor), mutating capabilities are explicitly gated behind environment variables:
   - `KINETIQO_MCP_ALLOW_SYNC=1`: Enables `kinetiqo_trigger_sync` (supports fast sync and full sync with `limit_days` time limitation).
   - `KINETIQO_MCP_ALLOW_STRAVA_WRITE=1`: Enables `kinetiqo_update_strava_description` (supports both template `preview_id` and custom AI prompt description strings).
   - `KINETIQO_MCP_ALLOW_PROFILE_WRITE=1`: Enables `kinetiqo_update_athlete_profile` (FTP and weight adjustments).
5. **No Third-Party Analytics Trackers**: Responses stream directly from the chosen AI provider API over secure HTTPS/TLS to your private Kinetiqo server, then to your browser via Server-Sent Events (SSE).

---

## 4. Multi-Provider Architecture

Kinetiqo separates the chat orchestration service from underlying AI providers, allowing athletes to choose the intelligence engine that best fits their budget, speed, and privacy preferences:

```
Athlete Web Browser (/chat)
       │
       ▼  (SSE streaming over HTTPS)
Kinetiqo Flask Application Server
       │
       ├── Provider Registry
       │     ├── Google Gemini Adapter (gemini-3.1-flash-lite, gemini-2.5-flash, etc.)
       │     ├── OpenRouter AI Adapter (Claude 3.5 Sonnet, Llama 3.3 70B, DeepSeek, etc.)
       │     ├── Vercel AI Gateway Adapter (Kimi K2.6, Llama 3.3 70B, DeepSeek R1, Claude Haiku 4.5, GPT-4o)
       │     ├── Kilo AI Gateway Adapter (Kilo Auto Free, Llama 3.3 70B, DeepSeek R1, Gemini 2.5 Flash, Qwen 2.5)
       │     └── Ollama / Local AI Adapter (Qwen, Llama, Mistral on your own hardware)
       │
       └── In-Process FastMCP Tool Layer
             └── Local Relational Database (PostgreSQL / MySQL / Firebird)
```

### 4.1 Google Gemini
- Official Google REST API adapter with server-side model discovery.
- Fast, cost-effective inference with generous context windows.
- Automatically selects the optimal available model (defaulting to `gemini-3.1-flash-lite`).

### 4.2 OpenRouter AI
- OpenAI-compatible gateway unlocking access to hundreds of cutting-edge open and proprietary models.
- **Custom Curated Model List**: Enter any OpenRouter model identifier (e.g. `meta-llama/llama-3.3-70b-instruct`, `deepseek/deepseek-chat`, `google/gemma-4-26b-a4b-it:free`, `nvidia/nemotron-3.5-lightning:free`).
- **Live Model Validation & Details**: Validates model IDs against OpenRouter metadata and displays published pricing, output-token bounds, descriptions, and rate/request limits in Settings.
- **Rate-limit transparency**: Rate limits are shown only when included in provider metadata; otherwise Settings says they are unpublished and may vary by provider or account. Kinetiqo does not infer or guarantee quotas.
- **Flexible Management**: Add (`+`) or remove (`-`) models on the fly in Settings.

### 4.3 Vercel AI Gateway
- Unified OpenAI-compatible edge gateway (`https://ai-gateway.vercel.sh/v1`) providing low-latency routing to leading open-weight and frontier models (Moonshot AI Kimi, Meta Llama, DeepSeek, Anthropic, OpenAI, etc.).
- **Custom Curated Model List**: Enter any Vercel AI Gateway model identifier (e.g. `moonshotai/kimi-k2.6`, `meta/llama-3.3-70b`, `deepseek/deepseek-r1`, `anthropic/claude-haiku-4.5`, `openai/gpt-4o`).
- **Live Model Validation & Details**: Automatically validates entered model IDs against Vercel's models API (`GET /v1/models/{model_id}` or catalog `/v1/models`), displaying published context/output-token limits, pricing, descriptions, tool-calling support, vision capabilities, and rate/request limits.
- **Rate-limit transparency**: Rate limits are shown only when included in provider metadata; otherwise Settings says they are unpublished and may vary by provider or account. Kinetiqo does not infer or guarantee quotas.
- **Fuzzy Model Suggestions**: If the organization prefix is omitted (e.g. `kimi-k2.6`), Kinetiqo searches the Vercel model catalog and suggests the exact canonical ID (`moonshotai/kimi-k2.6`) with a single-click suggestion button.
- **Flexible Management**: Add (`+`) or remove (`-`) configured models from the responsive table in Settings.

### 4.4 Kilo AI Gateway (kilo.ai)
- High-efficiency, zero-markup AI model gateway and aggregator (`https://api.kilo.ai/api/gateway`) from the creators of Kilo Code, providing unified OpenAI-compatible routing across 400+ models.
- **Free Auto-Routing Tier (`kilo-auto/free`)**: Dynamically routes training queries to the optimal healthy free-tier model on the fly, with up to 262k context, tool calling, and multimodal vision support at zero cost without credit card requirements.
- **Zero-Markup & Bring-Your-Own-Key (BYOK)**: Connects to underlying providers at provider list rates or zero markup for Kilo Pass / Gateway users.
- **Curated Model Registry**: Register any model identifier available on Kilo Gateway (e.g. `kilo-auto/free`, `meta-llama/llama-3.3-70b-instruct`, `deepseek/deepseek-r1`, `google/gemini-2.5-flash`, `qwen/qwen-2.5-coder-32b-instruct`, `anthropic/claude-3.5-haiku`, `openai/gpt-4o-mini`).
- **Live Validation & Suggestions**: Validates models via Kilo's model registry (`GET /api/gateway/models/{id}` and `/models`), automatically discovering context window size, tool-calling capabilities, vision support, pricing, and rate limits. Suggests canonical slugs when prefixes are omitted (e.g. `llama-3.3-70b-instruct` → `meta-llama/llama-3.3-70b-instruct`).
- **Multi-Turn Tool Execution**: Fully supports Kinetiqo's in-process FastMCP tool calling across endurance telemetry, MMP power curves, and fitness metrics.

### 4.5 Ollama (Local Hardware AI)
- **100% Private On-Premise Inference**: Connect to models running on your own PC or homelab server via Ollama's OpenAI-compatible API.
- **Automatic Model Discovery**: Detects all locally installed models (`qwen3:1.7b`, `qwen2.5:7b-instruct`, `llama3.1:8b`, etc.) without manual configuration.
- **Optional API Token**: No API key is required on your local network. An optional token field is available if Ollama is hosted behind a reverse proxy.
- **Remote Host Setup**: To connect across machines on your LAN, set `OLLAMA_HOST=0.0.0.0:11434` on the Ollama PC and provide its local IP (e.g. `http://192.168.1.150:11434`).
- **Provider-specific model details**: Ollama reports the local parameter size when available; pricing, context limits, and rate limits are not inferred.

### 4.6 Unified Provider Model Tables
- Gemini, OpenRouter, Vercel AI Gateway, Kilo AI Gateway, and Ollama use the same columns in Settings: **Model Name & ID**, **Context**, **Capabilities**, **Pricing & Limits**, **Default**, and **Actions**.
- Values such as Gemini context and output-token limits or Ollama parameter size are shown when their provider reports them. Unavailable metadata is displayed as `-`; pricing and rate limits are never guessed.
- Remove actions are available only for providers with user-managed model lists; other providers show `-` in the Actions column.

### 4.7 Dynamic Mid-Session Provider & Model Switching
- Seamlessly change models or AI providers mid-conversation at any turn from the composer model selector.
- If a quota or rate limit is reached on OpenRouter, Vercel, or Kilo, simply switch the selector to Google Gemini or your local Ollama model; Kinetiqo immediately routes the next query to the newly chosen provider and persists the updated configuration to the session.

### 4.8 Default Model & Multi-Model Automated Fallbacks
- **Default Model Designation (`★`)**:
  - Click the star icon in any provider's model table under **Settings → AI & API Providers** to designate your preferred default model.
  - New chat sessions automatically select this model. The active default model is highlighted with a gold star badge in the AI Settings header and on the right side of the `/chat` model dropdown.
- **Up to 3 Automated Fallback Models (Diamond Badges `1`, `2`, `3`)**:
  - Click the diamond icon (rotated 45° square) next to any model to designate it as a fallback.
  - Up to **3 fallback models** can be selected across any configured provider (e.g. Fallback 1: `kilo-auto/free`, Fallback 2: `google/gemma-4-26b-a4b-it:free`, Fallback 3: `gemini-3.1-flash-lite`).
  - **Click-Order Priority**: The fallback order strictly follows the chronological order in which you click them (1st clicked = Fallback 1, 2nd clicked = Fallback 2, 3rd clicked = Fallback 3).
  - **Visual Badges**: Active fallbacks display an orange diamond badge containing their rank (`1`, `2`, `3`) in the model table, in the AI Settings header badge row, and on the right side of the `/chat` model dropdown.
  - **Mutual Exclusivity & Bounds**: A default model cannot simultaneously be a fallback. Marking a fallback model as default automatically clears it from the fallback list. Attempting to add a 4th fallback is gracefully prevented with a notification.
  - **Informational Help Popover (`(?)`)**: An info button in the AI Settings header provides on-demand guidance regarding fallback mechanics and how to adjust them.
- **Seamless Streaming Failover**:
  - When submitting a prompt in `/chat`, if the primary model fails before producing output deltas (e.g. HTTP 429 quota exhaustion, provider downtime, or temporary network failure), Kinetiqo automatically and transparently attempts Fallback 1, then Fallback 2, and then Fallback 3.
  - The assistant message and session automatically adopt the provider and model that answered, ensuring uninterrupted coaching insights without manual model re-selection.

---

## 5. Web UI Features & Ergonomics (`/chat`)

- **Interactive Sidebar History**:
  - Full conversation persistence with automatic date-based sorting.
  - Hover deletion (`×`) to prune individual sessions instantly.
  - "+ New chat" button adhering to Kinetiqo's primary action button standards.
- **Prompt History & Copilot-Style Suggestions**:
  - **Arrow Up / Down Navigation**: Pressing Arrow Up at the first line of the composer rolls back through prompt history; pressing Arrow Down at the last line rolls forward.
  - **Copilot-Style Auto-Suggestions**: Real-time suggestion popup appears while typing, suggesting completions based on the athlete's prompt history across all past sessions.
  - **Database Index Optimization**: Accelerated across all chats via composite database index `idx_chat_messages_hist` on `(athlete_id, role, created_at)` across PostgreSQL, MySQL, and Firebird.
- **Live Generation Cancellation**:
  - When a prompt is executing, the send button transforms into an active red `■ Cancel` button.
  - Clicking cancel immediately terminates the stream via `AbortController`, signals server-side generator termination (`GeneratorExit`), displays a `■ Cancelled` indicator in the chat stream, and restores the composer.
- **Data Presentation & Charting Architecture**:
  - **Structured Data & Metric Tables**: Numerical telemetry, comparisons, time series, and scatter/trend comparisons are presented in clean, responsive Markdown tables and bulleted takeaways for 100% reliable rendering without parser fragility.
  - **Interactive Chart.js Engine (Self-Hosted)**:
    - Powered by self-hosted **Chart.js 4.5.1** (`static/vendor/chartjs/chart-4.5.1.umd.min.js`), completely replacing fragile DSL diagram libraries.
    - Features rich interactive canvas rendering: hover tooltips with exact values, responsive auto-scaling, clickable legend series toggling, dark/light theme-adaptive scales and grids, and a `[View code] / [View chart]` toggle.
    - When exporting responses via **Download HTML**, rendered charts are automatically converted to embedded high-resolution PNG data URLs so saved reports remain 100% visual and offline-ready.
  - **Comprehensive Supported Chart Taxonomy**:
    - **Core Chart Types**:
      - **Column Chart (Vertical Bar)**: Compares values across categories using vertical bars (Clustered, Stacked, and 100% Stacked; `type: 'bar'`).
      - **Bar Chart (Horizontal Bar)**: Horizontal bars (`type: 'bar', options: { indexAxis: 'y' }`) for rankings with long category labels (activity names, segments, athlete PR leaderboards).
      - **Line Chart**: Shows continuous trends and changes over equal time intervals or sequences (annual mileage, monthly elevation, FTP history, MMP power curves, CTL/ATL/TSB models), with stepped curves (`stepped: true`) and markers (`pointRadius`).
      - **Pie & Doughnut Charts**: Displays proportional parts to a whole, with doughnut charts featuring a hollow center (`type: 'pie'`, `type: 'doughnut'`), ideal for Coggan Power Zones (Z1–Z7), Heart Rate Zones (Z1–Z5), and sport type breakdowns.
      - **Area Chart**: Emphasizes the magnitude of change over time, showing filled spaces below lines (`type: 'line', fill: true`, stacked area via `scales: { y: { stacked: true } }`).
      - **XY Scatter Plot**: Maps numeric coordinate points for 2-variable correlation (`type: 'scatter'`, `[{x, y}]`), such as Heart Rate vs. Power, cadence vs. speed, and aerobic decoupling.
      - **Bubble Chart**: Maps numeric points with a 3rd data dimension (`type: 'bubble'`, `[{x, y, r}]`), where bubble radius `r` visualizes a 3rd metric (e.g. duration × watts × TSS/elevation).
    - **Specialized and Statistical Charts**:
      - **Histogram**: Displays frequency distribution of numeric telemetry data grouped into bins (`type: 'bar'` with `categoryPercentage: 1.0, barPercentage: 1.0` for gapless continuous bins).
      - **Pareto Chart**: Combines a column chart (sorted descending frequencies/counts on primary left y-axis) with a line graph (cumulative percentage curve 0–100% on secondary right y1-axis).
      - **Box and Whisker**: Summarizes data spread, median, quartiles, and statistical outliers (modeled in Chart.js via floating bars `[Q1, Q3]` for interquartile ranges, or clustered multi-dataset bars for Min, Q1, Median, Q3, Max).
      - **Waterfall Chart**: Visualizes cumulative positive and negative sequential contributions to a total using floating bar tuples `[start, end]`.
      - **Funnel Chart**: Tracks progressive reduction or stages through a multi-step process (`type: 'bar', indexAxis: 'y'` sorted descending).
      - **Stock Chart (High-Low-Close / Candlestick)**: Visualizes boundary and range data using floating bar tuples `[low, high]` for range bounds, combined with line markers for open/close values.
      - **Radar (Spider) Chart**: Compares multiple performance metrics or variables across radial axes (`type: 'radar'`), e.g. Power Skills spider profile across benchmark durations 1s, 5s, 10s, 30s, 1m, 5m, 10m, 30m, 60m in Watts or W/kg.
      - **Surface Chart**: Plots 3-D numerical data landscapes; visualized via multi-series contour lines or Bubble charts `[{x, y, r}]` where radius `r` represents the 3rd surface dimension.
      - **Treemap & Sunburst**: Maps hierarchical and multi-tiered proportional data (represented in Chart.js via multi-ring concentric Doughnut charts with multiple datasets, or stacked hierarchical bars).
      - **Combo Chart (Mixed / Dual-Axis)**: Combines two or more distinct chart types (such as column bars and a line curve) in a single view with dual y and y1 axes.
  - **Theme-Aware Styling**: Charts dynamically re-render with matching palettes (`dark` vs `light`) when toggling dark mode in the Kinetiqo header.
  - **Graceful Error Isolation**: If invalid chart configuration syntax is encountered, Kinetiqo avoids technical parser stack traces, displaying an elegant preview fallback and source view.
- **Dual-Format Response Export**:
  - **Markdown Export (`.md`)**: Downloads clean Markdown preserving exact formatting, telemetry tables, and code blocks.
  - **Self-Contained HTML Export (`.html`)**: Downloads unstyled, portable HTML with auto-embedded Base64 images and rendered high-res chart graphics (removing interactive toggle buttons and extraneous dashboard classes).
- **Dynamic Composer Animation**:
  - Rotating frame border utilizing Kinetiqo brand colors (`#df3c57`, `#e07d4b`, `#efc65e`, `#49ae9f`) during live response streaming.
- **Streamlined Message Footer**:
  - Crisp 1px top border separator in both light (`#e5e7eb`) and dark (`#3f3f46`) modes.
  - Unified right-aligned metadata row: `[Data used (X queries) ▾] · [Model Badge] · [Tokens: X in · Y out · Zs] · [Download MD] · [Download HTML]`.
  - Transparent, distraction-free provenance view with high-contrast text.

---

## 6. Configuration in Settings (`/settings`)

1. Navigate to **Settings** (`/settings`) → **AI & API Providers**.
2. Click **"+ Add AI Provider"** and select **Google Gemini**, **OpenRouter AI**, **Vercel AI Gateway**, **Kilo AI Gateway**, or **Ollama (Local AI)**.
3. Configure the provider:
   - **For Gemini**: Paste your API key; models are automatically discovered.
   - **For OpenRouter**: Enter your API key, then use the nested models table to add your preferred models with real-time validation.
   - **For Vercel AI Gateway**: Enter your Vercel gateway API key (Bearer token), then use the nested models table to add your preferred models (e.g. `moonshotai/kimi-k2.6`) with real-time validation.
   - **For Kilo AI Gateway**: Enter your Kilo gateway API key (from [kilo.ai](https://kilo.ai)), then use the nested models table to add your preferred models (e.g. `kilo-auto/free`) with real-time validation.
   - **For Ollama**: Enter your Ollama server URL (e.g. `http://localhost:11434` or `http://192.168.1.150:11434`). Test the connection to auto-discover all pulled models. An API key is optional.
4. Return to **AI Chat** (`/chat`), select your desired model from the dropdown, and begin asking training questions.

---

## 7. Free Models & Recommendations

### 7.1 Best Free Models on Kilo AI Gateway (`kilo.ai`)
Kilo AI Gateway provides zero-markup developer access and actively maintained free routing tiers:
1. **`kilo-auto/free` (Recommended Default)**:
   - **Context Window**: 262,144 tokens (256K).
   - **Capabilities**: Full function calling (tools) and multimodal image support.
   - **Cost**: 100% Free ($0 / $0 token pricing), no paid credits or credit card required.
   - **Why it's great**: Automatically routes requests to the healthiest and highest-capacity free open-weight models without manual switching.
2. **`deepseek/deepseek-r1:free` or `deepseek/deepseek-chat:free`**:
   - **Context Window**: 64,000–128,000 tokens.
   - **Capabilities**: High-depth reasoning, mathematical formulation, and deep training trend deduction.
   - **Cost**: Free tier routing where active on upstream partner networks.
3. **`meta-llama/llama-3.3-70b-instruct:free`**:
   - **Context Window**: 131,072 tokens.
   - **Capabilities**: Industry-standard open-weights conversational intelligence and tool-calling execution.
4. **`qwen/qwen-2.5-coder-32b-instruct:free`**:
   - **Context Window**: 131,072 tokens.
   - **Capabilities**: High logical precision, ideal for complex multi-step FastMCP data calculations.
5. **Ultra-Budget / High-Value Paid Tiers on Kilo**:
   - `google/gemini-2.5-flash`: 1M+ token context with micro-cent pricing ($0.075 / 1M tokens).
   - `openai/gpt-4o-mini`: 128k context with high tool-calling reliability ($0.15 / 1M tokens).
   - `anthropic/claude-3.5-haiku`: 200k context with lightning speed and vision support.

### 7.2 Best Free Models on OpenRouter
If you want verified 100% free models currently active on OpenRouter:
- `google/gemma-4-26b-a4b-it:free` (262k context, tools + multimodal vision support)
- `nvidia/nemotron-3.5-lightning:free` (131k context, tools support)
- DeepSeek flagship tier: `deepseek/deepseek-chat` (or `:free` variant when active)