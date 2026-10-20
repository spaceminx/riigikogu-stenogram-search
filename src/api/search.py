import functools
import itertools
import logging
import math
import re
import time
from datetime import datetime, timedelta

from estnltk import Text
from estnltk.vabamorf.morf import Vabamorf
from fastapi import HTTPException
from sqlalchemy import and_, func, literal, or_, select

from config import MEMBERSHIP_DATES, STOPWORDS
from src.load.database import SessionLocal
from src.load.models import (
    AgendaItem,
    Lemma,
    LemmaLink,
    Person,
    Speech,
    SpeechTerm,
    SystemMeta,
)
from src.transform.lemmatizer import lemmatize_text

logger = logging.getLogger(__name__)

_C0_CONTROL_REGEX = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HYPHEN_NUM_REGEX = re.compile(r"^([a-zA-Z0-9äöüõÄÖÜÕšžŠŽ]+)-(\d+)$")
_CLEAN_LEMMA_CHARS = ".,;:!?\"'()[]{}«»`~^/*+=<>@#$%&|\\_"

_UNSET = object()


def _get_last_sync_at(session) -> str | None:
    try:
        row = session.query(SystemMeta).filter_by(key="last_sync_at").first()
        return row.value if row else None
    except Exception:
        return None


_EXPANSION_CACHE: dict = {
    "last_sync_at": _UNSET,
    "expansions": {},
    "lemma_ids": {},
    "person_lemmas": None,
}


def clear_expansion_cache() -> None:
    """Clear cached lemma expansions and person lemmas."""
    _EXPANSION_CACHE["last_sync_at"] = _UNSET
    _EXPANSION_CACHE["expansions"].clear()
    _EXPANSION_CACHE["lemma_ids"].clear()
    _EXPANSION_CACHE["person_lemmas"] = None


def _check_and_update_expansion_sync(session) -> None:
    last_sync = _get_last_sync_at(session)
    if _EXPANSION_CACHE["last_sync_at"] != last_sync:
        _EXPANSION_CACHE["last_sync_at"] = last_sync
        _EXPANSION_CACHE["expansions"].clear()
        _EXPANSION_CACHE["lemma_ids"].clear()
        _EXPANSION_CACHE["person_lemmas"] = None


def _get_person_lemmas_cached(session) -> set[str]:
    _check_and_update_expansion_sync(session)
    if _EXPANSION_CACHE["person_lemmas"] is None:
        try:
            from src.transform.lemma_links import get_person_lemmas

            conn = session.connection() if session else None
            _EXPANSION_CACHE["person_lemmas"] = get_person_lemmas(conn=conn)
        except Exception as e:
            logger.warning("Failed to load person lemmas for search expansion: %s", e)
            _EXPANSION_CACHE["person_lemmas"] = set()
    return _EXPANSION_CACHE["person_lemmas"]


def _get_lemma_id_cached(session, lemma_str: str) -> int | None:
    _check_and_update_expansion_sync(session)
    if lemma_str in _EXPANSION_CACHE["lemma_ids"]:
        return _EXPANSION_CACHE["lemma_ids"][lemma_str]
    row = session.query(Lemma.id).filter(Lemma.lemma == lemma_str).first()
    lem_id = row[0] if row else None
    _EXPANSION_CACHE["lemma_ids"][lemma_str] = lem_id
    return lem_id


def _get_lemma_expansions_cached(session, target_lemma_id: int) -> dict[str, list[str]]:
    _check_and_update_expansion_sync(session)
    if target_lemma_id in _EXPANSION_CACHE["expansions"]:
        return _EXPANSION_CACHE["expansions"][target_lemma_id]

    rows = (
        session.query(Lemma.lemma, LemmaLink.kind)
        .join(LemmaLink, LemmaLink.lemma_id == Lemma.id)
        .filter(LemmaLink.target_lemma_id == target_lemma_id)
        .all()
    )
    by_kind: dict[str, list[str]] = {"compound_head": [], "name_form": [], "alias": []}
    for lem_str, kind in rows:
        if kind in by_kind:
            by_kind[kind].append(lem_str)
        else:
            by_kind[kind] = [lem_str]

    _EXPANSION_CACHE["expansions"][target_lemma_id] = by_kind
    return by_kind


def expand_lemma(session, base_lemma: str, allow_compound_head: bool = True) -> set[str]:
    """Expand a base lemma with linked compound heads, name forms, and aliases."""
    expanded = {base_lemma}
    if not session:
        return expanded
    target_id = _get_lemma_id_cached(session, base_lemma)
    if not target_id:
        return expanded
    by_kind = _get_lemma_expansions_cached(session, target_id)
    if allow_compound_head:
        for lem in by_kind.get("compound_head", []):
            expanded.add(lem)
    for lem in by_kind.get("name_form", []):
        expanded.add(lem)
    for lem in by_kind.get("alias", []):
        expanded.add(lem)
    return expanded


class QueryPhrase:
    """Represents a quoted search phrase with ordered positions of lemma alternatives."""

    def __init__(self, positions: list[set[str]], pattern: str):
        self.positions = positions  # list of lemma sets per word position
        self.pattern = pattern

    def __repr__(self) -> str:
        return f"QueryPhrase(positions={self.positions!r}, pattern={self.pattern!r})"


class QueryGroup(list):
    """Represents a comma-separated query group containing terms and phrases.

    Inherits from list so that iterating over or indexing the group yields its
    candidate terms (list[list[str]]), maintaining full backwards compatibility.
    """

    def __init__(
        self,
        terms: list[list[str]],
        phrases: list[QueryPhrase] | None = None,
        unquoted_terms: list[list[str]] | None = None,
    ):
        super().__init__(terms)
        self.terms = terms
        self.phrases = phrases or []
        self.unquoted_terms = unquoted_terms or []

    def __repr__(self) -> str:
        return (
            f"QueryGroup(terms={self.terms!r}, phrases={self.phrases!r},"
            f" unquoted_terms={self.unquoted_terms!r})"
        )


def _clean_lemma(lemma: str) -> str:
    cleaned = lemma.strip(_CLEAN_LEMMA_CHARS)
    return cleaned.lower() if any(c.isalnum() for c in cleaned) else ""


class LemmatizerUnavailableError(Exception):
    """Raised when lemmatizer is unavailable or returns None during search."""


def sanitize_query(query: str | None) -> str | None:
    """Sanitize user query string by stripping C0 control characters."""
    if query is None:
        return None
    cleaned = _C0_CONTROL_REGEX.sub("", query)
    if query.strip() and not cleaned.strip():
        raise HTTPException(status_code=400, detail="Vigane otsingupäring.")
    return cleaned


def check_query_complexity(query: str) -> None:
    """Check query nesting depth to prevent excessive recursion or stack exhaustion."""
    depth = 0
    max_d = 0
    for ch in query:
        if ch == "(":
            depth += 1
            if depth > max_d:
                max_d = depth
        elif ch == ")":
            depth = max(0, depth - 1)
    if max_d > 10:
        raise ValueError("Päring on liiga keeruline.")


