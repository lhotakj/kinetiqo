---
layout: default
title: Home
nav_order: 1
---
<div class="video-crop">
  <video class="full-width-video" loop autoplay muted>
    <source src="{{ '/assets/promo.mov' | relative_url }}" type="video/mp4">
    Your browser does not support the video tag.
  </video>
</div>


**Kinetiqo** is a self-hosted data warehouse for your Strava activities. It synchronizes your data into a high-performance SQL database (**PostgreSQL**, **MySQL/MariaDB**, or **Firebird**), providing full ownership and control over your fitness history.

Visualize your progress with the **built-in Web UI** or integrate with your preferred business intelligence tools. For advanced analytics, Kinetiqo includes pre-configured **Grafana dashboards**, transforming your workout data into actionable insights.

## Features

- **Advanced Visualization**: A streamlined web interface for daily monitoring and comprehensive Grafana dashboards for in-depth analysis.
- **Audit Logging**: Records all synchronization operations and data modifications, providing a complete audit trail within the Web UI.
- **Intelligent Synchronization**:
  - **Full Synchronization**: Conducts a comprehensive audit of your Strava history, retrieving all activities and reconciling any deletions.
  - **Incremental Synchronization**: Efficiently retrieves only the most recent activities, optimized for frequent updates.
- **Container-Native**: Architected for Docker environments, facilitating seamless integration into existing infrastructure.
- **Automated Scheduling**: Includes a built-in cron scheduler to ensure data currency without manual intervention.
- **Database Compatibility**:
  - **PostgreSQL** (version 18.0+)
  - **MySQL** (version 8.0+) / **MariaDB** (version 12.0+)
  - **Firebird** (versions 3.0+)
- **Performance Optimization**: Utilizes intelligent caching strategies to minimize API consumption and accelerate data retrieval.
- **Security**: Implements standard OAuth 2.0 protocols to safeguard user credentials.

