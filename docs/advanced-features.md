---
layout: default
title: Advanced Features
nav_order: 97
---

# Advanced Features

This page highlights advanced and power-user features in Kinetiqo.

## Power Skills Analysis
- Spider chart of best average power over 5s–1h durations
- Per-activity or aggregated across multiple activities
- Source activity identification, Strava links, and performance categories

## FTP & VO₂max Estimation
- FTP: 95% of best 20-min average power, with history chart
- VO₂max: Townsend method from 5-min MAP power, with trend and classification bands

## Fitness & Freshness (CTL/ATL/TSB)
- Calculated from suffer score using pandas
- Configurable time constants
- Visualized as a time series chart

## Activity Goals
- Set weekly, monthly, yearly distance/elevation goals per activity type
- Progress tracking and goal management in the Settings page

## Real-time Sync Progress
- Server-Sent Events (SSE) for live sync progress bar
- HTMX-powered reactivity for smooth UI updates

## Map Tile Proxy & API Keys
- Multiple map tile providers (OpenStreetMap, Mapy.cz, Thunderforest, CARTO, Esri)
- Server-side proxy for OSM tiles (satisfies usage policy)
- API key support for Mapy.cz and Thunderforest
- Greyed-out layers if API key missing

## Response Compression
- All HTTP responses (HTML, JSON, static) compressed via flask-compress (gzip/brotli)
- Reduces transfer sizes by 74–99%

## Version Check
- Asynchronous, cached check for new releases against GitHub
- Notification in the web UI if a new version is available

## Security & Audit Logging
- All sync/data changes are logged and viewable in the Web UI
- Session-based authentication with flask-login
- CSRF protection, parameterized SQL, secure cookies

## Customization & Extensibility
- All configuration via environment variables
- Add new database backends or web features via the repository/factory pattern
- Frontend libraries loaded via CDN, no build step required

For more, see [Configuration](configuration.md), [Web Interface](web.md), and [Architecture](architecture.md).

