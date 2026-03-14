from __future__ import annotations

import os
from typing import Any

import requests


SERPER_ENDPOINT = "https://google.serper.dev/search"


def serper_search(query: str, top_k: int = 5, timeout_sec: int = 10) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Returns a list of {title, link, snippet} items. Requires SERPER_API_KEY.
    Safe to call from request/worker paths: fails closed to empty results.
    """
    api_key = (os.getenv("SERPER_API_KEY") or "").strip()
    if not api_key:
        return [], {"mode": "disabled", "reason": "missing_SERPER_API_KEY"}

    payload: dict[str, Any] = {"q": query, "num": max(1, min(10, int(top_k)))}
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}

    try:
        resp = requests.post(SERPER_ENDPOINT, json=payload, headers=headers, timeout=timeout_sec)
        resp.raise_for_status()
        data = resp.json() if resp.content else {}
    except Exception as exc:
        return [], {"mode": "error", "reason": str(exc)[:180]}

    items: list[dict[str, Any]] = []
    for block_name in ("organic", "news", "places"):
        for row in (data.get(block_name) or [])[: int(top_k)]:
            title = (row.get("title") or "").strip()
            link = (row.get("link") or row.get("website") or "").strip()
            snippet = (row.get("snippet") or row.get("description") or "").strip()
            if not (title or link or snippet):
                continue
            items.append({"title": title, "link": link, "snippet": snippet})

    return items[: int(top_k)], {"mode": "serper", "count": len(items)}

