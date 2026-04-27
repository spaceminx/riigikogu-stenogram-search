from sqlalchemy import func, or_
from datetime import datetime, timedelta

from config import STOPWORDS
from src.load.database import SessionLocal
from src.load.models import Speech, SpeechTerm, Lemma
from src.transform.lemmatizer import lemmatize_text


def fill_missing_periods(results, interval, label):
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

            filled.append({
                label: period,
                "count": data.get(period, 0)
            })

            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

        return filled

    return [
        {
            label: period,
            "count": count
        }
        for period, count in results
    ]

def parse_query_groups(query):
    """
    comma = OR
    space in text = AND
    """
    groups = []
    raw_groups = query.split(",")

    for group in raw_groups:
        lemmas = lemmatize_text(group).split()
        lemmas = [lemma for lemma in lemmas if lemma not in STOPWORDS]
        if lemmas:
            groups.append(lemmas)

    return groups

def build_matching_speech_ids_query(session, groups):
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

def build_matching_conditions(session, groups):
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


def search_by_keyword(query, limit = 50):
    session = SessionLocal()

    try:
        groups = parse_query_groups(query)

        if not groups:
            return []

        matching_conditions = build_matching_conditions(session, groups)

        results = (
            session.query(
                Speech,
                func.sum(SpeechTerm.count).label("match_count")
            )
            .join(SpeechTerm, Speech.id == SpeechTerm.speech_id)
            .join(Lemma, SpeechTerm.lemma_id == Lemma.id)
            .filter(or_(*matching_conditions))
            .filter(
                Lemma.lemma.in_(
                    [lemma for group in groups for lemma in group])
            )
            .group_by(Speech.id)
            .order_by(Speech.date.desc())
            .limit(limit)
            .all()
        )

        output = []

        for speech, match_count in results:
            output.append({
                "speaker": speech.speaker,
                "text": speech.text,
                "count": int(match_count),
                "date": speech.date,
                "time": speech.time,
                "source_url": speech.source_url,
            })
        return output

    finally:
        session.close()




def keyword_activity(query: str, interval: str = "weekly"):
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

        results = (
            session.query(
                date_group.label("period"),
                func.count(Speech.id).label("total_count")
            )
            .join(matched_speeches, Speech.id == matched_speeches.c.speech_id)
            .group_by(date_group)
            .order_by(date_group)
            .all()
        )

        if interval == "monthly":
            return fill_missing_periods(
                results, interval, label
            )

        return [
            {
                label: period,
                "count": int(total_count)
            }
            for period, total_count in results
        ]

    finally:
        session.close()


def keyword_top_speakers(query, limit = 20):
    session = SessionLocal()
    try:
        groups = parse_query_groups(query)
        if not groups:
            return []

        matching_conditions = build_matching_conditions(session, groups)

        all_lemmas = [lemma for group in groups for lemma in group]

        results = (
            session.query(
                Speech.speaker,
                func.sum(SpeechTerm.count).label("total_count")
            )
            .join(SpeechTerm, Speech.id == SpeechTerm.speech_id)
            .join(Lemma, SpeechTerm.lemma_id == Lemma.id)
            .filter(or_(*matching_conditions))
            .filter(Lemma.lemma.in_(all_lemmas))
            .group_by(Speech.speaker)
            .order_by(func.sum(SpeechTerm.count).desc())
            .limit(limit)
            .all()
        )

        output = [
            {
                "speaker": speaker,
                "count": int(total_count)
            }
            for speaker, total_count in results
        ]
        return output
    finally:
        session.close()
