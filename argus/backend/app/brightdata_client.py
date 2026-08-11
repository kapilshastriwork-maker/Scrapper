"""Bright Data Scraper Studio API client (Data Collection API).

Uses the documented Data Collection endpoints (docs.brightdata.com):

- Trigger: POST https://api.brightdata.com/dca/trigger?collector=<id>&queue_next=1
  Body is a JSON array of inputs, e.g. [{"url": "..."}]. Response contains
  {"collection_id": "<snapshot_id>"}.
- Fetch result: GET https://api.brightdata.com/dca/dataset?id=<snapshot_id>
  A completed run returns a plain JSON object containing the scraped fields
  directly, e.g. {"title": "...", "price": {"value": 24999, ...}, "url": ...}.
  While still in progress it returns a different shape (a status/error object,
  to be confirmed against the API reference).
- Authorization: "Bearer <BRIGHTDATA_API_TOKEN>" on both calls.

The most recent snapshot id for a collector is tracked in the Collector table
(Collector.last_snapshot_id) so get_latest_result() can fetch it back.
"""

import httpx
from sqlalchemy.orm import Session

from app import config
from app.database import SessionLocal
from app.models import Collector

API_BASE = "https://api.brightdata.com"
TRIGGER_ENDPOINT = f"{API_BASE}/dca/trigger"
DATASET_ENDPOINT = f"{API_BASE}/dca/dataset"
REQUEST_TIMEOUT_SECONDS = 60

RESULT_DATA_KEYS = {"title", "url"}
ERROR_STATUSES = {"error", "failed", "failure"}


class BrightDataAPIError(Exception):
    def __init__(self, method: str, url: str, status_code: int | None, body: str):
        self.method = method
        self.url = url
        self.status_code = status_code
        self.body = body
        detail = f"HTTP {status_code}: {body}" if status_code is not None else body
        super().__init__(f"Bright Data API request failed: {method} {url} -> {detail}")


async def _request(method: str, url: str, **kwargs) -> dict:
    headers = {
        "Authorization": f"Bearer {config.BRIGHTDATA_API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.request(method, url, headers=headers, **kwargs)
    except httpx.RequestError as exc:
        raise BrightDataAPIError(method, url, None, str(exc)) from exc

    if response.status_code >= 400:
        raise BrightDataAPIError(method, url, response.status_code, response.text)

    try:
        return response.json()
    except ValueError:
        return {"status_code": response.status_code, "body": response.text}


def _is_ready_result(payload) -> bool:
    if not isinstance(payload, dict):
        return False
    return any(key in payload for key in RESULT_DATA_KEYS)


def _status_is_error(payload) -> bool:
    if not isinstance(payload, dict):
        return False
    status = payload.get("status")
    return isinstance(status, str) and status.lower() in ERROR_STATUSES


def normalize_price(raw_price) -> float | None:
    if raw_price is None:
        return None
    if isinstance(raw_price, dict):
        raw_price = raw_price.get("value")
    if raw_price is None:
        return None
    if isinstance(raw_price, str):
        raw_price = (
            raw_price.replace(",", "")
            .replace("₹", "")
            .replace("$", "")
            .replace("€", "")
            .strip()
        )
    try:
        return float(raw_price)
    except (TypeError, ValueError):
        return None


def extract_result_fields(result: dict) -> dict:
    input_data = result.get("input") or {}
    return {
        "title": result.get("title"),
        "price": normalize_price(result.get("price")),
        "original_price": normalize_price(result.get("original_price")),
        "stock_status": result.get("stock_status"),
        "url": result.get("url") or input_data.get("url"),
        "reviews": result.get("reviews"),
    }


def _save_last_snapshot_id(collector_id: str, snapshot_id: str) -> None:
    db: Session = SessionLocal()
    try:
        collector = db.get(Collector, collector_id)
        if collector is not None:
            collector.last_snapshot_id = snapshot_id
            db.commit()
    finally:
        db.close()


async def trigger_collector_run(collector_id: str, url: str) -> dict:
    result = await _request(
        "POST",
        TRIGGER_ENDPOINT,
        params={"collector": collector_id, "queue_next": "1"},
        json=[{"url": url}],
    )

    snapshot_id = result.get("collection_id")
    if snapshot_id:
        _save_last_snapshot_id(collector_id, snapshot_id)

    return result


async def get_run_status(collector_id: str, run_id: str) -> dict:
    result = await _request("GET", DATASET_ENDPOINT, params={"id": run_id})
    if _status_is_error(result):
        raise BrightDataAPIError(
            "GET", DATASET_ENDPOINT, None, f"run {run_id} failed: {result}"
        )
    if _is_ready_result(result):
        return {"status": "ready", "data": result}
    return result


async def wait_for_result(
    run_id: str, poll_interval: float = 5.0, timeout: float = 300.0
) -> dict:
    import asyncio

    elapsed = 0.0
    while elapsed < timeout:
        result = await _request("GET", DATASET_ENDPOINT, params={"id": run_id})
        if _status_is_error(result):
            raise BrightDataAPIError(
                "GET", DATASET_ENDPOINT, None, f"run {run_id} failed: {result}"
            )
        if _is_ready_result(result):
            return {"status": "ready", "data": result}
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
    raise BrightDataAPIError(
        "GET",
        DATASET_ENDPOINT,
        None,
        f"timed out after {timeout}s waiting for run {run_id}",
    )


async def get_latest_result(collector_id: str) -> dict | None:
    db: Session = SessionLocal()
    try:
        collector = db.get(Collector, collector_id)
        snapshot_id = collector.last_snapshot_id if collector is not None else None
    finally:
        db.close()

    if not snapshot_id:
        return None

    result = await _request("GET", DATASET_ENDPOINT, params={"id": snapshot_id})
    if _status_is_error(result):
        raise BrightDataAPIError(
            "GET", DATASET_ENDPOINT, None, f"run {snapshot_id} failed: {result}"
        )
    if _is_ready_result(result):
        return {"status": "ready", "data": result}
    return result
