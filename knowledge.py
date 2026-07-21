"""EFOS brand knowledge base.

Single source of truth for the AI pipeline: brand voice, category mapping,
founder bios, and factual guardrails. Loaded from efos_knowledge_base.md in the
project root so the automation stays aligned with efos.in.

This replaces the n8n "AI Memory Layer" seeding: the same facts that used to be
loaded into a vector store are embedded directly here as plain Python data.
"""
from __future__ import annotations

import re
from pathlib import Path

# Project root = grandparent of this file (05_automation/src -> 05_automation -> project root)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
KB_PATH = PROJECT_ROOT / "efos_knowledge_base.md"

# Category names -> Laravel category_id.
# IMPORTANT: these IDs were derived from the live efos.in `blogs` export you
# shared (u267672142_efos_webiste.csv). Your live `categories` table does NOT
# use 1-8; it uses a different set (e.g. 5,6,7,8,10,11,13,18,19,...). If any ID
# below is wrong for your site, the Laravel smart gate returns 422 and that blog
# is simply skipped (never published wrongly). Verify against your `categories`
# table and adjust if needed.
CATEGORY_IDS = {
    "Scholarships": 13,        # upcoming-exams bucket (closest live category)
    "Internships": 18,         # career guidance
    "Skill Development": 5,    # skill-integrated education
    "Careers": 7,              # entrance-exam / career-compass bucket
    "University Updates": 10,  # college selection
    "AI & Technology": 6,      # tech & IT careers
    "Government": 7,           # govt careers / defence / exams
    "Education": 8,            # traditional degrees / choose career
}

# Keyword -> category used by the topic selector when the model does not return one.
CATEGORY_KEYWORDS = {
    "Scholarships": ["scholarship", "scholarship", "fellowship", "stipend"],
    "Internships": ["intern", "internship", " apprenticeship"],
    "Skill Development": ["skill", "training", "course", "vocational", "certification"],
    "Careers": ["job", "career", "placement", "employment", "salary"],
    "University Updates": ["university", "college", "admission", "exam", "entrance"],
    "AI & Technology": ["ai", "artificial intelligence", "machine learning", "tech", "automation"],
    "Government": ["government", "policy", "scheme", "ministry", "pib", "ugc", "nep"],
    "Education": ["education", "student", "school", "learning", "study"],
}

# Rotating author bios (EFOS founders).
AUTHOR_BIOS = {
    "Sachin Jain": (
        "Sachin Jain is the Founder of EFOS (Education Future One Stop, efos.in) and "
        "EFOS Edumarketers Pvt. Ltd. An IIT Roorkee M.Tech with advanced certification "
        "from SPJIMR Mumbai, he has 15+ years of experience in career guidance and "
        "education-sector consulting, connecting India's youth to verified opportunities."
    ),
    "Dr. Akansha Jain": (
        "Dr. Akansha Jain is the Founder & Chairperson of the EFOS Foundation (efos.in). "
        "With a Ph.D. in Forex Risk Management, a Gold Medal in M.Com, and 18+ years of "
        "experience, she champions learn-and-earn pathways and employability-focused "
        "education for India's youth. Author of 'You Will Not Get a Job'."
    ),
}

AUTHOR_NAMES = list(AUTHOR_BIOS.keys())

# Factual guardrails injected into every AI prompt.
GUARDRAILS = (
    "EFOS = Education Future One Stop (efos.in), run by EFOS Edumarketers Pvt. Ltd. "
    "It is a verified-opportunities platform for Indian youth (16-35) covering education, "
    "careers, skills, internships, scholarships and jobs. "
    "CRITICAL FACTS YOU MUST OBEY:\n"
    "1. EFOS NEVER charges candidates any fee. EFOS earns a service fee from opportunity providers only.\n"
    "2. NEVER invent exact fees, deadlines, eligibility cut-offs, or district-level addresses. "
    "For those, direct readers to https://efos.in and the student login (https://efos.in/student/login).\n"
    "3. Use a warm, trustworthy, empathetic 'EFOSBuddy' tone. Cite efos.in for live data.\n"
    "4. Founders are BOTH Sachin Jain and Dr. Akansha Jain."
)

# Seed topics already published (KB Section 12) used to avoid repeats.
PUBLISHED_SEED_TITLES = [
    "Why Learn & Earn Programs Are the Smartest Career Choice in 2026",
    "Traditional BCA vs Skill-Based BCA",
    "Why to Study AI in Any Tech Career",
    "How to start a career in the Tech Industry",
    "What is a Cloud Computing Course",
    "Why EFOS BBA Retail with job is better for rural students",
    "Why EFOS Learn & Earn BBA Retail Program is a Game-Changer",
    "Why rural 12th pass students should do Hotel Management",
    "India Is Facing a Skills Crisis Not a Job Crisis",
    "12th Result Out Choose Your Future First",
    "How to Decide the Right College and Course After 12th",
]


def category_from_text(text: str) -> str:
    """Best-effort category guess from free text (used as a fallback)."""
    low = text.lower()
    best, best_score = "Education", 0
    for cat, kws in CATEGORY_KEYWORDS.items():
        score = sum(1 for k in kws if k in low)
        if score > best_score:
            best, best_score = cat, score
    return best


def normalize_slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:80]


def kb_text() -> str:
    """Return the raw knowledge base markdown (or a fallback note)."""
    try:
        return KB_PATH.read_text(encoding="utf-8")
    except OSError:
        return "(EFOS knowledge base file not found - using built-in guardrails only.)"
