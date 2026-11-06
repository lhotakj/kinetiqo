---
name: sync-documentation
description: Automatically audits and synchronizes Kinetiqo documentation across docs/, docs/concepts/, docs/usage.md, and README.md whenever features, routes, CLI commands, or schemas are added or modified.
---

# Kinetiqo Documentation Synchronization Skill

This skill enforces strict, automatic synchronization between Kinetiqo codebase changes and the project's documentation hierarchy across `docs/`, `docs/concepts/`, `docs/usage.md`, and `README.md`.

Whenever an AI coding agent or developer creates, modifies, or deprecates any feature, route, CLI command, configuration parameter, or database schema in Kinetiqo, it **MUST automatically execute this synchronization protocol before concluding the turn**.

---

## 1. Documentation Architecture & Rules

The Kinetiqo documentation follows a strict 4-tier hierarchy:

1. **`README.md` (Landing Hub & Showcase)**:
   - Must remain **concise** (~150–250 lines).
   - Serves as the landing page, visual showcase, and navigation hub.
   - Summarizes features in 1–2 sentences and links directly to `docs/<feature>.md`.
   - Never embed hundreds of lines of environment variables or verbose deployment templates into `README.md`.

2. **`docs/<feature>.md` (Authoritative Feature Guides)**:
   - Every single feature has its own dedicated, comprehensive markdown document.
   - Must adhere to the **Standardized Feature Structure** (see Section 3 below) to serve as a reliable source for regenerating the marketing website (`site/`).

3. **`docs/concepts/<concept>-concept.md` (Technical Specifications & Math)**:
   - **All architectural plans, mathematical derivations, algorithms, and deep concepts belong strictly in `docs/concepts/`**.
   - Under no circumstances should loose concept or plan files (`*-concept.md`, `*-plan.md`, `AI-try-*.md`) reside in the root repository directory or the root of `docs/`.

4. **`docs/usage.md` (Central Deployment & Configuration Guide)**:
   - Single authoritative source for running Kinetiqo across Docker, Docker Compose, and native Python.
   - Contains the complete `.env` environment variables reference table and production reverse-proxy configurations.

5. **Eliminate Duplications**:
   - Never duplicate feature content across multiple files.
   - If a concept exists in `docs/concepts/`, the feature guide in `docs/` must link to it rather than duplicating its content.

---

## 2. Triggers for Automatic Synchronization

Apply this skill whenever a change touches:

| Code Area Modified | Documentation Target to Update |
|---|---|
| **Web UI Routes & Templates** (`src/kinetiqo/web/`) | Corresponding `docs/<feature>.md` (e.g. `docs/activities.md`, `docs/maps.md`, `docs/poster.md`, `docs/mega-stats.md`, `docs/FONDO_O_METER.md`) |
| **CLI Commands** (`src/kinetiqo/cli.py`) | `docs/cli.md` (update options, commands, and examples) |
| **Environment Variables** (`src/kinetiqo/config.py`) | `docs/usage.md` (table in Section 5) and relevant `docs/<feature>.md` |
| **Database Schemas & Repositories** (`src/kinetiqo/db/`) | `docs/DATABASE.md` and feature docs relying on table schema changes |
| **Sync Engine & Worker Logic** (`src/kinetiqo/sync.py`) | `docs/sync.md` (update phases, rate limits, or options) |
| **Weather Enrichment** (`src/kinetiqo/weather.py`) | `docs/weather.md` and `docs/concepts/weather-concept.md` |
| **Model Context Protocol (MCP)** (`src/kinetiqo/mcp/`) | `docs/MCP.md` and `docs/concepts/mcp-concept.md` |
| **AI Chat & Providers** (`src/kinetiqo/chat/`) | `docs/AI.md` and `docs/concepts/ai-concept.md` |
| **Dockerfiles & Compose** (`Dockerfile*`, `docker-compose.yml`) | `docs/usage.md` |

---

## 3. Standardized Feature Documentation Template

To ensure all feature documents serve as structured, machine-parsable sources for generating the marketing website, every file in `docs/<feature>.md` must follow this structure:

```markdown
# [Feature Name]

[One-sentence elevator pitch describing the feature and its value.]

---

## 1. Overview & Capabilities
- Bulleted list of key user-facing capabilities, highlights, and unique strengths.

---

## 2. Technical Details / Algorithms / Under the Hood
- Physiological models, mathematical formulas, algorithms, or ETL workflows.
- Link to `docs/concepts/<feature>-concept.md` if deep specification exists.

---

## 3. Web UI & Interactive Controls
- Page routes, controls, sliders, color pickers, modals, or shortcuts.
- `localStorage` state persistence keys and defaults.

---

## 4. Web Routes & API Endpoints
| URL Route / Endpoint | Method | Purpose |
|---|---|---|
| ... | ... | ... |

---

## 5. Configuration & Environment Variables
| Variable | Type | Default | Description |
|---|---|---|---|
| ... | ... | ... | ... |

---

## 6. MCP & AI Integration
- Model Context Protocol tools exposed for AI assistants.

---

## 7. Visual Artifacts
- List of related screenshot assets (`docs/*.webp`).
```

---

## 4. Synchronization Verification Checklist

Before finishing any task, run through this mental checklist:

- [ ] **Did I add/modify an environment variable?** If yes, update `docs/usage.md` Section 5.
- [ ] **Did I add/modify a CLI command or flag?** If yes, update `docs/cli.md`.
- [ ] **Did I modify a web route, API endpoint, or UI control?** If yes, update the matching `docs/<feature>.md`.
- [ ] **Did I create a new concept, design, or architecture plan?** If yes, place it strictly in `docs/concepts/`.
- [ ] **Is `README.md` still concise and referencing the updated docs?**
- [ ] **Are there any duplicated markdown files in the repository?** If yes, delete the obsolete duplicates.

