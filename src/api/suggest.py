from collections import OrderedDict

from fastapi import HTTPException
from sqlalchemy import func, or_

from config import STOPWORDS
from src.load.models import Lemma, Speech, SystemMeta
from src.transform.lemma_links import get_person_lemmas

_UNSET = object()
_CACHE_MAX_SIZE = 2048
MAX_SUGGESTION_DF_RATIO = 0.20
SUGGEST_EXCLUDE = {"miski", "miks", "kaasa"}

_SUGGEST_CACHE: dict = {
    "last_sync_at": _UNSET,
    "total_speeches": None,
    "person_lemmas": None,
    "prefixes": OrderedDict(),
}


def clear_suggest_cache() -> None:
    """Clear in-process suggestions cache."""
    _SUGGEST_CACHE["last_sync_at"] = _UNSET
    _SUGGEST_CACHE["total_speeches"] = None
    _SUGGEST_CACHE["person_lemmas"] = None
    _SUGGEST_CACHE["prefixes"].clear()


def _get_last_sync_at(session) -> str | None:
    try:
        row = session.query(SystemMeta).filter_by(key="last_sync_at").first()
        return row.value if row else None
    except Exception:
        return None


def get_prefix_next(prefix: str) -> str:
    """Calculate upper bound for SQLite B-tree range query."""
    if not prefix:
        return ""
    return prefix[:-1] + chr(ord(prefix[-1]) + 1)


def get_search_suggestions(
    prefix: str,
    limit: int = 8,
    session=None,
) -> list[dict]:
    """Retrieve keyword suggestions for a typed search prefix.

    - Prefix: 2–40 chars, trimmed, lowercased for matching (<2 chars raises 422).
    - Uses SQLite unique B-tree index on lemmas(lemma) with range query (>= p and < p_next).
    - Excludes STOPWORDS, lemmas without letters, df < 3, and df > 20% of all speeches.
    - Orders by df desc, then lemma.
    - Capitalises display form for person names.
    """
    trimmed = prefix.strip()
    if len(trimmed) < 2:
        raise HTTPException(status_code=422, detail="Sisesta vähemalt 2 tähemärki.")
    if len(trimmed) > 40:
        raise HTTPException(status_code=422, detail="Maksimaalne pikkus on 40 tähemärki.")

    p_lower = trimmed.lower()
    clamped_limit = min(max(1, limit), 20)
    cache_key = (p_lower, clamped_limit)

    last_sync = _get_last_sync_at(session)
    if _SUGGEST_CACHE["last_sync_at"] != last_sync:
        clear_suggest_cache()
        _SUGGEST_CACHE["last_sync_at"] = last_sync

    if cache_key in _SUGGEST_CACHE["prefixes"]:
        _SUGGEST_CACHE["prefixes"].move_to_end(cache_key)
        return [dict(item) for item in _SUGGEST_CACHE["prefixes"][cache_key]]

    if _SUGGEST_CACHE["total_speeches"] is None:
        _SUGGEST_CACHE["total_speeches"] = session.query(func.count(Speech.id)).scalar() or 0
    total_speeches = _SUGGEST_CACHE["total_speeches"]

    if _SUGGEST_CACHE["person_lemmas"] is None:
        try:
            conn = session.connection()
            _SUGGEST_CACHE["person_lemmas"] = get_person_lemmas(conn=conn)
        except Exception:
            _SUGGEST_CACHE["person_lemmas"] = set()
    person_lemmas = _SUGGEST_CACHE["person_lemmas"]

    p_next = get_prefix_next(p_lower)

    # Range query on lemmas table unique index
    query = (
        session.query(Lemma.lemma, Lemma.df, Lemma.pos)
        .filter(Lemma.lemma >= p_lower)
        .filter(Lemma.lemma < p_next)
        .filter(Lemma.df.isnot(None))
        .filter(Lemma.df >= 3)
        .filter(
            or_(
                Lemma.pos.in_(["S", "H", "A", "Y"]),
                Lemma.pos.is_(None),
            )
        )
    )

    if total_speeches > 0:
        max_df = total_speeches * MAX_SUGGESTION_DF_RATIO
        query = query.filter(Lemma.df <= max_df)

    rows = query.all()

    valid_items = []
    stopwords = {w.casefold() for w in STOPWORDS}
    for lemma_text, df, pos in rows:
        lemma_cf = lemma_text.casefold()
        if lemma_cf in stopwords or lemma_cf in SUGGEST_EXCLUDE:
            continue
        if not any(c.isalpha() for c in lemma_text):
            continue
        # For NULL-pos lemmas, only keep if it is a known person name lemma
        if pos is None and lemma_text not in person_lemmas:
            continue
        valid_items.append((lemma_text, int(df)))

    # Order by df desc, then lemma asc
    valid_items.sort(key=lambda r: (-r[1], r[0]))
    top_items = valid_items[:clamped_limit]

    results = []
    for lemma_text, df in top_items:
        is_person = lemma_text in person_lemmas
        display_term = lemma_text.capitalize() if is_person else lemma_text
        results.append(
            {
                "term": display_term,
                "lemma": lemma_text,
                "df": df,
                "is_person": is_person,
            }
        )

    _SUGGEST_CACHE["prefixes"][cache_key] = results
    if len(_SUGGEST_CACHE["prefixes"]) > _CACHE_MAX_SIZE:
        _SUGGEST_CACHE["prefixes"].popitem(last=False)

    return results