_WORD_REGEX = re.compile(r"\b[a-zA-ZäöüõÄÖÜÕšžŠŽ0-9\-]+\b")
_VABAMORF = Vabamorf.instance()


def normalize_source_url(url: str | None) -> str | None:
    """Ensure Riigikogu stenogram URLs include the required language prefix /et/."""
    if not url:
        return url
    return re.sub(
        r"^https?://stenogrammid\.riigikogu\.ee/(?!et/|en/|ru/)(\d{12})(.*)$",
        r"https://stenogrammid.riigikogu.ee/et/\1\2",
        url,
    )


@functools.lru_cache(maxsize=50_000)
def _analyze_token_lemmas(token: str) -> frozenset[str]:
    """Return normalized base lemmas for a single word token using morphological analysis."""
    lemmas: set[str] = set()
    try:
        analyses = _VABAMORF.analyze([token], disambiguate=False, guess=True, propername=True)
        for item in analyses:
            for a in item.get("analysis", []):
                lemma = a.get("lemma", "")
                if lemma:
                    clean = _clean_lemma(lemma)
                    if clean:
                        lemmas.add(clean)

        if any(c.isupper() for c in token):
            lower_token = token.lower()
            lower_analyses = _VABAMORF.analyze(
                [lower_token], disambiguate=False, guess=True, propername=True
            )
            for item in lower_analyses:
                for a in item.get("analysis", []):
                    lemma = a.get("lemma", "")
                    if lemma:
                        clean = _clean_lemma(lemma)
                        if clean:
                            lemmas.add(clean)
    except Exception:
        pass
    return frozenset(lemmas)


def extract_matched_words(
    text: str,
    target_lemmas: set[str],
    phrases: list[QueryPhrase] | None = None,
    unquoted_lemmas: set[str] | None = None,
) -> list[str]:
    """Extract surface word tokens or phrase substrings from text matching target lemmas."""
    if not text:
        return []
    if not target_lemmas and not phrases:
        return []
    try:
        token_matches = list(_WORD_REGEX.finditer(text))
        if not token_matches:
            return []

        matched: set[str] = set()

        if phrases:
            # 1. Match phrases by walking token sequences in order with their spans
            for phrase in phrases:
                k = len(phrase.positions)
                if k == 0 or len(token_matches) < k:
                    continue
                for i in range(len(token_matches) - k + 1):
                    match = True
                    for j in range(k):
                        tok = token_matches[i + j].group(0)
                        lemmas = _analyze_token_lemmas(tok)
                        if not (lemmas & phrase.positions[j]):
                            match = False
                            break
                    if match:
                        start_pos = token_matches[i].start()
                        end_pos = token_matches[i + k - 1].end()
                        matched.add(text[start_pos:end_pos])

            # 2. Match non-phrase terms with word-level behavior
            word_target = (
                unquoted_lemmas
                if unquoted_lemmas is not None
                else (target_lemmas - {lem for p in phrases for pos in p.positions for lem in pos})
            )
            if word_target:
                for tm in token_matches:
                    tok = tm.group(0)
                    if _analyze_token_lemmas(tok) & word_target:
                        matched.add(tok)
        else:
            for tm in token_matches:
                tok = tm.group(0)
                if _analyze_token_lemmas(tok) & target_lemmas:
                    matched.add(tok)

        return sorted(matched, key=lambda s: (-len(s), s))
    except Exception:
        return []


def week_key_to_monday(key: str):
    """Convert a %Y-%W week string to the Monday date of that week. Handles week 00 edge case."""
    try:
        return datetime.strptime(f"{key}-1", "%Y-%W-%w").date()
    except ValueError:
        parts = key.split("-")
        year = int(parts[0])
        week = int(parts[1]) if len(parts) > 1 else 0
        if week == 0:
            return datetime(year, 1, 1).date()
        return (datetime(year, 1, 1) + timedelta(weeks=week)).date()


def fill_missing_periods(
    results: list,
    interval: str,
    label: str,
    denominators: dict[str, int] | None = None,
) -> list[dict]:
    """Fill gaps in timeline results with zero-count intervals."""
    if not results:
        return []

    data = {period: int(count) for period, count in results}

    periods = list(data.keys())

    if interval == "monthly":
        start = datetime.strptime(periods[0], "%Y-%m")
        end = datetime.strptime(periods[-1], "%Y-%m")

        filled = []
        current = start
        while current <= end:
            period = current.strftime("%Y-%m")
            cnt = data.get(period, 0)
            item = {label: period, "count": cnt}
            if denominators is not None:
                tot = denominators.get(period, 0)
                sh = round(cnt / tot, 4) if tot > 0 else None
                item["total"] = tot
                item["share"] = sh
            filled.append(item)
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
        return filled

    if interval in ("weekly", "week"):
        monday_counts: dict[str, int] = {}
        original_keys: dict[str, str] = {}
        for period, count in results:
            m = week_key_to_monday(period).isoformat()
            monday_counts[m] = monday_counts.get(m, 0) + int(count)
            if m not in original_keys or period != f"{int(period[:4])}-00":
                original_keys[m] = period

        first_monday = week_key_to_monday(periods[0])
        last_monday = week_key_to_monday(periods[-1])
        filled = []
        current = first_monday
        while current <= last_monday:
            m_str = current.isoformat()
            week_key = original_keys.get(m_str, current.strftime("%Y-%W"))
            cnt = monday_counts.get(m_str, 0)
            item = {
                label: week_key,
                "week_start": m_str,
                "count": cnt,
            }
            if denominators is not None:
                tot = denominators.get(m_str, 0)
                sh = round(cnt / tot, 4) if tot > 0 else None
                item["total"] = tot
                item["share"] = sh
            filled.append(item)
            current += timedelta(days=7)
        return filled

    if interval == "daily":
        start = datetime.strptime(periods[0], "%Y-%m-%d")
        end = datetime.strptime(periods[-1], "%Y-%m-%d")

        filled = []
        current = start
        while current <= end:
            period = current.strftime("%Y-%m-%d")
            cnt = data.get(period, 0)
            item = {label: period, "count": cnt}
            if denominators is not None:
                tot = denominators.get(period, 0)
                sh = round(cnt / tot, 4) if tot > 0 else None
                item["total"] = tot
                item["share"] = sh
            filled.append(item)
            current += timedelta(days=1)
        return filled

    if label == "week":
        out = []
        for period, count in results:
            m_str = week_key_to_monday(period).isoformat()
            cnt = int(count)
            item = {label: period, "week_start": m_str, "count": cnt}
            if denominators is not None:
                tot = denominators.get(m_str, 0)
                sh = round(cnt / tot, 4) if tot > 0 else None
                item["total"] = tot
                item["share"] = sh
            out.append(item)
        return out

    out = []
    for period, count in results:
        cnt = int(count)
        item = {label: period, "count": cnt}
        if denominators is not None:
            tot = denominators.get(period, 0)
            sh = round(cnt / tot, 4) if tot > 0 else None
            item["total"] = tot
            item["share"] = sh
        out.append(item)
    return out


