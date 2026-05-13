import httpx
from app.config import settings
from app.prompt_builder import SYSTEM_PROMPT, build_user_prompt

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


async def query_ai(title: str, options: str, qtype: str) -> str:
    """Send question to AI model and return the parsed answer string."""
    if not settings.ai_api_key:
        raise RuntimeError("AI_API_KEY is not configured")

    client = get_client()
    user_prompt = build_user_prompt(title, qtype, options)

    payload = {
        "model": settings.ai_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": settings.ai_temperature,
        "max_tokens": settings.ai_max_tokens,
    }

    headers = {
        "Authorization": f"Bearer {settings.ai_api_key}",
        "Content-Type": "application/json",
    }

    for attempt in range(3):
        try:
            resp = await client.post(
                f"{settings.ai_base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]

            from app.prompt_builder import parse_ai_response
            return parse_ai_response(content)

        except httpx.HTTPStatusError as e:
            if attempt == 2:
                raise RuntimeError(f"AI API error (status {e.response.status_code}): {e.response.text[:300]}")
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            if attempt == 2:
                raise RuntimeError(f"AI API connection error: {e}")

    raise RuntimeError("AI API: max retries exceeded")
