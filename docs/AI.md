# Kinetiqo AI Chat — Feature & Telemetry Guide

> **Version:** 3.0  
> **Status:** Active / Production Ready  
> **Primary Interfaces:** `/chat`, `/settings`, FastMCP tools layer  
> **Supported Providers:** Google Gemini, OpenRouter AI, Vercel AI Gateway, Kilo AI Gateway, Poe, Ollama (Local AI), Mistral AI, Anthropic Claude, PayPerQ, MagnetAPI
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
- *"Show me all activities when it was raining."*
- *"What was my strongest wind gust faced on bike this year?"*
- *"What was my coldest ride this winter?"*
- *"Show me rides where temperature exceeded 30°C."*
- *"Analyze my fatigue over the last 3 weeks — am I digging a hole or over-reaching productively?"*
- *"What is my current VO₂max trend based on 5-minute MAP power intervals?"*
- *"Compare my aerobic decoupling and cadence between indoor turbo trainer sessions and outdoor road rides."*
- *"What are my benchmark power records across 5s, 1m, 5m, and 20m, and when were they set?"*
- *"Did I pace my Gran Fondo climb efficiently yesterday based on my FTP?"*

---

## 2. Core Capabilities

### 2.1 Direct Grounding via 32 Read-Only MCP Tools
The assistant does not guess or hallucinate metrics. When asked a training question, it autonomously discovers and calls in-process read-only tools:
- **Activity Discovery & Telemetry Search**: `kinetiqo_search_activities` filters by power, heart rate, cadence, speed, distance, dates, and full weather criteria (`weather_condition`, `min_temp_c`, `max_temp_c`, `min_wind_speed_kmh`, `min_wind_gust_kmh`, `has_weather`), with fast keyset sorting by `wind_gust`, `wind_speed`, `temp`, `watts`, and `start_date`, returning dual-unit weather payloads (`km/h` and `m/s`).
- **Activity Weather & Hourly Snapshots**: `kinetiqo_get_activity_weather` returns saved hourly historical weather snapshots, wind direction, and headwind provenance for an activity from the local `weather` table. For severe weather queries (e.g. peak wind gusts), the AI performs a two-step drill-down: fast candidate discovery via `kinetiqo_search_activities(sort_by='wind_gust')` followed by hourly snapshot analysis via `kinetiqo_get_activity_weather`. It is read-only, bounded, never requests live weather on demand, and never returns GPS coordinates. Configure `VISUAL_CROSSING_API_KEY` and enable weather during sync to populate it; see [Weather enrichment](weather.md).
- **Power & Performance**: `kinetiqo_get_power_skills`, `kinetiqo_get_personal_records`, `kinetiqo_get_ftp_history`, `kinetiqo_get_vo2max_trend`.
- **Fitness & Freshness**: `kinetiqo_get_fitness_and_freshness` (computing daily CTL, ATL, and TSB form using athlete-specific exponential moving averages).
- **Milestones & Trophies**: `kinetiqo_get_verified_koms`, `kinetiqo_get_segment_trophies`, `kinetiqo_get_fondo_milestones`, and `kinetiqo_get_training_goals`.
- **Visual Artifacts**: `kinetiqo_generate_activity_poster`, `kinetiqo_generate_mega_stats_infographic`, `kinetiqo_generate_fondo_infographic`, and `kinetiqo_generate_map_artifact`.

### 2.2 Transparent Data Provenance ("Data used")
Every assistant answer that queries athlete telemetry features a prominent, interactive **"Data used (X local queries)"** toggle in the message footer. Clicking it exposes the exact underlying analytical tools and execution latency (e.g., `get fitness freshness (18ms)`, `get personal records (24ms)`).

