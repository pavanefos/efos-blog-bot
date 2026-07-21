"""AI research and SEO HTML blog writer.

Replaces the n8n 'AI Researches Topic' + 'Parse Research JSON' +
'AI Writes SEO HTML Blog' + 'Parse Writer JSON' nodes.

Focus: produce WELL-FORMATTED, structurally clean HTML that renders nicely on
the EFOS site (which prints content unescaped inside <div class="description">).
"""
from __future__ import annotations

import json
import re
from typing import Any

from .ai_client import chat_json
from .knowledge import AUTHOR_BIOS, AUTHOR_NAMES, GUARDRAILS
from .logger import log

FORMAT_RULES = """
HTML FORMATTING RULES (strict):
- Start with exactly ONE <h1> (the blog title). No other h1.
- Use <h2> for main sections, <h3> only inside an h2 section. Never skip a level.
- Every section heading MUST be followed by at least one <p> paragraph.
- Wrap EVERY paragraph in <p>...</p>. Never output bare text outside a tag.
- Use <ul><li>...</li></ul> for lists (never use "-" or "*" bullets in text).
- Use <strong> for emphasis, never ALL CAPS shouting.
- Keep paragraphs 2-4 sentences. Add a blank line between block elements.
- Add a <h2>Key Takeaways</h2> near the end with a short <ul>.
- Add a <h2>Frequently Asked Questions</h2> with <h3>Question?</h3> then <p>Answer.</p>.
- End with a <h2>Conclusion</h2> paragraph.
- Do NOT invent exact fees, deadlines, or eligibility. For those, link to https://efos.in.
- Output clean, indented HTML. No Markdown, no code fences, no \\n\\n inside tags.
"""


def research(topic: str, category: str) -> dict[str, Any]:
    system = (
        "You are the EFOS AI Research Agent. EFOS (efos.in) is Education Future One Stop, "
        "a verified-opportunities platform for Indian youth. Never claim EFOS charges "
        "candidates; EFOS earns from providers. Prefer official/government/EFOS sources.\n"
        + GUARDRAILS
    )
    user = (
        "Research this topic. Return ONLY JSON: "
        '{"executive_summary":"","important_facts":[""],"statistics":[""],"latest_updates":[""],'
        '"useful_urls":[""],"faqs":[{"question":"","answer":""}],"key_takeaways":[""]}. '
        f"Topic: {topic}. Category: {category}."
    )
    data = chat_json(system, user, max_tokens=1024)
    log.info(f"Researched '{topic}' ({len(data.get('important_facts', []))} facts).")
    return data


def write_blog(topic: str, category: str, research_data: dict[str, Any]) -> dict[str, Any]:
    system = (
        "You are the EFOS SEO Blog Writer. Voice: warm, trustworthy, empathetic (EFOSBuddy). "
        "Audience: Indian youth 16-35. Ground EFOS facts in efos.in; never invent exact "
        "fees/deadlines; never say EFOS charges candidates.\n" + GUARDRAILS + FORMAT_RULES
    )
    user = (
        "Write a short SEO blog as clean HTML. "
        'Return ONLY JSON: '
        '{"seo_title":"","slug":"","meta_title":"","meta_description":"","meta_keywords":"","html_blog":"","author_bio":"","word_count":0}. '
        f"Topic: {topic}. Category: {category}. "
        f"Research: {json.dumps(research_data, ensure_ascii=False)[:2000]}"
    )
    data = chat_json(system, user, max_tokens=2048)
    data["seo_title"]    = data.get("seo_title") or topic[:60]
    data["slug"]         = data.get("slug") or _slugify(topic)
    data["meta_title"]   = data.get("meta_title") or data.get("seo_title", topic[:60])
    data["meta_description"] = data.get("meta_description") or data.get("og_description", "") or topic[:155]
    data["meta_keywords"] = data.get("meta_keywords") or ", ".join(data.get("keywords", [topic])[:5])
    data["html_blog"]    = data.get("html_blog", "")
    data["author_bio"]   = data.get("author_bio", "")
    data["word_count"]   = data.get("word_count") or len(data.get("html_blog", "").split())
    if "html_blog" in data:
        data["html_blog"] = format_html(data["html_blog"])
    log.info(f"Wrote blog '{data.get('seo_title', topic)}' ({data.get('word_count', 0)} words).")
    return data


def _slugify(text: str) -> str:
    import re
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text)
    return text[:100].strip("-")


def pick_author(blog: dict[str, Any]) -> str:
    bio = blog.get("author_bio", "")
    for name in AUTHOR_NAMES:
        if name in bio:
            return AUTHOR_BIOS[name]
    # Fallback: rotate by hashing the title for variety.
    return AUTHOR_BIOS[AUTHOR_NAMES[hash(blog.get("seo_title", "")) % len(AUTHOR_NAMES)]]


def format_html(html: str) -> str:
    """Normalize AI-produced HTML into clean, well-structured markup.

    - Converts any leftover Markdown bullets / bare text into proper tags.
    - Ensures block elements are separated by newlines.
    - Fixes common unclosed-tag issues lightly.
    - Re-indents for readability.
    """
    if not html:
        return html

    # Strip code fences if the model wrapped the HTML.
    html = re.sub(r"^```(?:html)?", "", html.strip(), flags=re.I)
    html = re.sub(r"```$", "", html.strip())

    # Convert Markdown-style bullets (-, *, •) at line start into <li> (loosely;
    # the real list wrapping happens below if a <ul> already exists).
    html = re.sub(r"(?m)^[\s]*[-*•]\s+", "• ", html)

    # Ensure blank line between block-level tags for clean separation, but keep
    # the tag and its immediate text on the same line (no newline right after
    # the opening tag, which would cause odd spacing).
    block_tags = r"h1|h2|h3|h4|p|ul|ol|li|blockquote|table|pre|div|section"
    # Put a newline BEFORE a block opening/closing tag (separates blocks).
    html = re.sub(r">(<\s*/?(" + block_tags + r")\b)", r">\n<\1", html)
    # Remove any newline that sits immediately after an opening tag's ">".
    html = re.sub(r"(<(" + block_tags + r")\b[^>]*>)\n+", r"\1", html)
    # Ensure a single newline after a closing block tag.
    html = re.sub(r"(</(" + block_tags + r")\b[^>]*>)\n*", r"\1\n", html)

    # Collapse 3+ blank lines to 2.
    html = re.sub(r"\n{3,}", "\n\n", html)

    html = html.strip()
    return html
