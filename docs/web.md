---
layout: default
title: Web Interface
nav_order: 4
---

# Web Interface

Kinetiqo provides a modern, responsive web interface to manage and visualize your Strava activities. The interface is designed to be intuitive and powerful, offering advanced filtering, bulk operations, beautiful visualizations, and comprehensive activity analysis tools.

## Authentication

The web interface requires authentication using configurable credentials:
- **Default Login**: `admin` / `admin123`
- **Configuration**: Set via `WEB_LOGIN` and `WEB_PASSWORD` environment variables
- **Session Management**: Uses Flask-Login for secure session handling

## Navigation

The main navigation is located on the left sidebar (or top on mobile devices) and provides access to the core features:

### Activities

The **Activities** page is the central dashboard of Kinetiqo. It displays a comprehensive list of your synchronized activities and provides powerful tools for management and analysis.

**Key Features:**

*   **Advanced Activity Table**: 
    *   **Sortable Columns**: Click any column header to sort (ID, Name, Type, Date, Distance, Elevation, Moving Time, Speed, Heart Rate, Power metrics, etc.)
    *   **Column Management**: Use "Select columns" to customize which data fields are displayed
    *   **Column Reordering**: Drag and drop column headers to reorder the table layout
    *   **Responsive Design**: Table adapts to different screen sizes with horizontal scrolling on mobile
*   **Comprehensive Filtering**:
    *   **Search**: Filter activities by name using the search bar
    *   **Date Filters**: Choose from presets (Today, Yesterday, This Week, Last 7 Days, This Month, This Year, etc.) or select custom date ranges
    *   **Activity Type Filters**: Multi-select dropdown to filter by specific activity types (Ride, Run, Hike, Swim, etc.)
    *   **Real-time Filtering**: All filters apply instantly without page reloads
*   **Bulk Operations**:
    *   **Selection Tools**:
        - **Select/Deselect All**: Toggle selection for all visible activities on current page
        - **Select All on All Pages**: Select every activity matching current filters across the entire database
        - **Clear Selection**: Reset all selections
    *   **Data Actions**:
        - **Delete Selected**: Permanently remove selected activities from the local database with confirmation
        - **Export to CSV**: Download selected activities' data as CSV for external analysis
    *   **Visualization Actions**:
        - **Display on Map**: Visualize GPS tracks of selected activities on an interactive map
        - **Power Skills**: Analyze power performance across different time intervals (cycling activities with power data)
*   **Live Totals**: View aggregated statistics (total distance, elevation gain, and moving time) for currently filtered activities
*   **Strava Integration**: Direct links to view each activity on Strava.com
*   **Comprehensive Data Display**: Shows detailed metrics including power data (average watts, max watts, weighted average), heart rate, temperature, elevation profiles, gear information, and achievement counts

### Power Skills ⚡

The **Power Skills** page provides advanced power analysis for cycling activities, similar to Strava's power curve visualization.

**Features:**

*   **Spider Chart Visualization**: Interactive radar chart showing best average power across different time intervals
*   **Multiple Duration Analysis**: Analyzes power across 13 different time intervals:
    - Sprint durations: 5s, 15s, 30s
    - Attack durations: 1m, 2m, 3m, 5m
    - Endurance durations: 10m, 15m, 20m, 30m, 45m, 60m
*   **Detailed Data Table**: 
    - Best average power for each duration
    - Performance categories (Sprint, Attacks, Endurance)
    - Source activity identification with Strava links
    - Activity dates and names
*   **Multi-Activity Analysis**: Computes best power across all selected activities
*   **Power Meter Requirement**: Requires activities recorded with power meter devices
*   **Dark Mode Support**: Fully compatible with light and dark themes

### Full Sync

The **Full Sync** page allows you to perform a complete synchronization with the Strava API, ideal for initial setup or comprehensive data updates.

**Features:**

*   **Flexible Scope Control**: 
    - **Dynamic Time Limits**: Choose from intelligently calculated presets (This Week, This Month, Last 2 Months, Last 6 Months, This Year, Last Year, Last 2 Years)
    - **All-Time Sync**: Option to sync entire Strava history
    - **Adaptive Calculations**: Time periods adjust based on current date
*   **Real-time Progress**: 
    - **Server-Sent Events (SSE)**: Live streaming of sync progress without page refreshes
    - **Detailed Logging**: Shows activities being processed, API responses, database operations
    - **Error Handling**: Displays detailed error messages and retry attempts