def _extract_positions_with_tokens(text_str: str) -> list[tuple[str, set[str]]]:
    """Lemmatise text into an ordered list of (token_text, alternative_lemmas_set)."""
    if not text_str.strip():
        return []
    if lemmatize_text(text_str) is None:
        raise LemmatizerUnavailableError("Otsingu keeletöötlus pole hetkel saadaval.")

    try:
        est_text = Text(f"{text_str} .")
        est_text.tag_layer()
    except Exception as e:
        logger.error("Lemmatization failed on %r: %s", text_str[:100], e)
        raise LemmatizerUnavailableError("Otsingu keeletöötlus pole hetkel saadaval.") from e

    words1 = [w for w in est_text.words if w.text != "." and any(c.isalnum() for c in w.text)]
    if not words1:
        return []

    alternatives_list: list[set[str]] = []
    for w in words1:
        base_lemma = _clean_lemma(w.lemma[0])
        alternatives_list.append({base_lemma} if base_lemma else set())

    # Samm 2 (suurtäht): kui sõna oli algselt väiketäheline, lemmatiseeri ka suurtähelisena (capitalize).
    if any(any(c.islower() for c in w.text) for w in words1):
        try:
            cap_str = " ".join(w.text.capitalize() for w in words1)
            cap_text = Text(f"{cap_str} .")
            cap_text.tag_layer()
            words_cap = [
                w for w in cap_text.words if w.text != "." and any(c.isalnum() for c in w.text)
            ]
            if len(words_cap) == len(words1):
                for i in range(len(words1)):
                    l_cap = _clean_lemma(words_cap[i].lemma[0])
                    if l_cap:
                        alternatives_list[i].add(l_cap)
        except Exception:
            pass

    # Kui sõna oli suurtäheline, lemmatiseeri ka väiketähelisena
    if any(any(c.isupper() for c in w.text) for w in words1):
        try:
            lower_str = " ".join(w.text.lower() for w in words1)
            lower_text = Text(f"{lower_str} .")
            lower_text.tag_layer()
            words_lower = [
                w for w in lower_text.words if w.text != "." and any(c.isalnum() for c in w.text)
            ]
            if len(words_lower) == len(words1):
                for i in range(len(words1)):
                    l_lower = _clean_lemma(words_lower[i].lemma[0])
                    if l_lower:
                        alternatives_list[i].add(l_lower)
        except Exception:
            pass

    # Samm 3 (sidekriipsuga numbrid): kui sõna sisaldab sidekriipsu ja numbrit (nt "COVID-19"),
    # lisa alternatiiviks ka eesosa ("covid", lemmatiseerituna "covid", "cov").
    for i, w in enumerate(words1):
        m = _HYPHEN_NUM_REGEX.match(w.text)
        if m:
            prefix = m.group(1)
            if prefix.lower():
                alternatives_list[i].add(prefix.lower())
            try:
                t_pre = Text(f"{prefix} .")
                t_pre.tag_layer()
                for pw in t_pre.words:
                    if pw.text != ".":
                        for pl in pw.lemma:
                            clean_pl = _clean_lemma(pl)
                            if clean_pl:
                                alternatives_list[i].add(clean_pl)
            except Exception:
                pass

    return [(words1[i].text, alternatives_list[i]) for i in range(len(words1))]


def _extract_positions_with_alternatives(text_str: str) -> list[set[str]]:
    """Lemmatise text into an ordered list of positions, each with a set of alternative lemmas."""
    return [alts for _tok, alts in _extract_positions_with_tokens(text_str)]


def _build_phrase_pattern(positions: list[set[str]]) -> str:
    """Build a regex pattern for SQLite phrase matching: (?:^| )(alt|alt) (alt) ...(?: |$)."""
    parts = []
    for pos in positions:
        alts = sorted(re.escape(lem) for lem in pos if lem)
        if not alts:
            continue
        parts.append(f"({'|'.join(alts)})")
    if not parts:
        return ""
    return f"(?:^| ){' '.join(parts)}(?: |$)"


def build_phrase_filter_clause(phrase: QueryPhrase, text_col=Speech.text_lemmas):
    """Build SQL filter condition for a phrase using instr() fast path or phrase_match regex fallback.

    When the product of alternatives across phrase positions is <= 16, build the condition as:
    OR(instr(' ' || text_lemmas || ' ', ' alt1 alt2 … ') > 0) over all combinations,
    and fall back to phrase_match only above that limit.
    """
    product = math.prod(len(pos) for pos in phrase.positions)
    if product <= 16:
        combos = list(itertools.product(*[sorted(pos) for pos in phrase.positions]))
        haystack = literal(" ").concat(text_col).concat(literal(" "))
        instr_conds = [func.instr(haystack, f" {' '.join(c)} ") > 0 for c in combos]
        return or_(*instr_conds) if len(instr_conds) > 1 else instr_conds[0]
    return func.phrase_match(text_col, phrase.pattern)


def _split_group_phrases_and_words(group_str: str) -> tuple[list[str], str]:
    """Split a comma group into quoted phrase strings and unquoted remainder.

    An unmatched quote is ignored (treated as no quotes).
    """
    if group_str.count('"') % 2 != 0:
        return [], group_str.replace('"', " ")

    phrases: list[str] = []

    def _repl(m: re.Match) -> str:
        content = m.group(1).strip()
        if content:
            phrases.append(content)
        return " "

    unquoted = re.sub(r'"([^"]*)"', _repl, group_str)
    return phrases, unquoted


