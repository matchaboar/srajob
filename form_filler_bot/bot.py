from pathlib import Path
from typing import Any, Dict, Optional

import httpx
import yaml


class FormFillerBot:
    """Handles resume data and job application queueing."""

    def __init__(self, convex_url: str) -> None:
        self.convex_url = convex_url.rstrip("/")

    def load_resume(self, path: Path) -> Dict[str, Any]:
        """Load resume information from a YAML file."""
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    def store_resume(self, resume: Dict[str, Any]) -> None:
        """Send resume data to the convex backend."""
        httpx.post(f"{self.convex_url}/api/resume", json=resume)

    def queue_application(self, job_url: str) -> None:
        """Queue a job application for form filling."""
        httpx.post(
            f"{self.convex_url}/api/form-fill/queue", json={"jobUrl": job_url}
        )

    def next_application(self) -> Optional[Dict[str, Any]]:
        """Fetch the next queued job application, if any."""
        resp = httpx.get(f"{self.convex_url}/api/form-fill/next")
        if resp.status_code != 200 or not resp.content:
            return None
        data = resp.json()
        return data or None
