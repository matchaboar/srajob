from __future__ import annotations

import asyncio
import os
import sys
import uuid
from typing import Any

import httpx


def normalize_convex_base(url: str) -> str:
    """Normalize Convex HTTP base.

    - Ensures no trailing slash
    - If using `.convex.cloud`, switch to `.convex.site` for HTTP router
    """
    base = url.strip().rstrip("/")
    if base.endswith(".convex.cloud"):
        base = base.replace(".convex.cloud", ".convex.site")
    return base


async def main() -> None:
    base_env = os.environ.get("CONVEX_HTTP_URL")
    if not base_env:
        raise SystemExit(
            "Set CONVEX_HTTP_URL to your Convex HTTP base (e.g., https://<deployment>.convex.site)"
        )

    base = normalize_convex_base(base_env)
    print(f"Using CONVEX_HTTP_URL={base}")

    async with httpx.AsyncClient(timeout=30) as client:
        # 1) GET /api/sites
        r = await client.get(f"{base}/api/sites")
        if r.status_code != 200:
            raise SystemExit(f"GET /api/sites failed: {r.status_code} {r.text}")
        print("GET /api/sites: OK")

        # 2) POST /api/sites
        uniq = uuid.uuid4().hex[:8]
        site_payload = {
            "name": f"healthcheck-{uniq}",
            "url": f"https://example.com/jobs/{uniq}",
            "pattern": f"https://example.com/jobs/{uniq}/**",
            "enabled": True,
        }
        r = await client.post(f"{base}/api/sites", json=site_payload)
        if r.status_code != 201:
            raise SystemExit(f"POST /api/sites failed: {r.status_code} {r.text}")
        site_id = r.json().get("id")
        print(f"POST /api/sites: OK -> id={site_id}")

        # 3) GET /api/sites (verify our new site appears)
        r = await client.get(f"{base}/api/sites")
        if r.status_code != 200:
            raise SystemExit(f"Re-GET /api/sites failed: {r.status_code} {r.text}")
        sites: list[dict[str, Any]] = r.json()
        if not any(s.get("url") == site_payload["url"] for s in sites):
            raise SystemExit("Seeded site missing from GET /api/sites")
        print("Re-GET /api/sites: OK (seed verified)")

        # 4) POST /api/jobs
        job_payload = {
            "title": f"Software Engineer (Health Check {uniq})",
            "company": "SampleSoft",
            "description": "Sample listing created by automated health check for development.",
            "location": "Remote - US",
            "remote": True,
            "level": "mid",
            "totalCompensation": 145000,
            "url": f"https://example.com/job/{uniq}",
            "test": True,
        }
        r = await client.post(f"{base}/api/jobs", json=job_payload)
        if r.status_code != 201:
            raise SystemExit(f"POST /api/jobs failed: {r.status_code} {r.text}")
        job_id = r.json().get("jobId")
        print(f"POST /api/jobs: OK -> jobId={job_id}")

    print("Health check: SUCCESS")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
