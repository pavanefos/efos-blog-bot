"""EFOS AI Blog Automation - command line entry point + daily scheduler.

Usage:
  python -m src                 # run the scheduler (default), sleeps until SCHEDULE_HOUR:MINUTE daily
  python -m src --once          # run a single publishing cycle now
  python -m src --once --dry-run# run once without publishing (set DRY_RUN=true)
  python -m src --test          # test connections (Laravel API + OpenRouter)
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta

from .config import CFG
from .logger import log
from .pipeline import run_once


def _next_run_times() -> list[datetime]:
    """Return today's + tomorrow's schedule times as datetimes, sorted."""
    times: list[datetime] = []
    for day in (0, 1):
        base = (datetime.now() + timedelta(days=day)).replace(
            second=0, microsecond=0
        )
        src = CFG.schedule_times or [f"{CFG.schedule_hour:02d}:{CFG.schedule_minute:02d}"]
        for t in src:
            h, m = t.split(":")
            times.append(base.replace(hour=int(h), minute=int(m)))
    return sorted(times)


def _seconds_until_next_run() -> float:
    now = datetime.now()
    upcoming = [t for t in _next_run_times() if t > now]
    if not upcoming:
        upcoming = _next_run_times()  # fallback (shouldn't happen)
    return (upcoming[0] - now).total_seconds()


def run_scheduler() -> None:
    slots = CFG.schedule_times or [f"{CFG.schedule_hour:02d}:{CFG.schedule_minute:02d}"]
    log.info(
        f"Scheduler started. Will publish ~{CFG.blogs_per_day} blog(s) per slot at "
        f"these times daily: {', '.join(slots)} (dry_run={CFG.dry_run}). "
        "Runs every day until stopped."
    )
    while True:
        wait = _seconds_until_next_run()
        log.info(f"Next run at {_next_run_times()[0].strftime('%Y-%m-%d %H:%M')} "
                 f"(in {wait/60:.0f} min).")
        time.sleep(wait)
        try:
            run_once()
        except Exception as e:  # noqa: BLE001 - never crash the scheduler
            log.error(f"Scheduler cycle error: {e}")


def test_connections() -> None:
    import requests

    log.info("Testing OpenRouter connection...")
    try:
        from .ai_client import chat_json

        out = chat_json("Reply with JSON: {\"ok\":true}", "Return {\"ok\":true} as JSON.")
        log.info(f"OpenRouter OK: {out}")
    except Exception as e:  # noqa: BLE001
        log.error(f"OpenRouter FAILED: {e}")

    log.info(f"Testing Laravel API at {CFG.publish_url} ...")
    try:
        r = requests.post(
            CFG.publish_url,
            headers={"Authorization": f"Bearer {CFG.ai_blog_token}", "Accept": "application/json"},
            data={"category_id": "999999"},
            timeout=30,
        )
        # We expect 401/403 (bad token) or 422 (validation) - any structured JSON
        # response proves the endpoint is reachable.
        log.info(f"Laravel reachable (HTTP {r.status_code}). Body: {r.text[:200]}")
    except Exception as e:  # noqa: BLE001
        log.error(f"Laravel UNREACHABLE: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="EFOS AI Blog Automation (Python, no n8n/Node).")
    parser.add_argument("--once", action="store_true", help="Run a single cycle and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Do not publish (override DRY_RUN).")
    parser.add_argument("--test", action="store_true", help="Test API connections and exit.")
    args = parser.parse_args()

    if args.dry_run:
        CFG.dry_run = True

    if args.test:
        test_connections()
        return

    if args.once:
        run_once()
        return

    run_scheduler()


if __name__ == "__main__":
    main()
