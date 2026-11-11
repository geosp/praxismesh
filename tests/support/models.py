"""Minimal clients for the model endpoints (vLLM), naming the endpoint on failure."""

from __future__ import annotations

from typing import Any

import httpx


class EndpointUnreachableError(RuntimeError):
    pass


def request(
    base_url: str, method: str, path: str, api_key: str = "", **kwargs: Any
) -> dict[str, Any]:
    url = base_url.rstrip("/") + path
    headers = {"Authorization": f"Bearer {api_key}", "x-api-key": api_key} if api_key else {}
    try:
        # Connect fails fast; generation may take a while.
        timeout = httpx.Timeout(120, connect=5)
        response = httpx.request(method, url, headers=headers, timeout=timeout, **kwargs)
    except httpx.TransportError as e:
        raise EndpointUnreachableError(f"model endpoint {base_url} is unreachable: {e!r}") from e
    response.raise_for_status()
    body: dict[str, Any] = response.json()
    return body


def served_models(base_url: str, api_key: str = "") -> list[str]:
    return [m["id"] for m in request(base_url, "GET", "/v1/models", api_key)["data"]]
