"""Temporal workflows and worker entrypoints for scraping jobs.

This package defines a scheduled workflow that:
- Reads the list of sites to scrape from Convex (HTTP route: /api/sites)
- Uses FetchFox to scrape pages and collects items
- Stores raw scrape results back into Convex (HTTP route: /api/scrapes)
"""

