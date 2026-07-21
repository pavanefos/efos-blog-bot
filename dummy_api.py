"""Dummy local Laravel-style Blog API for SAFE testing.

This is NOT the live site. It mimics the real Laravel endpoint exactly so you can
test the Python automation end-to-end without disturbing efos.in:

  POST http://127.0.0.1:8088/api/ai/publish-blog

Contract (mirrors 01_Backup Laravel code):
  - Bearer token required (any non-empty value; checked like VerifyApiToken)
  - multipart/form-data: category_id, title, slug, short_content, content(HTML),
    meta_title, meta_description, meta_keywords, alt, image(file), status
  - Smart gate: category exists, unique title/slug, content >= 1500 chars
    (stripped), meta_title/description/keywords present, valid image
  - Responses: 201 success, 401/403 auth, 422 smart-gate reject, 500 error

It writes published blogs to a local SQLite-free JSON file (dummy_data/blogs.json)
and stores uploaded images under dummy_data/uploads/. A GET listing endpoint is
included so you can inspect what was published.

Run:  python dummy_api.py            (listens on 127.0.0.1:8088)
"""
from __future__ import annotations

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
PORT = 8088
BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "dummy_data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
BLOGS_FILE = os.path.join(DATA_DIR, "blogs.json")

# Mirror the category ids used by the automation (src/knowledge.CATEGORY_IDS).
VALID_CATEGORIES = {1, 2, 3, 4, 5, 6, 7, 8}

# Label -> id, returned by GET /api/ai/categories (matches automation map).
VALID_CATEGORIES_JSON = {
    "Scholarships": 13,
    "Internships": 18,
    "Skill Development": 5,
    "Careers": 7,
    "University Updates": 10,
    "AI & Technology": 6,
    "Government": 7,
    "Education": 8,
}

os.makedirs(UPLOAD_DIR, exist_ok=True)


def load_blogs() -> list[dict]:
    if not os.path.exists(BLOGS_FILE):
        return []
    try:
        with open(BLOGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_blogs(blogs: list[dict]) -> None:
    with open(BLOGS_FILE, "w", encoding="utf-8") as f:
        json.dump(blogs, f, indent=2, ensure_ascii=False)


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "")


