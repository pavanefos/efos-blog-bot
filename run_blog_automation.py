"""EFOS AI Blog Automation - Complete standalone runner.

This replaces the entire n8n workflow with a single Python script.
No Node.js, no n8n, no $env variables needed.

Usage:
  python run_blog_automation.py                 # Run once now
  python run_blog_automation.py --schedule      # Run as daemon (scheduled)
  python run_blog_automation.py --dry-run       # Generate but don't publish
"""
import sys
import os
import json
import time
import argparse
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.config import CFG
from src.logger import log
from src.pipeline import run_once
from src.state import StateStore


def run_scheduler():
    """Run as a daemon, executing at scheduled times."""
    slots = CFG.schedule_times or [f"{CFG.schedule_hour:02d}:{CFG.schedule_minute:02d}"]
    log.info(f"Scheduler started. Will publish ~{CFG.blogs_per_day} blog(s) per slot at {', '.join(slots)} daily.")

    while True:
        now = datetime.now()
        upcoming = []
        for day in (0, 1):
            base = (now + timedelta(days=day)).replace(second=0, microsecond=0)
            for t in slots:
                h, m = t.split(":")
                upcoming.append(base.replace(hour=int(h), minute=int(m)))

        upcoming = sorted([t for t in upcoming if t > now])
        if not upcoming:
            upcoming = sorted(upcoming)

        wait = (upcoming[0] - now).total_seconds()
        log.info(f"Next run at {upcoming[0].strftime('%Y-%m-%d %H:%M')} (in {wait/60:.0f} min).")
        time.sleep(wait)

        try:
            run_once()
        except Exception as e:
            log.error(f"Scheduler cycle error: {e}")


def main():
    parser = argparse.ArgumentParser(description="EFOS AI Blog Automation (Python, no n8n)")
    parser.add_argument("--schedule", action="store_true", help="Run as scheduler daemon")
    parser.add_argument("--dry-run", action="store_true", help="Generate blogs but don't publish")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    args = parser.parse_args()

    if args.dry_run:
        CFG.dry_run = True

    if args.schedule:
        run_scheduler()
        return

    # Default: run once
    published = run_once()
    print(f"\n✓ Done. Published {published} blog(s).")
    if published == 0:
        print("  Check logs/ for details. Blogs may have been skipped due to:")
        print("  - Duplicate topics (already published)")
        print("  - Smart gate validation failures (Laravel API)")
        print("  - API errors (OpenRouter / Laravel)")


if __name__ == "__main__":
    main()
