# EFOS AI Blog Automation (Python — no Node.js, no n8n)

A complete, standalone daily automation that replaces the n8n workflow. It runs
the full pipeline **without Node.js and without n8n**:

```
Every day at SCHEDULE_HOUR:SCHEDULE_MINUTE
        │
        ▼
Find Trending Education Topics  (Google News RSS + Google Trends RSS)
        │
        ▼
AI selects the BEST N topics  (N = BLOGS_PER_DAY, e.g. 6)
        │
        ▼
AI researches each topic
        │
        ▼
AI writes SEO-optimized HTML blog
        │
        ▼
AI generates a Featured Image  (OpenRouter / DALL·E)
        │
        ▼
Upload image + post to Laravel Blog API  (POST /api/ai/publish-blog)
        │
        ▼
Blog appears on EFOS (efos.in)
```

## What your website is (so you understand the pipeline)
- **efos.in is a Laravel (PHP) website** backed by a **MySQL database**.
- Each blog is a **row in the `blogs` table** with columns:
  `category_id, name, slug, short_content, content (HTML), image, alt,
  meta_title, meta_description, meta_keywords, status, user_id`.
- The frontend reads these rows to show the blog list and detail pages
  (`career-updates.blade.php`, `career-updates-details.blade.php`). So when the
  automation inserts a row + uploads an image, it shows up automatically.
- The ready-made endpoint `POST /api/ai/publish-blog` (in `01_Backup`) accepts
  the blog and has a "smart gate" that rejects duplicates / too-short content /
  missing SEO / bad category.

## How category IDs work (IMPORTANT — verified from your live DB)
Your live `categories` table does **NOT** use 1–8. From your `blogs` export the
real IDs in use include: 1,3,5,6,7,8,9,10,11,12,13,16,17,18,19,20,21,22,23,24,
25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,41.

The automation maps topic labels -> your real IDs in `src/knowledge.py`
(`CATEGORY_IDS`). It ALSO calls `GET /api/ai/categories` at runtime to fetch the
authoritative mapping from the site, falling back to the hardcoded map. The
dummy server (`dummy_api.py`) implements that same endpoint so local tests match.

If a topic maps to a wrong/missing category id, Laravel returns **422** and that
single blog is skipped (never published wrongly) — the rest of the run continues.

## Setup
```bash
cd 05_automation
python -m pip install -r requirements.txt
cp .env.local.example .env      # points at the SAFE local dummy server
# Edit .env: put your real OPENROUTER_API_KEY (AI_BLOG_TOKEN is fake for local)
```

## Local testing FIRST (safe — touches nothing on efos.in)
```bash
# 1) Start the dummy API (listens on http://127.0.0.1:8088)
python dummy_api.py

# 2) In another terminal, dry-run (no AI spend, no real publish):
python -m src --once --dry-run

# 3) Real local run (publishes INTO the dummy server, not your live site):
python -m src --once

# 4) Inspect what the dummy received:
#    open http://127.0.0.1:8088/api/ai/blogs  (JSON of published blogs)
#    images land in 05_automation/dummy_data/uploads/
```
When you're happy with quality, you can stop the dummy server.

## Go live (only after local testing passes)
1. Deploy the API files from `01_Backup` to your Laravel site
   (controller, route, middleware, service, request, DTO, contract, trait).
2. Add `AI_BLOG_TOKEN=...` (and optional `BLOG_AI_USER_ID`) to the live
   Laravel `.env`; set `services.ai_blog.token`.
3. Add `GET /api/ai/categories` to the live API returning your
   topic-label -> category_id map (mirror `dummy_api.py`).
4. In the automation `.env`, set `LARAVEL_API_URL=https://www.efos.in` and the
   real `AI_BLOG_TOKEN`.
5. Run once to confirm it appears on efos.in, then switch to the scheduler:
   `python -m src`  (or cron: `0 9 * * * python -m src --once`).

## Run options
```bash
python -m src                 # long-lived daily scheduler (fires at SCHEDULE_TIMES)
python -m src --once          # one cycle now
python -m src --once --dry-run# one cycle, no publishing
python -m src --test          # test API connections
```
Optional PHP trigger: `php run_ai_blog.php` (same flags).

## Scheduling (fixed times, fully automatic)
Set `SCHEDULE_TIMES` in `.env` as a comma list of 24h times. The scheduler runs
a full cycle (publishing `BLOGS_PER_DAY` blogs) at EACH time, every day, until
you stop it (Ctrl+C). Example for 9am,11am,1pm,3pm,5pm,7pm with 2 blogs each:

```
SCHEDULE_TIMES=9,11,13,15,17,19
BLOGS_PER_DAY=2
```

## Featured images (ChatGPT image API)
```
USE_IMAGE_API=true
IMAGE_PROVIDER=chatgpt
OPENAI_API_KEY=sk-...your-openai-key
IMAGE_MODEL=dall-e-3
```
With `IMAGE_PROVIDER=openrouter` it uses OpenRouter instead (needs IMAGE_MODEL
access on your plan). If the key/provider fails, blogs publish without an image
(no crash).


## Key config (`.env`)
| Var | Meaning |
|-----|---------|
| `OPENROUTER_API_KEY` | AI provider key (https://openrouter.ai/keys) |
| `AI_MODEL` | chat model, default `openai/gpt-4o-mini` |
| `IMAGE_MODEL` | image model, default `openai/dall-e-3`; `USE_IMAGE_API=false` to skip |
| `LARAVEL_API_URL` | base URL of efos.in (no trailing slash) |
| `AI_BLOG_TOKEN` | Bearer token for the Laravel API |
| `SCHEDULE_HOUR` / `SCHEDULE_MINUTE` | daily run time |
| `BLOGS_PER_DAY` | how many blogs per day (4–5+ → set 5) |
| `DEDUP_DAYS` | skip topics already published in last N days |
| `DRY_RUN` | `true` to test without publishing |

## Safety notes
- Local quality gate mirrors Laravel's smart gate (min 1500 chars, required SEO
  fields, valid category) before any image/API spend.
- Publish responses: `201` success; `422` smart-gate reject (no retry);
  `401/403` auth/IP misconfig; `5xx`/network → 3 retries with backoff.
- The dummy server stores data only in `05_automation/dummy_data/` — deleting
  that folder resets all local test blogs.
