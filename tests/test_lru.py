"""Tests for the size-bounded cache dict."""

import threading

from src.api.lru import MISSING, LRUDict


def test_lru_dict_evicts_least_recently_used():
    cache = LRUDict(2)
    cache["a"] = 1
    cache["b"] = 2
    assert cache.get("a") == 1  # "a" is now the most recently used
    cache["c"] = 3
    assert list(cache) == ["a", "c"]
    assert cache.get("b", MISSING) is MISSING


def test_lru_dict_keeps_none_values_distinct_from_missing():
    cache = LRUDict(4)
    cache["unknown-lemma"] = None
    assert cache.get("unknown-lemma", MISSING) is None
    assert cache.get("other", MISSING) is MISSING


def test_lru_dict_concurrent_access_stays_bounded():
    cache = LRUDict(50)
    errors = []

    def worker(offset):
        try:
            for i in range(2_000):
                cache[(offset, i)] = i
                cache.get((offset, i - 1), MISSING)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(cache) <= 50


def test_request_keyed_api_caches_are_bounded():
    from src.api.alignment import _ALIGNMENT_CACHE
    from src.api.search import _ACTIVITY_DENOMINATOR_CACHE, _EXPANSION_CACHE
    from src.api.votings import _VOTE_PARTICIPATION_CACHE

    caches = [
        _EXPANSION_CACHE["expansions"],
        _EXPANSION_CACHE["lemma_ids"],
        _ACTIVITY_DENOMINATOR_CACHE["denominators"],
        _VOTE_PARTICIPATION_CACHE["members"],
        _VOTE_PARTICIPATION_CACHE["factions"],
        _ALIGNMENT_CACHE["persons"],
    ]
    for cache in caches:
        assert isinstance(cache, LRUDict)
        assert 0 < cache.maxsize <= 50_000
