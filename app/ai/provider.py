"""Bounded Groq requests and per-model admission; never log prompts or responses."""
import asyncio
from copy import deepcopy
import json
import hashlib
import logging
import math
import os
import time
from collections import defaultdict, deque

from groq import APIStatusError, RateLimitError, APIConnectionError
from ..utils.documents import DocumentError
from .local_review import verify_local_review

logger = logging.getLogger(__name__)
SCHEMA_REPAIR_PROMPT = ("The provider rejected the preceding output for JSON schema validation. Return the complete supplied "
    "schema, including every required property and nested property. Use null only where nullable, and "
    "empty arrays for absent warnings/conflicts. Do not add prose or change source facts.")


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


def strict_schema(schema):
    """Groq strict mode requires every object property, including nullable ones."""
    value = deepcopy(schema)
    def walk(node):
        if isinstance(node, dict):
            node.pop("title", None)
            node.pop("default", None)
            if node.get("type") == "object":
                node["required"] = list(node.get("properties", {}))
                node["additionalProperties"] = False
            for key, item in node.items():
                if key in {"properties", "$defs"}:
                    for child in item.values():
                        walk(child)
                else:
                    walk(item)
        elif isinstance(node, list):
            for item in node:
                walk(item)
    walk(value)
    return value



def verify_processing_review(client=None):
    """Fail closed until the actual provider account and minor safeguards have been reviewed."""
    if verify_local_review(client):
        return
    reference = os.getenv("AI_GROQ_REVIEW_REFERENCE", "").strip()
    # Iris enforces owner audience/deployment restrictions separately. Medusa's
    # registered-user authorization cannot inherit those scoped attestations.
    if (os.getenv("AI_REVIEW_SCOPE") is not None
            or reference.lower().startswith(("owner-preview:", "owner-production:", "local-nwu:"))):
        raise DocumentError("Document AI processing is awaiting an applicable review. No provider request was sent.",
                            503, "provider_review_required")
    checks = ("NO_TRAINING", "RETENTION", "INTERNATIONAL_TRANSFER", "MINOR_SAFEGUARDS")
    if (not all(os.getenv(f"AI_GROQ_{check}_VERIFIED") == "true" for check in checks)
            or not reference):
        raise DocumentError("Document AI processing is awaiting a privacy review. No provider request was sent.",
                            503, "provider_review_required")

def request_format(purpose, schema, model=None):
    """One format builder for admission planning and the actual provider request."""
    model = model or model_for(purpose)
    strict = model in {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}
    request_schema = strict_schema(schema) if strict else schema
    schema_id = hashlib.sha256(json.dumps(request_schema, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]
    label = "".join(c for c in schema.get("title", purpose.title() + "Extraction")
                    if c.isascii() and (c.isalnum() or c in "_-"))[:40] or "Extraction"
    response_format = {"type": "json_schema", "json_schema": {
        "name": label + "_" + schema_id, "schema": request_schema, "strict": strict}}
    return response_format, schema_id, strict


async def complete(client, purpose, messages, schema, output_tokens, *, on_rejected=None):
    verify_processing_review(client)
    model = model_for(purpose)
    response_format, schema_id, strict = request_format(purpose, schema, model)
    messages = list(messages)
    for attempt in range(2):
        tokens = estimate_tokens({"messages": messages, "response_format": response_format}) + output_tokens
        await limiter.reserve(model, tokens)
        logger.info("stage=model_request purpose=%s model=%s schema_id=%s estimated_tokens=%d output_limit=%d", purpose, model, schema_id, tokens, output_tokens)
        try:
            verify_processing_review(client)
            # GPT-OSS reasoning consumes the same bounded completion allowance.
            # Literal workers keep room for JSON; grading retains the model's
            # default effort for its more complex rules. Custom models are unchanged.
            options = {"reasoning_effort": "medium" if purpose == "grading" else "low"} if strict else {}
            response = await client.chat.completions.create(model=model, messages=messages,
                response_format=response_format, temperature=0, max_completion_tokens=output_tokens, **options)
            usage = getattr(response, "usage", None)
            if usage is not None:
                logger.info("stage=model_response purpose=%s input_tokens=%s output_tokens=%s", purpose,
                            getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None))
            return response
        except RateLimitError as exc:
            if attempt:
                raise
            try:
                delay = min(120, max(1, float(exc.response.headers.get("retry-after", "61"))))
            except (TypeError, ValueError):
                delay = 61
            await asyncio.sleep(delay)
        except APIConnectionError:
            if attempt:
                raise
            logger.warning("stage=model_transport_retry purpose=%s model=%s", purpose, model)
            await asyncio.sleep(2)
        except APIStatusError as exc:
            # Metadata only. Raw provider errors may include generated source text.
            logger.warning("stage=model_rejected purpose=%s model=%s upstream_status=%s", purpose, model, exc.status_code)
            body = exc.body if isinstance(exc.body, dict) else {}
            detail = body.get("error", body)
            failed = detail.get("failed_generation") if isinstance(detail, dict) else None
            if isinstance(failed, str):
                if on_rejected is not None:
                    await on_rejected(failed, 'provider_schema')
                try:
                    generated = json.loads(failed)
                    valid_json = True
                except ValueError:
                    generated, valid_json = None, False
                logger.warning("stage=model_rejection_metadata purpose=%s failed_characters=%d valid_json=%s root_type=%s",
                               purpose, len(failed), valid_json, type(generated).__name__)
                if isinstance(generated, dict):
                    missing = len(set(response_format["json_schema"]["schema"].get("required", [])) - set(generated))
                    from .partials import PARTIALS, GRADING_PARTIALS
                    from pydantic import ValidationError
                    kind = next((item for item in [*PARTIALS.values(), *GRADING_PARTIALS.values()]
                                 if set(item.model_fields) == set(schema.get("properties", {}))), None)
                    errors = []
                    if kind is not None:
                        try:
                            kind.model_validate(generated)
                        except ValidationError as error:
                            errors = sorted({item["type"] for item in error.errors()})
                    logger.warning("stage=model_rejection_shape purpose=%s missing_root_fields=%d validation_types=%s",
                                   purpose, missing, ",".join(errors) or "none")
            if (not attempt and exc.status_code == 400 and isinstance(detail, dict)
                    and detail.get("code") == "json_validate_failed"):
                messages.append({"role": "user", "content": SCHEMA_REPAIR_PROMPT})
                logger.warning("stage=model_schema_retry purpose=%s model=%s", purpose, model)
                continue
            raise
