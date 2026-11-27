"""The one place that talks to Claude."""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

MODEL = os.environ.get("CONTENT_ENGINE_MODEL", "claude-opus-5-5")
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeError(RuntimeError):
    pass


_client = None


def client():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY (or an `ant auth login` profile)
    return _client


def text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def image_block(path: Path) -> dict:
    media = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    data = base64.standard_b64encode(path.read_bytes()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}


def ask(system: str, content: list[dict], *, effort: str = "high", max_tokens: int = 64000,
        api=None) -> str:
    """Send one request and return Claude's text answer.

    Streams (long answers would otherwise hit HTTP timeouts), caches the system prompt
    (the same for every video in a step), and asks the API to retry on a fallback model
    if the request is declined.
    """
    api = api or client()
    with api.beta.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": content}],
        output_config={"effort": effort},
        betas=[FALLBACK_BETA],
        fallbacks="default",
    ) as stream:
        msg = stream.get_final_message()

    if msg.stop_reason == "refusal":
        details = getattr(msg, "stop_details", None)
        raise ClaudeError(f"Claude declined this request ({getattr(details, 'category', None)}): "
                          f"{getattr(details, 'explanation', '')}")
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    if msg.stop_reason == "max_tokens":
        log.warning("Answer hit the %d-token limit and is cut off at the end", max_tokens)
        text += "\n\n> Note: this answer reached the length limit and is cut off here.\n"
    u = msg.usage
    log.info("Claude: %s in (%s cached), %s out", u.input_tokens, getattr(u, "cache_read_input_tokens", 0),
             u.output_tokens)
    return text
