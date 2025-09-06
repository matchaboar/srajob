import json
from pathlib import Path
import pprint
from pydantic import BaseModel
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
    JsonXPathExtractionStrategy,
)

MAX_PAGES = 5
URL_MODE = "URL_MODE"
LOCAL_FILE_MODE = "LOCAL_FILE_MODE"


class NextPage(BaseModel):
    next_page_text: str
    next_page_selector: str


browser_config = BrowserConfig()
browser_config.headless = False
browser_config.browser_type = "chromium"
browser_config.verbose = True
browser_config.browser_mode = "docker"


# @param local_file_path: should be like 'test/datadog_live_page.html'
#   so it is relative to the root of this repo.
async def try_xpath_schema(
    url: str | None,
    local_file_path: str | None,
    schema_text: dict,
    schema_next_page: dict | None,
):
    file_url = ""
    if url:
        file_url = url
        print(f"provided args: {url=}, therefore {file_url=}")
    else:
        print(f"provided args: {local_file_path=}, therefore {file_url=}")
        file_url = f"file://{local_file_path}"
    session_results = []

    async with AsyncWebCrawler(config=browser_config) as crawler:
        session_id = "my_session"
        # we could check for LLM generation of the next page selector schema, but
        # let's assume we got it already.
        next_schema = _get_cached_xpath_schema_datadog()
        text_run_config = _get_run_config(
            schema_text,
            session_id,
            _get_next_page_wait_for_js(
                next_schema["baseSelector"], next_schema["fields"][0]["selector"]
            ),
            _get_next_page_js(next_schema["baseSelector"], next_schema["fields"][0]["selector"]),
        )

        # get text results from initial starting url.
        text_result = await crawler.arun(url=file_url, config=text_run_config)

        # get the text results from pages after the initial url.
        for page_index in range(MAX_PAGES):
            # Mark that we will not switch navigation except by js code.
            text_run_config.js_only = True
            text_result = await crawler.arun(url=file_url, config=text_run_config)
            if text_result.success:
                print(f"Successful text results for {page_index=}.")
                session_results += [json.loads(text_result.extracted_content)]
            else:
                print(f"Failed to crawl raw HTML: {text_result.error_message}")

    print("extracted_content: ----------")
    pprint.pprint(session_results)
    return session_results


def _get_next_page_js(baseSelector: str, selector: str):
    load_js = ""
    with open(Path("./src/srajob/content_selection/next_page/next_page.js"), "r") as f:
        load_js = f.read()
    load_js += f"clickNextPage(f{baseSelector}, f{selector})"
    load_js = """js: () => {
        {load_js}
    }"""


def _get_next_page_wait_for_js(baseSelector: str, selector: str):
    load_js = ""
    with open(Path("./src/srajob/content_selection/next_page/wait_condition.js"), "r") as f:
        load_js = f.read()
    load_js += f"checkForNextPage(f{baseSelector}, f{selector});"
    load_js = """js: () => {
        {load_js}
    }"""


def _get_run_config(schema: dict, session_id="", wait_for="", js_code=""):
    crawler_run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        exclude_external_links=True,
        word_count_threshold=2,
        extraction_strategy=JsonXPathExtractionStrategy(schema),
        scan_full_page=True,
        remove_overlay_elements=False,
        magic=False,
        simulate_user=False,
        js_only=True,
        delay_before_return_html=2,
    )
    if session_id:
        crawler_run_config.session_id = session_id
    if wait_for:
        crawler_run_config.wait_for = wait_for
    if js_code:
        crawler_run_config.js_code = js_code

    return crawler_run_config


def _get_xpath_schema(html_document: str, llm_config):
    return JsonXPathExtractionStrategy.generate_schema(
        html_document,
        schema_type="xpath",
        llm_config=llm_config,
        query="Next page button, link, or selector, sometimes in text as '>' character.",
    )


def _get_cached_xpath_schema_datadog():
    return {
        "name": "Pagination",
        "baseSelector": "//div[@id='pagination']",
        "fields": [
            {
                "name": "next_page_button",
                "selector": ".//li[contains(@class, 'nextPage')]/a",
                "type": "attribute",
                "attribute": "href",
            }
        ],
    }