### 2.3 Pre-Built Athlete Coaching & Operations Workflows
The 13 integrated prompt workflows in `src/kinetiqo/mcp/prompts.py` equip the AI with structured evaluation frameworks:
1. **Post-Ride Debrief (`post_ride_debrief`)**: Analyzes sensor coverage, sustained power blocks, sprint surges, pacing splits, and offers commemorative poster generation or Strava description updates.
2. **Sync & Strava Update Workflow (`sync_and_update_strava`)**: Initiates fast or full sync with customizable time limits (`limit_days`), validates imported telemetry, formulates custom workout summaries, and publishes updated descriptions to Strava.
3. **Race Readiness Assessment (`race_readiness_assessment`)**: Evaluates athlete form, peak power skills, and acute:chronic training workload prior to target events.
4. **Poster Creative Director (`poster_creative_director`)**: Recommends a visual direction, typography, and map styling for an activity poster.
5. **Weekly Training Review (`weekly_training_review`)**: Reviews volume, elevation, mechanical work, goals, and workload trends.
6. **Recovery & Freshness Audit (`endurance_recovery_advisor`)**: Evaluates TSB (Form), ATL (Fatigue), and CTL (Fitness) after major endurance milestones.
7. **Season Power Audit (`season_power_audit`)**: Audits season power, Mean Maximal Power, FTP history, and benchmark records.
8. **Training Habit & Volume Profile (`training_habit_and_volume_profile`)**: Examines recurring weekly volume, elevation, ride frequency, and day-of-week habits.
9. **Aerobic Decoupling & Efficiency (`aerobic_decoupling_and_efficiency`)**: Reviews aerobic efficiency and cardiac drift.
10. **VO₂max & FTP Progression (`ftp_breakthrough_and_power_zones_audit`)**: Analyzes 5-minute MAP trends, 95% 20-minute FTP steps, and Coggan power zones.
11. **Training Stress & Overreaching Check (`training_stress_and_overreaching_check`)**: Audits ACWR ratios, CTL ramp rates, and fatigue accumulation.
12. **Cadence & Pedaling Efficiency (`cadence_and_pedaling_efficiency_analysis`)**: Analyzes cadence dynamics and pedaling efficiency.
13. **Interval Session Quality (`interval_session_quality_audit`)**: Evaluates interval execution, recovery, consistency, and power fade.

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

### 3.1 Named Strava Description Agents

The **Settings → Strava description templates** panel supports multiple specialized Kinetiqo Agents. Use the orange **+ Add Agent** action in the top-right of the agent panel to append a draft row. Every row displays its variable below the Name input—initially `{{agent-ai-<new>}}`, then its normalized lowercase slug such as `{{agent-ai-indoor-bike}}`—and has a larger prompt editor. Rows are separated for readability. The variable picker lists only configured, enabled named-agent placeholders; legacy generic aliases are unsupported. Each agent response is cached independently per activity. Saving an agent prompt clears that agent's cached responses so the next eligible sync generates fresh text; an empty prompt intentionally skips the AI call and resolves its placeholder to empty text. Description output uses the **✨ Kinetiqo AI** prefix only when an AI placeholder produced content; otherwise it uses **✨ Kinetiqo**. Template mini-headers use the AI label when their text contains a named `{{agent-ai-...}}` placeholder.

Use **Try this prompt with your activity** beside an agent prompt to open its larger preview dialog. There, start typing an activity name or full/partial Strava activity ID, select one result, then use the dialog's final **Try** action. **Try** requires enabled agents and an explicitly selected default AI model. The dialog uses the standard dark backdrop and animated loading asset while progressing through activity preparation, model generation, and response completion, then shows the response and any fallback-model status. Previews never save the prompt, cache a response, modify the activity, or call Strava.

**Delete agent** opens a dark-overlay confirmation dialog for every row, including drafts. For a referenced saved agent, it lists the affected templates and explains that confirming removes the agent placeholder from each of them.

