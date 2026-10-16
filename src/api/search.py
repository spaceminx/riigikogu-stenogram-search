import logging
import re
import time
from datetime import datetime, timedelta

from estnltk import Text
from estnltk.vabamorf.morf import Vabamorf
from fastapi import HTTPException
from sqlalchemy import func, or_, select

from config import MEMBERSHIP_DATES, STOPWORDS
from src.load.database import SessionLocal
from src.load.models import Lemma, Person, Speech, SpeechTerm
from src.transform.lemmatizer import lemmatize_text

logger = logging.getLogger(__name__)

_C0_CONTROL_REGEX = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HYPHEN_NUM_REGEX = re.compile(r"^([a-zA-Z0-9äöüõÄÖÜÕšžŠŽ]+)-(\d+)$")
_CLEAN_LEMMA_CHARS = ".,;:!?\"'()[]{}«»`~^/*+=<>@#$%&|\\_"


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


def extract_matched_words(text: str, target_lemmas: set[str]) -> list[str]:
    """Extract surface word tokens from text matching any of target lemmas with high-speed morphological analysis."""
    if not text or not target_lemmas:
        return []
    try:
        tokens = list(set(_WORD_REGEX.findall(text)))
        if not tokens:
            return []
        analyses = _VABAMORF.analyze([t.lower() for t in tokens])
        matched = set()
        for token, item in zip(tokens, analyses, strict=True):
            for a in item.get("analysis", []):
                lemma = a.get("lemma", "")
                if lemma and lemma.lower() in target_lemmas:
                    matched.add(token)
                    break
        return sorted(matched, key=len, reverse=True)
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


def fill_missing_periods(results: list, interval: str, label: str) -> list[dict]:
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
            filled.append({label: period, "count": data.get(period, 0)})
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
            filled.append(
                {
                    label: week_key,
                    "week_start": m_str,
                    "count": monday_counts.get(m_str, 0),
                }
            )
            current += timedelta(days=7)
        return filled

    if interval == "daily":
        start = datetime.strptime(periods[0], "%Y-%m-%d")
        end = datetime.strptime(periods[-1], "%Y-%m-%d")

        filled = []
        current = start
        while current <= end:
            period = current.strftime("%Y-%m-%d")
            filled.append({label: period, "count": data.get(period, 0)})
            current += timedelta(days=1)
        return filled

    if label == "week":
        return [
            {label: period, "week_start": week_key_to_monday(period).isoformat(), "count": count}
            for period, count in results
        ]
    return [{label: period, "count": count} for period, count in results]


def _extract_group_terms(group: str) -> tuple[bool, list[list[str]]]:
    """Extract content terms from a query group with case and hyphen expansions.

    Returns (has_any_words, content_terms) where content_terms is a list of positions,
    and each position contains a list of alternative lemmas.
    """
    if lemmatize_text(group) is None:
        raise LemmatizerUnavailableError("Otsingu keeletöötlus pole hetkel saadaval.")

    try:
        est_text = Text(f"{group} .")
        est_text.tag_layer()
    except Exception as e:
        logger.error("Lemmatization failed on query group %r: %s", group[:100], e)
        raise LemmatizerUnavailableError("Otsingu keeletöötlus pole hetkel saadaval.") from e

    words1 = [w for w in est_text.words if w.text != "." and any(c.isalnum() for c in w.text)]
    if not words1:
        return (False, [])

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


def is_only_stopwords(query: str) -> bool:
    """Check if query contains non-empty words but all of them are in STOPWORDS."""
    check_query_complexity(query)
    raw_groups = [g.strip() for g in query.split(",") if g.strip()]
    if len(raw_groups) > 10:
        raise ValueError("Liiga palju otsingurühmi: lubatud kuni 10 komaga eraldatud rühma.")
    has_any_words = False
    for group in raw_groups:
        has_words, terms = _extract_group_terms(group)
        if len(terms) > 10:
            raise ValueError("Liiga palju sõnu ühes rühmas: lubatud kuni 10 sisusõna.")
        if has_words:
            has_any_words = True
            if terms:
                return False
    return has_any_words


def parse_query_groups(query: str) -> list[list[list[str]]]:
    """Parse comma-separated OR groups and space-separated AND keywords into filtered lemma alternatives."""
    check_query_complexity(query)
    groups = []
    raw_groups = [g.strip() for g in query.split(",") if g.strip()]
    if len(raw_groups) > 10:
        raise ValueError("Liiga palju otsingurühmi: lubatud kuni 10 komaga eraldatud rühma.")

    for group in raw_groups:
        has_words, terms = _extract_group_terms(group)
        if len(terms) > 10:
            raise ValueError("Liiga palju sõnu ühes rühmas: lubatud kuni 10 sisusõna.")
        if terms:
            groups.append(terms)

    return groups


