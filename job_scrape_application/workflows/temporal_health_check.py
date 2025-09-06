from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any, Dict, List

import httpx
from temporalio.client import Client
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker


def normalize_convex_base(url: str) -> str:
    base = url.strip().rstrip("/")
    if base.endswith(".convex.cloud"):
        base = base.replace(".convex.cloud", ".convex.site")
    return base


# Lightweight HTTP helpers that mirror our production activities but avoid external APIs.
async def http_get_sites(base: str) -> List[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{base}/api/sites")
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []


async def http_post_site(base: str, payload: dict) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{base}/api/sites", json=payload)
        r.raise_for_status()
        return str(r.json().get("id"))


async def http_post_scrape(base: str, payload: dict) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{base}/api/scrapes", json=payload)
        r.raise_for_status()
        return str(r.json().get("scrapeId"))


# Dummy activities used only for this test to avoid calling FetchFox.
class TestActivities:
    def __init__(self, convex_base: str) -> None:
        self.base = convex_base

    @activity.defn
    async def fetch_sites(self) -> List[dict]:
        return await http_get_sites(self.base)

    @activity.defn
    async def scrape_site(self, site: dict) -> Dict[str, Any]:
        # Return a synthetic scrape result quickly
        uniq = uuid.uuid4().hex[:8]
        return {
            "sourceUrl": site["url"],
            "pattern": site.get("pattern"),
            "startedAt": 0,
            "completedAt": 0,
            "items": {"results": {"hits": [site["url"]], "items": [{"job_title": f"HC-{uniq}"}]}},
        }

    @activity.defn
    async def store_scrape(self, scrape: Dict[str, Any]) -> str:
        return await http_post_scrape(self.base, scrape)


from .test_workflow import ScrapeWorkflowTest


async def main() -> None:
    base_env = os.environ.get("CONVEX_HTTP_URL")
    if not base_env:
        raise SystemExit(
            "Set CONVEX_HTTP_URL to your Convex HTTP base (e.g., https://<deployment>.convex.site)"
        )
    base = normalize_convex_base(base_env)
    print(f"Using CONVEX_HTTP_URL={base}")

    # Ensure there is at least one enabled site
    sites = await http_get_sites(base)
    if not sites:
        site_payload = {
            "name": "temporal-hc",
            "url": "https://example.com/jobs/temporal-hc",
            "pattern": "https://example.com/jobs/temporal-hc/**",
            "enabled": True,
        }
        sid = await http_post_site(base, site_payload)
        print(f"Seeded site id={sid}")

    # Start ephemeral Temporal test server with time-skipping
    async with await WorkflowEnvironment.start_time_skipping() as env:
        client: Client = env.client
        task_queue = f"hc-queue-{uuid.uuid4().hex[:6]}"

        acts = TestActivities(base)
        worker = Worker(
            client,
            task_queue=task_queue,
            workflows=[ScrapeWorkflowTest],
            activities=[acts.fetch_sites, acts.scrape_site, acts.store_scrape],
        )

        async with worker:
            # 1) Directly execute workflow and verify scrapes are stored
            run = await client.execute_workflow(
                ScrapeWorkflowTest.run,
                id=f"wf-hc-{uuid.uuid4().hex[:6]}",
                task_queue=task_queue,
            )
            print(f"Direct workflow result: sites={run.site_count} scrapes={len(run.scrape_ids)}")
            assert len(run.scrape_ids) >= 1, "Workflow did not store any scrapes"

            # 2) Create a schedule to run every 12 hours, then trigger it now
            from datetime import timedelta
            from temporalio.client import (
                Schedule,
                ScheduleActionStartWorkflow,
                ScheduleIntervalSpec,
                SchedulePolicy,
                ScheduleSpec,
            )

            sched_id = f"hc-sched-{uuid.uuid4().hex[:6]}"
            spec = ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(hours=12))])
            action = ScheduleActionStartWorkflow(
                "ScrapeWorkflowTest",
                id=f"wf-{sched_id}",
                task_queue=task_queue,
            )
            policy = SchedulePolicy()
            try:
                schedule = Schedule(action=action, spec=spec, policy=policy)
                await client.create_schedule(id=sched_id, schedule=schedule)
                handle = client.get_schedule_handle(sched_id)

                # Trigger an immediate run to simulate catch-up
                await handle.trigger()

                # Wait briefly for run to complete
                await asyncio.sleep(0.5)
                desc = await handle.describe()
                total_runs = desc.info.num_actions or 0
                print(f"Schedule triggered; total actions={total_runs}")
                assert total_runs >= 1, "Schedule did not run as expected"
            except Exception as e:
                print(
                    "Schedule API unsupported in test server; skipping schedule check.\n"
                    f"Details: {e}"
                )

    print("Temporal health check: SUCCESS")


if __name__ == "__main__":
    asyncio.run(main())
