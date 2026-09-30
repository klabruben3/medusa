"""Bounded Groq requests and per-model admission; never log prompts or responses."""
import asyncio
import json
import logging
import math
import os
import time
from collections import defaultdict, deque

from groq import APIStatusError, RateLimitError
from ..utils.documents import DocumentError

logger = logging.getLogger(__name__)


def estimate_tokens(value):
    # Conservative approximation for bilingual prose/JSON, not a model tokenizer.
    # Reserve additional headroom and still handle provider-side rejections.
    return math.ceil(len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) / 3) + 256


def model_for(purpose):
    default = "openai/gpt-oss-120b" if purpose == "grading" else "openai/gpt-oss-20b"
    return os.getenv(f"GROQ_{purpose.upper()}_MODEL") or os.getenv("GROQ_MODULE_MODEL") or default


def request_budget():
    try:
        return max(2000, int(os.getenv("GROQ_TPM_BUDGET", "8000")))
    except ValueError:
        raise DocumentError("GROQ_TPM_BUDGET must be an integer.", 503, "invalid_token_budget") from None


class ModelLimiter:
    def __init__(self, clock=time.monotonic, sleep=asyncio.sleep):
        self.entries = defaultdict(deque)
        self.clock, self.sleep = clock, sleep

    async def reserve(self, model, tokens):
        budget = request_budget()
        if tokens > budget - 500:
            raise DocumentError("An extraction request exceeds the configured token budget. Split this document into smaller sections or configure a higher account limit.", 413, "request_budget_exceeded")
        while True:
            now = self.clock()
            queue = self.entries[model]
            while queue and now - queue[0][0] >= 61:
                queue.popleft()
            # No await between checking and recording: atomic in this event loop.
            if sum(entry[1] for entry in queue) + tokens <= budget - 500 and len(queue) < 25:
                queue.append((now, tokens))
                return
            delay = max(0.01, 61 - (now - queue[0][0]))
            logger.info("stage=waiting_for_model model=%s wait_seconds=%.1f", model, delay)
            await self.sleep(delay)


limiter = ModelLimiter()


async def complete(client, purpose, messages, schema, output_tokens):
    model = model_for(purpose)
    response_format = {"type": "json_schema", "json_schema": {
        "name": purpose.title() + "Extraction", "schema": schema, "strict": False}}
    tokens = estimate_tokens({"messages": messages, "response_format": response_format}) + output_tokens
    for attempt in range(2):
        await limiter.reserve(model, tokens)
        logger.info("stage=model_request purpose=%s model=%s estimated_tokens=%d output_limit=%d", purpose, model, tokens, output_tokens)
        try:
            return await client.chat.completions.create(model=model, messages=messages,
                response_format=response_format, temperature=0, max_completion_tokens=output_tokens)
        except RateLimitError as exc:
            if attempt:
                raise
            try:
                delay = min(120, max(1, float(exc.response.headers.get("retry-after", "61"))))
            except (TypeError, ValueError):
                delay = 61
            await asyncio.sleep(delay)
        except APIStatusError as exc:
            # Metadata only. Raw provider errors may include generated source text.
            logger.warning("stage=model_rejected purpose=%s model=%s upstream_status=%s", purpose, model, exc.status_code)
            raise