def _parse_multipart(body: bytes, boundary: str) -> tuple[dict, dict | None]:
    """Minimal multipart/form-data parser (no external deps)."""
    fields: dict[str, str] = {}
    image: dict | None = None
    delimiter = ("--" + boundary).encode()
    parts = body.split(delimiter)
    for part in parts:
        if part in (b"", b"--", b"--\r\n"):
            continue
        if not part.startswith(b"\r\n"):
            continue
        head, _, payload = part.partition(b"\r\n\r\n")
        if not head:
            continue
        # header lines
        head_text = head.decode("utf-8", "replace")
        name_match = re.search(r'name="([^"]+)"', head_text)
        if not name_match:
            continue
        name = name_match.group(1)
        fn_match = re.search(r'filename="([^"]*)"', head_text)
        ctype_match = re.search(r"Content-Type: (.+)", head_text)
        # strip trailing CRLF from payload
        if payload.endswith(b"\r\n"):
            payload = payload[:-2]
        if fn_match and fn_match.group(1):
            if ctype_match and ctype_match.group(1).startswith("image"):
                image = {
                    "filename": fn_match.group(1),
                    "content_type": ctype_match.group(1).strip(),
                    "data": payload,
                }
        else:
            fields[name] = payload.decode("utf-8", "replace")
    return fields, image


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter logging
        print(f"[dummy-api] {fmt % args}")

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/ai/blogs":
            self._send(200, {"status": True, "count": len(load_blogs()), "data": load_blogs()})
            return
        if self.path == "/api/ai/categories":
            # Reflect the automation's known category map so the live+local
            # contract matches (topic label -> id).
            self._send(200, {"status": True, "data": VALID_CATEGORIES_JSON})
            return
        if self.path == "/":
            self._send(
                200,
                {
                    "service": "EFOS dummy Blog API (local test only)",
                    "endpoints": {
                        "POST /api/ai/publish-blog": "publish a blog (multipart)",
                        "GET  /api/ai/blogs": "list published blogs",
                    },
                },
            )
            return
        self._send(404, {"message": "Not found"})

    def do_POST(self):
        if self.path != "/api/ai/publish-blog":
            self._send(404, {"message": "Not found"})
            return

        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or not auth[7:].strip():
            self._send(401, {"status": False, "message": "Unauthorized."})
            return

        ctype = self.headers.get("Content-Type", "")
        m = re.match(r"multipart/form-data; boundary=(.+)", ctype)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)

        fields: dict[str, str] = {}
        image = None
        if m:
            try:
                fields, image = _parse_multipart(raw, m.group(1))
            except Exception as e:  # noqa: BLE001
                self._send(422, {"status": False, "message": "Validation failed.",
                                 "errors": {"body": [f"parse error: {e}"]}})
                return
        else:
            # Fallback: application/x-www-form-urlencoded (e.g. when no file is sent)
            from urllib.parse import parse_qs

            parsed = parse_qs(raw.decode("utf-8", "replace"))
            fields = {k: (v[0] if v else "") for k, v in parsed.items()}

        # --- Smart gate (mirrors BlogPublishService::assertPublishable) ---
        errors: dict[str, list[str]] = {}

        cat = fields.get("category_id", "")
        if not cat.isdigit() or int(cat) not in VALID_CATEGORIES:
            errors.setdefault("category_id", []).append("The selected category id is invalid.")

        title = fields.get("title", "")
        if not title:
            errors.setdefault("title", []).append("The title field is required.")
        elif len(title) > 255:
            errors.setdefault("title", []).append("The title must not exceed 255 characters.")

        slug = fields.get("slug", "")
        if slug and len(slug) > 255:
            errors.setdefault("slug", []).append("The slug must not exceed 255 characters.")

        content = fields.get("content", "")
        if len(strip_tags(content)) < 1500:
            errors.setdefault("content", []).append(
                "Content is too short. Minimum 1500 characters required.")

        for f in ("meta_title", "meta_description", "meta_keywords"):
            if not fields.get(f):
                errors.setdefault(f, []).append(f"The {f} field is required.")

        # duplicate title/slug against already-published
        blogs = load_blogs()
        if any(b["title"] == title for b in blogs):
            errors.setdefault("title", []).append("A blog with this title already exists.")
        if slug and any(b.get("slug") == slug for b in blogs):
            errors.setdefault("slug", []).append("A blog with this slug already exists.")

        # image validity (must be present and look like an image)
        if image is not None:
            if not image["content_type"].startswith("image/"):
                errors.setdefault("image", []).append("The image must be a file of type: jpeg,png,jpg,gif,webp.")
            elif len(image["data"]) > 2048 * 1024:
                errors.setdefault("image", []).append("The image may not be greater than 2048 KB.")
        # NOTE: real Laravel requires an image; dummy allows none for image-less tests.

        if errors:
            self._send(422, {"status": False, "message": "Publish rejected.",
                             "error": "Smart gate validation failed.", "errors": errors})
            return

        # --- Persist ---
        try:
            img_path = None
            if image is not None:
                ext = os.path.splitext(image["filename"])[1] or ".jpg"
                fname = f"media_{os.urandom(4).hex()}{ext}"
                with open(os.path.join(UPLOAD_DIR, fname), "wb") as fh:
                    fh.write(image["data"])
                img_path = f"uploads/blogs/{fname}"

            new_id = (max([b["id"] for b in blogs], default=0)) + 1
            final_slug = slug or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            rec = {
                "id": new_id,
                "category_id": int(cat),
                "title": title,
                "slug": final_slug,
                "short_content": fields.get("short_content", ""),
                "content": content,
                "image": img_path,
                "alt": fields.get("alt", ""),
                "meta_title": fields.get("meta_title", ""),
                "meta_description": fields.get("meta_description", ""),
                "meta_keywords": fields.get("meta_keywords", ""),
                "status": int(fields.get("status", 1) or 1),
                "url": f"http://127.0.0.1:{PORT}/{final_slug}",
            }
            blogs.append(rec)
            save_blogs(blogs)
            self._send(201, {
                "status": True,
                "message": "Blog published successfully.",
                "data": {"id": new_id, "slug": final_slug, "url": rec["url"]},
            })
        except Exception as e:  # noqa: BLE001
            self._send(500, {"status": False, "message": "Failed to publish blog.",
                             "error": str(e)})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"EFOS dummy Blog API listening on http://{HOST}:{PORT}")
    print(f"Published blogs stored in: {BLOGS_FILE}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
