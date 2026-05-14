import asyncio
import logging

import httpx
from app.config import settings
from app.prompt_builder import SYSTEM_PROMPT_DEEP, build_user_prompt

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=settings.ai_timeout)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _call_ai(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    """Single AI call, returns raw content string. Raises on failure."""
    client = get_client()

    payload = {
        "model": settings.ai_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": settings.ai_temperature,
        "max_tokens": max_tokens,
    }

    headers = {
        "Authorization": f"Bearer {settings.ai_api_key}",
        "Content-Type": "application/json",
    }

    resp = await client.post(
        f"{settings.ai_base_url}/chat/completions",
        json=payload,
        headers=headers,
    )
    resp.raise_for_status()
    data = resp.json()
    choice = data["choices"][0]
    content = (choice.get("message", {}).get("content") or "").strip()
    finish = choice.get("finish_reason", "unknown")

    logger.info("AI raw response (%d chars, finish=%s): %s",
                len(content), finish, content[:300])
    if settings.debug:
        logger.debug("AI full response:\n%s", content)

    return content, finish


async def query_ai(title: str, options: str, qtype: str) -> str:
    """Send question to AI with deep reasoning + optional web search."""
    if not settings.ai_api_key:
        raise RuntimeError("AI_API_KEY is not configured")

    # Build search context for first encounter
    search_context = ""
    if settings.web_search:
        try:
            from app.search import search_web
            # Use the question title + key context words as search query
            query = title[:200]
            search_context = await search_web(query)
        except Exception as e:
            logger.warning("Web search skipped: %s", e)

    user_prompt = build_user_prompt(title, qtype, options, search_context)

    logger.info("AI query (deep): title=%s, type=%s, search=%s",
                title[:80], qtype, "yes" if search_context else "no")
    logger.debug("User prompt:\n%s", user_prompt)

    for attempt in range(3):
        try:
            content, finish = await _call_ai(
                SYSTEM_PROMPT_DEEP, user_prompt, settings.ai_max_tokens_deep
            )

            if not content:
                delay = (attempt + 1) * 2
                logger.warning("AI returned empty response (attempt %d/3, finish=%s), retry in %ds",
                              attempt + 1, finish, delay)
                await asyncio.sleep(delay)
                continue

            # Truncated response: retry with higher max_tokens
            if finish == "length" and attempt < 2:
                new_max = settings.ai_max_tokens_deep * 2
                logger.warning("AI response truncated (finish=length), retry with max_tokens=%d", new_max)
                content, finish = await _call_ai(SYSTEM_PROMPT_DEEP, user_prompt, new_max)
                if not content:
                    continue
                from app.prompt_builder import parse_ai_response
                return parse_ai_response(content)

            from app.prompt_builder import parse_ai_response
            return parse_ai_response(content)

        except httpx.HTTPStatusError as e:
            logger.error("AI API error (attempt %d/3): status=%d, body=%s",
                         attempt + 1, e.response.status_code, e.response.text[:500])
            if attempt < 2:
                await asyncio.sleep((attempt + 1) * 2)
            else:
                raise RuntimeError(f"AI API error (status {e.response.status_code}): {e.response.text[:300]}")
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            logger.error("AI API connection error (attempt %d/3): %s", attempt + 1, e)
            if attempt < 2:
                await asyncio.sleep((attempt + 1) * 2)
            else:
                raise RuntimeError(f"AI API connection error: {e}")

    raise RuntimeError("AI API: max retries exceeded (empty responses)")
