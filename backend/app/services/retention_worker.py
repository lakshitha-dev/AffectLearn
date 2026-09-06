"""Scheduled enforcement of the research-data retention limit.

WHY THIS EXISTS

The participant-facing copy states that study data is deleted within 90 days. That existed as a
sentence and not as a job, which the thesis records as a prerequisite for opening the pilot. A
retention limit nobody enforces is a retention limit you are not keeping — it is just a plan to
delete something later, and "later" has no deadline.

WHY A LIFESPAN TASK AND NOT CRON

This deployment has no scheduler, no Celery and no cron: `research_worker` is the only existing
background job and it is an asyncio task started in the FastAPI lifespan. Introducing a second
scheduling technology for one daily sweep would add an operational surface — another thing to
deploy, monitor and get wrong — for no benefit at this scale. This follows the pattern already in
the codebase so there is one place to look for background work.

The consequence is honest and worth stating: the sweep only runs while the API is running, so a
long outage delays it. A retention limit measured in days tolerates that; one measured in hours
would not, and would need real scheduling.

WHAT IT DELETES

`research_events` only. That is what the retention promise covers. A learner's account, their
enrolments and their own course progress are theirs to keep until they ask for erasure, and
quietly deleting somebody's learning history because a research limit expired would be a
different and unwelcome decision made under cover of a privacy feature.
"""

from __future__ import annotations

import asyncio

import structlog

from app.core.config import settings
from app.services import data_rights_service

logger = structlog.get_logger(__name__)

#: Seconds between sweeps. Daily: the limit is measured in days, so sweeping more often would
#: only add load, and sweeping less often would let rows outlive the promise by up to the gap.
_SWEEP_INTERVAL_SECONDS = 24 * 60 * 60

#: Delay before the first sweep, so a deploy that crash-loops does not run a delete on every boot.
_INITIAL_DELAY_SECONDS = 60


async def run_retention_worker(stop_event: asyncio.Event) -> None:
    """Sweep expired research events until `stop_event` is set. Never raises.

    A failed sweep is logged and retried on the next cycle rather than killing the task: a
    transient database problem must not silently disable retention for the lifetime of the
    process, which is exactly the failure mode the research worker's Redis handling was fixed for.
    """
    days = int(getattr(settings, "RESEARCH_RETENTION_DAYS", 90) or 0)
    if days <= 0:
        logger.info("retention_worker_disabled", days=days)
        return

    logger.info("retention_worker_started", days=days)
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=_INITIAL_DELAY_SECONDS)
        return  # asked to stop during the initial delay
    except asyncio.TimeoutError:
        pass

    while not stop_event.is_set():
        try:
            from app.db.session import async_session

            async with async_session() as db:
                removed = await data_rights_service.purge_research_events_older_than(
                    db, days=days
                )
            logger.info("retention_sweep_complete", removed=removed, days=days)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — one bad sweep must not disable retention forever
            logger.exception("retention_sweep_failed", days=days)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=_SWEEP_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            continue

    logger.info("retention_worker_stopped")
