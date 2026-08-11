"""Self-healing scrape pipeline orchestration.

Coordinates the Bright Data client, result validation, and heal-event
proposal into a single flow that schedulers and API endpoints call.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from app import brightdata_client
from app.database import SessionLocal
from app.models import Collector, HealEvent, ScrapeResult

logger = logging.getLogger("argus.orchestrator")

HEAL_ENDPOINT = (
    "https://api.brightdata.com/dca/collectors/{collector_id}/refactor_template"
)
PHONE_PRICE_FLOOR = 1000.0
HEAL_PROMPT_LIMIT = 1000
HEAL_IN_PROGRESS_PHRASE = "refactor job is still in progress"
HEAL_COOLDOWN_MINUTES = 10
WAIT_RESULT_RETRIES = 1
WAIT_RETRY_DELAY_SECONDS = 5.0


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


def _find_in_flight_heal(collector_id: str) -> HealEvent | None:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=HEAL_COOLDOWN_MINUTES)
    db = SessionLocal()
    try:
        return (
            db.query(HealEvent)
            .filter(
                HealEvent.collector_id == collector_id,
                HealEvent.status.in_(["pending", "heal_already_in_progress"]),
                HealEvent.detected_at >= cutoff,
            )
            .order_by(HealEvent.detected_at.desc())
            .first()
        )
    finally:
        db.close()


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

    result = None
    for attempt in range(WAIT_RESULT_RETRIES + 1):
        try:
            result = await brightdata_client.wait_for_result(snapshot_id)
            break
        except brightdata_client.BrightDataAPIError as exc:
            if attempt < WAIT_RESULT_RETRIES:
                logger.warning(
                    "collector=%s wait_for_result attempt %d/%d failed (%s); "
                    "retrying in %ss",
                    collector_id,
                    attempt + 1,
                    WAIT_RESULT_RETRIES + 1,
                    exc,
                    WAIT_RETRY_DELAY_SECONDS,
                )
                await asyncio.sleep(WAIT_RETRY_DELAY_SECONDS)
            else:
                logger.error(
                    "collector=%s wait_for_result failed after %d attempts: %s",
                    collector_id,
                    WAIT_RESULT_RETRIES + 1,
                    exc,
                )
                raise
    if result is None:
        raise RuntimeError(
            f"wait_for_result for collector {collector_id} did not produce a result"
        )

    raw_data = result["data"]
    fields = brightdata_client.extract_result_fields(raw_data)

    reviews_json = (
        json.dumps(fields["reviews"]) if isinstance(fields["reviews"], list) else None
    )
    now = datetime.now(timezone.utc)
    scrape_result = ScrapeResult(
        collector_id=collector_id,
        title=fields["title"],
        price=fields["price"],
        original_price=fields["original_price"],
        stock_status=fields["stock_status"],
        url=fields["url"],
        reviews=reviews_json,
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


def _validate_reviews(result: ScrapeResult) -> list[str]:
    raw = json.loads(result.raw_json) if result.raw_json else None
    schema_has_reviews = isinstance(raw, dict) and "reviews" in raw

    reviews = None
    if result.reviews is not None:
        try:
            reviews = json.loads(result.reviews)
        except (TypeError, ValueError):
            reviews = None

    if schema_has_reviews and reviews is None:
        return ["reviews field is missing"]

    if not isinstance(reviews, list) or not reviews:
        return []

    for entry in reviews:
        if not isinstance(entry, dict):
            return ["reviews contain malformed entries"]
        name = entry.get("reviewer_name")
        text = entry.get("text")
        rating = entry.get("rating")
        if not name or not str(name).strip() or not text or not str(text).strip():
            return ["reviews contain malformed entries"]
        if not (
            isinstance(rating, (int, float))
            and not isinstance(rating, bool)
            and 1 <= rating <= 5
        ):
            return ["reviews contain malformed entries"]

    return []


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

    issues.extend(_validate_reviews(result))

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

    reviews_desc = ""
    if any("reviews" in issue for issue in issues):
        parsed = None
        if result.reviews:
            try:
                parsed = json.loads(result.reviews)
            except (TypeError, ValueError):
                parsed = None
        if isinstance(parsed, list) and parsed:
            first = parsed[0]
            if isinstance(first, dict):
                name = first.get("reviewer_name", "?")
                rating = first.get("rating", "?")
                snippet = str(first.get("text", ""))[:60]
            else:
                name, rating, snippet = "?", "?", ""
            reviews_desc = (
                f" reviews={len(parsed)} entries; first entry: "
                f"reviewer_name={name!r}, rating={rating!r}, text={snippet!r}"
            )
        else:
            reviews_desc = " reviews=(missing or empty)"

    lines.append(
        f"Current extracted values: title={title!r}, price={price}, "
        f"stock_status={result.stock_status!r}, url={result.url!r}.{reviews_desc}"
    )

    correct_guidance = (
        "Correct output should contain the full product title, the full price as one "
        "number (e.g. 24999, not 24), and a valid stock status."
    )
    if reviews_desc:
        correct_guidance += (
            " It should also include a reviews list where each entry has a "
            "reviewer_name, a text, and a numeric rating between 1 and 5."
        )
    lines.append(correct_guidance)

    fields_phrase = "price, title, stock status, and url"
    if reviews_desc:
        fields_phrase = "price, title, stock status, url, and reviews"
    lines.append(
        f"Please update the collector template so {fields_phrase} are extracted correctly."
    )
    return "\n".join(lines)[:HEAL_PROMPT_LIMIT]


def _ensure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )


async def trigger_heal(
    collector: Collector, issues: list[str], result: ScrapeResult
) -> HealEvent:
    _ensure_logging()

    prompt = build_heal_prompt(collector, issues, result)

    # TODO(verify): endpoint path and request body field name ("prompt" vs
    # "instructions") are unconfirmed; check docs.brightdata.com before live use.
    endpoint = HEAL_ENDPOINT.format(collector_id=collector.brightdata_collector_id)
    logger.info(
        "POST heal prompt -> collector_id=%s brightdata_collector_id=%s "
        "prompt_length=%d (limit %d)\nprompt:\n%s",
        collector.id,
        collector.brightdata_collector_id,
        len(prompt),
        HEAL_PROMPT_LIMIT,
        prompt,
    )

    heal_status = "pending"
    error_message = None
    try:
        response = await brightdata_client._request(
            "POST", endpoint, json={"prompt": prompt}
        )
    except brightdata_client.BrightDataAPIError as exc:
        response = {"status_code": exc.status_code, "body": exc.body}
        if (
            exc.status_code == 409
            and HEAL_IN_PROGRESS_PHRASE in (exc.body or "").lower()
        ):
            heal_status = "heal_already_in_progress"
        else:
            heal_status = "heal_request_failed"
        error_message = str(exc)
        logger.error(
            "heal POST failed collector_id=%s status=%s error=%s\nprompt:\n%s",
            collector.id,
            heal_status,
            error_message,
            prompt,
        )

    heal_event = HealEvent(
        collector_id=collector.id,
        detected_at=datetime.now(timezone.utc),
        issue_description="; ".join(issues),
        heal_prompt=prompt,
        status=heal_status,
        diff_summary=json.dumps(response),
        error_message=error_message,
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
        in_flight = _find_in_flight_heal(collector_id)
        if in_flight is not None:
            heal_event = in_flight
            logger.info(
                "collector=%s heal already in flight (event=%s, status=%s); "
                "skipping duplicate",
                collector_id,
                in_flight.id,
                in_flight.status,
            )
        else:
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
