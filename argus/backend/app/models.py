from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Collector(Base):
    __tablename__ = "collectors"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    brightdata_collector_id: Mapped[str] = mapped_column(String, nullable=False)
    site_url: Mapped[str] = mapped_column(String, nullable=False)
    last_snapshot_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    scrape_results: Mapped[list[ScrapeResult]] = relationship(
        back_populates="collector"
    )
    heal_events: Mapped[list[HealEvent]] = relationship(back_populates="collector")


class ScrapeResult(Base):
    __tablename__ = "scrape_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collector_id: Mapped[str] = mapped_column(
        String, ForeignKey("collectors.id"), nullable=False
    )
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    original_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    discount_percentage: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stock_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    collector: Mapped[Collector] = relationship(back_populates="scrape_results")


class HealEvent(Base):
    __tablename__ = "heal_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collector_id: Mapped[str] = mapped_column(
        String, ForeignKey("collectors.id"), nullable=False
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    issue_description: Mapped[str] = mapped_column(Text, nullable=False)
    heal_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    diff_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    collector: Mapped[Collector] = relationship(back_populates="heal_events")
