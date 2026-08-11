"""Periodic self-heal checks for every collector via APScheduler.

Runs run_and_check() from orchestrator.py for each collector on a repeating
schedule. Non-blocking: AsyncIOScheduler schedules jobs on the running event
loop, so the FastAPI server keeps serving requests.
"""

import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import brightdata_client
from app.database import SessionLocal
from app.models import Collector
from app.orchestrator import run_and_check

SCHEDULE_INTERVAL_MINUTES = 10

logger = logging.getLogger("argus.scheduler")

_scheduler: Optional[AsyncIOScheduler] = None


def _ensure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )


async def _run_all_collectors() -> None:
    db = SessionLocal()
    try:
        collector_ids = [c.id for c in db.query(Collector.id).all()]
    finally:
        db.close()

    if not collector_ids:
        logger.info("No collectors to check")
        return

    for collector_id in collector_ids:
        try:
            outcome = await run_and_check(collector_id)
        except brightdata_client.BrightDataAPIError as exc:
            logger.error(
                "collector=%s run failed: Bright Data API error: %s",
                collector_id,
                exc,
            )
            continue
        except Exception as exc:  # noqa: BLE001 - keep the loop going
            logger.error("collector=%s run failed: %s", collector_id, exc)
            continue

        issues = outcome["issues"]
        heal_event = outcome["heal_event"]
        heal_status = heal_event.status if heal_event is not None else None
        logger.info(
            "collector=%s issues=%s heal_event=%s",
            collector_id,
            bool(issues),
            heal_status,
        )


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler

    _ensure_logging()

    if _scheduler is not None:
        return _scheduler

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _run_all_collectors,
        "interval",
        minutes=SCHEDULE_INTERVAL_MINUTES,
        id="collect_all",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "Scheduler started (runs run_and_check for every collector every %d minutes)",
        SCHEDULE_INTERVAL_MINUTES,
    )
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler

    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info("Scheduler stopped")