*   **Rate Limit Management**: Automatically handles Strava API rate limits with exponential backoff
*   **Stop Control**: Ability to cancel ongoing sync operations
*   **Comprehensive Processing**: 
    - Fetches activity metadata and detailed GPS/sensor streams
    - Performs intelligent diffing to avoid duplicate data
    - Handles activity deletions and updates

### Fast Sync

The **Fast Sync** page is optimized for frequent updates, checking only for recent activities.

**Features:**

*   **Incremental Updates**: Efficiently fetches only new activities since last sync
*   **Quick Execution**: Designed for daily or frequent automated updates
*   **Real-time Progress**: Same SSE-powered live progress as Full Sync
*   **Smart Timing**: Automatically determines appropriate time range based on last sync

### Activity Map

The **Activity Map** is a powerful GPS visualization tool accessed by selecting activities and clicking "Display on map".

**Features:**

*   **Modern Mapping Technology**:
    - **Leaflet.js**: Interactive mapping with smooth pan/zoom
    - **Canvas Rendering**: High-performance rendering of GPS tracks
    - **Gzip Compression**: Efficient data transfer for large datasets
*   **Customization Options**:
    - **Multiple Base Maps**: OpenStreetMap, CartoDB (Light/Dark), Esri World Imagery
    - **Route Styling**: Adjustable color, line width, and opacity
    - **Real-time Updates**: Changes apply instantly without reloading
*   **Advanced Features**:
    - **Multi-Activity Overlay**: Display multiple routes simultaneously
    - **Automatic Bounds**: Map automatically zooms to fit all selected activities
    - **PNG Export**: Download high-quality map images for sharing
    - **Progress Tracking**: Shows data download and rendering progress
*   **Performance Optimized**: Handles large datasets with progressive loading and efficient rendering

### Logs

The **Logs** page provides comprehensive audit trails and system transparency.

**Features:**

*   **Operation History**: Complete record of all sync operations and system activities
*   **Detailed Tracking**: 
    - Timestamps with user-friendly formatting
    - Action types (sync, delete, bulk operations)
    - Activity counts (added/removed)
    - Trigger sources (web interface, scheduled cron, CLI)
    - User attribution and success status
*   **Recent Activity**: Shows latest 25 operations for quick system health monitoring
*   **Error Visibility**: Failed operations clearly marked with error details

### Settings

The **Settings** page displays current system configuration and operational status.

**Features:**

*   **Schedule Monitoring**:
    - Current cron expressions for Full Sync and Fast Sync
    - Human-readable schedule descriptions (e.g., "Daily at 02:00", "Every 6 hours")
    - Schedule status and next execution times
*   **Database Information**:
    - Active database type (PostgreSQL, MySQL, or Firebird)
    - Connection details (host, port)
    - Table record counts for activities, streams, and logs
*   **System Status**: Overview of current configuration and operational parameters

## Technical Features

### User Experience
*   **Responsive Design**: Optimized for desktop, tablet, and mobile devices
*   **Dark Mode Support**: Automatic detection of system preference with manual toggle
*   **HTMX Integration**: Smooth, JavaScript-enhanced interactions without full page reloads
*   **Progressive Enhancement**: Core functionality works without JavaScript

### Performance & Caching
*   **Static Asset Optimization**: 1-year browser caching for CSS/JS with version-based cache busting
*   **Gzip Compression**: Automatic compression for large data transfers
*   **Efficient Database Queries**: Optimized SQL with proper indexing and pagination
*   **Client-side Processing**: DataTables for responsive sorting and filtering

### Security & Reliability
*   **CSRF Protection**: Built-in request verification
*   **SQL Injection Prevention**: Parameterized queries throughout
*   **Session Security**: Secure cookie handling and session management
*   **Error Handling**: Graceful degradation and user-friendly error messages

### Browser Compatibility
*   **Modern Standards**: Built with current web standards for optimal performance
*   **Progressive Enhancement**: Graceful fallback for older browsers
*   **CDN Dependencies**: Reliable external resources with fallback handling

The web interface represents a comprehensive solution for fitness data management, combining powerful analytical tools with an intuitive user experience that scales from casual users to serious athletes requiring detailed performance analysis.