def _parse_single_group(
    group_str: str,
    expand: bool = True,
    session=None,
) -> QueryGroup | None:
    """Parse a single comma group into QueryGroup containing phrases and terms."""
    phrase_strs, unquoted_str = _split_group_phrases_and_words(group_str)

    phrases: list[QueryPhrase] = []
    phrase_candidate_terms: list[list[str]] = []
    total_positions = 0

    person_lemmas = _get_person_lemmas_cached(session) if (session and expand) else set()

    for p_str in phrase_strs:
        positions = _extract_positions_with_alternatives(p_str)
        if not positions:
            continue
        total_positions += len(positions)

        # Check if phrase contains only stopwords
        is_all_stopwords = all(
            all(lemma in STOPWORDS for lemma in pos if lemma) for pos in positions
        )
        if is_all_stopwords:
            raise ValueError("Fraas koosneb ainult stoppsõnadest.")

        # Multi-word phrase expansion: expand name_form and alias per position (no compound_head)
        # Note: 1-word quoted strings (len(positions) == 1) are quoted in q and get NO expansion.
        if expand and session and len(positions) >= 2:
            expanded_positions: list[set[str]] = []
            for pos in positions:
                expanded_pos = set(pos)
                for lem in pos:
                    if lem:
                        expanded_pos.update(expand_lemma(session, lem, allow_compound_head=False))
                expanded_positions.append(expanded_pos)
            positions = expanded_positions

        pattern = _build_phrase_pattern(positions)
        phrases.append(QueryPhrase(positions=positions, pattern=pattern))

        # Candidate filtering: non-stopword positions of the phrase as normal AND terms
        for pos in positions:
            non_stop = [lem for lem in pos if lem not in STOPWORDS]
            if non_stop:
                phrase_candidate_terms.append(sorted(non_stop))

    unquoted_terms: list[list[str]] = []
    if unquoted_str.strip():
        u_tokens_and_alts = _extract_positions_with_tokens(unquoted_str)
        for tok, alts in u_tokens_and_alts:
            is_cap = any(c.isupper() for c in tok)
            expanded_alts = set(alts)
            if expand and session:
                for lem in alts:
                    if not lem:
                        continue
                    # Rule B: skip compound_head expansion only when query term is capitalised
                    # in user's query AND its lemma is a first/last name lemma from persons.
                    allow_compound_head = not (is_cap and lem in person_lemmas)
                    expanded_alts.update(
                        expand_lemma(session, lem, allow_compound_head=allow_compound_head)
                    )

            non_stop = [lem for lem in expanded_alts if lem not in STOPWORDS]
            if non_stop:
                unquoted_terms.append(sorted(non_stop))
                total_positions += 1

    if total_positions > 10:
        raise ValueError("Liiga palju sõnu ühes rühmas: lubatud kuni 10 sisusõna.")

    combined_terms: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for term in phrase_candidate_terms + unquoted_terms:
        t = tuple(term)
        if t not in seen:
            seen.add(t)
            combined_terms.append(term)

    if not combined_terms and not phrases:
        return None

    return QueryGroup(terms=combined_terms, phrases=phrases, unquoted_terms=unquoted_terms)


def _extract_group_terms(group: str) -> tuple[bool, list[list[str]]]:
    """Extract content terms from a query group with case and hyphen expansions.

    Returns (has_any_words, content_terms) where content_terms is a list of positions,
    and each position contains a list of alternative lemmas.
    """
    alternatives_list = _extract_positions_with_alternatives(group)
    if not alternatives_list:
        return (False, [])

    content_terms: list[list[str]] = []
    seen_terms: set[tuple[str, ...]] = set()
    for alts in alternatives_list:
        filtered = [lemma for lemma in alts if lemma not in STOPWORDS]
        if filtered:
            term_tuple = tuple(sorted(filtered))
            if term_tuple not in seen_terms:
                seen_terms.add(term_tuple)
                content_terms.append(list(term_tuple))

    return (True, content_terms)


MAX_QUERY_GROUPS = 10


def split_query_groups(query: str) -> list[str]:
    """Split query string by commas outside double quotes.

    If the query has an odd number of quotes (unmatched quote),
    quotes are ignored and splitting happens at all commas.
    """
    if not query or not query.strip():
        return []
    s = query.strip()
    respect_quotes = s.count('"') % 2 == 0

    groups: list[str] = []
    current: list[str] = []
    in_quotes = False

    for ch in s:
        if ch == '"' and respect_quotes:
            in_quotes = not in_quotes
            current.append(ch)
        elif ch == "," and not in_quotes:
            part = "".join(current).strip()
            if part:
                groups.append(part)
            current = []
        else:
            current.append(ch)

    part = "".join(current).strip()
    if part:
        groups.append(part)

    return groups


def is_only_stopwords(query: str) -> bool:
    """Check if query contains non-empty words but all of them are in STOPWORDS."""
    check_query_complexity(query)
    raw_groups = split_query_groups(query)
    if len(raw_groups) > MAX_QUERY_GROUPS:
        raise ValueError("Liiga palju otsingurühmi: lubatud kuni 10 komaga eraldatud rühma.")
    has_any_words = False
    for group in raw_groups:
        phrase_strs, unquoted_str = _split_group_phrases_and_words(group)
        for p in phrase_strs:
            if p.strip():
                has_any_words = True
        if unquoted_str.strip():
            u_pos = _extract_positions_with_alternatives(unquoted_str)
            if u_pos:
                has_any_words = True
        qg = _parse_single_group(group, expand=False)
        if qg is not None:
            return False
    return has_any_words


def parse_query_groups(
    query: str,
    expand: bool = True,
    session=None,
) -> list[QueryGroup]:
    """Parse comma-separated OR groups and space-separated AND keywords/phrases into filtered lemma alternatives."""
    check_query_complexity(query)
    groups = []
    raw_groups = split_query_groups(query)
    if len(raw_groups) > MAX_QUERY_GROUPS:
        raise ValueError("Liiga palju otsingurühmi: lubatud kuni 10 komaga eraldatud rühma.")

    close_session_at_end = False
    if expand and session is None:
        session = SessionLocal()
        close_session_at_end = True

    try:
        for group in raw_groups:
            qg = _parse_single_group(group, expand=expand, session=session)
            if qg:
                groups.append(qg)
        return groups
    finally:
        if close_session_at_end:
            session.close()


def build_matching_speech_ids_query(session, groups: list):
    """Build a SQL subquery returning distinct speech IDs matching query lemma groups."""
    group_queries = []

    for group in groups:
        term_queries = []
        terms = getattr(group, "terms", group)
        for term_alts in terms:
            tq = (
                session.query(SpeechTerm.speech_id.label("speech_id"))
                .join(Lemma, SpeechTerm.lemma_id == Lemma.id)
                .filter(Lemma.lemma.in_(term_alts))
            )
            term_queries.append(tq)

        if not term_queries:
            continue
        if len(term_queries) == 1:
            gq = term_queries[0].distinct()
        else:
            gq = term_queries[0].intersect(*term_queries[1:])
        group_queries.append(gq)

    if not group_queries:
        return session.query(Speech.id.label("speech_id")).filter(False).subquery()

    if len(group_queries) == 1:
        return group_queries[0].subquery()

    union_query = group_queries[0].union(*group_queries[1:])
    return union_query.subquery()


