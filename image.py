"""Featured image generation + download.

Replaces the n8n 'AI Generates Featured Image' + 'Download Image' nodes.
If image generation is disabled or fails, returns None (Laravel accepts optional image).
"""
from __future__ import annotations

import io

import requests

from .ai_client import generate_image
from .config import CFG
from .logger import log


def build_featured_image(topic: str, meta_description: str) -> bytes | None:
    """Generate a featured image and return its binary content, or None."""
    if not CFG.use_image_api:
        return None

    prompt = (
        f"Editorial, brand-safe featured image for an EFOS (efos.in) career-education blog "
        f"titled: {topic}. Indian youth, trustworthy, modern, hopeful, no text in image."
    )

    # Try primary provider/model, fall back to secondary on 404/unsupported-model.
    primary = (CFG.image_provider, CFG.image_model)
    fallback_providers = [
        ("openrouter", "stabilityai/stable-diffusion-xl-base-1.0"),
        ("openrouter", "black-forest-labs/FLUX.1-schnette"),
    ]

    tried = []
    for provider, model in [primary] + fallback_providers:
        if (provider, model) in tried:
            continue
        tried.append((provider, model))
        try:
            url = _generate(provider, model, prompt)
            if url:
                log.info(f"Generated image via {provider}/{model}.")
                return _download(url)
        except Exception as e:
            log.warning(f"Image generation failed for {provider}/{model}: {e}")

    log.warning("All image generation attempts failed. Publishing without image.")
    return None


def _generate(provider: str, model: str, prompt: str) -> str | None:
    if provider == "chatgpt":
        return _generate_image_chatgpt(model, prompt)
    return _generate_image_openrouter(model, prompt)


def _generate_image_openrouter(model: str, prompt: str) -> str | None:
    payload = {"model": model, "prompt": prompt, "n": 1}
    resp = requests.post(
        "https://openrouter.ai/api/v1/images/generations",
        headers=_openrouter_headers(),
        json=payload,
        timeout=180,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", [{}])[0].get("url")


def _generate_image_chatgpt(model: str, prompt: str) -> str | None:
    if not CFG.openai_api_key:
        return None
    payload = {
        "model": "dall-e-3",
        "prompt": prompt,
        "size": "1792x1024",
        "n": 1,
        "response_format": "url",
    }
    headers = {"Authorization": f"Bearer {CFG.openai_api_key}", "Content-Type": "application/json"}
    resp = requests.post("https://api.openai.com/v1/images/generations", headers=headers, json=payload, timeout=180)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json().get("data", [{}])[0].get("url")


def _download(url: str) -> bytes | None:
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    return resp.content


def _openrouter_headers() -> dict[str, str]:
    from .ai_client import CFG
    return {
        "Authorization": f"Bearer {CFG.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://efos.in",
        "X-Title": "EFOS AI Blog",
    }
