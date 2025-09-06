from os import write
from fetchfox_sdk import FetchFox

from srajob.sites import sites

URL = sites.DATADOG_SWE_US
URL_PATTERN = "https://careers.datadoghq.com/detail/**"

start_urls = [URL]

fox = FetchFox(api_key="ff_k2osgu7tfjvnt7dzdr91jy75jc7386k4v9ghslbu")

job_listing_template = {
    "job_title": "str | None",
    "url": "str | None",
    "location": "str | None",
    "remote": "True | False | None",
}

print(f"""
job_listing template
:--------------
{job_listing_template}
""")

data = fox.scrape({
    "pattern": URL_PATTERN,
    "start_urls": start_urls,
    "max_depth": 5,
    "max_visits": 20,
    "template": job_listing_template,
})

with open("./datas.json", "w+") as f:
    f.write(data)

print("Found URLs:", data.get("results", {}).get("hits", []))
print("Extracted items:", data.get("results", {}).get("items", []))