def build_matching_speech_ids_query(session, groups: list[list[list[str]]]):
    """Build a SQL subquery returning distinct speech IDs matching query lemma groups."""
    group_queries = []

    for group in groups:
        term_queries = []
        for term_alts in group:
            tq = (
                session.query(SpeechTerm.speech_id.label("speech_id"))
                .join(Lemma, SpeechTerm.lemma_id == Lemma.id)
                .filter(Lemma.lemma.in_(term_alts))
            )
            term_queries.append(tq)

        if not term_queries:
            continue
        if len(term_queries) == 1:
            gq = term_queries[0]
        else:
            gq = term_queries[0].intersect(*term_queries[1:])
        group_queries.append(gq)

    if not group_queries:
        return session.query(Speech.id.label("speech_id")).filter(False).subquery()

    if len(group_queries) == 1:
        return group_queries[0].subquery()

    union_query = group_queries[0].union(*group_queries[1:])
    return union_query.subquery()


def build_matching_conditions(session, groups: list[list[list[str]]]) -> list:
    """Build SQL filter conditions for speech IDs matching each lemma group."""
    matched_subquery = build_matching_speech_ids_query(session, groups)
    col = list(matched_subquery.c)[0]
    return [Speech.id.in_(select(col))]


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
        groups = parse_query_groups(query)

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

        if not speech_filters:
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
        output = []
        for speech, match_count in results:
            matched_words = (
                extract_matched_words(speech.text, target_lemmas_set)
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
        groups = parse_query_groups(query)
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

        matched_speeches = build_matching_speech_ids_query(session, groups)
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
        ).join(matched_speeches, Speech.id == list(matched_speeches.c)[0])

        if speech_filters:
            query_builder = query_builder.filter(*speech_filters)

        results = query_builder.group_by(date_group).order_by(date_group).all()
        if interval in ("monthly", "daily", "weekly", "week"):
            return fill_missing_periods(results, interval, label)
        return [{label: period, "count": int(total_count)} for period, total_count in results]
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


def get_session_speeches(session_date: str) -> list[dict]:
    """Return the transcript entries for one plenary date, ordered as spoken."""
    session = SessionLocal()
    try:
        speeches = (
            session.query(Speech)
            .filter(Speech.date == session_date)
            .order_by(Speech.source_file.asc(), Speech.start_time.asc(), Speech.id.asc())
            .all()
        )
        return [
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
                "count": 0,
                "matched_words": [],
                "date": speech.date,
                "time": speech.time,
                "source_file": speech.source_file,
                "source_url": normalize_source_url(speech.source_url),
                "agenda_title": speech.agenda_title,
                "video_url": speech.video_url,
            }
            for speech in speeches
        ]
    finally:
        session.close()


_OVERVIEW_CACHE: dict = {"data": None, "timestamp": 0.0}
_OVERVIEW_CACHE_TTL: float = 3600.0


def get_dashboard_overview() -> dict:
    """Return archive-wide speakers and the latest plenary sessions."""
    now = time.time()
    if (
        _OVERVIEW_CACHE["data"] is not None
        and (now - _OVERVIEW_CACHE["timestamp"]) < _OVERVIEW_CACHE_TTL
    ):
        return _OVERVIEW_CACHE["data"]

    session = SessionLocal()
    try:
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
            topic_rows = (
                session.query(
                    Speech.source_file,
                    Lemma.lemma,
                    func.sum(SpeechTerm.count).label("occurrences"),
                )
                .join(SpeechTerm, Speech.id == SpeechTerm.speech_id)
                .join(Lemma, SpeechTerm.lemma_id == Lemma.id)
                .filter(Speech.source_file.in_(source_files))
                .group_by(Speech.source_file, Lemma.lemma)
                .order_by(Speech.source_file.asc(), func.sum(SpeechTerm.count).desc())
                .all()
            )
            stopwords = {word.casefold() for word in STOPWORDS}
            for source_file, lemma, _occurrences in topic_rows:
                normalized = lemma.casefold()
                topics = topics_by_source[source_file]
                if len(normalized) >= 4 and normalized not in stopwords and len(topics) < 3:
                    topics.append(lemma)

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
        groups = parse_query_groups(query)
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


def get_speech_context(speech_id: int, query: str | None = None) -> dict | None:
    """Retrieve full transcript context (all speeches in chronological order) for a given speech."""
    parsed_groups = None
    if query and not is_only_stopwords(query):
        parsed_groups = parse_query_groups(query)

    session = SessionLocal()
    try:
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
        if parsed_groups:
            target_lemmas = {lemma for group in parsed_groups for term in group for lemma in term}
            if target_lemmas and speeches:
                speech_ids = [s.id for s in speeches]
                matching_speech_ids = {
                    row[0]
                    for row in session.query(SpeechTerm.speech_id)
                    .join(Lemma, SpeechTerm.lemma_id == Lemma.id)
                    .filter(SpeechTerm.speech_id.in_(speech_ids))
                    .filter(Lemma.lemma.in_(target_lemmas))
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
                    "matched_words": extract_matched_words(s.text, target_lemmas)
                    if s.id in matching_speech_ids
                    else [],
                }
                for s in speeches
            ],
        }
    finally:
        session.close()
