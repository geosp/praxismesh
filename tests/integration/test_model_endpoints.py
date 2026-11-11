"""Model endpoints (model-endpoints spec). Skipped when VLLM_BASE_URL is unset or
empty; fail, naming the endpoint, when it is set but unreachable."""

from __future__ import annotations

import os
import re

import pytest

from tests.support.models import EndpointUnreachableError, request, served_models

pytestmark = pytest.mark.integration

BASE_URL = os.environ.get("VLLM_BASE_URL", "")
MODEL = os.environ.get("VLLM_MODEL", "spark")
API_KEY = os.environ.get("VLLM_API_KEY", "")
PROMPT = "Reply with exactly one word: ready"

needs_endpoint = pytest.mark.skipif(
    not BASE_URL, reason="VLLM_BASE_URL is unset or empty; model endpoint not configured"
)


def test_model_name_has_no_slash() -> None:
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
    # Its own address (port 9, discard), not the configured one, so it also runs in CI.
    unreachable = "http://127.0.0.1:9"
    with pytest.raises(EndpointUnreachableError, match=re.escape(unreachable)):
        served_models(unreachable)