def build_matching_conditions(session, groups: list) -> list:
    """Build SQL filter conditions for speech IDs matching each lemma group."""
    has_phrases = any(bool(getattr(g, "phrases", None)) for g in groups)
    if not has_phrases:
        matched_subquery = build_matching_speech_ids_query(session, groups)
        col = list(matched_subquery.c)[0]
        return [Speech.id.in_(select(col))]

    group_conditions = []
    for group in groups:
        terms = getattr(group, "terms", group)
        term_queries = []
        for term_alts in terms:
            tq = (
                session.query(SpeechTerm.speech_id.label("speech_id"))
                .join(Lemma, SpeechTerm.lemma_id == Lemma.id)
                .filter(Lemma.lemma.in_(term_alts))
            )
            term_queries.append(tq)

        conds = []
        if term_queries:
            if len(term_queries) == 1:
                gq = term_queries[0].distinct()
            else:
                gq = term_queries[0].intersect(*term_queries[1:])
            subq = gq.subquery()
            cand_col = list(subq.c)[0]
            conds.append(Speech.id.in_(select(cand_col)))

        for p in getattr(group, "phrases", []):
            conds.append(build_phrase_filter_clause(p, Speech.text_lemmas))

        if conds:
            if len(conds) == 1:
                group_conditions.append(conds[0])
            else:
                group_conditions.append(and_(*conds))

    if not group_conditions:
        return [Speech.id.in_(select(Speech.id).filter(False))]

    return group_conditions


CHAIR_ROLES = ("Esimees", "Aseesimees")
SPEECH_TYPE_CATEGORIES = {
    "speeches": ["SPEECH", "SPEECH_CONTINUE"],
    "questions": ["SMALL_SPEECH"],
    "procedural": ["PROCEDURAL"],
}


def build_speech_filters(
    membership: str = "all",
    faction: str | None = None,
    speaker: str | None = None,
    speaker_uuid: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    exclude_chair: bool = False,
    speech_category: str | None = None,
) -> list:
    """Build list of SQLAlchemy filter clauses for Speech table."""
    filters = []

    if membership and membership != "all":
        if membership not in MEMBERSHIP_DATES:
            raise ValueError("Tundmatu koosseis")
        start_bound, end_bound = MEMBERSHIP_DATES[membership]
        filters.append(Speech.date >= start_bound)
        filters.append(Speech.date <= end_bound)

    if faction:
        filters.append(Speech.speaker_faction == faction)

    if speaker and speaker.strip():
        filters.append(Speech.speaker.ilike(f"%{speaker.strip()}%"))

    if speaker_uuid and speaker_uuid.strip():
        filters.append(Speech.speaker_uuid == speaker_uuid.strip())

    if start_date:
        filters.append(Speech.date >= start_date)

    if end_date:
        filters.append(Speech.date <= end_date)

    if exclude_chair:
        filters.append(or_(Speech.speaker_role.is_(None), Speech.speaker_role.notin_(CHAIR_ROLES)))

    if speech_category and speech_category in SPEECH_TYPE_CATEGORIES:
        filters.append(Speech.speech_type.in_(SPEECH_TYPE_CATEGORIES[speech_category]))

    return filters


def search_by_keyword(
    query: str,
    limit: int = 50,
    offset: int = 0,
    membership: str = "all",
    faction: str | None = None,
    speaker: str | None = None,
    speaker_uuid: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    sort_by: str = "date_desc",
    include_matched_words: bool = True,
    exclude_chair: bool = False,
    speech_category: str | None = None,
    expand: bool = True,
) -> tuple[list[dict], int]:
    """Search speeches by keyword query with lemma matching, filters, and frequency scoring."""
    if is_only_stopwords(query):
        raise ValueError(
            "Otsingupäring on liiga üldine (sisaldab ainult stopsõnu). Palun sisesta täpsem märksõna."
        )

    if start_date and end_date and start_date > end_date:
        raise ValueError("Alguskuupäev ei saa olla hilisem kui lõppkuupäev.")

    session = SessionLocal()

    try:
        groups = parse_query_groups(query, expand=expand, session=session)

        if not groups:
            return [], 0

        matching_conditions = build_matching_conditions(session, groups)
        speech_filters = build_speech_filters(
            membership=membership,
            faction=faction,
            speaker=speaker,
            speaker_uuid=speaker_uuid,
            start_date=start_date,
            end_date=end_date,
            exclude_chair=exclude_chair,
            speech_category=speech_category,
        )

        all_lemmas = [lemma for group in groups for term in group for lemma in term]

        if sort_by == "match_count_desc":
            base_query = (
                session.query(Speech, func.sum(SpeechTerm.count).label("match_count"))
                .join(SpeechTerm, Speech.id == SpeechTerm.speech_id)
                .join(Lemma, SpeechTerm.lemma_id == Lemma.id)
                .filter(or_(*matching_conditions))
                .filter(Lemma.lemma.in_(all_lemmas))
            )
            if speech_filters:
                base_query = base_query.filter(*speech_filters)

            grouped_query = base_query.group_by(Speech.id)
            ordered_query = grouped_query.order_by(
                func.sum(SpeechTerm.count).desc(), Speech.date.desc(), Speech.id.desc()
            )
            results = ordered_query.offset(offset).limit(limit).all()
        else:
            base_query = session.query(Speech.id).filter(or_(*matching_conditions))
            if speech_filters:
                base_query = base_query.filter(*speech_filters)

            if sort_by == "date_asc":
                ordered_query = base_query.order_by(Speech.date.asc(), Speech.id.asc())
            else:
                ordered_query = base_query.order_by(Speech.date.desc(), Speech.id.desc())

            matching_speech_ids = [r[0] for r in ordered_query.offset(offset).limit(limit).all()]

            if matching_speech_ids:
                speeches_by_id = {
                    s.id: s
                    for s in session.query(Speech).filter(Speech.id.in_(matching_speech_ids)).all()
                }
                match_counts = dict(
                    session.query(SpeechTerm.speech_id, func.sum(SpeechTerm.count))
                    .join(Lemma, SpeechTerm.lemma_id == Lemma.id)
                    .filter(SpeechTerm.speech_id.in_(matching_speech_ids))
                    .filter(Lemma.lemma.in_(all_lemmas))
                    .group_by(SpeechTerm.speech_id)
                    .all()
                )
                results = [
                    (speeches_by_id[s_id], match_counts.get(s_id, 0))
                    for s_id in matching_speech_ids
                    if s_id in speeches_by_id
                ]
            else:
                results = []

        has_phrases = any(bool(getattr(g, "phrases", None)) for g in groups)

        if not speech_filters and not has_phrases:
            if len(groups) == 1 and len(groups[0]) == 1 and len(groups[0][0]) == 1:
                total_count = (
                    session.query(func.count(SpeechTerm.speech_id))
                    .join(Lemma, SpeechTerm.lemma_id == Lemma.id)
                    .filter(Lemma.lemma == groups[0][0][0])
                    .scalar()
                    or 0
                )
            else:
                matched_subquery = build_matching_speech_ids_query(session, groups)
                total_count = (
                    session.query(func.count()).select_from(matched_subquery).scalar() or 0
                )
        else:
            count_query = session.query(Speech.id).filter(or_(*matching_conditions))
            if speech_filters:
                count_query = count_query.filter(*speech_filters)
            total_count = count_query.distinct().count()

        target_lemmas_set = set(all_lemmas) if include_matched_words else set()
        all_phrases = (
            [p for g in groups for p in getattr(g, "phrases", [])] if include_matched_words else []
        )
        unquoted_lemmas = (
            {lemma for g in groups for term in getattr(g, "unquoted_terms", []) for lemma in term}
            if include_matched_words
            else set()
        )
        output = []
        for speech, match_count in results:
            matched_words = (
                extract_matched_words(
                    speech.text,
                    target_lemmas_set,
                    phrases=all_phrases,
                    unquoted_lemmas=unquoted_lemmas,
                )
                if include_matched_words
                else []
            )
            output.append(
                {
                    "id": speech.id,
                    "speech_key": speech.speech_key,
                    "speaker": speech.speaker,
                    "speaker_role": speech.speaker_role,
                    "speaker_faction": speech.speaker_faction,
                    "speaker_uuid": speech.speaker_uuid,
                    "speech_type": speech.speech_type,
                    "external_id": speech.external_id,
                    "start_time": speech.start_time,
                    "end_time": speech.end_time,
                    "duration_seconds": speech.duration_seconds,
                    "text": speech.text,
                    "count": int(match_count),
                    "matched_words": matched_words,
                    "date": speech.date,
                    "time": speech.time,
                    "source_file": speech.source_file,
                    "source_url": normalize_source_url(speech.source_url),
                    "agenda_title": speech.agenda_title,
                    "video_url": speech.video_url,
                }
            )
        return output, total_count

    finally:
        session.close()


