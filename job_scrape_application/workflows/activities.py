from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, TypedDict

import httpx
from fetchfox_sdk import FetchFox

from .config import settings


class Site(TypedDict, total=False):
    _id: str
    name: Optional[str]
    url: str
    pattern: Optional[str]
    enabled: bool
    lastRunAt: Optional[int]


async def fetch_sites() -> List[Site]:
    if not settings.convex_http_url:
        raise RuntimeError("CONVEX_HTTP_URL env var is required")
    url = settings.convex_http_url.rstrip("/") + "/api/sites"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected sites payload: {data!r}")
        return data  # type: ignore[return-value]


def scrape_site(site: Site) -> Dict[str, Any]:
    if not settings.fetchfox_api_key:
        raise RuntimeError("FETCHFOX_API_KEY env var is required for FetchFox")

    fox = FetchFox(api_key=settings.fetchfox_api_key)

    start_urls = [site["url"]]
    template = {
        "job_title": "str | None",
        "url": "str | None",
        "location": "str | None",
        "remote": "True | False | None",
    }

    payload: Dict[str, Any] = {
        "start_urls": start_urls,
        "max_depth": 5,
        "max_visits": 20,
        "template": template,
    }
    pattern = site.get("pattern")
    if pattern:
        payload["pattern"] = pattern

    started_at = int(time.time() * 1000)
    # FetchFox may return dict or JSON string depending on version
    result = fox.scrape(payload)
    try:
        result_obj: Dict[str, Any] = result if isinstance(result, dict) else json.loads(result)
    except Exception:
        # Last resort: wrap opaque content
        result_obj = {"raw": result}
    completed_at = int(time.time() * 1000)

    return {
        "sourceUrl": site["url"],
        "pattern": pattern,
        "startedAt": started_at,
        "completedAt": completed_at,
        "items": result_obj,
    }


async def store_scrape(scrape: Dict[str, Any]) -> str:
    if not settings.convex_http_url:
        raise RuntimeError("CONVEX_HTTP_URL env var is required")
    url = settings.convex_http_url.rstrip("/") + "/api/scrapes"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=scrape)
        resp.raise_for_status()
        data = resp.json()
        return str(data.get("scrapeId"))