On Fast or Full Sync, **Retrigger AI agents** is off by default. When enabled, it refreshes named-agent responses only for named placeholders referenced by each of the newest 30 eligible activities in the selected sync scope. Cache invalidation is strictly **per activity and per agent token**:
- **Non-destructive preservation**: Any other agent responses cached on that activity (outside the active sport template) are preserved intact.
- **Safe fallback on failure**: Invalidation occurs only upon a successful, non-empty response. If an agent fails or times out, its previous cached response is retained in memory and the database, an explicit warning is logged in the sync progress log (`Warning: AI Agent regeneration failed for activity <id> ('<name>'): <agent> (<status>). Previous cached response(s) were retained.`), and the activity is tagged as `[agent-<name>: error kept cached]`.
- **Normalized sync tags**: Each processed activity line reports its agent status as `[agent-<name>: cache]`, `[agent-<name>: refreshed]`, `[agent-<name>: error kept cached]`, or `[agent-<name>: error]` directly following the Strava description status.
This cache refresh does not write to Strava unless **Update Strava description** is also selected; when it is, the description can use fresh successful responses alongside retained failed-agent responses. The CLI equivalent is `kinetiqo.py sync --retrigger-ai-agents`.

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
       │     ├── Poe Adapter (GPT-4o, Claude-3.5-Sonnet bot handles)
       │     ├── Mistral AI Adapter (Mistral Small, Mistral Large, Codestral)
       │     ├── Anthropic Claude Adapter (Claude 3.7 Sonnet, Claude 3.5 Sonnet, Claude 3.5 Haiku, Claude 3 Opus)
       │     ├── PayPerQ Adapter (Auto Router, AutoClaw Eco, Claude Sonnet 4.6, DeepSeek R1, GPT-4o, Gemini 2.5 Flash)
       │     ├── MagnetAPI Adapter (Power AI, ChatGPT 6.1 SOL, Claude Opus 5.5, DeepSeek Flash)
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

### 4.5 Poe
- Connects configured Poe bot handles through Poe's OpenAI-compatible Chat Completions API (`https://api.poe.com/v1/chat/completions`).
- Save a Poe API key in **Settings → AI & API Providers**, then add a bot handle. Kinetiqo validates the handle using Poe's bot endpoint and only retains metadata explicitly returned by Poe.
- Poe does not assume a default bot; configure at least one handle and mark the desired model as the default in its Settings table.
- Supports streaming responses and Kinetiqo's in-process read-only tool calling through the shared OpenAI-compatible adapter.

### 4.6 Ollama (Local Hardware AI)
- **100% Private On-Premise Inference**: Connect to models running on your own PC or homelab server via Ollama's OpenAI-compatible API.
- **Automatic Model Discovery**: Detects all locally installed models (`qwen3:1.7b`, `qwen2.5:7b-instruct`, `llama3.1:8b`, etc.) without manual configuration.
- **Optional API Token**: No API key is required on your local network. An optional token field is available if Ollama is hosted behind a reverse proxy.
- **Remote Host Setup**: To connect across machines on your LAN, set `OLLAMA_HOST=0.0.0.0:11434` on the Ollama PC and provide its local IP (e.g. `http://192.168.1.150:11434`).
- **Provider-specific model details**: Ollama reports the local parameter size when available; pricing, context limits, and rate limits are not inferred.

