from __future__ import annotations

import asyncio
from temporalio.client import Client
from temporalio.worker import Worker

from .config import settings
from . import activities
from .scrape_workflow import ScrapeWorkflow


async def main() -> None:
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )

    worker = Worker(
        client,
        task_queue=settings.task_queue,
        workflows=[ScrapeWorkflow],
        activities=[
            activities.fetch_sites,
            activities.scrape_site,
            activities.store_scrape,
        ],
    )

    print(
        f"Worker started. Namespace={settings.temporal_namespace} "
        f"Address={settings.temporal_address} TaskQueue={settings.task_queue}"
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())

