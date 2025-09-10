from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from temporalio.client import Client
import traceback
from temporalio.worker import Worker

from .config import settings
from . import activities
from .scrape_workflow import ScrapeWorkflow
from .demo_workflow import DemoWorkflow
from .form_fill_workflow import FormFillWorkflow
from .ai_form_activities import (
    lease_next_ai_application,
    complete_ai_application,
    fail_ai_application,
    get_resume_for_user,
    run_form_fill,
    queue_jobs_for_user,
)


async def main() -> None:
    print("[worker] Connecting to Temporal...")
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )
    print(f"[worker] Connected. namespace={settings.temporal_namespace} address={settings.temporal_address}")

    # Thread pool for synchronous activities (e.g., run_form_fill, scrape_site)
    sync_executor = ThreadPoolExecutor(max_workers=8)

    worker = Worker(
        client,
        task_queue=settings.task_queue,
        workflows=[ScrapeWorkflow, FormFillWorkflow, DemoWorkflow],
        activities=[
            activities.fetch_sites,
            activities.lease_site,
            activities.scrape_site,
            activities.store_scrape,
            activities.complete_site,
            activities.fail_site,
            # AI form fill activities
            lease_next_ai_application,
            complete_ai_application,
            fail_ai_application,
            get_resume_for_user,
            run_form_fill,
        ],
        activity_executor=sync_executor,
    )

    print(
        f"[worker] Started. namespace={settings.temporal_namespace} "
        f"address={settings.temporal_address} task_queue={settings.task_queue}"
    )
    async def _starter_loop() -> None:
        # Periodically lease next pending AI apply and start workflow runs
        # This is a lightweight on-demand trigger based on DB queue
        while True:
            try:
                leased = await lease_next_ai_application()
                if leased:
                    qid = str(leased["_id"])
                    url = str(leased["jobUrl"])  # noqa: N806
                    uid = str(leased["userId"])  # noqa: N806
                    print(f"[starter] Leased queued application id={qid} user={uid}")
                    try:
                        await client.start_workflow(
                            FormFillWorkflow.run,
                            args=[qid, url, uid],
                            id=f"formfill-{qid}",
                            task_queue=settings.task_queue,
                        )
                        print(f"[starter] Started FormFillWorkflow run id=formfill-{qid}")
                    except Exception as e:  # noqa: BLE001
                        # Mark queue item as failed if we couldn't start
                        print(f"[starter] Failed to start workflow for {qid}: {e}")
                        try:
                            await fail_ai_application(qid, f"start failed: {e}")
                        except Exception as e2:  # noqa: BLE001
                            print(f"[starter] Also failed to mark error for {qid}: {e2}")
                else:
                    # Fast poll for responsive pickup without busy-waiting
                    await asyncio.sleep(0.4)
            except Exception:
                # Backoff a bit on errors
                print("[starter] Error in loop:\n" + traceback.format_exc())
                await asyncio.sleep(1.0)

    async def _seeding_loop() -> None:
      # Periodically seed queue with recent jobs for configured users
      # Skips if no Convex HTTP URL or no user IDs configured
      interval = max(15, int(settings.ai_apply_seed_interval_seconds))
      limit = max(1, int(settings.ai_apply_seed_limit))
      while True:
          try:
              if settings.convex_http_url and settings.ai_apply_user_ids:
                  for uid in settings.ai_apply_user_ids:
                      try:
                          cnt = await queue_jobs_for_user(uid, limit=limit, only_unqueued=True)
                          if cnt:
                              print(f"Seeded {cnt} jobs for user {uid}")
                      except Exception as e:  # noqa: BLE001
                          print(f"Seeding error for user {uid}: {e}")
              await asyncio.sleep(interval)
          except Exception:
              await asyncio.sleep(interval)

    # Run worker, seeder and starter concurrently
    await asyncio.gather(worker.run(), _starter_loop(), _seeding_loop())


if __name__ == "__main__":
    asyncio.run(main())
