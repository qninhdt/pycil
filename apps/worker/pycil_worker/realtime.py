"""Worker-side Centrifugo publish over the shared realtime module.

Reuses the API's Centrifugo client (publish is HTTP + API key, no DB) so the
worker and API publish identical payloads to the same owner-scoped channels.
"""

from pycil.ports import centrifugo as client
from shared.realtime import channels
from shared.realtime.payloads import GradingResult, JobUpdate


async def publish_job(owner_uid: str, job_id: str, status: str, detail: str | None = None) -> None:
    await client.publish(
        channels.user_jobs(owner_uid, job_id),
        JobUpdate(job_id=job_id, status=status, detail=detail).to_dict(),
    )


async def publish_grading(owner_uid: str, result: GradingResult) -> None:
    await client.publish(
        channels.user_grading(owner_uid, result.response_id),
        result.to_dict(),
    )
