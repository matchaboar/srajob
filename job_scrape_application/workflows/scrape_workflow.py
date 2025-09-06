from __future__ import annotations

from dataclasses import dataclass
from typing import List

from temporalio import workflow

# Import activity call prototypes inside workflow via type hints / names
with workflow.unsafe.imports_passed_through():
    from .activities import fetch_sites, scrape_site, store_scrape, Site


@dataclass
class ScrapeSummary:
    site_count: int
    scrape_ids: List[str]


@workflow.defn(name="ScrapeWorkflow")
class ScrapeWorkflow:
    @workflow.run
    async def run(self) -> ScrapeSummary:  # type: ignore[override]
        sites = await workflow.execute_activity(
            fetch_sites,
            schedule_to_close_timeout=workflow.timedelta(seconds=30),
        )

        scrape_ids: List[str] = []
        for site in sites:
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

        return ScrapeSummary(site_count=len(sites), scrape_ids=scrape_ids)

