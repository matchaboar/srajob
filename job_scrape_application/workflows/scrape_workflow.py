from __future__ import annotations

from dataclasses import dataclass
from typing import List

from temporalio import workflow

# Import activity call prototypes inside workflow via type hints / names
with workflow.unsafe.imports_passed_through():
    from .activities import (
        fetch_sites,
        lease_site,
        scrape_site,
        store_scrape,
        complete_site,
        fail_site,
        Site,
    )


@dataclass
class ScrapeSummary:
    site_count: int
    scrape_ids: List[str]


@workflow.defn(name="ScrapeWorkflow")
class ScrapeWorkflow:
    @workflow.run
    async def run(self) -> ScrapeSummary:  # type: ignore[override]
        scrape_ids: List[str] = []
        leased_count = 0

        # Keep leasing jobs until none available
        while True:
            site = await workflow.execute_activity(
                lease_site,
                "scraper-worker",  # logical worker id; replace if needed
                schedule_to_close_timeout=workflow.timedelta(seconds=30),
            )

            if not site:
                break

            leased_count += 1

            try:
                res = await workflow.execute_activity(
                    scrape_site,
                    site,
                    start_to_close_timeout=workflow.timedelta(minutes=10),
                )
                scrape_id = await workflow.execute_activity(
                    store_scrape,
                    res,
                    schedule_to_close_timeout=workflow.timedelta(seconds=30),
                )
                scrape_ids.append(scrape_id)

                # Mark site completed so next lease skips it
                await workflow.execute_activity(
                    complete_site,
                    site["_id"],
                    schedule_to_close_timeout=workflow.timedelta(seconds=30),
                )
            except Exception as e:  # noqa: BLE001
                # On failure, record and release the lock for retry after TTL or immediately
                await workflow.execute_activity(
                    fail_site,
                    site["_id"],
                    str(e),
                    schedule_to_close_timeout=workflow.timedelta(seconds=30),
                )

        return ScrapeSummary(site_count=leased_count, scrape_ids=scrape_ids)
