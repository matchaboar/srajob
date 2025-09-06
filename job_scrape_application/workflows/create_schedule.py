from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio.client import Client
from temporalio.client.schedule import (
    ScheduleActionStartWorkflow,
    ScheduleCalendarSpec,
    SchedulePolicy,
    ScheduleSpec,
)

from .config import settings


SCHEDULE_ID = "scrape-every-12-hours"


async def main() -> None:
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )

    spec = ScheduleSpec(
        calendars=[
            # Every 12 hours, at minute 0
            ScheduleCalendarSpec(hour="*/12", minute="0"),
        ]
    )

    action = ScheduleActionStartWorkflow(
        "ScrapeWorkflow",
        id=f"wf-{SCHEDULE_ID}",
        task_queue=settings.task_queue,
    )

    policy = SchedulePolicy(
        # If a run is missed (e.g., worker down), buffer at most 1 and run once
        catchup_window=timedelta(hours=12),
        overlap=SchedulePolicy.OverlapPolicy.SKIP,
    )

    # Create or update the schedule idempotently
    handle = client.get_schedule_handle(SCHEDULE_ID)
    try:
        await handle.describe()
        await handle.update(overwrite=True, spec=spec, action=action, policy=policy)
        print(f"Updated schedule: {SCHEDULE_ID}")
    except Exception:
        await client.create_schedule(
            id=SCHEDULE_ID,
            spec=spec,
            action=action,
            policy=policy,
        )
        print(f"Created schedule: {SCHEDULE_ID}")


if __name__ == "__main__":
    asyncio.run(main())