### 4.7 Mistral AI
- **Official Mistral REST API Adapter**: Direct connection to `https://api.mistral.ai/v1` using your Mistral API key from [console.mistral.ai](https://console.mistral.ai).
- **Automatic Model Discovery**: Queries `GET /v1/models` on save and refresh to discover all available chat generation models (`mistral-small-latest`, `mistral-large-latest`, `codestral-latest`, `ministral-8b-latest`, `pixtral-large-latest`, etc.).
- **Smart Model Filtering**: Automatically filters out embedding (`mistral-embed`), moderation (`mistral-moderation-latest`), and OCR models to display only operational conversational models.
- **Model Selection & Multi-Model Cascading**: Easily mark any discovered Mistral model as your Default (`★`) or assign it to Fallback slots (`1`, `2`, `3`).
- **In-Process FastMCP Tool Calling**: Full streaming SSE multi-turn tool calling with all 32 read-only Kinetiqo telemetry and analytics tools.

### 4.8 Anthropic Claude
- **Official Anthropic Claude REST API Adapter**: Direct connection to `https://api.anthropic.com/v1` using your Anthropic API key (`sk-ant-...`) from [console.anthropic.com](https://console.anthropic.com).
- **Automatic Model Discovery**: Automatically queries `GET /v1/models` on key save and page load to list all available Claude generation models (`claude-3-7-sonnet-20250219`, `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022`, `claude-3-opus-20240229`, etc.).
- **Smart Model Filtering**: Automatically excludes legacy deprecated models (Claude 1 and Claude 2 series) and prioritizes modern frontier reasoning models.
- **Model Selection & Cascading**: Mark any discovered Claude model as your Default (`★`) or assign it to Fallback slots (`1`, `2`, `3`).
- **In-Process FastMCP Tool Calling**: Full streaming SSE multi-turn tool calling via Anthropic Messages API with structured JSON Schema tools.

### 4.9 PayPerQ
- **PayPerQ AI Router & Chat API Adapter**: Connects to `https://api.ppq.ai/v1` via your PayPerQ API key from [ppq.ai/chat](https://ppq.ai/chat).
- **Automatic Model Discovery**: Automatically queries `GET /v1/models` on key save and page load to list all available PayPerQ router and generation models (`auto`, `autoclaw/eco`, `claude-sonnet-4.6`, `deepseek/deepseek-r1`, `openai/gpt-4o`, `google/gemini-2.5-flash`, etc.).
- **Smart Model Ranking**: Automatically organizes models with PayPerQ's smart auto-router (`auto`) and eco tier (`autoclaw/eco`) prioritized first, followed by frontier models.
- **Model Selection & Cascading**: Mark any discovered PayPerQ model as your Default (`★`) or assign it to Fallback slots (`1`, `2`, `3`).
- **In-Process FastMCP Tool Calling**: Full OpenAI-compatible streaming SSE multi-turn tool calling across all 32 read-only Kinetiqo telemetry and analytics tools.

### 4.10 MagnetAPI
- Unified OpenAI-compatible AI model gateway (`https://api.magnetapi.org/v1`) providing high-performance routing to leading frontier and open-weight models (Power AI auto-destination, ChatGPT 6.1 SOL, Claude Opus 5.5, Claude Sonnet 5.5, DeepSeek Flash, GPT-daybreak-blue-latest, etc.).
- **Automatic Model Discovery**: Queries `GET /v1/models` on key save and page load to automatically discover and list all available MagnetAPI generation models (`power-ai`, `gpt-6.1-sol`, `gpt-6-astra`, `claude-opus-5-5`, `claude-sonnet-5-5`, `deepseek-flash`, etc.).
- **Smart Model Ranking**: Prioritizes `power-ai` (auto-managed destination) first, followed by advanced reasoners (`gpt-6.1-sol`), frontier Claude models, and efficient coding models.
- **Model Selection & Cascading**: Mark any discovered MagnetAPI model as your Default (`★`) or assign it to Fallback slots (`1`, `2`, `3`).
- **In-Process FastMCP Tool Calling**: Full OpenAI-compatible streaming SSE multi-turn tool calling across all 32 read-only Kinetiqo telemetry and analytics tools.

### 4.11 Unified Provider Model Tables
- Gemini, OpenRouter, Vercel AI Gateway, Kilo AI Gateway, Poe, Ollama, Mistral AI, Anthropic Claude, PayPerQ, and MagnetAPI use the same columns in Settings: **Model Name & ID**, **Context**, **Capabilities**, **Pricing & Limits**, **Default**, and **Actions**.
- Values such as Gemini context and output-token limits, Mistral context sizes, Claude 200K context limits, or Ollama parameter size are shown when their provider reports them. Unavailable metadata is displayed as `-`; pricing and rate limits are never guessed.
- Remove actions are available only for providers with user-managed model lists (OpenRouter, Vercel, Kilo, Poe); discovered-model providers (Gemini, Ollama, Mistral, Anthropic, PayPerQ, MagnetAPI) show `-` in the Actions column.
- Settings communicates with unified parameterized REST endpoints (`/api/settings/ai/providers/<provider_id>`), enabling seamless addition of future backends with minimal adapter code and zero UI duplication.

### 4.12 Dynamic Mid-Session Provider & Model Switching
- Seamlessly change models or AI providers mid-conversation at any turn from the composer model selector.
- If a quota or rate limit is reached on OpenRouter, Vercel, Kilo, PayPerQ, or MagnetAPI, simply switch the selector to Google Gemini, Anthropic Claude, or your local Ollama model; Kinetiqo immediately routes the next query to the newly chosen provider and persists the updated configuration to the session.

### 4.13 Default Model & Multi-Model Automated Fallbacks
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

- **Collapsible Model Selector with Provider Sections**:
  - The model selection dropdown in `/chat` groups models cleanly under their respective AI provider (Google Gemini, OpenRouter, Vercel, Kilo, Mistral, Anthropic, etc.) with provider brand icons.
  - **Expand/Collapse Chevron Toggle**: A small expand/collapse icon at the far right of each provider header allows toggling provider visibility on demand.
  - **State Persistence via `localStorage`**: The collapsed/expanded state is saved in `localStorage` (`kinetiqo_chat_collapsed_providers`). Providers are expanded by default if no preference is stored.
  - **Accessible Keyboard Navigation**: Arrow Up / Arrow Down keyboard traversal dynamically skips collapsed groups so focus remains only on visible models.
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
    - When exporting responses via **Download HTML**, rendered charts are automatically converted to embedded high-resolution PNG data URLs (with crisp white backgrounds and high-contrast dark text/legends for optimal printing and reading) so saved reports remain 100% visual and offline-ready.
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
2. Click **"+ Add AI Provider"** and select **Google Gemini**, **OpenRouter AI**, **Vercel AI Gateway**, **Kilo AI Gateway**, **Poe**, **Ollama (Local AI)**, **Mistral AI**, **Anthropic Claude**, **PayPerQ**, or **MagnetAPI**.
3. Configure the provider:
   - **For Gemini**: Paste your API key; credentials are validated and models are automatically discovered.
   - **For Mistral AI**: Enter your Mistral API key; credentials are validated and available models are automatically discovered from Mistral's API.
   - **For Anthropic Claude**: Enter your Anthropic API key (`sk-ant-...`); credentials are authenticated against `api.anthropic.com/v1/models` and operational Claude models are discovered.
   - **For PayPerQ**: Enter your PayPerQ API key (from [ppq.ai/chat](https://ppq.ai/chat)); credentials are authenticated against `api.ppq.ai/v1/models` and operational generation models are automatically discovered.
   - **For MagnetAPI**: Enter your MagnetAPI key (from [magnetapi.org](https://magnetapi.org)); credentials are authenticated against `api.magnetapi.org/v1/models` and operational generation models are automatically discovered.
   - **For OpenRouter**: Enter your API key (validated against OpenRouter's auth endpoint), then use the nested models table to add your preferred models with real-time validation.
   - **For Vercel AI Gateway**: Enter your Vercel gateway API key (Bearer token, validated against Vercel models catalog), then use the nested models table to add your preferred models (e.g. `moonshotai/kimi-k2.6`) with real-time validation.
   - **For Kilo AI Gateway**: Enter your Kilo gateway API key (from [kilo.ai](https://kilo.ai), validated against Kilo catalog), then use the nested models table to add your preferred models (e.g. `kilo-auto/free`) with real-time validation.
   - **For Poe**: Enter your Poe API key (validated against Poe bot API), then add your bot handles (e.g. `GPT-4o`, `Claude-3.5-Sonnet`) with live handle validation.
   - **For Ollama**: Enter your Ollama server URL (e.g. `http://localhost:11434` or `http://192.168.1.150:11434`). Test the connection to auto-discover all pulled models. An API key is optional and validated if provided.
4. **Instant Authorization Verification & Error Feedback**:
   - On saving, credentials are authenticated with the upstream provider before being persisted. If authorization fails (e.g. invalid key, expired token, insufficient credits), the key is rejected without saving, the input field is highlighted in light red (`bg-red-50 dark:bg-red-950/40 border-red-400 dark:border-red-600`) and focused, and the exact upstream error message is displayed on the status pill.
   - Typing into the input field automatically clears the error highlighting.
   - If a stored key expires or is rejected on refresh, the card header and form status pills display the error in red and a warning dot appears next to the provider in the provider navigation list.
5. Return to **AI Chat** (`/chat`), select your desired model from the dropdown, and begin asking training questions.

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