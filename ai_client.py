"""Thin HTTP client for OpenRouter (chat completions + image generation)."""
from __future__ import annotations

import json
import time
from typing import Any

import requests

from .config import CFG
from .logger import log

OPENROUTER_CHAT = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_IMAGES = "https://openrouter.ai/api/v1/images/generations"


class OpenRouterError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {CFG.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://efos.in",
        "X-Title": "EFOS AI Blog",
    }


def chat_json(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    max_retries: int = 3,
    max_tokens: int = 2048,
) -> dict[str, Any]:
    """Call the chat model and parse a JSON object response.

    The model is instructed (in the prompt) to return ONLY JSON. This helper
    extracts and parses it, retrying on transient failures / bad JSON.
    Falls back to CFG.ai_fallback_models on 402 / model errors.
    """
    model = model or CFG.ai_model
    fallbacks = [m.strip() for m in CFG.ai_fallback_models.split(",") if m.strip()]
    models_to_try = [model] + fallbacks

    last_err: Exception | None = None
    for current_model in models_to_try:
        payload = {
            "model": current_model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if ":free" not in current_model:
            payload["response_format"] = {"type": "json_object"}

        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.post(OPENROUTER_CHAT, headers=_headers(), json=payload, timeout=120)
                if resp.status_code == 402:
                    raise OpenRouterError(f"HTTP 402: Insufficient credits for {current_model}. Trying next model...")
                if resp.status_code == 404:
                    raise OpenRouterError(f"HTTP 404: Model {current_model} not found. Trying next model...")
                if resp.status_code != 200:
                    raise OpenRouterError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    raise OpenRouterError(f"No choices in response for {current_model}: {data}")
                content = choices[0].get("message", {}).get("content")
                if not content:
                    raise OpenRouterError(f"Empty content in response for {current_model}")
                return _extract_json(content)
            except (OpenRouterError, KeyError, ValueError, requests.RequestException) as e:
                last_err = e
                log.warning(f"chat_json model={current_model} attempt {attempt} failed: {e}")
                time.sleep(2 * attempt)
        log.warning(f"Model {current_model} exhausted. Trying next fallback...")

    raise OpenRouterError(f"chat_json failed after trying {models_to_try}: {last_err}")


def _extract_json(content: str) -> dict[str, Any]:
    """Parse JSON that may be wrapped in markdown code fences."""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.lower().startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def generate_image(prompt: str, *, size: str = "1792x1024") -> str | None:
    """Generate an image and return its URL, or None if disabled/failed.

    Provider is chosen by IMAGE_PROVIDER:
      - "openrouter" -> OpenRouter images endpoint (model from IMAGE_MODEL)
      - "chatgpt"    -> OpenAI ChatGPT image API (needs OPENAI_API_KEY)
    """
    if not CFG.use_image_api:
        return None
    if CFG.image_provider == "chatgpt":
        return _generate_image_chatgpt(prompt, size=size)
    return _generate_image_openrouter(prompt, size=size)


def _generate_image_openrouter(prompt: str, *, size: str) -> str | None:
    payload = {
        "model": CFG.image_model,
        "prompt": prompt,
        "size": size,
        "n": 1,
    }
    try:
        resp = requests.post(OPENROUTER_IMAGES, headers=_headers(), json=payload, timeout=180)
        if resp.status_code != 200:
            log.warning(f"Image generation failed HTTP {resp.status_code}: {resp.text[:200]}")
            return None
        return resp.json()["data"][0]["url"]
    except (requests.RequestException, KeyError, IndexError) as e:
        log.warning(f"Image generation error: {e}")
        return None


def _generate_image_chatgpt(prompt: str, *, size: str) -> str | None:
    """Generate an image via the OpenAI ChatGPT image API (api.openai.com)."""
    if not CFG.openai_api_key:
        log.warning("IMAGE_PROVIDER=chatgpt but OPENAI_API_KEY is empty. Skipping image.")
        return None
    # ChatGPT image API accepts sizes 1024x1024 / 1792x1024 / 1024x1792.
    payload = {
        "model": "dall-e-3",
        "prompt": prompt,
        "size": size if size in ("1024x1024", "1792x1024", "1024x1792") else "1024x1024",
        "n": 1,
        "response_format": "url",
    }
    headers = {
        "Authorization": f"Bearer {CFG.openai_api_key}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers=headers,
            json=payload,
            timeout=180,
        )
        if resp.status_code != 200:
            log.warning(f"ChatGPT image failed HTTP {resp.status_code}: {resp.text[:200]}")
            return None
        return resp.json()["data"][0]["url"]
    except (requests.RequestException, KeyError, IndexError) as e:
        log.warning(f"ChatGPT image error: {e}")
        return None
