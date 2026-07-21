"""Local state + dedup store.

Replaces the heavy 'AI Memory Layer' vector store with a simple JSON file that
tracks published topics/slugs (and seeds from the KB's already-published list)
so the automation does not repeat itself within DEDUP_DAYS.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from .config import CFG
from .knowledge import PUBLISHED_SEED_TITLES, normalize_slug


class StateStore:
    def __init__(self) -> None:
        self.path: Path = CFG.state_dir / "published.json"
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        # Seed with already-published titles from the knowledge base.
        seeded = {
            "published": [
                {"slug": normalize_slug(t), "title": t, "date": "1970-01-01"}
                for t in PUBLISHED_SEED_TITLES
            ]
        }
        return seeded

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")

    def is_duplicate(self, title: str, slug: str) -> bool:
        slug = slug or normalize_slug(title)
        cutoff = datetime.now() - timedelta(days=CFG.dedup_days)
        for rec in self._data.get("published", []):
            if rec.get("slug") == slug:
                return True
            if rec.get("title", "").strip().lower() == title.strip().lower():
                return True
        return False

    def record(self, title: str, slug: str, url: str = "") -> None:
        slug = slug or normalize_slug(title)
        self._data.setdefault("published", []).append(
            {"slug": slug, "title": title, "url": url, "date": datetime.now().isoformat(timespec="seconds")}
        )
        self._save()

    def prune_old(self) -> None:
        cutoff = datetime.now() - timedelta(days=CFG.dedup_days * 4)
        kept = []
        for rec in self._data.get("published", []):
            try:
                d = datetime.fromisoformat(rec.get("date", "1970-01-01"))
            except ValueError:
                d = datetime(1970, 1, 1)
            if d >= cutoff or rec.get("date") == "1970-01-01":  # keep seed entries
                kept.append(rec)
        self._data["published"] = kept
        self._save()
