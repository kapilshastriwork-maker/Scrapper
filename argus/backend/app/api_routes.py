"""HTTP API routes for Argus: collectors, scrape results, and heal events."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Collector, HealEvent, ScrapeResult
from app.orchestrator import run_and_check

router = APIRouter()

RESULTS_LIMIT = 20
HEAL_EVENTS_LIMIT = 50


class CollectorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    site_url: str
    last_snapshot_id: Optional[str]
    last_status: Optional[str]
    last_run_at: Optional[datetime]
    created_at: datetime


class ScrapeResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    collector_id: str
    title: Optional[str]
    price: Optional[float]
    original_price: Optional[float]
    stock_status: Optional[str]
    url: Optional[str]
    scraped_at: datetime
    is_valid: bool


class HealEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    collector_id: str
    collector_name: Optional[str]
    detected_at: datetime
    issue_description: str
    heal_prompt: str
    status: str
    diff_summary: Optional[str]
    error_message: Optional[str]
    resolved_at: Optional[datetime]


def _get_collector_or_404(db: Session, collector_id: str) -> Collector:
    collector = db.get(Collector, collector_id)
    if collector is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown collector: {collector_id}"
        )
    return collector


def _get_heal_event_or_404(db: Session, event_id: int) -> HealEvent:
    event = db.get(HealEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Unknown heal event: {event_id}")
    return event


@router.get("/collectors", response_model=list[CollectorOut])
def list_collectors(db: Session = Depends(get_db)):
    return db.query(Collector).order_by(Collector.name).all()


@router.get("/collectors/{collector_id}/results", response_model=list[ScrapeResultOut])
def list_collector_results(collector_id: str, db: Session = Depends(get_db)):
    _get_collector_or_404(db, collector_id)
    return (
        db.query(ScrapeResult)
        .filter(ScrapeResult.collector_id == collector_id)
        .order_by(ScrapeResult.scraped_at.desc())
        .limit(RESULTS_LIMIT)
        .all()
    )


@router.post("/collectors/{collector_id}/run")
async def run_collector(collector_id: str, db: Session = Depends(get_db)):
    _get_collector_or_404(db, collector_id)

    try:
        outcome = await run_and_check(collector_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    result = outcome["result"]
    heal_event = outcome["heal_event"]
    return {
        "collector_id": collector_id,
        "issues": outcome["issues"],
        "heal_event_status": heal_event.status if heal_event is not None else None,
        "result": {
            "id": result.id,
            "title": result.title,
            "price": result.price,
            "original_price": result.original_price,
            "stock_status": result.stock_status,
            "url": result.url,
            "scraped_at": result.scraped_at,
            "is_valid": result.is_valid,
        },
    }


def _heal_event_with_name(event: HealEvent) -> HealEventOut:
    return HealEventOut(
        id=event.id,
        collector_id=event.collector_id,
        collector_name=event.collector.name if event.collector else None,
        detected_at=event.detected_at,
        issue_description=event.issue_description,
        heal_prompt=event.heal_prompt,
        status=event.status,
        diff_summary=event.diff_summary,
        error_message=event.error_message,
        resolved_at=event.resolved_at,
    )


@router.get("/heal-events", response_model=list[HealEventOut])
def list_heal_events(db: Session = Depends(get_db)):
    events = (
        db.query(HealEvent)
        .order_by(HealEvent.detected_at.desc())
        .limit(HEAL_EVENTS_LIMIT)
        .all()
    )
    return [_heal_event_with_name(event) for event in events]


@router.get("/heal-events/{event_id}", response_model=HealEventOut)
def get_heal_event(event_id: int, db: Session = Depends(get_db)):
    event = _get_heal_event_or_404(db, event_id)
    return _heal_event_with_name(event)


@router.post("/heal-events/{event_id}/approve", response_model=HealEventOut)
def approve_heal_event(event_id: int, db: Session = Depends(get_db)):
    event = _get_heal_event_or_404(db, event_id)
    event.status = "approved"
    event.resolved_at = datetime.utcnow()
    db.commit()
    db.refresh(event)
    return _heal_event_with_name(event)


@router.post("/heal-events/{event_id}/reject", response_model=HealEventOut)
def reject_heal_event(event_id: int, db: Session = Depends(get_db)):
    event = _get_heal_event_or_404(db, event_id)
    event.status = "rejected"
    event.resolved_at = datetime.utcnow()
    db.commit()
    db.refresh(event)
    return _heal_event_with_name(event)
