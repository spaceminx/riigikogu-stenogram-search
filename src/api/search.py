import re
import time
from datetime import datetime, timedelta

from estnltk.vabamorf.morf import Vabamorf
from sqlalchemy import func, or_

from config import MEMBERSHIP_DATES, STOPWORDS
from src.load.database import SessionLocal
from src.load.models import Lemma, Speech, SpeechTerm
from src.transform.lemmatizer import lemmatize_text

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

    return [{label: period, "count": count} for period, count in results]


def is_only_stopwords(query: str) -> bool:
    """Check if query contains non-empty words but all of them are in STOPWORDS."""
    raw_groups = query.split(",")
    has_any_words = False
    for group in raw_groups:
        lemmas = lemmatize_text(group).split()
        if lemmas:
            has_any_words = True
            if any(lemma not in STOPWORDS for lemma in lemmas):
                return False
    return has_any_words


def parse_query_groups(query: str) -> list[list[str]]:
    """Parse comma-separated OR groups and space-separated AND keywords into filtered lemmas."""
    groups = []
    raw_groups = query.split(",")

    for group in raw_groups:
        lemmas = lemmatize_text(group).split()
        lemmas = [lemma for lemma in lemmas if lemma not in STOPWORDS]
        if lemmas:
            groups.append(list(dict.fromkeys(lemmas)))

    return groups


def build_matching_speech_ids_query(session, groups: list[list[str]]):
    """Build a SQL subquery returning distinct speech IDs matching query lemma groups."""
    group_queries = []

    for group in groups:
        q = (
            session.query(Speech.id.label("speech_id"))
            .join(SpeechTerm, Speech.id == SpeechTerm.speech_id)
            .join(Lemma, SpeechTerm.lemma_id == Lemma.id)
            .filter(Lemma.lemma.in_(group))
            .group_by(Speech.id)
            .having(func.count(func.distinct(Lemma.lemma)) == len(group))
        )

        group_queries.append(q)

    if len(group_queries) == 1:
        return group_queries[0].subquery()

    union_query = group_queries[0]

    for q in group_queries[1:]:
        union_query = union_query.union(q)

    return union_query.subquery()


def build_matching_conditions(session, groups: list[list[str]]) -> list:
    """Build SQL filter conditions for speech IDs matching each lemma group."""
    matching_conditions = []

    for group in groups:
        group_query = (
            session.query(Speech.id)
            .join(SpeechTerm, Speech.id == SpeechTerm.speech_id)
            .join(Lemma, SpeechTerm.lemma_id == Lemma.id)
            .filter(Lemma.lemma.in_(group))
            .group_by(Speech.id)
            .having(func.count(func.distinct(Lemma.lemma)) == len(group))
        )

        matching_conditions.append(Speech.id.in_(group_query))

    return matching_conditions


