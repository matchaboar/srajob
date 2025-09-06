---
trigger: always_on
---

# Rules
- This is a powershell 7 shell on Windows. This is not BASH. Do not use BASH commands.
- If you need to use python, use `uv` and not python/pip commands. Example: `uv run` or `uv add`

# Frontend Code Structure
- The UI is in job_board_application.
- The components job_board_application/src

# Data & Storage
- The database is in job_board_application
- The database is convex and its configuration is in job_board_application/convex

# Job Scrape Application
- The scrape workflow logic is in job_scrape_application
- This should use temporal for workflows
- Data should be stored in the convex database in job_board_application