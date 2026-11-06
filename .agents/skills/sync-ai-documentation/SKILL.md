---
name: sync-ai-documentation
description: Automatically synchronizes AI Chat features, OpenRouter/Gemini provider specs, and user docs between code, docs/concepts/ai-concept.md, and docs/AI.md.
---

# AI Documentation & Feature Synchronization Skill

This skill enforces strict, automatic synchronization between Kinetiqo AI implementation code, the authoritative technical specification ([docs/concepts/ai-concept.md](file:///H:/WORKING/kinetiqo/docs/concepts/ai-concept.md)), and the user-facing feature guide ([docs/AI.md](file:///H:/WORKING/kinetiqo/docs/AI.md)).

Whenever an AI coding agent analyzes, creates, or modifies any AI-related code or configuration in Kinetiqo, it **MUST automatically execute this synchronization protocol before concluding the turn**.

---

## 1. Triggers for Automatic Synchronization

Apply this skill whenever a change touches:
1. **AI Chat Backend & Providers**:
   - `src/kinetiqo/chat/` (service, models, repository, encryption, context, tools, providers).
   - Gemini provider (`src/kinetiqo/chat/providers/gemini.py`) or OpenRouter provider (`src/kinetiqo/chat/providers/openrouter.py`).
2. **FastMCP & Telemetry Tools**:
   - `src/kinetiqo/mcp/tools/` (discovery, allowlists, power skills, physiology, filters).
   - `src/kinetiqo/mcp/prompts.py` (coaching workflows and evaluation templates).
3. **Web Interfaces**:
   - AI Chat UI: `src/kinetiqo/web/templates/chat.html`, `src/kinetiqo/web/static/js/chat.js`.
   - Settings UI: `src/kinetiqo/web/templates/settings.html` (AI provider cards, API key inputs, model tables).
   - Routes: `src/kinetiqo/web/app.py` (`/chat`, `/api/chat/*`, `/api/settings/ai/*`).
4. **Database & Schema**:
   - `src/kinetiqo/db/schema.py` and `src/kinetiqo/chat/repository.py` (`chat_provider_keys`, `chat_sessions`, `chat_messages`).

---

## 2. Mandatory Synchronization Checklist

Before finishing any task touching AI components, complete the following verification steps:

### Check 1: Update Authoritative Specification (`docs/concepts/ai-concept.md`)
- [ ] Reflect newly added or updated provider adapters (e.g., OpenRouter, Gemini).
- [ ] Document changes to the Settings UI layout (e.g. "+ Add AI provider", nested model management tables with `+` and `-` buttons, live API validation).
- [ ] Document any new read-only tools added to the allowlist or changes to `CYCLING_SPORT_TYPES` filtering.
- [ ] Keep the request lifecycle, token usage formats, and database persistence schemas updated across PostgreSQL, MySQL, and Firebird.

### Check 2: Update User Feature Excerpt (`docs/AI.md`)
- [ ] Verify that feature descriptions match the real code (capabilities, provenance toggle behavior, model dropdown options).
- [ ] Ensure the OpenRouter and Gemini configuration steps reflect the actual `/settings` page controls.
- [ ] Keep the list of available tools and coaching workflows synchronized with `src/kinetiqo/mcp/prompts.py`.
- [ ] Ensure security rules (read-only gates, AES-256-GCM encryption, private self-hosting) are clearly stated.

### Check 3: UI & Design Consistency Standard
- [ ] Chat composer animation uses the pure 4-brand-color palette (`#df3c57`, `#e07d4b`, `#efc65e`, `#49ae9f`).
- [ ] Assistant message footer maintains the 1px top border (`#e5e7eb` in light mode, `#3f3f46` in dark mode) and right-aligned unified metadata row (`text-xs text-gray-500 dark:text-zinc-400`).
- [ ] Expanded "Data used" queries div has zero background or borders, with high-contrast text across both themes.
- [ ] Model management in Settings displays models in a responsive table with `+` and `-` buttons (no trash bin icon).

### Check 4: Automated Testing Verification
- [ ] Run isolated mocked unit tests with no live network or database calls:
  ```bash
  cmd /c "set PYTHONPATH=src && uv run --with-requirements requirements.txt python -m unittest discover -s tests -p test_chat*.py -v"
  ```
- [ ] Ensure all mock assertions reflect updated prompt lengths or tool counts (e.g. `test_mcp_server.py`).

---

## 3. Provider Contract Reference

| Provider | Base URL | Auth Header | Tool Calling Schema | Model Discovery / Validation |
|---|---|---|---|---|
| **Google Gemini** | Google REST API | `x-goog-api-key` | Gemini JSON Schema | Dynamic via `models.list` API |
| **OpenRouter AI** | `https://openrouter.ai/api/v1` | `Authorization: Bearer <KEY>` | Standard OpenAI functions (`tools`) | Model ID validated against OpenRouter catalog |
| **Vercel AI Gateway** | `https://ai-gateway.vercel.sh/v1` | `Authorization: Bearer <KEY>` | Standard OpenAI functions (`tools`) | Model ID validated against Vercel catalog |
| **Kilo AI Gateway** | `https://api.kilo.ai/api/gateway` | `Authorization: Bearer <KEY>` | Standard OpenAI functions (`tools`) | Model ID validated against Kilo catalog |
| **Ollama** | Configurable local URL | Optional Bearer key | OpenAI-compatible functions | Dynamic model discovery from local server |

---

## 4. Multi-Provider Settings Standard

In `src/kinetiqo/web/templates/settings.html`:
- Keep all providers in one provider selector and follow the existing provider adapter, settings API, and model-discovery conventions when adding a provider.
- Render every provider's model list with the same columns and order: **Model Name & ID**, **Context**, **Capabilities**, **Pricing & Limits**, **Default**, **Actions**.
- Use only provider-supplied/documented metadata; display `-` for missing values, especially pricing, model limits, and rate quotas. Never infer them.
- Show remove actions only for user-managed model lists; use `-` for discovered, non-removable models while retaining the shared table layout.
- Add mocked tests for metadata normalization, endpoint serialization/persistence, and the settings table contract, then update both `docs/concepts/ai-concept.md` and `docs/AI.md`.
