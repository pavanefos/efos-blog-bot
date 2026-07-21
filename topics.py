"""Topic discovery: pull trending education/career news, deduplicate, and let
the AI select the best N topics for today.

Replaces the n8n 'Google News RSS' + 'Google Trends RSS' + 'Discover & Dedup'
+ 'AI Selects ONE Best Topic' nodes, but extended to return up to BLOGS_PER_DAY
topics instead of just one.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import feedparser
import requests

from .config import CFG
from .knowledge import GUARDRAILS, category_from_text
from .logger import log

NEWS_RSS = (
    "https://news.google.com/rss/search?"
    "q=education+OR+career+OR+internship+OR+scholarship+OR+skill+development"
    "&hl=en-IN&gl=IN&ceid=IN:en"
)
TRENDS_RSS = "https://trends.google.com/trending/rss?geo=IN"


@dataclass
class TopicCandidate:
    title: str
    category: str
    keywords: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


def _fetch_feed(url: str, limit: int = 40) -> list[TopicCandidate]:
    try:
        raw = requests.get(url, timeout=30).content
        parsed = feedparser.parse(raw)
    except requests.RequestException as e:
        log.warning(f"Feed fetch failed ({url}): {e}")
        return []

    out: list[TopicCandidate] = []
    for entry in parsed.entries[:limit]:
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        src = entry.get("link", "")
        out.append(TopicCandidate(title=title, category=category_from_text(title), sources=[src]))
    return out


def discover_candidates() -> list[TopicCandidate]:
    news = _fetch_feed(NEWS_RSS)
    trends = _fetch_feed(TRENDS_RSS)
    merged = news + trends

    # Deduplicate by normalized title.
    seen: set[str] = set()
    unique: list[TopicCandidate] = []
    for c in merged:
        key = "".join(c.title.lower().split())
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    log.info(f"Discovered {len(unique)} unique trending candidates.")
    return unique


def select_topics(candidates: list[TopicCandidate], count: int) -> list[dict[str, Any]]:
    """Ask the AI to rank & select the best `count` topics."""
    if not candidates:
        return []

    system = (
        "You are the EFOS AI editorial selector. EFOS = Education Future One Stop "
        "(efos.in), an Indian verified-opportunities platform for youth (16-35) covering "
        "education, careers, skills, internships, scholarships, jobs.\n" + GUARDRAILS
    )
    user = (
        f"From the candidate topics below, select the {count} BEST, DISTINCT topics to publish "
        "blogs about today. Prefer: trending, fresh, strong SEO opportunity, relevant to Indian "
        "youth, low competition, and covering DIFFERENT categories where possible. "
        "Return ONLY JSON: {\"topics\": [{\"topic\":\"\",\"category\":\"one of "
        "Scholarships,Internships,Skill Development,Careers,University Updates,AI & Technology,"
        "Government,Education\",\"score\":0,\"reason\":\"\",\"keywords\":[\"\",\"\"]}]}. "
        f"Candidates: {[c.title for c in candidates]}"
    )

    data = ai_chat_json_safe(system, user)
    raw_topics = data.get("topics", []) if isinstance(data, dict) else []
    if not isinstance(raw_topics, list):
        raw_topics = []

    chosen: list[dict[str, Any]] = []
    for t in raw_topics[:count]:
        if not isinstance(t, dict) or not t.get("topic"):
            continue
        chosen.append(
            {
                "topic": str(t["topic"]).strip(),
                "category": str(t.get("category") or category_from_text(str(t.get("topic", "")))),
                "score": float(t.get("score", 0) or 0),
                "reason": str(t.get("reason", "")),
                "keywords": t.get("keywords", []) or [],
            }
        )
    log.info(f"AI selected {len(chosen)} topics.")
    return chosen


def ai_chat_json_safe(system: str, user: str) -> dict[str, Any]:
    """Wrapper that never raises - returns {} on failure so the run can continue."""
    from .ai_client import chat_json, CFG

    models = [CFG.ai_model] + CFG.ai_fallback_models.split(",")
    for model in models:
        model = model.strip()
        if not model:
            continue
        try:
            return chat_json(system, user, model=model, max_tokens=CFG.ai_max_tokens)
        except Exception as e:  # noqa: BLE001 - defensive for scheduling
            log.warning(f"AI model {model} failed: {e}. Trying next...")
    log.error("AI select failed: all models exhausted")
    return {}
