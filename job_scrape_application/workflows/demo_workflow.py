from __future__ import annotations

from temporalio import workflow


@workflow.defn(name="DemoWorkflow")
class DemoWorkflow:
    @workflow.run
    async def run(self, url: str) -> str:  # type: ignore[override]
        workflow.logger.info("DemoWorkflow received url: %s", url)
        # Sleep briefly to make the run visible in UI
        await workflow.sleep(1)
        return f"Preview-only workflow completed for {url}"

