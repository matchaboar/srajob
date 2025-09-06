from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx


CONVEX = os.environ.get("CONVEX_HTTP_URL")


async def main() -> None:
    if not CONVEX:
        raise SystemExit("Set CONVEX_HTTP_URL to your Convex HTTP base URL (e.g., https://<deployment>.convex.cloud)")

    base = CONVEX.rstrip("/")

    async with httpx.AsyncClient(timeout=30) as client:
        # Ensure backend is reachable
        try:
            r = await client.get(f"{base}/api/sites")
            r.raise_for_status()
            print("GET /api/sites OK (initial)")
        except Exception as e:
            raise SystemExit(f"Convex HTTP not reachable at {CONVEX}: {e}")

        # Seed a test site
        payload = {
            "name": "Test Site",
            "url": "https://example.com/jobs",
            "pattern": "https://example.com/jobs/**",
            "enabled": True,
        }
        r = await client.post(f"{base}/api/sites", json=payload)
        r.raise_for_status()
        print("POST /api/sites OK ->", r.json())

        # Verify it appears in list
        r = await client.get(f"{base}/api/sites")
        r.raise_for_status()
        sites: list[dict[str, Any]] = r.json()
        assert any(s.get("url") == payload["url"] for s in sites), "Seeded site missing from GET"
        print(f"GET /api/sites OK (count={len(sites)})")

        # Store a dummy scrape
        now = int(time.time() * 1000)
        scrape = {
            "sourceUrl": payload["url"],
            "pattern": payload["pattern"],
            "startedAt": now,
            "completedAt": now,
            "items": {"results": {"hits": [payload["url"]], "items": [{"job_title": "N/A"}]}},
        }
        r = await client.post(f"{base}/api/scrapes", json=scrape)
        r.raise_for_status()
        print("POST /api/scrapes OK ->", r.json())


if __name__ == "__main__":
    asyncio.run(main())