_ACTIVITY_DENOMINATOR_CACHE: dict = {
    "last_sync_at": _UNSET,
    "denominators": {},
}


def clear_activity_denominator_cache() -> None:
    """Clear in-memory cached activity denominator data."""
    _ACTIVITY_DENOMINATOR_CACHE["last_sync_at"] = _UNSET
    _ACTIVITY_DENOMINATOR_CACHE["denominators"].clear()


def get_activity_denominator(
    session,
    interval: str = "weekly",
    membership: str = "all",
    faction: str | None = None,
    speaker: str | None = None,
    speaker_uuid: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    exclude_chair: bool = False,
    speech_category: str | None = None,
) -> dict[str, int]:
    """Calculate and return denominator speech counts per period for the given speech filters."""
    last_sync = _get_last_sync_at(session)
    if _ACTIVITY_DENOMINATOR_CACHE["last_sync_at"] != last_sync:
        _ACTIVITY_DENOMINATOR_CACHE["last_sync_at"] = last_sync
        _ACTIVITY_DENOMINATOR_CACHE["denominators"].clear()

    cache_key = (
        interval,
        str(membership),
        faction,
        speaker.strip() if speaker else None,
        speaker_uuid.strip() if speaker_uuid else None,
        start_date,
        end_date,
        bool(exclude_chair),
        speech_category,
    )
    if cache_key in _ACTIVITY_DENOMINATOR_CACHE["denominators"]:
        return _ACTIVITY_DENOMINATOR_CACHE["denominators"][cache_key]

    if interval == "daily":
        date_group = Speech.date
    elif interval == "monthly":
        date_group = func.strftime("%Y-%m", Speech.date)
    else:
        date_group = func.strftime("%Y-%W", Speech.date)

    speech_filters = build_speech_filters(
        membership=membership,
        faction=faction,
        speaker=speaker,
        speaker_uuid=speaker_uuid,
        start_date=start_date,
        end_date=end_date,
        exclude_chair=exclude_chair,
        speech_category=speech_category,
    )
    query = session.query(date_group.label("period"), func.count(Speech.id).label("total_count"))
    if speech_filters:
        query = query.filter(*speech_filters)
    denom_results = query.group_by(date_group).all()

    if interval in ("weekly", "week"):
        denom_map: dict[str, int] = {}
        for period, count in denom_results:
            m = week_key_to_monday(period).isoformat()
            denom_map[m] = denom_map.get(m, 0) + int(count)
    else:
        denom_map = {period: int(count) for period, count in denom_results}

    _ACTIVITY_DENOMINATOR_CACHE["denominators"][cache_key] = denom_map
    return denom_map


def keyword_activity(
    query: str,
    interval: str = "weekly",
    membership: str = "all",
    faction: str | None = None,
    speaker: str | None = None,
    speaker_uuid: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    exclude_chair: bool = False,
    speech_category: str | None = None,
    expand: bool = True,
) -> list[dict]:
    """Calculate timeline frequency of keyword occurrences aggregated by day, week, or month with filters."""
    if is_only_stopwords(query):
        raise ValueError(
            "Otsingupäring on liiga üldine (sisaldab ainult stopsõnu). Palun sisesta täpsem märksõna."
        )

    if start_date and end_date and start_date > end_date:
        raise ValueError("Alguskuupäev ei saa olla hilisem kui lõppkuupäev.")

    session = SessionLocal()
    try:
        groups = parse_query_groups(query, expand=expand, session=session)
        if not groups:
            return []

        if interval == "daily":
            date_group = Speech.date
            label = "date"
        elif interval == "monthly":
            date_group = func.strftime("%Y-%m", Speech.date)
            label = "month"
        else:
            date_group = func.strftime("%Y-%W", Speech.date)
            label = "week"

        matching_conditions = build_matching_conditions(session, groups)
        speech_filters = build_speech_filters(
            membership=membership,
            faction=faction,
            speaker=speaker,
            speaker_uuid=speaker_uuid,
            start_date=start_date,
            end_date=end_date,
            exclude_chair=exclude_chair,
            speech_category=speech_category,
        )
        query_builder = session.query(
            date_group.label("period"), func.count(Speech.id).label("total_count")
        ).filter(or_(*matching_conditions))

        if speech_filters:
            query_builder = query_builder.filter(*speech_filters)

        results = query_builder.group_by(date_group).order_by(date_group).all()

        denom_map = get_activity_denominator(
            session=session,
            interval=interval,
            membership=membership,
            faction=faction,
            speaker=speaker,
            speaker_uuid=speaker_uuid,
            start_date=start_date,
            end_date=end_date,
            exclude_chair=exclude_chair,
            speech_category=speech_category,
        )

        if interval in ("monthly", "daily", "weekly", "week"):
            return fill_missing_periods(results, interval, label, denominators=denom_map)
        output = []
        for period, total_count in results:
            cnt = int(total_count)
            tot = denom_map.get(period, 0)
            sh = round(cnt / tot, 4) if tot > 0 else None
            output.append({label: period, "count": cnt, "total": tot, "share": sh})
        return output
    finally:
        session.close()


def get_plenary_session_dates() -> list[str]:
    """Return distinct dates represented by plenary-session transcripts in the archive."""
    session = SessionLocal()
    try:
        return [
            row.date
            for row in (session.query(Speech.date).distinct().order_by(Speech.date.desc()).all())
        ]
    finally:
        session.close()


