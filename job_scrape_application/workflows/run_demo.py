from __future__ import annotations

import asyncio
import os
import sys
import uuid
from temporalio.client import Client

from .config import settings
from .demo_workflow import DemoWorkflow


async def main() -> None:
    # Allow URL via arg or env, with safe default
    url = (
        (sys.argv[1] if len(sys.argv) > 1 else None)
        or os.environ.get("DEMO_URL")
        or "https://example.com/job/preview"
    )

    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )

    run_id = f"demo-{uuid.uuid4().hex[:8]}"
    await client.start_workflow(
        DemoWorkflow.run,
        url,
        id=run_id,
        task_queue=settings.task_queue,
    )
    print(f"Started DemoWorkflow id={run_id} url={url} task_queue={settings.task_queue}")


if __name__ == "__main__":
    asyncio.run(main())

