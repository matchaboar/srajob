from __future__ import annotations

from dataclasses import dataclass

from temporalio import workflow

# Import activity prototypes inside workflow
with workflow.unsafe.imports_passed_through():
    from .ai_form_activities import (
        get_resume_for_user,
        run_form_fill,
        complete_ai_application,
        fail_ai_application,
    )


@dataclass
class FormFillResult:
    queue_id: str
    status: str


@workflow.defn(name="FormFillWorkflow")
class FormFillWorkflow:
    @workflow.run
    async def run(self, queue_id: str, job_url: str, user_id: str) -> FormFillResult:  # type: ignore[override]
        workflow.logger.info("FormFillWorkflow start: queue_id=%s user_id=%s url=%s", queue_id, user_id, job_url)
        try:
            resume = await workflow.execute_activity(
                get_resume_for_user,
                args=[user_id],
                schedule_to_close_timeout=workflow.timedelta(seconds=30),
            )
            result = await workflow.execute_activity(
                run_form_fill,
                args=[job_url, resume],
                start_to_close_timeout=workflow.timedelta(minutes=10),
            )
            await workflow.execute_activity(
                complete_ai_application,
                args=[queue_id, result.get("filledData"), result.get("logs")],
                schedule_to_close_timeout=workflow.timedelta(seconds=30),
            )
            workflow.logger.info("FormFillWorkflow completed: queue_id=%s", queue_id)
            return FormFillResult(queue_id=queue_id, status="COMPLETED")
        except Exception as e:  # noqa: BLE001
            await workflow.execute_activity(
                fail_ai_application,
                args=[queue_id, str(e)],
                schedule_to_close_timeout=workflow.timedelta(seconds=30),
            )
            workflow.logger.error("FormFillWorkflow error: queue_id=%s error=%s", queue_id, str(e))
            return FormFillResult(queue_id=queue_id, status="ERROR")
