# Argus — Self-Healing Price Intelligence

**Built for "Into the Scrape-Verse" by WeMakeDevs, powered by Bright Data Scraper Studio.**

Most scrapers break silently the moment a site changes its layout — a renamed CSS class, a restructured price block, a redesigned page — and nobody notices until the data's already gone stale. Argus is a price and stock intelligence platform that detects those breaks automatically, diagnoses what changed in plain language, proposes a fix through Bright Data's Scraper Studio heal API, and recovers — all with a human approving the fix before it's applied.

## What it does

Argus tracks real product listings (iPhone 17 Pro across Amazon.in, Flipkart, and Croma) plus a controlled demo storefront we built ourselves specifically to prove the self-healing loop on demand. For each collector, Argus:

1. **Runs on a schedule** via Bright Data Scraper Studio, pulling structured price/stock data
2. **Validates every result** — missing fields, implausible values (e.g. a phone priced at ₹24 instead of ₹24,999), broken URLs
3. **On a detected break**, auto-generates a plain-language diagnosis and calls Bright Data's collector refactor/heal endpoint
4. **Surfaces the proposed fix for human review** — heals are never auto-applied; a person inspects the diff and approves or rejects it, matching Bright Data's own human-in-the-loop design
5. **Logs the entire event** — detection, diagnosis, prompt, decision, outcome — to a live "Heal Feed" so the whole cycle is auditable, not just claimed

## Proof, not a claim

We didn't just build the pipeline — we broke it, repeatedly, on purpose, and recorded every cycle:

- Three genuinely different page redesigns tested against our own demo storefront (simple card → real marketplace-style nested markup → currency-format edge case), each one detected, diagnosed, and healed correctly with real Bright Data API calls
- A real API failure (an unexpected 422 from the heal endpoint) that our system caught, logged, and recovered from without crashing — reliability under a genuine external fault, not just the happy path
- An honest edge case: Croma's real site now gates pricing behind a pincode entry. Argus correctly detects the missing data, requests a heal, and — importantly — recognizes when Bright Data's proposed fix is a no-op (there's genuinely nothing to select, because the price isn't in the page at all) and declines it rather than pretending to heal something that isn't a scraper bug. This is validation behaving intelligently, not just pattern-matching.

## Engineered for reliability, not just demoed

Manual testing surfaced real failure modes — a duplicate heal request rejected with a 409, a malformed heal request rejected with a 422 — so we hardened the orchestrator against them instead of just noting they happened:

- **Heal cooldown / deduplication** — before requesting a heal, Argus checks for an existing pending or in-progress heal for that collector in the last 10 minutes and reuses it instead of firing a duplicate request
- **Retry with backoff** — a failed or slow poll against Bright Data is retried once before the run is treated as failed, so a transient network hiccup doesn't get misdiagnosed as a broken scraper
- **Automated test coverage** (`backend/tests/test_orchestrator.py`) — pytest cases mocking every real failure mode we hit: a clean run, a missing-field break, a 409 conflict, a generic heal-API error, and duplicate-heal prevention. All passing.

```
pytest tests/ -v
# 5 passed
```

## Architecture

```
Scraper Studio (Bright Data)
   ↓ scheduled trigger + poll (/dca/trigger, /dca/dataset)
FastAPI backend (Python)
   ├── orchestrator.py  — run → validate → diagnose → heal → record
   ├── brightdata_client.py — typed API wrapper (trigger, poll, heal)
   ├── APScheduler — runs every collector every 10 minutes
   └── REST API — /collectors, /heal-events, /collectors/{id}/run, approve/reject
   ↓
React dashboard (Vite + TypeScript + Tailwind)
   ├── Products — live price/stock cards per collector
   ├── Heal Feed — chronological detect→heal→approve timeline
   └── Collector Health — status, success rate, last run per collector
```

**Demo storefront:** a static site we built and deployed ourselves (GitHub Pages), used specifically to trigger controlled, on-demand breaks by redesigning the page's HTML structure — proving the heal loop works against real, different page structures, not just one lucky case.

## Tech stack

- **Backend:** Python, FastAPI, SQLAlchemy, SQLite, APScheduler, httpx, pytest
- **Frontend:** React, TypeScript, Vite, Tailwind CSS
- **Scraping/Healing:** Bright Data Scraper Studio (Data Collection API + refactor/heal API)
- **Demo hosting:** GitHub Pages + GitHub Actions (auto-deploy on push)

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- A free Bright Data account (5,000 free monthly credits, no card required)

### Backend
```bash
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1   # Windows PowerShell
pip install -r requirements.txt
cp .env.example .env          # fill in your Bright Data token, collector IDs, and Telegram credentials
python seed_collectors.py
uvicorn app.main:app --reload
```
Backend runs at `http://localhost:8000` (API docs at `/docs`).

### Frontend
```bash
cd frontend
npm install
cp .env.example .env          # set VITE_API_BASE_URL if not using the default
npm run dev
```
Dashboard runs at `http://localhost:5173`.

### Running tests
```bash
cd backend
pytest tests/ -v
```

### Environment variables
See `backend/.env.example` for the full list — Bright Data API token, one collector ID + site URL per tracked product, and Telegram bot credentials for price-drop alerts.

## What's next

The detect → validate → heal → approve loop is general — it isn't hardcoded to smartphones. Extending Argus to other product categories or sites is a matter of building new Scraper Studio collectors and adding their IDs to the config; the orchestration, validation, and healing logic already works for any collector. We scoped this build to a focused, fully-proven case rather than a broad, shakier one.

## Team

Built by Kapil Shastri for the "Into the Scrape-Verse" hackathon (Aug 2026).