from fastapi import APIRouter, Query
from src.api.search import (
    search_by_keyword,
    keyword_top_speakers,
    keyword_activity
)

router = APIRouter()


@router.get("/")
def root():
    return {"status": "ok"}


@router.get("/search")
def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
):
    results = search_by_keyword(q, limit)

    return {
        "query": q,
        "count": len(results),
        "results": results,
    }

@router.get("/search/activity")
def search_activity(
        q: str = Query(..., min_length=1),
        interval: str = Query("monthly")
):
    return {
        "query": q,
        "interval": interval,
        "activity": keyword_activity(q, interval)
    }

@router.get("/search/speakers")
def search_speakers(q, limit: int = 20):
    return {
        "query": q,
        "speakers": keyword_top_speakers(q, limit)
    }