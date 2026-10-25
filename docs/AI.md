# Kinetiqo AI Chat — Feature & Telemetry Guide

> **Version:** 3.0  
> **Status:** Active / Production Ready  
> **Primary Interfaces:** `/chat`, `/settings`, FastMCP tools layer  
> **Supported Providers:** Google Gemini, OpenRouter AI, Vercel AI Gateway, Ollama (Local AI)  
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

### 2.3 Pre-Built Athlete Coaching Workflows
Integrated prompt workflows in `src/kinetiqo/mcp/prompts.py` equip the AI with structured evaluation frameworks:
1. **Recovery & Freshness Audit**: Evaluates TSB (Form) vs ATL (Fatigue) and CTL (Fitness).
2. **VO₂max & FTP Progression**: Analyzes 5-min MAP power trend lines and 95% 20-min FTP steps.
3. **Indoor vs. Outdoor Load Analysis**: Dissects cadence, normalized power, and heart rate divergence.
4. **Climbing & Elevation Breakdown**: VAM (vertical ascent in meters/hour) and sustained hill-climb pacing.
5. **Gran Fondo & Milestone Audit**: Century rides, marathon efforts, and long-range endurance consistency.

---

## 3. Privacy, Isolation & Security

1. **100% Self-Hosted & Scoped**: All telemetry queries execute against the local database, strictly isolated to the authenticated athlete (`athlete_id = current_user.id`).
2. **Encrypted Provider Keys**: External API keys are encrypted at rest using **AES-256-GCM** with an envelope key derived via HKDF-SHA256. API keys are never rendered in HTML, logged, or sent to the browser.
3. **Hard Read-Only Safety Gates**: Mutating actions (triggering Strava sync, updating Strava activity descriptions, altering athlete FTP/weight) are **strictly forbidden** from the chat tool allowlist. The AI cannot modify athlete records.
4. **No Third-Party Analytics Trackers**: Responses stream directly from the chosen AI provider API over secure HTTPS/TLS to your private Kinetiqo server, then to your browser via Server-Sent Events (SSE).

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
- **Live Model Validation**: Automatically validates model IDs against OpenRouter's metadata API, fetching context lengths and capabilities.
- **Flexible Management**: Add (`+`) or remove (`-`) models on the fly in Settings.

### 4.3 Vercel AI Gateway
- Unified OpenAI-compatible edge gateway (`https://ai-gateway.vercel.sh/v1`) providing low-latency routing to leading open-weight and frontier models (Moonshot AI Kimi, Meta Llama, DeepSeek, Anthropic, OpenAI, etc.).
- **Custom Curated Model List**: Enter any Vercel AI Gateway model identifier (e.g. `moonshotai/kimi-k2.6`, `meta/llama-3.3-70b`, `deepseek/deepseek-r1`, `anthropic/claude-haiku-4.5`, `openai/gpt-4o`).
- **Live Model Validation**: Automatically validates entered model IDs against Vercel's models API (`GET /v1/models/{model_id}` or catalog `/v1/models`), checking context window capacity, tool-calling support, and vision capabilities.
- **Fuzzy Model Suggestions**: If the organization prefix is omitted (e.g. `kimi-k2.6`), Kinetiqo searches the Vercel model catalog and suggests the exact canonical ID (`moonshotai/kimi-k2.6`) with a single-click suggestion button.
- **Flexible Management**: Add (`+`) or remove (`-`) configured models from the responsive table in Settings.

### 4.4 Ollama (Local Hardware AI)
- **100% Private On-Premise Inference**: Connect to models running on your own PC or homelab server via Ollama's OpenAI-compatible API.
- **Automatic Model Discovery**: Detects all locally installed models (`qwen3:1.7b`, `qwen2.5:7b-instruct`, `llama3.1:8b`, etc.) without manual configuration.
- **Optional API Token**: No API key is required on your local network. An optional token field is available if Ollama is hosted behind a reverse proxy.
- **Remote Host Setup**: To connect across machines on your LAN, set `OLLAMA_HOST=0.0.0.0:11434` on the Ollama PC and provide its local IP (e.g. `http://192.168.1.150:11434`).

### 4.5 Dynamic Mid-Session Provider & Model Switching
- Seamlessly change models or AI providers mid-conversation at any turn from the composer model selector.
- If a quota or rate limit is reached on OpenRouter or Vercel, simply switch the selector to Google Gemini or your local Ollama model; Kinetiqo immediately routes the next query to the newly chosen provider and persists the updated configuration to the session.

---

## 5. Web UI Features & Ergonomics (`/chat`)

- **Interactive Sidebar History**:
  - Full conversation persistence with automatic date-based sorting.
  - Hover deletion (`×`) to prune individual sessions instantly.
  - "+ New chat" button adhering to Kinetiqo's primary action button standards.
- **Dynamic Composer Animation**:
  - Rotating frame border utilizing Kinetiqo brand colors (`#df3c57`, `#e07d4b`, `#efc65e`, `#49ae9f`) during live response streaming.
- **Streamlined Message Footer**:
  - Crisp 1px top border separator in both light (`#e5e7eb`) and dark (`#3f3f46`) modes.
  - Unified right-aligned metadata row: `[Data used (X queries) ▾] · [Tokens: X in · Y out · Zs] · [Download response]`.
  - Transparent, distraction-free provenance view with high-contrast text.
- **Markdown & Code Rendering**:
  - Tables, mathematical formulas, bullet points, and code blocks rendered smoothly with auto-sanitization.
  - One-click Markdown export (`Download response`).

---

## 6. Configuration in Settings (`/settings`)

1. Navigate to **Settings** (`/settings`) → **AI & API Providers**.
2. Click **"+ Add AI Provider"** and select **Google Gemini**, **OpenRouter AI**, **Vercel AI Gateway**, or **Ollama (Local AI)**.
3. Configure the provider:
   - **For Gemini**: Paste your API key; models are automatically discovered.
   - **For OpenRouter**: Enter your API key, then use the nested models table to add your preferred models with real-time validation.
   - **For Vercel AI Gateway**: Enter your Vercel gateway API key (Bearer token), then use the nested models table to add your preferred models (e.g. `moonshotai/kimi-k2.6`) with real-time validation.
   - **For Ollama**: Enter your Ollama server URL (e.g. `http://localhost:11434` or `http://192.168.1.150:11434`). Test the connection to auto-discover all pulled models. An API key is optional.
4. Return to **AI Chat** (`/chat`), select your desired model from the dropdown, and begin asking training questions.

## 7. Free models

If you want verified 100% free models currently active on OpenRouter:
- `google/gemma-4-26b-a4b-it:free` (262k context, tools + multimodal vision support)
- `nvidia/nemotron-3.5-lightning:free` (131k context, tools support)

If you want DeepSeek: `deepseek/deepseek-chat`