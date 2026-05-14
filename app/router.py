from fastapi import APIRouter, Body, Query

from app.models import QueryRequest, QueryResponse, QueryData, StatsResponse, StatsData
from app.utils import normalize, compute_fingerprint, compute_options_hash
from app.database import get_question, insert_question, upsert_question, get_stats
from app.ai_client import query_ai

router = APIRouter()

# Statistics (in-process counters)
_cache_hits = 0
_cache_misses = 0


def _extract_params(
    body: QueryRequest | None = None,
    title_q: str | None = None,
    options_q: str | None = None,
    type_q: str | None = None,
) -> tuple[str, str | None, str | None]:
    """Extract params from JSON body first, fall back to query string."""
    if body and body.title:
        return body.title, body.options, body.type
    return title_q or "", options_q, type_q


async def _process_question(
    title: str,
    options: str | None = None,
    qtype: str | None = None,
    force_refresh: bool = False,
) -> QueryResponse:
    global _cache_hits, _cache_misses

    title = normalize(title)
    qtype = normalize(qtype)
    options = normalize(options)

    if not title:
        return QueryResponse(code=4, msg="Title is required")

    fingerprint = compute_fingerprint(title, qtype, options)
    opts_hash = compute_options_hash(options)

    if not force_refresh:
        cached = await get_question(fingerprint)
        if cached is not None:
            _cache_hits += 1
            return QueryResponse(
                code=0,
                data=QueryData(question=cached["title"], answer=cached["answer"]),
                msg="success (cached)",
            )

    # Cache miss - query AI
    _cache_misses += 1

    try:
        answer = await query_ai(title, options, qtype)
    except RuntimeError as e:
        return QueryResponse(code=2, msg=str(e))
    except ValueError as e:
        return QueryResponse(code=3, msg=str(e))

    if force_refresh:
        await upsert_question(fingerprint, title, options, qtype, answer, opts_hash)
    else:
        await upsert_question(fingerprint, title, options, qtype, answer, opts_hash)

    return QueryResponse(
        code=0,
        data=QueryData(question=title, answer=answer),
        msg="success (ai)",
    )


@router.get("/query")
async def query_get(
    title: str = Query(""),
    options: str | None = Query(None),
    type: str | None = Query(None),
):
    return await _process_question(title, options, type)


@router.post("/query")
async def query_post(
    body: QueryRequest | None = Body(None),
    title: str = Query(""),
    options: str | None = Query(None),
    type: str | None = Query(None),
):
    t, o, ty = _extract_params(body, title, options, type)
    return await _process_question(t, o, ty)


@router.get("/reload")
async def reload_get(
    title: str = Query(""),
    options: str | None = Query(None),
    type: str | None = Query(None),
):
    return await _process_question(title, options, type, force_refresh=True)


@router.post("/reload")
async def reload_post(
    body: QueryRequest | None = Body(None),
    title: str = Query(""),
    options: str | None = Query(None),
    type: str | None = Query(None),
):
    t, o, ty = _extract_params(body, title, options, type)
    return await _process_question(t, o, ty, force_refresh=True)


@router.get("/stats")
async def stats():
    global _cache_hits, _cache_misses
    db_stats = await get_stats()
    return StatsResponse(
        data=StatsData(
            total=db_stats["total"],
            hit_count=_cache_hits,
            miss_count=_cache_misses,
        ),
    )


@router.get("/")
@router.head("/")
async def root():
    return {"service": "OCS AI Question Bank", "version": "1.0.0"}


@router.get("/health")
@router.head("/health")
async def health():
    return {"status": "ok"}
