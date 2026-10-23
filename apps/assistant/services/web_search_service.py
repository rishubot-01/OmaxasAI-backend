
"""
OmaxasAI Web Search service.

Uses Tavily Search API to retrieve current web results.
Search results are untrusted external content and must be
treated as data, never as system instructions.
"""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TAVILY_SEARCH_URL = "https://api.tavily.com/search"
DEFAULT_TIMEOUT_SECONDS = 20
MAX_RESULTS_LIMIT = 10


class WebSearchError(RuntimeError):
    """Raised when a web search cannot be completed."""


def search_web(
    query: str,
    *,
    max_results: int = 5,
    search_depth: str = "basic",
    topic: str = "general",
    time_range: str | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> dict:
    """
    Search the web and return normalized search results.

    Args:
        query: The user's search query.
        max_results: Number of results to request (1-10).
        search_depth: "basic", "fast", or "advanced".
        topic: "general", "news", or "finance".
        time_range: Optional "day", "week", "month", or "year".
        include_domains: Optional list of domains to prioritize.
        exclude_domains: Optional list of domains to exclude.

    Returns:
        {
            "query": str,
            "answer": str | None,
            "results": [
                {
                    "title": str,
                    "url": str,
                    "content": str,
                    "score": float | None,
                    "published_date": str | None
                }
            ]
        }

    Raises:
        ValueError: If the input is invalid.
        WebSearchError: If configuration or the provider request fails.
    """

    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search query cannot be empty.")

    query = query.strip()

    if len(query) > 500:
        raise ValueError("Search query cannot exceed 500 characters.")

    if not 1 <= max_results <= MAX_RESULTS_LIMIT:
        raise ValueError(
            f"max_results must be between 1 and {MAX_RESULTS_LIMIT}."
        )

    allowed_depths = {"basic", "fast", "advanced"}
    if search_depth not in allowed_depths:
        raise ValueError(
            "search_depth must be basic, fast, or advanced."
        )

    allowed_topics = {"general", "news", "finance"}
    if topic not in allowed_topics:
        raise ValueError(
            "topic must be general, news, or finance."
        )

    allowed_time_ranges = {"day", "week", "month", "year"}
    if time_range is not None and time_range not in allowed_time_ranges:
        raise ValueError(
            "time_range must be day, week, month, year, or None."
        )

    api_key = os.getenv("TAVILY_API_KEY", "").strip()

    if not api_key:
        raise WebSearchError(
            "Web Search is not configured. Set TAVILY_API_KEY "
            "in the server environment."
        )

    payload = {
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "topic": topic,
        "include_answer": True,
        "include_raw_content": False,
    }

    if time_range is not None:
        payload["time_range"] = time_range

    if include_domains:
        payload["include_domains"] = _validate_domains(include_domains)

    if exclude_domains:
        payload["exclude_domains"] = _validate_domains(exclude_domains)

    request = Request(
        TAVILY_SEARCH_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(
            request,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as response:
            response_data = json.loads(
                response.read().decode("utf-8")
            )

    except HTTPError as exc:
        # Do not expose provider response bodies or credentials.
        raise WebSearchError(
            f"Web Search provider returned HTTP {exc.code}."
        ) from exc

    except (URLError, TimeoutError) as exc:
        raise WebSearchError(
            "Web Search provider could not be reached."
        ) from exc

    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise WebSearchError(
            "Web Search provider returned an invalid response."
        ) from exc

    if not isinstance(response_data, dict):
        raise WebSearchError(
            "Web Search provider returned an unexpected response."
        )

    raw_results = response_data.get("results", [])

    if not isinstance(raw_results, list):
        raise WebSearchError(
            "Web Search provider returned invalid search results."
        )

    normalized_results = []

    for item in raw_results[:max_results]:
        if not isinstance(item, dict):
            continue

        title = item.get("title")
        url = item.get("url")
        content = item.get("content")

        # Return only well-formed web result records.
        if not isinstance(url, str) or not url.startswith(
            ("https://", "http://")
        ):
            continue

        normalized_results.append({
            "title": title if isinstance(title, str) else "",
            "url": url,
            "content": content if isinstance(content, str) else "",
            "score": _safe_score(item.get("score")),
            "published_date": (
                item.get("published_date")
                if isinstance(item.get("published_date"), str)
                else None
            ),
        })

    answer = response_data.get("answer")

    return {
        "query": query,
        "answer": answer if isinstance(answer, str) else None,
        "results": normalized_results,
    }


def _validate_domains(domains: list[str]) -> list[str]:
    """Validate domain filters without accepting arbitrary URLs."""

    if not isinstance(domains, list):
        raise ValueError("Domain filters must be lists.")

    validated = []

    for domain in domains:
        if not isinstance(domain, str):
            raise ValueError("Each domain must be a string.")

        domain = domain.strip().lower()

        if (
            not domain
            or "://" in domain
            or "/" in domain
            or " " in domain
        ):
            raise ValueError(
                f"Invalid domain filter: {domain!r}"
            )

        validated.append(domain)

    return validated


def _safe_score(value) -> float | None:
    """Return a valid numeric relevance score, if available."""

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None

