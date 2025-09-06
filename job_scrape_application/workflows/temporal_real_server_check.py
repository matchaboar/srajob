from __future__ import annotations

import asyncio
import os
import uuid
from datetime import timedelta
from typing import Any, Dict

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleIntervalSpec,
    SchedulePolicy,
    ScheduleSpec,
)
from temporalio.worker import Worker

from .temporal_health_check import TestActivities, normalize_convex_base
from .test_workflow import ScrapeWorkflowTest


async def main() -> None:
    convex_base = os.environ.get("CONVEX_HTTP_URL")
    if not convex_base:
        raise SystemExit(
            "Set CONVEX_HTTP_URL to your Convex HTTP base (e.g., https://<deployment>.convex.site)"
        )
    convex_base = normalize_convex_base(convex_base)

    temporal_address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    # Wait for Temporal server to be ready
    client: Client | None = None
    for attempt in range(30):
        try:
            client = await Client.connect(temporal_address, namespace=temporal_namespace)
            break
        except Exception as e:
            if attempt == 29:
                raise
            await asyncio.sleep(1)
    assert client is not None

    task_queue = f"real-hc-{uuid.uuid4().hex[:6]}"
    acts = TestActivities(convex_base)

    async with Worker(
        client,
        task_queue=task_queue,
        workflows=[ScrapeWorkflowTest],
        activities=[acts.fetch_sites, acts.scrape_site, acts.store_scrape],
    ):
        # 1) Direct workflow run to verify DB writes
        result = await client.execute_workflow(
            ScrapeWorkflowTest.run,
            id=f"wf-realhc-{uuid.uuid4().hex[:6]}",
            task_queue=task_queue,
        )
        print(f"Direct workflow result: sites={result.site_count} scrapes={len(result.scrape_ids)}")
        assert len(result.scrape_ids) >= 1

        # 2) Create a schedule that runs every 12 hours and trigger immediately
        sched_id = f"sched-hc-{uuid.uuid4().hex[:6]}"
        spec = ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(hours=12))])
        action = ScheduleActionStartWorkflow(
            "ScrapeWorkflowTest",
            id=f"wf-{sched_id}",
            task_queue=task_queue,
        )
        schedule = Schedule(action=action, spec=spec, policy=SchedulePolicy())

        await client.create_schedule(id=sched_id, schedule=schedule)
        handle = client.get_schedule_handle(sched_id)

        # Trigger now
        await handle.trigger()
        # Wait a moment for run
        await asyncio.sleep(2)
        desc = await handle.describe()
        total_actions = desc.info.num_actions or 0
        print(f"Schedule triggered; actions={total_actions}")
        assert total_actions >= 1

        # Optional cleanup: pause and delete schedule
        # await handle.pause()
        # await handle.delete()

    print("Temporal real server check: SUCCESS")


if __name__ == "__main__":
    asyncio.run(main())