def format_session_speech(
    speech: Speech,
    agenda_item_uuid: str | None = None,
    draft_uuid: str | None = None,
) -> dict:
    """Format a Speech model into standard session transcript response dictionary."""
    return {
        "id": speech.id,
        "speech_key": speech.speech_key,
        "speaker": speech.speaker,
        "speaker_role": speech.speaker_role,
        "speaker_faction": speech.speaker_faction,
        "speaker_uuid": speech.speaker_uuid,
        "speech_type": speech.speech_type,
        "external_id": speech.external_id,
        "start_time": speech.start_time,
        "end_time": speech.end_time,
        "duration_seconds": speech.duration_seconds,
        "text": speech.text,
        "count": 0,
        "matched_words": [],
        "date": speech.date,
        "time": speech.time,
        "source_file": speech.source_file,
        "source_url": normalize_source_url(speech.source_url),
        "agenda_title": speech.agenda_title,
        "video_url": speech.video_url,
        "agenda_item_uuid": agenda_item_uuid,
        "draft_uuid": draft_uuid,
    }


def get_session_speeches(session_date: str) -> list[dict]:
    """Return the transcript entries for one plenary date, ordered as spoken."""
    session = SessionLocal()
    try:
        results = (
            session.query(
                Speech,
                AgendaItem.agenda_item_uuid,
                AgendaItem.draft_uuid,
            )
            .outerjoin(
                AgendaItem,
                and_(
                    Speech.source_file == AgendaItem.source_file,
                    Speech.agenda_title == AgendaItem.steno_title,
                    Speech.agenda_title.isnot(None),
                ),
            )
            .filter(Speech.date == session_date)
            .order_by(Speech.source_file.asc(), Speech.start_time.asc(), Speech.id.asc())
            .all()
        )
        seen_speech_ids = set()
        speeches_list = []
        for speech, agenda_item_uuid, draft_uuid in results:
            if speech.id in seen_speech_ids:
                continue
            seen_speech_ids.add(speech.id)
            speeches_list.append(format_session_speech(speech, agenda_item_uuid, draft_uuid))
        return speeches_list
    finally:
        session.close()


_OVERVIEW_CACHE: dict = {"data": None, "timestamp": 0.0, "last_sync_at": None}
_OVERVIEW_CACHE_TTL: float = 3600.0


def get_dashboard_overview() -> dict:
    """Return archive-wide speakers and the latest plenary sessions."""
    session = SessionLocal()
    try:
        current_sync_at = None
        try:
            meta_row = session.query(SystemMeta).filter_by(key="last_sync_at").first()
            if meta_row:
                current_sync_at = meta_row.value
        except Exception:
            pass

        now = time.time()
        if (
            _OVERVIEW_CACHE["data"] is not None
            and _OVERVIEW_CACHE.get("last_sync_at") == current_sync_at
            and (now - _OVERVIEW_CACHE["timestamp"]) < _OVERVIEW_CACHE_TTL
        ):
            return _OVERVIEW_CACHE["data"]
        speaker_rows = (
            session.query(
                Speech.speaker_uuid,
                func.max(Person.full_name).label("full_name"),
                func.max(Speech.speaker).label("speaker_fallback"),
                func.count(Speech.id).label("speech_count"),
            )
            .outerjoin(Person, Speech.speaker_uuid == Person.uuid)
            .filter(
                Speech.speaker_uuid.isnot(None),
                Speech.speaker_role.is_(None),
            )
            .group_by(Speech.speaker_uuid)
            .order_by(
                func.count(Speech.id).desc(),
                func.coalesce(func.max(Person.full_name), func.max(Speech.speaker)).asc(),
            )
            .limit(4)
            .all()
        )

        speakers = []
        for s_uuid, full_name, speaker_fallback, speech_count in speaker_rows:
            latest_speech = (
                session.query(Speech.speaker_faction)
                .filter(
                    Speech.speaker_uuid == s_uuid,
                    Speech.speaker_faction.isnot(None),
                    Speech.speaker_faction != "",
                )
                .order_by(Speech.date.desc(), Speech.time.desc(), Speech.id.desc())
                .first()
            )
            speakers.append(
                {
                    "speaker": full_name or speaker_fallback,
                    "speaker_uuid": s_uuid,
                    "faction": latest_speech[0] if latest_speech else None,
                    "count": int(speech_count),
                }
            )

        # Fast lookup for top 3 recent sessions using date index
        recent_speeches = (
            session.query(Speech.source_file, Speech.date, Speech.source_url)
            .filter(Speech.source_file.isnot(None), Speech.source_file != "")
            .order_by(Speech.date.desc(), Speech.id.desc())
            .limit(1000)
            .all()
        )
        session_map: dict[str, dict] = {}
        for sp in recent_speeches:
            if sp.source_file not in session_map:
                session_map[sp.source_file] = {
                    "source_file": sp.source_file,
                    "date": sp.date,
                    "source_url": sp.source_url,
                }
                if len(session_map) == 3:
                    break

        source_files = list(session_map.keys())
        topics_by_source: dict[str, list[str]] = {source_file: [] for source_file in source_files}

        if source_files:
            total_speeches = session.query(func.count(Speech.id)).scalar() or 0
            topic_rows = (
                session.query(
                    Speech.source_file,
                    Lemma.lemma,
                    Lemma.df,
                    func.sum(SpeechTerm.count).label("occurrences"),
                )
                .join(SpeechTerm, Speech.id == SpeechTerm.speech_id)
                .join(Lemma, SpeechTerm.lemma_id == Lemma.id)
                .filter(Speech.source_file.in_(source_files))
                .group_by(Speech.source_file, Lemma.id, Lemma.lemma, Lemma.df)
                .all()
            )
            stopwords = {word.casefold() for word in STOPWORDS}
            candidates_by_source: dict[str, list[tuple[float, str]]] = {
                sf: [] for sf in source_files
            }
            for source_file, lemma, df, occurrences in topic_rows:
                normalized = lemma.casefold()
                if (
                    len(normalized) < 4
                    or normalized in stopwords
                    or df is None
                    or df < 3
                    or total_speeches <= 0
                    or df >= total_speeches
                ):
                    continue
                score = float(occurrences) * math.log(total_speeches / df)
                candidates_by_source[source_file].append((score, lemma))

            for source_file, candidates in candidates_by_source.items():
                candidates.sort(key=lambda item: (-item[0], item[1]))
                topics_by_source[source_file] = [lemma for _, lemma in candidates[:3]]

        sessions = [
            {
                "date": row["date"],
                "source_url": normalize_source_url(
                    row["source_url"].split("#")[0] if row["source_url"] else None
                ),
                "topics": topics_by_source.get(row["source_file"], []),
            }
            for row in session_map.values()
        ]

        # Monthly speech counts for past 24 months, excluding chair DIRECTOR
        current_dt = datetime.now()
        months = []
        cur_y = current_dt.year
        cur_m = current_dt.month
        for _ in range(24):
            months.append(f"{cur_y:04d}-{cur_m:02d}")
            cur_m -= 1
            if cur_m == 0:
                cur_m = 12
                cur_y -= 1
        months.reverse()

        month_col = func.strftime("%Y-%m", Speech.date)
        start_month = months[0]
        end_month = months[-1]

        activity_rows = (
            session.query(
                month_col.label("month"),
                func.count(Speech.id).label("count"),
            )
            .filter(
                Speech.date >= f"{start_month}-01",
                Speech.date <= f"{end_month}-31",
                or_(
                    Speech.speech_type.is_(None),
                    Speech.speech_type != "DIRECTOR",
                    Speech.speaker_role.is_(None),
                    ~Speech.speaker_role.in_(CHAIR_ROLES),
                ),
            )
            .group_by(month_col)
            .all()
        )
        counts_by_month = {row.month: int(row.count) for row in activity_rows}
        activity = [{"month": m, "count": counts_by_month.get(m, 0)} for m in months]

        result = {"speakers": speakers, "sessions": sessions, "activity": activity}
        _OVERVIEW_CACHE["data"] = result
        _OVERVIEW_CACHE["timestamp"] = now
        _OVERVIEW_CACHE["last_sync_at"] = current_sync_at
        return result
    finally:
        session.close()


