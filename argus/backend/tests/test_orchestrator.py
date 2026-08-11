import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from app import brightdata_client
from app.models import Collector, HealEvent, ScrapeResult
from app.orchestrator import HEAL_IN_PROGRESS_PHRASE, run_and_check


def product_data(**overrides):
    data = {
        "title": "Argus Phone X1",
        "price": 24999,
        "original_price": None,
        "stock_status": "In Stock",
        "url": "https://example.com",
    }
    data.update(overrides)
    return data


def _patch_api(monkeypatch, data, heal_side_effect=None):
    monkeypatch.setattr(
        brightdata_client,
        "trigger_collector_run",
        AsyncMock(return_value={"collection_id": "snap_1"}),
    )
    monkeypatch.setattr(
        brightdata_client,
        "wait_for_result",
        AsyncMock(return_value={"status": "ready", "data": data}),
    )
    if heal_side_effect is not None:
        monkeypatch.setattr(
            brightdata_client,
            "_request",
            AsyncMock(side_effect=heal_side_effect),
        )
    else:
        monkeypatch.setattr(brightdata_client, "_request", AsyncMock(return_value={}))


def test_clean_run_produces_no_issues_and_no_heal(db_env, monkeypatch):
    _patch_api(monkeypatch, product_data())

    outcome = asyncio.run(run_and_check("demo"))

    assert outcome["issues"] == []
    assert outcome["heal_event"] is None

    db = db_env()
    collector = db.get(Collector, "demo")
    assert collector.last_status == "success"
    assert db.query(ScrapeResult).count() == 1
    db.close()


def test_missing_price_creates_pending_heal(db_env, monkeypatch):
    _patch_api(monkeypatch, product_data(price=None))

    outcome = asyncio.run(run_and_check("demo"))

    assert outcome["issues"] == ["price is missing"]
    assert outcome["heal_event"] is not None
    assert outcome["heal_event"].status == "pending"

    db = db_env()
    assert db.query(HealEvent).count() == 1
    db.close()


def test_409_heal_in_progress_does_not_raise(db_env, monkeypatch):
    exc = brightdata_client.BrightDataAPIError(
        "POST",
        "https://api.brightdata.com/dca/collectors/c_demo/refactor_template",
        409,
        HEAL_IN_PROGRESS_PHRASE,
    )
    _patch_api(monkeypatch, product_data(price=None), heal_side_effect=exc)

    outcome = asyncio.run(run_and_check("demo"))

    heal_event = outcome["heal_event"]
    assert heal_event.status == "heal_already_in_progress"
    assert heal_event.error_message is not None


def test_generic_heal_error_becomes_heal_request_failed(db_env, monkeypatch):
    exc = brightdata_client.BrightDataAPIError(
        "POST",
        "https://api.brightdata.com/dca/collectors/c_demo/refactor_template",
        500,
        "boom",
    )
    _patch_api(monkeypatch, product_data(price=None), heal_side_effect=exc)

    outcome = asyncio.run(run_and_check("demo"))

    heal_event = outcome["heal_event"]
    assert heal_event.status == "heal_request_failed"
    assert "500" in heal_event.error_message


def test_in_flight_heal_prevents_duplicate(db_env, monkeypatch):
    heal = AsyncMock(return_value={})
    monkeypatch.setattr(
        brightdata_client,
        "trigger_collector_run",
        AsyncMock(return_value={"collection_id": "snap_1"}),
    )
    monkeypatch.setattr(
        brightdata_client,
        "wait_for_result",
        AsyncMock(return_value={"status": "ready", "data": product_data(price=None)}),
    )
    monkeypatch.setattr(brightdata_client, "_request", heal)

    first = asyncio.run(run_and_check("demo"))
    second = asyncio.run(run_and_check("demo"))

    assert first["heal_event"].status == "pending"
    assert heal.call_count == 1
    assert second["heal_event"].id == first["heal_event"].id

    db = db_env()
    count = db.query(HealEvent).filter(HealEvent.collector_id == "demo").count()
    assert count == 1
    db.close()


def _saved_reviews(db_env) -> str | None:
    db = db_env()
    result = db.query(ScrapeResult).order_by(ScrapeResult.id.desc()).first()
    reviews = result.reviews if result is not None else None
    db.close()
    return reviews


def test_empty_reviews_list_is_valid_and_stored(db_env, monkeypatch):
    _patch_api(monkeypatch, product_data(reviews=[]))

    outcome = asyncio.run(run_and_check("demo"))

    assert outcome["issues"] == []
    assert outcome["heal_event"] is None
    assert _saved_reviews(db_env) == "[]"


def test_reviews_key_present_but_null_is_missing(db_env, monkeypatch):
    _patch_api(monkeypatch, product_data(reviews=None))

    outcome = asyncio.run(run_and_check("demo"))

    assert "reviews field is missing" in outcome["issues"]
    assert _saved_reviews(db_env) is None


def test_valid_reviews_are_stored_without_issues(db_env, monkeypatch):
    reviews = [
        {"reviewer_name": "Priya Sharma", "text": "Great phone.", "rating": 5},
        {"reviewer_name": "Rahul Mehta", "text": "Solid battery.", "rating": 4},
    ]
    _patch_api(monkeypatch, product_data(reviews=reviews))

    outcome = asyncio.run(run_and_check("demo"))

    assert outcome["issues"] == []
    saved = _saved_reviews(db_env)
    assert saved is not None
    assert json.loads(saved) == reviews


@pytest.mark.parametrize(
    "reviews",
    [
        [{"text": "No name.", "rating": 5}],
        [{"reviewer_name": "  ", "text": "Blank name.", "rating": 5}],
        [{"reviewer_name": "A", "text": "", "rating": 5}],
        [{"reviewer_name": "A", "text": "ok", "rating": 6}],
        [{"reviewer_name": "A", "text": "ok", "rating": "5"}],
        [{"reviewer_name": "A", "text": "ok", "rating": 5}, "not-a-dict"],
    ],
)
def test_malformed_reviews_entry_is_flagged(db_env, monkeypatch, reviews):
    _patch_api(monkeypatch, product_data(reviews=reviews))

    outcome = asyncio.run(run_and_check("demo"))

    assert "reviews contain malformed entries" in outcome["issues"]
