"""Model endpoints (model-endpoints spec). Skipped when VLLM_BASE_URL is unset or
empty; fail, naming the endpoint, when it is set but unreachable."""

from __future__ import annotations

import os
import re

import pytest

from tests.support.models import EndpointUnreachableError, request, served_models

pytestmark = pytest.mark.integration

BASE_URL = os.environ.get("VLLM_BASE_URL", "")
MODEL = os.environ.get("VLLM_MODEL", "")
API_KEY = os.environ.get("VLLM_API_KEY", "")
PROMPT = "Reply with exactly one word: ready"

needs_endpoint = pytest.mark.skipif(
    not BASE_URL, reason="VLLM_BASE_URL is unset or empty; model endpoint not configured"
)


@needs_endpoint
def test_model_name_configured() -> None:
    assert MODEL, "VLLM_MODEL is empty; set the served model name in infra/.env"
    assert "/" not in MODEL, f"VLLM_MODEL must not contain '/': {MODEL!r}"


@needs_endpoint
def test_model_listed() -> None:
    assert MODEL in served_models(BASE_URL, API_KEY)


@needs_endpoint
def test_messages_endpoint() -> None:
    reply = request(
        BASE_URL,
        "POST",
        "/v1/messages",
        API_KEY,
        json={"model": MODEL, "max_tokens": 64, "messages": [{"role": "user", "content": PROMPT}]},
    )
    assert any(block.get("type") == "text" and block["text"].strip() for block in reply["content"])


@needs_endpoint
def test_chat_endpoint() -> None:
    reply = request(
        BASE_URL,
        "POST",
        "/v1/chat/completions",
        API_KEY,
        json={"model": MODEL, "max_tokens": 64, "messages": [{"role": "user", "content": PROMPT}]},
    )
    assert reply["choices"][0]["message"]["content"].strip()


def test_unreachable_endpoint_fails() -> None:
    # Checks the failure path, so it uses its own address (port 9, discard) rather
    # than the configured endpoint, and also runs in CI (design follow-up 2, M2).
    unreachable = "http://127.0.0.1:9"
    with pytest.raises(EndpointUnreachableError, match=re.escape(unreachable)):
        served_models(unreachable)
