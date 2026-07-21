"""Publish a finished blog to the Laravel Blog API.

Replaces the n8n 'Laravel Blog API (Publish)' HTTP node, including:
- multipart/form-data upload (text fields + image file)
- Bearer auth via AI_BLOG_TOKEN
- Retry on 5xx / network errors (3x backoff)
- 422 (smart gate) -> no retry, logged
- 401/403 -> auth misconfig, alerted

Also runs a LOCAL pre-publish quality check (mirrors Laravel's smart gate) so we
never spend an image/API call on content that would be rejected.
"""
from __future__ import annotations

import json
import time
from typing import Any

import requests
from requests_toolbelt import MultipartEncoder

from .config import CFG
from .knowledge import CATEGORY_IDS
from .logger import log


def fetch_valid_categories() -> dict[str, int]:
    """Fetch the live topic-label -> category_id map from the API.

    The dummy and (to-be-deployed) live API expose GET /api/ai/categories so the
    automation always uses your REAL category ids instead of guessing. Falls back
    to the built-in CATEGORY_IDS map if the endpoint is unavailable.
    """
    try:
        resp = requests.get(
            CFG.laravel_api_url + "/api/ai/categories",
            headers={"Accept": "application/json"},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            if isinstance(data, dict) and data:
                return {str(k): int(v) for k, v in data.items()}
    except requests.RequestException:
        pass
    return dict(CATEGORY_IDS)


def local_quality_check(blog: dict[str, Any], category: str, cat_map: dict[str, int]) -> tuple[bool, str]:
    """Mirror Laravel's BlogPublishService::assertPublishable. Returns (ok, reason)."""
    content = blog.get("html_blog", "") or ""
    plain_len = len(_strip_tags(content))
    if plain_len < 1500:
        return False, f"Content too short ({plain_len} chars, need 1500)."
    for field in ("meta_title", "meta_description", "meta_keywords"):
        if not blog.get(field):
            return False, f"Missing required SEO field: {field}."
    cat_id = cat_map.get(category, cat_map.get("Education"))
    if cat_id is None:
        return False, f"Unknown category id for '{category}'."
    return True, ""


def publish(blog: dict[str, Any], category: str, image_bytes: bytes | None) -> dict[str, Any]:
    """Publish one blog. Returns the API JSON response dict."""
    cat_map = fetch_valid_categories()
    ok, reason = local_quality_check(blog, category, cat_map)
    if not ok:
        raise RuntimeError(f"Local quality gate blocked publish: {reason}")

    cat_id = cat_map.get(category, cat_map.get("Education"))
    payload = {
        "category_id": str(cat_id),
        "title": (blog.get("seo_title") or blog.get("topic", ""))[:255],
        "slug": (blog.get("slug") or "")[:255],
        "short_content": (blog.get("meta_description") or "")[:255],
        "content": blog.get("html_blog", ""),
        "meta_title": (blog.get("meta_title") or "")[:255],
        "meta_description": blog.get("meta_description", ""),
        "meta_keywords": blog.get("meta_keywords", ""),
        "alt": (blog.get("seo_title") or "")[:255],
        "status": "1",
    }
    log.info(f"Publishing payload keys: {list(payload.keys())}")
    log.info(f"  meta_title={payload['meta_title'][:50]!r}")
    log.info(f"  meta_description={payload['meta_description'][:50]!r}")
    log.info(f"  meta_keywords={payload['meta_keywords'][:50]!r}")

    files = {}
    if image_bytes:
        files["image"] = ("featured.jpg", image_bytes, "image/jpeg")

    if CFG.dry_run:
        log.info(f"[DRY-RUN] Would publish '{payload['title']}' to category {cat_id}.")
        return {"status": True, "message": "DRY-RUN", "data": {"slug": payload["slug"]}}

    last_err: Exception | None = None
    for attempt in range(1, 4):
        try:
            if files:
                resp = requests.post(
                    CFG.publish_url,
                    headers={"Authorization": f"Bearer {CFG.ai_blog_token}", "Accept": "application/json"},
                    data=payload,
                    files=files,
                    timeout=120,
                )
            else:
                m = MultipartEncoder(fields=payload)
                resp = requests.post(
                    CFG.publish_url,
                    headers={"Authorization": f"Bearer {CFG.ai_blog_token}", "Accept": "application/json", "Content-Type": m.content_type},
                    data=m,
                    timeout=120,
                )
            if resp.status_code == 201:
                data = resp.json()
                log.info(f"Published '{payload['title']}' -> {data.get('data', {}).get('url')}")
                return data
            if resp.status_code == 422:
                log.error(f"Smart gate rejected '{payload['title']}': {resp.text[:300]}")
                _save_failed_payload(payload, blog, resp.text)
                return resp.json()
            if resp.status_code in (401, 403):
                log.error(f"Auth error {resp.status_code}: check AI_BLOG_TOKEN / IP allow-list.")
                return resp.json()
            # 5xx or other -> retry
            last_err = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        except requests.RequestException as e:
            last_err = e
        log.warning(f"Publish attempt {attempt} failed: {last_err}. Retrying...")
        time.sleep(2 * attempt)

    raise RuntimeError(f"Publish failed after retries: {last_err}")


def _strip_tags(html: str) -> str:
    import re

    return re.sub(r"<[^>]+>", "", html or "")


def _save_failed_payload(payload: dict, blog: dict, error: str) -> None:
    """Save failed publish payload for manual review."""
    import os
    from datetime import datetime

    out_dir = CFG.state_dir / "failed_publishes"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = payload.get("slug", "untitled")
    fname = out_dir / f"{ts}_{slug}.json"
    rec = {
        "timestamp": ts,
        "payload": payload,
        "blog": blog,
        "error": error,
    }
    try:
        fname.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info(f"Saved failed payload to {fname}")
    except OSError as e:
        log.warning(f"Could not save failed payload: {e}")
