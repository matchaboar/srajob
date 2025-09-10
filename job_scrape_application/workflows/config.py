from __future__ import annotations

import os
from dataclasses import dataclass


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

    # Auto-seeding AI apply queue
    # Comma-separated list of Convex user IDs to seed queue for
    ai_apply_user_ids: list[str] = None  # type: ignore[assignment]
    # Max number of recent jobs to enqueue per tick
    ai_apply_seed_limit: int = int(os.getenv("AI_APPLY_SEED_LIMIT", "10"))
    # Interval between seed cycles in seconds
    ai_apply_seed_interval_seconds: int = int(os.getenv("AI_APPLY_SEED_INTERVAL_SECONDS", "60"))


def _parse_user_ids(raw: str | None) -> list[str]:
    if not raw:
        return []
    out = [s.strip() for s in raw.split(",")]
    return [s for s in out if s]


settings = Settings()
settings.ai_apply_user_ids = _parse_user_ids(os.getenv("AI_APPLY_USER_IDS") or os.getenv("AI_APPLY_USER_ID"))
