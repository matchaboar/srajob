import os
import json
from fetchfox_sdk import FetchFox

from srajob.sites import sites

URL = sites.DATADOG_SWE_US
URL_PATTERN = "https://careers.datadoghq.com/detail/**"

start_urls = [URL]

api_key = os.getenv("FETCHFOX_API_KEY")
if not api_key:
    raise SystemExit(
        "FETCHFOX_API_KEY is required. Run your command via 'dotenvx run -- uv run ...' or set it in your environment."
    )

fox = FetchFox(api_key=api_key)

job_listing_template = {
    "job_title": "str | None",
    "url": "str | None",
    "location": "str | None",
    "remote": "True | False | None",
}

print(
    f"""
job_listing template
:--------------
{job_listing_template}
"""
)

result = fox.scrape(
    {
        "pattern": URL_PATTERN,
        "start_urls": start_urls,
        "max_depth": 5,
        "max_visits": 20,
        "template": job_listing_template,
    }
)

# FetchFox may return JSON string or dict depending on version
data = result if isinstance(result, dict) else json.loads(result)

with open("./datas.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Found URLs:", data.get("results", {}).get("hits", []))
print("Extracted items:", data.get("results", {}).get("items", []))
