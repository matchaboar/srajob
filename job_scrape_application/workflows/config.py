from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv


load_dotenv()


@dataclass
class Settings:
    temporal_address: str = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    temporal_namespace: str = os.getenv("TEMPORAL_NAMESPACE", "default")
    task_queue: str = os.getenv("TEMPORAL_TASK_QUEUE", "scraper-task-queue")

    # Convex base URL where HTTP router is served, e.g. "http://localhost:4000" or
    # "https://<deployment>.convex.cloud". The workflow appends /api/... routes.
    convex_http_url: str | None = os.getenv("CONVEX_HTTP_URL")

    # API key for FetchFox SDK
    fetchfox_api_key: str | None = os.getenv("FETCHFOX_API_KEY")


settings = Settings()

