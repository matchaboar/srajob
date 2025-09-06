from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from typing import Any, Dict, Optional

import httpx

LOG_PATH = os.path.join(os.path.dirname(__file__), "test_lease_complete.out.txt")


def log(msg: str) -> None:
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def env_or_exit() -> str:
    base = os.getenv("CONVEX_HTTP_URL")
    if not base or "<your-deployment>" in base:
        print("SKIP: Set CONVEX_HTTP_URL to a running Convex HTTP router (e.g., https://xxx.convex.site)")
        sys.exit(0)
    return base.rstrip("/")


async def post_json(client: httpx.AsyncClient, url: str, payload: Dict[str, Any]) -> Any:
    r = await client.post(url, json=payload)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return json.loads(r.text)


async def main() -> None:
    # reset log file
    try:
        if os.path.exists(LOG_PATH):
            os.remove(LOG_PATH)
    except Exception:
        pass

    base = env_or_exit()
    worker_id = f"test-worker-{uuid.uuid4()}"
    unique = uuid.uuid4().hex[:8]

    async with httpx.AsyncClient(timeout=30) as client:
        log(f"Base={base} worker={worker_id} unique={unique}")
        # 1) Create two sites
        site_payloads = [
            {
                "name": f"Test Site A {unique}",
                "url": f"https://example.com/jobs/{unique}/a",
                "pattern": f"https://example.com/jobs/{unique}/a/**",
                "enabled": True,
            },
            {
                "name": f"Test Site B {unique}",
                "url": f"https://example.com/jobs/{unique}/b",
                "pattern": f"https://example.com/jobs/{unique}/b/**",
                "enabled": True,
            },
        ]

        created_ids: list[str] = []
        for payload in site_payloads:
            log("POST /api/sites")
            res = await post_json(client, f"{base}/api/sites", payload)
            if not res or "id" not in res:
                raise RuntimeError(f"Failed to create site: {res}")
            created_ids.append(res["id"])

        # 2) Lease one (may pick any existing available site on the deployment)
        log("POST /api/sites/lease #1")
        lease1 = await post_json(client, f"{base}/api/sites/lease", {"workerId": worker_id, "lockSeconds": 60})
        if not lease1 or "_id" not in lease1:
            raise AssertionError(f"Expected a lease result, got: {lease1}")
        first_id = lease1["_id"]

        # 3) Mark it complete
        log("POST /api/sites/complete #1")
        _ = await post_json(client, f"{base}/api/sites/complete", {"id": first_id})

        # 4) Lease again, should be the other one
        log("POST /api/sites/lease #2")
        lease2 = await post_json(client, f"{base}/api/sites/lease", {"workerId": worker_id, "lockSeconds": 60})
        if not lease2 or "_id" not in lease2:
            raise AssertionError(f"Expected a second lease result, got: {lease2}")
        second_id = lease2["_id"]
        if second_id == first_id:
            raise AssertionError("Second lease returned the same (completed) site; expected a different one")

        # 5) Cleanup: mark second completed too so it won't be picked again
        log("POST /api/sites/complete #2")
        _ = await post_json(client, f"{base}/api/sites/complete", {"id": second_id})

        print("PASS: Completed first job; next lease returned a different, not completed job")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except SystemExit as e:
        # Propagate intended exits (e.g., SKIP)
        raise
    except Exception as e:
        # Ensure failures are visible on stdout in this harness
        print(f"FAIL: {e!r}")
        raise
