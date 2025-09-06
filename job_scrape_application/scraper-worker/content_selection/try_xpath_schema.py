import asyncio
import json
from pathlib import Path
import pprint
from pydantic import BaseModel
from crawl4ai import (
    AsyncWebCrawler,
    CrawlerRunConfig,
    JsonXPathExtractionStrategy,
    CacheMode,
)
from requests import session


class JobListing(BaseModel):
    job_title: str
    url: str
    location: str | None
    remote: bool | None


# @param local_file_path: should be like 'test/datadog_live_page.html'
#   so it is relative to the root of this repo.
async def try_xpath_schema(
    local_file_path: str,
    schema_text: dict,
    schema_next_page: dict,
):
    file_url = f"file://{local_file_path}"
    print(f"provided args: {local_file_path=}, therefore {file_url=}")
    session_results = []

    async with AsyncWebCrawler() as crawler:
        session_id = "my_session"
        text_run_config = _get_run_config(schema_text, session_id)
        next_page_run_config = _get_run_config(schema_next_page, session_id)

        page_number = 1
        while page_number:
            # get the text results from page.
            text_result = await crawler.arun(url=file_url, config=text_run_config)
            if text_result.success:
                print(f"Successful text results for {page_number=}.")
                session_results += [json.loads(text_result.extracted_content)]
                # print(result.markdown)
            else:
                print(f"Failed to crawl raw HTML: {text_result.error_message}")

            next_page_result = await crawler.arun(url=file_url, config=next_page_run_config)

    print("extracted_content: ----------")
    pprint.pprint(session_results)

    # js_code, wait_for, and session_id for dynamic "load more" buttons or JS-based pagination


def _get_js_next_page(selector: str):
    return f"""
    const selector = '{selector}';
    const button = document.querySelector(selector);
    if (button) button.click();
    """


def _get_run_config(schema: dict, session_id=""):
    crawler_run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        exclude_external_links=True,
        word_count_threshold=2,
        extraction_strategy=JsonXPathExtractionStrategy(schema),
        scan_full_page=True,
        remove_overlay_elements=True,
        magic=True,
        simulate_user=True,
    )
    if session_id:
        crawler_run_config.session_id = session_id
    return crawler_run_config


async def main():
    html_file_path = Path("test/datadog_live_page.html")
    local_file_path = "test/datadog_live_page.html"
    file_url = f"file://{local_file_path}"
    print(f"file_url: {file_url}")

    schema_python = {
        "name": "Job Listings",
        "baseSelector": "//li[contains(@class, 'ais-Hits-item')]",
        "fields": [
            {
                "name": "job_title",
                "selector": ".//h3[contains(@class, 'job-title')]",
                "type": "text",
            },
            {
                "name": "department",
                "selector": ".//div[contains(@class, 'job-card-department')]/p",
                "type": "text",
            },
            {
                "name": "location",
                "selector": ".//div[contains(@class, 'job-card-location')]/p",
                "type": "text",
            },
            {"name": "job_url", "selector": ".//a", "type": "attribute", "attribute": "href"},
        ],
    }

    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        exclude_external_links=True,
        word_count_threshold=2,
        extraction_strategy=JsonXPathExtractionStrategy(schema_python),
        scan_full_page=True,
        remove_overlay_elements=True,
        magic=True,
        simulate_user=True,
    )

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=file_url, config=config)
        if result.success:
            print("Successful crawl")
            # print(result.markdown)
        else:
            print(f"Failed to crawl raw HTML: {result.error_message}")
        extracted_content = json.loads(result.extracted_content)
        print("extracted_content: ----------")
        pprint.pprint(extracted_content)


if __name__ == "__main__":
    asyncio.run(main())
