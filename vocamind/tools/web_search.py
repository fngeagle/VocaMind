"""网络搜索工具：默认 DuckDuckGo（无需 API Key），可选 Tavily。"""
from __future__ import annotations

import os
from typing import Any

import requests

MAX_RESULTS_CAP = 10


def _normalize_results(raw: list[dict[str, Any]]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for row in raw:
        title = str(row.get("title") or row.get("name") or "").strip()
        url = str(row.get("href") or row.get("url") or row.get("link") or "").strip()
        snippet = str(row.get("body") or row.get("content") or row.get("snippet") or "").strip()
        if title or url or snippet:
            items.append({"title": title, "url": url, "snippet": snippet})
    return items


def _format_results(query: str, backend: str, results: list[dict[str, str]]) -> str:
    lines = [f"Search ({backend}): {query}", f"Results: {len(results)}", ""]
    for idx, item in enumerate(results, start=1):
        lines.append(f"{idx}. {item['title'] or '(no title)'}")
        if item["url"]:
            lines.append(f"   URL: {item['url']}")
        if item["snippet"]:
            lines.append(f"   {item['snippet'][:500]}")
        lines.append("")
    return "\n".join(lines).strip()


def _search_duckduckgo(query: str, max_results: int) -> list[dict[str, str]]:
    from ddgs import DDGS

    with DDGS() as ddgs:
        raw = list(ddgs.text(query, max_results=max_results))
    return _normalize_results(raw)


def _search_tavily(query: str, max_results: int) -> list[dict[str, str]]:
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        raise ValueError("TAVILY_API_KEY 未设置")

    response = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "include_answer": False,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return _normalize_results(data.get("results", []))


def _resolve_backend(backend: str) -> str:
    choice = (backend or "auto").strip().lower()
    if choice == "auto":
        return "tavily" if os.getenv("TAVILY_API_KEY", "").strip() else "duckduckgo"
    if choice in ("duckduckgo", "ddg", "tavily"):
        return "duckduckgo" if choice in ("duckduckgo", "ddg") else "tavily"
    raise ValueError(f"不支持的 backend: {backend}")


def run_web_search(query: str, max_results: int = 5, backend: str = "auto") -> str:
    """搜索互联网并返回标题、链接与摘要。"""
    text = (query or "").strip()
    if not text:
        return "Error: query 不能为空"

    limit = max(1, min(int(max_results or 5), MAX_RESULTS_CAP))
    try:
        resolved = _resolve_backend(backend)
    except ValueError as exc:
        return f"Error: {exc}"

    try:
        if resolved == "tavily":
            results = _search_tavily(text, limit)
        else:
            results = _search_duckduckgo(text, limit)
    except Exception as exc:
        if resolved == "tavily":
            try:
                results = _search_duckduckgo(text, limit)
                resolved = "duckduckgo (fallback)"
            except Exception as fallback_exc:
                return f"Error: Tavily 失败 ({exc}); DuckDuckGo 回落也失败 ({fallback_exc})"
        else:
            return f"Error: {exc}"

    if not results:
        return f"No results for: {text}"
    return _format_results(text, resolved, results)
