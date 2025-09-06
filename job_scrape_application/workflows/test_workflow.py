from __future__ import annotations

from dataclasses import dataclass
from typing import List

from temporalio import workflow


@dataclass
class ScrapeSummary:
    site_count: int
    scrape_ids: List[str]


@workflow.defn(name="ScrapeWorkflowTest")
class ScrapeWorkflowTest:
    @workflow.run
    async def run(self) -> ScrapeSummary:  # type: ignore[override]
        with workflow.unsafe.imports_passed_through():
            pass

        sites = await workflow.execute_activity(
            "fetch_sites",
            schedule_to_close_timeout=workflow.timedelta(seconds=30),
        )
        scrape_ids: List[str] = []
        for site in sites:
            res = await workflow.execute_activity(
                "scrape_site",
                site,
                start_to_close_timeout=workflow.timedelta(seconds=30),
            )
            scrape_id = await workflow.execute_activity(
                "store_scrape",
                res,
                schedule_to_close_timeout=workflow.timedelta(seconds=30),
            )
            scrape_ids.append(scrape_id)
        return ScrapeSummary(site_count=len(sites), scrape_ids=scrape_ids)