def build_speech_filters(
    membership: str = "all",
    faction: str | None = None,
    speaker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list:
    """Build list of SQLAlchemy filter clauses for Speech table."""
    filters = []

    if membership in MEMBERSHIP_DATES:
        start_bound, end_bound = MEMBERSHIP_DATES[membership]
        filters.append(Speech.date >= start_bound)
        filters.append(Speech.date <= end_bound)

    if faction:
        filters.append(Speech.speaker_faction == faction)

    if speaker and speaker.strip():
        filters.append(Speech.speaker.ilike(f"%{speaker.strip()}%"))

    if start_date:
        filters.append(Speech.date >= start_date)

    if end_date:
        filters.append(Speech.date <= end_date)

    return filters


def search_by_keyword(
    query: str,
    limit: int = 50,
    offset: int = 0,
    membership: str = "all",
    faction: str | None = None,
    speaker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    sort_by: str = "date_desc",
    include_matched_words: bool = True,
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
            start_date=start_date,
            end_date=end_date,
        )

        all_lemmas = [lemma for group in groups for lemma in group]

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
        if sort_by == "date_asc":
            ordered_query = grouped_query.order_by(Speech.date.asc(), Speech.id.asc())
        elif sort_by == "match_count_desc":
            ordered_query = grouped_query.order_by(
                func.sum(SpeechTerm.count).desc(), Speech.date.desc(), Speech.id.desc()
            )
        else:
            ordered_query = grouped_query.order_by(Speech.date.desc(), Speech.id.desc())

        results = ordered_query.offset(offset).limit(limit).all()

        count_query = (
            session.query(Speech.id)
            .join(SpeechTerm, Speech.id == SpeechTerm.speech_id)
            .join(Lemma, SpeechTerm.lemma_id == Lemma.id)
            .filter(or_(*matching_conditions))
            .filter(Lemma.lemma.in_(all_lemmas))
        )
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
                    "speaker": speech.speaker,
                    "speaker_role": speech.speaker_role,
                    "speaker_faction": speech.speaker_faction,
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
    start_date: str | None = None,
    end_date: str | None = None,
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
            start_date=start_date,
            end_date=end_date,
        )
        query_builder = session.query(
            date_group.label("period"), func.count(Speech.id).label("total_count")
        ).join(matched_speeches, Speech.id == list(matched_speeches.c)[0])

        if speech_filters:
            query_builder = query_builder.filter(*speech_filters)

        results = query_builder.group_by(date_group).order_by(date_group).all()
        if interval in ("monthly", "daily"):
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
            for row in (
                session.query(Speech.date)
                .filter(
                    Speech.date.like("____-__-__"),
                    Speech.source_file.isnot(None),
                    Speech.source_file != "",
                )
                .distinct()
                .order_by(Speech.date.desc())
                .all()
            )
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
            .order_by(Speech.time.asc(), Speech.source_file.asc(), Speech.id.asc())
            .all()
        )
        return [
            {
                "id": speech.id,
                "speaker": speech.speaker,
                "speaker_role": speech.speaker_role,
                "speaker_faction": speech.speaker_faction,
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
            session.query(Speech.speaker, func.count(Speech.id).label("speech_count"))
            .filter(
                Speech.speaker.isnot(None),
                Speech.speaker != "",
                Speech.speaker_faction.isnot(None),
                Speech.speaker_faction != "",
            )
            .group_by(Speech.speaker)
            .order_by(func.count(Speech.id).desc(), Speech.speaker.asc())
            .limit(4)
            .all()
        )

        speakers = []
        for speaker_name, speech_count in speaker_rows:
            latest_speech = (
                session.query(Speech.speaker_faction)
                .filter(Speech.speaker == speaker_name)
                .order_by(Speech.date.desc(), Speech.time.desc())
                .first()
            )
            speakers.append(
                {
                    "speaker": speaker_name,
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
        result = {"speakers": speakers, "sessions": sessions}
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
    start_date: str | None = None,
    end_date: str | None = None,
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
            start_date=start_date,
            end_date=end_date,
        )

        all_lemmas = [lemma for group in groups for lemma in group]

        query_builder = (
            session.query(Speech.speaker, func.sum(SpeechTerm.count).label("total_count"))
            .join(SpeechTerm, Speech.id == SpeechTerm.speech_id)
            .join(Lemma, SpeechTerm.lemma_id == Lemma.id)
            .filter(or_(*matching_conditions))
            .filter(Lemma.lemma.in_(all_lemmas))
        )

        if speech_filters:
            query_builder = query_builder.filter(*speech_filters)

        results = (
            query_builder.group_by(Speech.speaker)
            .order_by(func.sum(SpeechTerm.count).desc())
            .limit(limit)
            .all()
        )

        output = [
            {"speaker": speaker_name, "count": int(total_count)}
            for speaker_name, total_count in results
        ]
        return output
    finally:
        session.close()


def get_speech_context(speech_id: int, query: str | None = None) -> dict | None:
    """Retrieve full transcript context (all speeches in chronological order) for a given speech."""
    session = SessionLocal()
    try:
        target_speech = session.query(Speech).filter(Speech.id == speech_id).first()
        if not target_speech:
            return None

        speeches = (
            session.query(Speech)
            .filter(Speech.source_file == target_speech.source_file)
            .order_by(Speech.id.asc())
            .all()
        )

        target_lemmas: set[str] = set()
        matching_speech_ids: set[int] = set()
        if query and not is_only_stopwords(query):
            groups = parse_query_groups(query)
            target_lemmas = {lemma for group in groups for lemma in group}
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
                    "date": s.date,
                    "time": s.time,
                    "speaker": s.speaker,
                    "speaker_role": s.speaker_role,
                    "speaker_faction": s.speaker_faction,
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