def keyword_top_speakers(
    query: str,
    limit: int = 20,
    membership: str = "all",
    faction: str | None = None,
    speaker: str | None = None,
    speaker_uuid: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    exclude_chair: bool = False,
    speech_category: str | None = None,
    expand: bool = True,
) -> list[dict]:
    """Rank parliament members by mention count for a given keyword query with filters."""
    if is_only_stopwords(query):
        raise ValueError(
            "Otsingupäring on liiga üldine (sisaldab ainult stopsõnu). Palun sisesta täpsem märksõna."
        )

    if start_date and end_date and start_date > end_date:
        raise ValueError("Alguskuupäev ei saa olla hilisem kui lõppkuupäev.")

    session = SessionLocal()
    try:
        groups = parse_query_groups(query, expand=expand, session=session)
        if not groups:
            return []

        matching_conditions = build_matching_conditions(session, groups)
        speech_filters = build_speech_filters(
            membership=membership,
            faction=faction,
            speaker=speaker,
            speaker_uuid=speaker_uuid,
            start_date=start_date,
            end_date=end_date,
            exclude_chair=exclude_chair,
            speech_category=speech_category,
        )

        all_lemmas = [lemma for group in groups for term in group for lemma in term]
        group_expr = func.coalesce(Speech.speaker_uuid, Speech.speaker)

        query_builder = (
            session.query(
                func.max(Speech.speaker_uuid).label("speaker_uuid"),
                func.max(Speech.speaker).label("speaker_name"),
                func.max(Person.full_name).label("person_full_name"),
                func.sum(SpeechTerm.count).label("total_count"),
            )
            .outerjoin(Person, Speech.speaker_uuid == Person.uuid)
            .join(SpeechTerm, Speech.id == SpeechTerm.speech_id)
            .join(Lemma, SpeechTerm.lemma_id == Lemma.id)
            .filter(or_(*matching_conditions))
            .filter(Lemma.lemma.in_(all_lemmas))
        )

        if speech_filters:
            query_builder = query_builder.filter(*speech_filters)

        results = (
            query_builder.group_by(group_expr)
            .order_by(func.sum(SpeechTerm.count).desc())
            .limit(limit)
            .all()
        )

        output = [
            {
                "speaker": person_full_name or speaker_name,
                "speaker_uuid": s_uuid,
                "count": int(total_count),
            }
            for s_uuid, speaker_name, person_full_name, total_count in results
        ]
        return output
    finally:
        session.close()


def get_speech_context(
    speech_id: int,
    query: str | None = None,
    expand: bool = True,
) -> dict | None:
    """Retrieve full transcript context (all speeches in chronological order) for a given speech."""
    session = SessionLocal()
    try:
        parsed_groups = None
        if query and not is_only_stopwords(query):
            parsed_groups = parse_query_groups(query, expand=expand, session=session)
        target_speech = session.query(Speech).filter(Speech.id == speech_id).first()
        if not target_speech:
            return None

        speeches = (
            session.query(Speech)
            .filter(Speech.source_file == target_speech.source_file)
            .order_by(Speech.start_time.asc(), Speech.id.asc())
            .all()
        )

        target_lemmas: set[str] = set()
        matching_speech_ids: set[int] = set()
        all_phrases = (
            [p for g in parsed_groups for p in getattr(g, "phrases", [])] if parsed_groups else []
        )
        unquoted_lemmas = (
            {
                lemma
                for g in parsed_groups
                for term in getattr(g, "unquoted_terms", [])
                for lemma in term
            }
            if parsed_groups
            else set()
        )
        if parsed_groups and speeches:
            target_lemmas = {lemma for group in parsed_groups for term in group for lemma in term}
            if target_lemmas:
                speech_ids = [s.id for s in speeches]
                matching_conditions = build_matching_conditions(session, parsed_groups)
                matching_speech_ids = {
                    row[0]
                    for row in session.query(Speech.id)
                    .filter(Speech.id.in_(speech_ids))
                    .filter(or_(*matching_conditions))
                    .all()
                }

        return {
            "target_speech_id": target_speech.id,
            "target_speech_key": target_speech.speech_key,
            "speech_key": target_speech.speech_key,
            "speaker_uuid": target_speech.speaker_uuid,
            "speech_type": target_speech.speech_type,
            "external_id": target_speech.external_id,
            "start_time": target_speech.start_time,
            "end_time": target_speech.end_time,
            "duration_seconds": target_speech.duration_seconds,
            "date": target_speech.date,
            "time": target_speech.time,
            "source_file": target_speech.source_file,
            "source_url": normalize_source_url(target_speech.source_url),
            "agenda_title": target_speech.agenda_title,
            "video_url": target_speech.video_url,
            "total_speeches": len(speeches),
            "speeches": [
                {
                    "id": s.id,
                    "speech_key": s.speech_key,
                    "date": s.date,
                    "time": s.time,
                    "speaker": s.speaker,
                    "speaker_role": s.speaker_role,
                    "speaker_faction": s.speaker_faction,
                    "speaker_uuid": s.speaker_uuid,
                    "speech_type": s.speech_type,
                    "external_id": s.external_id,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "duration_seconds": s.duration_seconds,
                    "text": s.text,
                    "source_url": normalize_source_url(s.source_url),
                    "agenda_title": s.agenda_title,
                    "video_url": s.video_url,
                    "matched_words": (
                        extract_matched_words(
                            s.text,
                            target_lemmas,
                            phrases=all_phrases,
                            unquoted_lemmas=unquoted_lemmas,
                        )
                        if s.id in matching_speech_ids
                        else []
                    ),
                }
                for s in speeches
            ],
        }
    finally:
        session.close()
