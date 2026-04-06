---
layout: default
title: Web Interface
nav_order: 4
---

# Web Interface

Kinetiqo provides a modern, responsive web interface to manage and visualize your Strava activities. The interface is designed to be intuitive and powerful, offering advanced filtering, bulk operations, beautiful visualizations, and comprehensive activity analysis tools.

## Authentication & Security

- **Session-based authentication** using Flask-Login
- **Default login**: `admin` / `admin123` (set via `WEB_LOGIN` and `WEB_PASSWORD`)
- **Secure cookies** and session management
- **CSRF protection** and parameterized queries throughout

## Navigation & Pages

- **Activities**: Searchable/filterable DataTables grid, column reordering, export, bulk actions, map, Power Skills, CSV export
- **Map**: Interactive Leaflet.js map with multiple tile providers, Canvas renderer, and server-side proxy
- **Power Skills**: Spider chart of best average power (5s–1h), per-activity or aggregated
- **FTP**: FTP estimation history chart (95% of best 20-min power)
- **Fitness & Freshness**: CTL/ATL/TSB chart from suffer score
- **VO₂max**: VO₂max estimation from 5-min MAP power, with trend and classification
- **Settings**: Athlete profile, activity goals, app config, schedule monitoring
- **Logs**: Audit log viewer for sync/data changes
- **License**: Open-source licenses, map tile attributions
- **Login**: Session-based authentication

## Key Features

- **Advanced Activity Table**: Sortable, filterable, column management, responsive design
- **Bulk Operations**: Select/deselect all, delete, export, map, Power Skills
- **Live Totals**: Aggregated stats for filtered activities
- **Strava Integration**: Direct links to Strava.com
- **Comprehensive Data**: Power, heart rate, temperature, elevation, gear, achievements
- **Spider Chart**: Power Skills analysis for cycling activities
- **Charts**: Fitness & Freshness, FTP, VO₂max, goals
- **Interactive Maps**: Multi-provider, Canvas renderer, PNG export
- **Dark Mode**: System preference detection and manual toggle
- **HTMX**: Real-time sync progress via SSE
- **Audit Logging**: All sync/data changes viewable in Logs
- **Responsive Design**: Optimized for all devices
- **Performance**: Gzip/brotli compression, client-side DataTables, efficient SQL
- **Security**: CSRF, SQL injection prevention, session security
- **Browser Compatibility**: Modern standards, CDN dependencies

## Advanced Features

- **Real-time Sync Progress**: SSE-powered progress bar during sync
- **Map Tile Proxy**: Satisfies OSM usage policy, API key support for Mapy.cz/Thunderforest
- **Version Check**: Asynchronous, cached check for new releases
- **Settings Page**: Schedule monitoring, database info, system status
- **Logs Page**: Operation history, error visibility, recent activity

## Tips

- All internal navigation stays in the same tab. Only external links open in a new tab.
- Map layers requiring API keys appear greyed-out until configured.
- All features are available in both light and dark mode.

For a full walkthrough of each page and feature, see the sidebar or visit the [official documentation](https://kinetiqo.lhotak.net).
