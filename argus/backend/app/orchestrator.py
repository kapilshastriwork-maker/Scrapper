"""Self-healing scrape pipeline orchestration.

Coordinates the Bright Data client, result validation, and heal-event
proposal into a single flow that schedulers and API endpoints call.
"""

import json
from datetime import datetime
from urllib.parse import urlsplit

from app import brightdata_client
from app.database import SessionLocal
from app.models import Collector, HealEvent, ScrapeResult

HEAL_ENDPOINT = (
    "https://api.brightdata.com/dca/collectors/{collector_id}/refactor_template"
)
PHONE_PRICE_FLOOR = 1000.0
HEAL_PROMPT_LIMIT = 1000


def _get_collector(collector_id: str) -> Collector | None:
    db = SessionLocal()
    try:
        return db.get(Collector, collector_id)
    finally:
        db.close()


def _host(value: str) -> str:
    if "://" not in value:
        value = f"https://{value}"
    return (urlsplit(value).hostname or "").lower()


def _url_matches_site(url: str, site_url: str) -> bool:
    expected = _host(site_url)
    actual = _host(url)
    return bool(expected) and expected == actual


async def run_collector(collector_id: str) -> ScrapeResult:
    collector = _get_collector(collector_id)
    if collector is None:
        raise ValueError(f"Unknown collector: {collector_id}")

    trigger_response = await brightdata_client.trigger_collector_run(
        collector.brightdata_collector_id, collector.site_url
    )
    snapshot_id = trigger_response.get("collection_id")
    if not snapshot_id:
        raise RuntimeError(
            f"No collection_id returned when triggering collector {collector_id}"
        )

    result = await brightdata_client.wait_for_result(snapshot_id)
    raw_data = result["data"]
    fields = brightdata_client.extract_result_fields(raw_data)

    now = datetime.utcnow()
    scrape_result = ScrapeResult(
        collector_id=collector_id,
        title=fields["title"],
        price=fields["price"],
        original_price=fields["original_price"],
        stock_status=fields["stock_status"],
        url=fields["url"],
        raw_json=json.dumps(raw_data),
        scraped_at=now,
    )

    db = SessionLocal()
    try:
        db.add(scrape_result)
        saved = db.get(Collector, collector_id)
        if saved is not None:
            saved.last_snapshot_id = snapshot_id
            saved.last_run_at = now
            saved.last_status = "success"
        db.commit()
        db.refresh(scrape_result)
        return scrape_result
    finally:
        db.close()


def validate_result(result: ScrapeResult) -> list[str]:
    issues: list[str] = []
    collector = _get_collector(result.collector_id)

    if not result.title or not result.title.strip():
        issues.append("title is missing or empty")

    if result.price is None:
        issues.append("price is missing")
    elif result.price <= 0:
        issues.append(f"price is zero or negative (got {result.price})")
    elif result.price < PHONE_PRICE_FLOOR:
        issues.append(
            f"price {result.price} is implausibly low for a phone listing "
            f"(expected at least {PHONE_PRICE_FLOOR:g})"
        )

    if not result.stock_status or not result.stock_status.strip():
        issues.append("stock_status is missing or empty")

    if not result.url:
        issues.append("url is missing")
    elif collector is not None and not _url_matches_site(
        result.url, collector.site_url
    ):
        issues.append(
            f"url {result.url} does not match the expected site domain {collector.site_url}"
        )

    db = SessionLocal()
    try:
        result.is_valid = len(issues) == 0
        db.add(result)
        db.commit()
        db.refresh(result)
    finally:
        db.close()

    return issues


def build_heal_prompt(
    collector: Collector, issues: list[str], result: ScrapeResult
) -> str:
    title = result.title or "(missing)"
    price = f"{result.price:g}" if result.price is not None else "(missing)"
    lines = [
        f"The collector for {collector.name} at {collector.site_url} returned a product "
        "page with the following problems:"
    ]
    lines.extend(f"- {issue}" for issue in issues)
    lines.append(
        f"Current extracted values: title={title!r}, price={price}, "
        f"stock_status={result.stock_status!r}, url={result.url!r}."
    )
    lines.append(
        "Correct output should contain the full product title, the full price as one "
        "number (e.g. 24999, not 24), and a valid stock status."
    )
    lines.append(
        "Please update the collector template so price, title, stock status, and url "
        "are extracted correctly."
    )
    return "\n".join(lines)[:HEAL_PROMPT_LIMIT]


async def trigger_heal(
    collector: Collector, issues: list[str], result: ScrapeResult
) -> HealEvent:
    prompt = build_heal_prompt(collector, issues, result)

    # TODO(verify): endpoint path and request body field name ("prompt" vs
    # "instructions") are unconfirmed; check docs.brightdata.com before live use.
    endpoint = HEAL_ENDPOINT.format(collector_id=collector.brightdata_collector_id)
    response = await brightdata_client._request(
        "POST", endpoint, json={"prompt": prompt}
    )

    heal_event = HealEvent(
        collector_id=collector.id,
        detected_at=datetime.utcnow(),
        issue_description="; ".join(issues),
        heal_prompt=prompt,
        status="pending",
        diff_summary=json.dumps(response),
    )

    db = SessionLocal()
    try:
        db.add(heal_event)
        db.commit()
        db.refresh(heal_event)
        return heal_event
    finally:
        db.close()


async def run_and_check(collector_id: str) -> dict:
    result = await run_collector(collector_id)
    issues = validate_result(result)

    collector = _get_collector(collector_id)
    if collector is None:
        raise ValueError(f"Unknown collector: {collector_id}")

    heal_event = None
    if issues:
        heal_event = await trigger_heal(collector, issues, result)

    db = SessionLocal()
    try:
        saved = db.get(Collector, collector_id)
        if saved is not None:
            saved.last_status = "degraded" if issues else "success"
        db.commit()
    finally:
        db.close()

    return {"result": result, "issues": issues, "heal_event": heal_event}
