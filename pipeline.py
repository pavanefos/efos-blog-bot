"""Main orchestrator for the EFOS daily AI blog automation (Node-free).

Pipeline (mirrors the n8n workflow, replacing every node):
   1. Topic discovery  (Google News + Trends RSS)        -> topics.py
   2. AI selects best N topics                            -> topics.py
   3. For each topic:
        a. AI research + write blog in ONE call          -> writer.py
        b. AI generates + downloads featured image        -> image.py
        c. Publish to Laravel Blog API (multipart)        -> publisher.py
        d. Record in local dedup state                    -> state.py
   4. Loop until BLOGS_PER_DAY published (or out of topics).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime

from .config import CFG
from .image import build_featured_image
from .logger import log
from .publisher import publish
from .state import StateStore
from .topics import discover_candidates, select_topics
from .writer import pick_author, write_blog_with_research


def run_once() -> int:
    """Run one publishing cycle. Returns number of blogs published."""
    store = StateStore()
    store.prune_old()

    candidates = discover_candidates()
    if not candidates:
        log.error("No trending candidates found. Aborting run.")
        return 0

    wanted = min(_blogs_per_day(), len(candidates))
    chosen = select_topics(candidates, wanted)
    if not chosen:
        log.error("AI topic selection returned nothing. Aborting run.")
        return 0

    published = 0
    for item in chosen:
        topic = item["topic"]
        category = item["category"]
        slug = ""

        if store.is_duplicate(topic, ""):
            log.info(f"Skipping duplicate topic: {topic}")
            continue

        try:
            blog = write_blog_with_research(topic, category)
            blog.setdefault("topic", topic)
            blog.setdefault("seo_title", topic)
            slug = blog.get("slug", "") or ""
            if slug:
                slug = slug + "-" + datetime.now().strftime("%H%M")

            if store.is_duplicate(blog.get("seo_title", topic), slug):
                log.info(f"Skipping duplicate (post-write) topic: {topic}")
                continue

            author_bio = pick_author(blog)
            html = blog.get("html_blog", "")
            if author_bio and "<!--AUTHOR-->" in html:
                html = html.replace("<!--AUTHOR-->", f"<p><em>{author_bio}</em></p>")
            elif author_bio:
                html = html + f"\n<p><em>About the author: {author_bio}</em></p>"
            blog["html_blog"] = html

            image_bytes = build_featured_image(
                blog.get("seo_title", topic), blog.get("meta_description", "")
            )

            result = publish(blog, category, image_bytes)
            if result.get("status") is True:
                store.record(
                    blog.get("seo_title", topic),
                    slug,
                    result.get("data", {}).get("url", ""),
                )
                published += 1
            else:
                log.warning(f"Publish returned failure for '{topic}': {result}")
                from pathlib import Path
                out_dir = CFG.state_dir / "pending_blogs"
                out_dir.mkdir(parents=True, exist_ok=True)
                fname = out_dir / f"{slug or 'untitled'}_{datetime.now():%Y%m%d_%H%M%S}.json"
                fname.write_text(
                    json.dumps({"blog": blog, "category": category, "publish_result": result}, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                log.info(f"Saved pending blog to {fname}")
        except Exception as e:
            log.error(f"Failed to process topic '{topic}': {e}")

    log.info(f"Daily run complete. Published {published} blog(s).")
    return published


def _blogs_per_day() -> int:
    try:
        from .config import CFG
        return max(1, CFG.blogs_per_day)
    except Exception:
        return 5
