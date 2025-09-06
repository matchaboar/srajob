import asyncio
import json
from pathlib import Path
from pydantic import BaseModel, Field
from crawl4ai import (
    AsyncWebCrawler,
    CrawlerRunConfig,
    JsonXPathExtractionStrategy,
    LLMConfig,
    CacheMode,
)
from crawl4ai import LLMExtractionStrategy
from srajob.constants import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, MODEL_NAME


class JobListing(BaseModel):
    job_title: str
    url: str
    location: str | None
    remote: bool | None


class JobListPage(BaseModel):
    job_list: list[JobListing]
    next_page: str


async def main():
    html_file_path = Path("test/datadog_live_page.html")
    local_file_path = "test/datadog_live_page.html"
    file_url = f"file://{local_file_path}"
    print(f"file_url: {file_url}")
    with open(html_file_path, "r", encoding="utf-8") as file:
        html_document = file.read()
    # print(f'html_document: {html_document}')
    llm_config = LLMConfig(
        provider=MODEL_NAME,
        base_url=OPENROUTER_BASE_URL,
        api_token=OPENROUTER_API_KEY,
    )

    # llm_strategy = LLMExtractionStrategy(
    #     llm_config=llm_config,
    #     schema=JobListPage.model_json_schema(),
    #     extraction_type="schema",
    #     instruction="Extract the job information.",
    #     chunk_token_threshold=1200,
    #     overlap_rate=0.1,
    #     apply_chunking=True,
    #     input_format="html",
    # )
    # config = CrawlerRunConfig(
    #     cache_mode=CacheMode.BYPASS,
    #     exclude_external_links=True,
    #     word_count_threshold=2,
    #     extraction_strategy=llm_strategy,
    # )

    xpath_schema = JsonXPathExtractionStrategy.generate_schema(
        html_document,
        schema_type="xpath",
        llm_config=llm_config,
        target_json_example=JobListPage.model_json_schema(),
    )

    print("getting xpath schema:")
    print(xpath_schema)

    # async with AsyncWebCrawler() as crawler:
    #     result = await crawler.arun(url=file_url, config=config)
    #     if result.success:
    #         print("Markdown Content from Raw HTML:")
    #         print(result.markdown)
    #     else:
    #         print(f"Failed to crawl raw HTML: {result.error_message}")
    #     extracted_content = json.loads(result.extracted_content)
    #     print('extracted_content: ----------')
    #     print(extracted_content)


if __name__ == "__main__":
    asyncio.run(main())
