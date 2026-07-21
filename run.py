"""EFOS AI Blog Automation - Standalone Runner (NO n8n required)

Usage:
  python run.py                  # Run the scheduler (runs at scheduled times)
  python run.py --once           # Run one publishing cycle now
  python run.py --once --dry-run # Run without publishing
  python run.py --test           # Test API connections

Output:
  - Logs: logs/run_YYYY-MM-DD.log
  - Published blogs: state/published.json
  - Ready-to-publish payloads: output/pending_blogs/ (JSON files)
"""
import sys
import os

# Ensure the package can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.config import CFG
from src.logger import log
from src.pipeline import run_once


def main():
    print("=" * 60)
    print("EFOS AI Blog Automation - Python Runner (No n8n)")
    print("=" * 60)
    print(f"Laravel URL: {CFG.laravel_api_url}")
    print(f"AI Model: {CFG.ai_model}")
    print(f"Blogs per day: {CFG.blogs_per_day}")
    print(f"Schedule times: {CFG.schedule_times}")
    print(f"Dry run: {CFG.dry_run}")
    print("=" * 60)

    # Check dependencies
    try:
        import requests
        import feedparser
        print("Dependencies OK (requests, feedparser)")
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Install with: pip install requests feedparser")
        return 1

    # Run
    published = run_once()
    print(f"\nRun complete. Published {published} blog(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
