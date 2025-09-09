import asyncio
from datetime import datetime
import logging
import os
import platform
import shutil

from browser_use import Agent, Browser
import yaml

# Support running as a script (uv run main.py) or as a module (-m form_filler_2.main)
try:
    from .openrouter_llm import get_openrouter_llm  # type: ignore
except Exception:  # pragma: no cover - fallback for direct script execution
    from openrouter_llm import get_openrouter_llm  # type: ignore

# Apply human-like typing patch for browser_use tools
try:  # pragma: no cover
    from .human_typing_patch import apply as apply_human_typing_patch  # type: ignore
except Exception:  # pragma: no cover
    from human_typing_patch import apply as apply_human_typing_patch  # type: ignore
apply_human_typing_patch()


def _get_browser() -> Browser:
    """Create and configure a local Browser session correctly.

    Use keyword args to align with BrowserSession signature and avoid
    pydantic validation issues.
    """
    executable_path = "/usr/bin/google-chrome"
    headless = False
    keep_alive = True

    exec_arg = executable_path if os.path.exists(executable_path) else None
    logging.getLogger(__name__).info(
        "Launching browser | exec=%s headless=%s",
        exec_arg or "<playwright default>",
        headless,
    )

    return Browser(
        headless=headless,
        keep_alive=keep_alive,
        executable_path=exec_arg,
        cross_origin_iframes=True,
        window_size={"width": 1200, "height": 2000},
        disable_security=True,
    )


def get_example_yml_str() -> str:
    with open(
        "/home/boarcoder/github/srajob/form_filler_2/prompt/example_resume/priya_desi.yml", "r"
    ) as file:
        data = yaml.safe_load(file)
    return yaml.dump(data)


async def main():
    # Allow overriding the target URL via env var to support localhost testing
    # uv run python -m form_filler_2.serve_test_pages --port 8765 --duration 600
    url = "http://127.0.0.1:8765/datadog_job_7073137_app.html"
    # url = os.getenv(
    #     "TARGET_URL",
    #     "file:///home/boarcoder/github/srajob/form_filler_bot/test_pages/datadog_job_7073137_app.html",
    # )
    candidate_resume_and_answers = get_example_yml_str()
    browser = _get_browser()
    await browser.start()

    initial_task = f"""
    - Navigate to {url}
    """
    fill_field_task = f"""
    - Please view the candidate information so that you can accurately fill in the form fields, 
      and fill in the fields on the web page and determine the text to fill in each field based on the candidate resume and answers. 
      If it says to upload or manually put resume, ignore that field. This is the candidate resume:
      {candidate_resume_and_answers}
    - Do not submit the form, just fill it in. Check that all fields other than the resume are filled, and correct any missing ones. Do not submit.
    - Once you are done, save the HTML to a local file.
    """

    try:
        # Create AI agent with our custom Playwright-powered tools
        # Load OpenRouter vars from environment (provided by dotenvx run)
        openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        openrouter_model = "google/gemini-2.5-pro"  # os.getenv("OPENROUTER_MODEL", "x-ai/grok-4")

        if not openrouter_api_key:
            raise SystemExit(
                "OPENROUTER_API_KEY is required. Run via 'dotenvx run -- uv run python -m form_filler_2.main' or set it in your environment."
            )

        agent = Agent(
            llm=get_openrouter_llm(openrouter_api_key, openrouter_model),
            task=initial_task,
            browser_session=browser,
            headless=True,
        )

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        await asyncio.wait_for(agent.run(max_steps=40), timeout=60)

        followup_timeout = int(os.getenv("FOLLOWUP_RUN_TIMEOUT_SECONDS", "500"))
        agent.add_new_task(fill_field_task)
        await asyncio.wait_for(agent.run(max_steps=40), timeout=followup_timeout)

        # Keep browser open briefly to see results
        logging.info("Integration demo completed! Browser will close shortly...")
        await asyncio.sleep(2)  # Brief pause to see results

    except Exception as e:
        logging.exception("Error during run: %s", e)
        raise

    finally:
        if browser:
            try:
                await browser.kill()
            except Exception:
                logging.exception("Error while killing browser")
        logging.info("Cleanup complete")


if __name__ == "__main__":
    # Configure logging level
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Run with a hard timeout to avoid infinite runs
    overall_timeout = int(os.getenv("OVERALL_TIMEOUT_SECONDS", "600"))
    try:
        asyncio.run(asyncio.wait_for(main(), timeout=overall_timeout))
    except asyncio.TimeoutError:
        logging.error("Overall timeout (%ss) reached; exiting.", overall_timeout)
