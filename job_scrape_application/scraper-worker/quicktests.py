import asyncio
from srajob.sites import sites
from srajob.content_selection.next_page.next_page_pattern import try_xpath_schema
from srajob.schema import datadog

import os

os.environ["PWDEBUG"] = "1"

if __name__ == "__main__":
    res = asyncio.run(try_xpath_schema(sites.DATADOG_SWE_US, "", datadog.schema, None))
    print("res - --")
    print(res)
