"""Swap a demo-shop layout into index.html, push, then run the demo collector.

Usage (from anywhere):

    python test_layout_swap.py layout-a.html

Flow:
  1. Copy ../demo-shop/<layout> over ../demo-shop/index.html
  2. Commit ("Test swap: <layout>") and push from the repo root
  3. Pause so GitHub Pages can redeploy
  4. Run the self-heal pipeline for the "demo" collector and print the outcome
"""

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

os.chdir(Path(__file__).resolve().parent)

from app import brightdata_client  # noqa: E402
from app.orchestrator import run_and_check  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent
DEMO_SHOP_DIR = BACKEND_DIR.parent / "demo-shop"
REPO_ROOT = BACKEND_DIR.parents[1]

HEAL_IN_PROGRESS_PHRASE = "refactor job is still in progress"


def run_git(args: list[str]) -> None:
    print(f"$ git {' '.join(args)}")
    try:
        result = subprocess.run(
            args,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr.strip() or f"git {' '.join(args)} failed\n")
        raise SystemExit(1) from exc
    output = (result.stdout or "").strip()
    if output:
        print(output)


def swap_layout(layout: str) -> None:
    src = DEMO_SHOP_DIR / layout
    if not src.is_file():
        available = sorted(p.name for p in DEMO_SHOP_DIR.iterdir() if p.is_file())
        sys.stderr.write(
            f"Layout file not found: {src}\n"
            f"Available files in demo-shop: {', '.join(available)}\n"
        )
        raise SystemExit(1)

    shutil.copyfile(src, DEMO_SHOP_DIR / "index.html")
    print(f"Swapped {DEMO_SHOP_DIR.name}/index.html <- {layout}")


def git_commit_and_push(layout: str) -> None:
    run_git(["git", "add", "argus/demo-shop/index.html"])

    if run_git_result(["git", "diff", "--cached", "--quiet"]):
        print("index.html is unchanged; nothing to commit.")
    else:
        run_git(["git", "commit", "-m", f"Test swap: {layout}"])

    run_git(["git", "push"])


def run_git_result(args: list[str]) -> bool:
    result = subprocess.run(
        args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


async def check_demo_collector() -> None:
    try:
        outcome = await run_and_check("demo")
    except brightdata_client.BrightDataAPIError as exc:
        if (
            exc.status_code == 409
            and HEAL_IN_PROGRESS_PHRASE in (exc.body or "").lower()
        ):
            print(
                "A refactor/heal job is already in progress for this collector; skipped healing."
            )
            raise SystemExit(0)
        print(f"Bright Data API error: {exc}")
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"Unexpected error while running the demo collector: {exc}")
        raise SystemExit(1) from exc

    result = outcome["result"]
    print("--- Scrape result ---")
    print(f"title        : {result.title}")
    print(f"price        : {result.price}")
    print(f"original_price: {result.original_price}")
    print(f"stock_status : {result.stock_status}")
    print(f"url          : {result.url}")

    issues = outcome["issues"]
    print("--- Issues ---")
    if issues:
        for issue in issues:
            print(f"- {issue}")
    else:
        print("(none)")

    heal_event = outcome["heal_event"]
    print("--- Heal ---")
    if heal_event is not None:
        print(f"heal_event.status: {heal_event.status}")
        if heal_event.status == "heal_already_in_progress":
            print("The collector is already being healed (409 refactor in progress).")
    else:
        print("no heal proposed (no issues detected)")

    if issues:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Swap a demo-shop layout into index.html, push, and run the demo collector."
    )
    parser.add_argument(
        "layout",
        help="Layout file in demo-shop/ to copy over index.html, e.g. layout-a.html",
    )
    args = parser.parse_args()

    swap_layout(args.layout)
    git_commit_and_push(args.layout)

    print("Waiting ~30-60 seconds for GitHub Pages to redeploy...")
    input("Press Enter once the deployment finishes: ")

    asyncio.run(check_demo_collector())


if __name__ == "__main__":
    main()
