# Kinetiqo Documentation

This directory contains the official documentation website for Kinetiqo.

## Overview

The documentation site features:
- **Dark Theme Design** - Inspired by GitHub Docs with a professional dark background
- **Collapsible Navigation** - Three main sections: Getting Started, How-tos, and References
- **Responsive Layout** - Works seamlessly on desktop, tablet, and mobile devices
- **Smooth Scrolling** - Enhanced navigation with smooth scroll behavior
- **Strava Integration** - Visual branding and references to Strava API

## Local Development

To preview the documentation locally:

```bash
cd docs
python3 -m http.server 8080
```

Then open your browser and navigate to `http://localhost:8080/`

## File Structure

```
docs/
├── index.html          # Main documentation page
├── css/
│   └── styles.css      # Dark theme styling
├── js/
│   └── navigation.js   # Collapsible navigation and smooth scrolling
└── README.md           # This file
```

## Deployment

The documentation is designed to be hosted on **kinetiqo.lhotak.net** via Cloudflare Pages.

### Cloudflare Pages Setup

1. Log into your Cloudflare account
2. Go to Pages section
3. Create a new project
4. Connect your GitHub repository (lhotakj/kinetiqo)
5. Set the build settings:
   - **Build command**: (leave empty - static site)
   - **Build output directory**: `docs`
   - **Branch**: `main` or your preferred branch

### Custom Domain

The site is configured to work with the domain `kinetiqo.lhotak.net`. Update DNS settings in Cloudflare:

1. Add a CNAME record pointing to your Cloudflare Pages deployment
2. Enable HTTPS (automatic with Cloudflare)

## Features

### Navigation Sections

#### Getting Started
- Installation
- Quick Start
- Configuration

#### How-tos
- Sync Activities
- Database Setup
- Docker Deployment

#### References
- API Reference
- Environment Variables
- Troubleshooting

### Design Elements

- 🚀 **Logo Icon** - Rocket emoji representing speed and innovation
- **Strava Logo** - SVG logo in the hero section
- **Feature Cards** - Highlighting key features with icons
- **Code Blocks** - Syntax-highlighted code examples
- **Footer** - Copyright and links to GitHub and domain

## Technologies

- Pure HTML5
- CSS3 with CSS Variables for theming
- Vanilla JavaScript (no frameworks required)
- Responsive design with CSS Grid and Flexbox

## Browser Support

The documentation site supports all modern browsers:
- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)
- Mobile browsers (iOS Safari, Chrome Mobile)

## Contributing

To update the documentation:

1. Edit `index.html` for content changes
2. Modify `css/styles.css` for styling updates
3. Update `js/navigation.js` for navigation behavior
4. Test locally before committing
5. Submit a pull request

## License

Copyright © 2026 Kinetiqo. All rights reserved.
