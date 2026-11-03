"""Draft list: the upstream draft list joined with each draft's plenary readings, votings and speeches."""

import json
import re
import threading
from typing import Any

from sqlalchemy import text

from config import MEMBERSHIP_DATES
from src.api.votings import _get_last_sync_at
from src.load.models import AgendaItem, Draft, Voting

STATUS_GROUPS = ("in_process", "adopted", "rejected", "withdrawn", "lapsed", "other")
SORTS = ("recent", "initiated")

# Riigikogu's final stages; a draft still in proceedings is "in_process" whatever its stage
_STAGE_GROUPS = {
    "VASTU_VOETUD": "adopted",
    "TAGASI_LYKATUD": "rejected",
    "TAGASI_VOETUD": "withdrawn",
    "TAGASI_VOETUD_TAISKOGUL_MENETLEMATA": "withdrawn",
    "VALJA_LANGENUD_KOOSEISU_LOPPEMISEGA": "lapsed",
}

_MARK_QUERY = re.compile(r"(\d+)\s*([A-Za-z]{2})?")
_AGENDA_MARK = re.compile(r"(\d+)\s*([A-Z]{2})?")

_SPEECH_COUNTS_SQL = text(
    """
    SELECT a.draft_uuid, COUNT(DISTINCT s.id)
    FROM agenda_items a
    JOIN speeches s ON s.source_file = a.source_file AND s.agenda_title = a.steno_title
    WHERE a.draft_uuid IS NOT NULL
    GROUP BY a.draft_uuid
    """
)

_UNSET = object()
_CACHE: dict = {"last_sync_at": _UNSET, "items": None}
_CACHE_LOCK = threading.Lock()


def status_group(proceeding_status: str | None, stage: str | None) -> str | None:
    """Group a draft's stage for filtering; None when the draft is not in the upstream list."""
    if proceeding_status == "IN_PROCESS":
        return "in_process"
    if proceeding_status is None and stage is None:
        return None
    return _STAGE_GROUPS.get(stage, "other")


def membership_on(day: str | None) -> int | None:
    """The membership sitting on a day, for drafts missing from the upstream list."""
    if not day:
        return None
    for number, (start, end) in MEMBERSHIP_DATES.items():
        if start <= day <= end and str(number).isdigit():
            return int(number)
    return None


def parse_mark(raw: str | None) -> tuple[int | None, str | None]:
    """Split an agenda or voting mark ("919" or "919 SE") into the number and the type."""
    match = _AGENDA_MARK.match(str(raw or ""))
    if not match:
        return None, None
    return int(match.group(1)), match.group(2)


def _voting_uuids(raw: str | None) -> list[str]:
    try:
        loaded = json.loads(raw) if raw else []
    except ValueError:
        return []
    return loaded if isinstance(loaded, list) else []


def build_draft_index(session) -> list[dict[str, Any]]:
    """Every draft from the drafts table, plus drafts known only from the agenda."""
    activity: dict[str, dict] = {}

    def entry(uuid: str) -> dict:
        return activity.setdefault(
            uuid, {"readings": 0, "votings": set(), "dates": [], "mark": None, "title": None}
        )

    for draft_uuid, sitting_date, voting_uuids, mark, title in session.query(
        AgendaItem.draft_uuid,
        AgendaItem.sitting_date,
        AgendaItem.voting_uuids,
        AgendaItem.draft_mark,
        AgendaItem.draft_title,
    ).filter(AgendaItem.draft_uuid.isnot(None)):
        e = entry(draft_uuid)
        e["readings"] += 1
        e["votings"].update(_voting_uuids(voting_uuids))
        if sitting_date:
            e["dates"].append(sitting_date)
        e["mark"] = e["mark"] or mark
        e["title"] = e["title"] or title

    drafts = {d.uuid: d for d in session.query(Draft)}
    voting_dates: dict[str, str | None] = {}
    for uuid, doc_uuid, sitting_date, vote_date in session.query(
        Voting.uuid, Voting.related_document_uuid, Voting.sitting_date, Voting.date
    ):
        voting_dates[uuid] = sitting_date or vote_date
        if doc_uuid and (doc_uuid in drafts or doc_uuid in activity):
            entry(doc_uuid)["votings"].add(uuid)

    speech_counts = dict(session.execute(_SPEECH_COUNTS_SQL).all())

    items: list[dict[str, Any]] = []
    for uuid in drafts.keys() | {u for u, e in activity.items() if e["readings"]}:
        e = activity.get(uuid) or entry(uuid)
        votings = [v for v in e["votings"] if v in voting_dates]
        dates = sorted(e["dates"] + [voting_dates[v] for v in votings if voting_dates[v]])
        d = drafts.get(uuid)
        if d:
            item = {
                "uuid": uuid,
                "membership": d.membership,
                "mark": d.mark,
                "type_code": d.type_code,
                "title": d.title,
                "stage": d.stage,
                "status": d.status,
                "status_date": d.status_date,
                "proceeding_status": d.proceeding_status,
                "initiated": d.initiated,
                "leading_committee": (
                    {"uuid": d.leading_committee_uuid, "name": d.leading_committee}
                    if d.leading_committee
                    else None
                ),
            }
        else:
            # A draft of an earlier membership discussed in this one, or no drafts.json yet
            mark, type_code = parse_mark(e["mark"])
            item = {
                "uuid": uuid,
                "membership": membership_on(dates[0] if dates else None),
                "mark": mark,
                "type_code": type_code,
                "title": e["title"],
                "stage": None,
                "status": None,
                "status_date": None,
                "proceeding_status": None,
                "initiated": None,
                "leading_committee": None,
            }
        item["status_group"] = status_group(item["proceeding_status"], item["stage"])
        item["reading_count"] = e["readings"]
        item["voting_count"] = len(votings)
        item["speech_count"] = speech_counts.get(uuid, 0)
        item["first_plenary_date"] = dates[0] if dates else None
        item["last_plenary_date"] = dates[-1] if dates else None
        item["last_activity"] = max(
            (x for x in (item["status_date"], item["last_plenary_date"], item["initiated"]) if x),
            default=None,
        )
        items.append(item)
    return items


def get_draft_index(session) -> list[dict[str, Any]]:
    """The draft index, rebuilt after every database sync."""
    last_sync = _get_last_sync_at(session)
    with _CACHE_LOCK:
        if _CACHE["items"] is None or _CACHE["last_sync_at"] != last_sync:
            _CACHE["items"] = build_draft_index(session)
            _CACHE["last_sync_at"] = last_sync
        return _CACHE["items"]


def clear_draft_cache() -> None:
    with _CACHE_LOCK:
        _CACHE["last_sync_at"] = _UNSET
        _CACHE["items"] = None


def _matches_query(item: dict, q: str) -> bool:
    mark = _MARK_QUERY.fullmatch(q)
    if mark and item["mark"] == int(mark.group(1)):
        # Agenda marks carry no type, so a draft of unknown type matches on the number alone
        wanted = (mark.group(2) or "").upper()
        if not wanted or not item["type_code"] or item["type_code"].upper() == wanted:
            return True
    title = (item["title"] or "").casefold()
    return all(word in title for word in q.casefold().split())


def filter_drafts(
    items: list[dict],
    *,
    membership: int | None = None,
    type_code: str | None = None,
    status: str | None = None,
    committee: str | None = None,
    q: str | None = None,
    sort: str = "recent",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Filter, sort and page the draft index; facets count each filter's values under the others."""
    q = (q or "").strip()
    checks = {
        "membership": lambda i: membership is None or i["membership"] == membership,
        "q": lambda i: not q or _matches_query(i, q),
        "type": lambda i: type_code is None or i["type_code"] == type_code,
        "status": lambda i: status is None or i["status_group"] == status,
        "committee": lambda i: (
            committee is None or (i["leading_committee"] or {}).get("uuid") == committee
        ),
    }

    def matching(skip: str | None = None) -> list[dict]:
        return [i for i in items if all(check(i) for name, check in checks.items() if name != skip)]

    results = matching()
    if sort == "initiated":
        results.sort(key=lambda i: (i["membership"] or 0, i["mark"] or 0), reverse=True)
        results.sort(key=lambda i: i["initiated"] or "", reverse=True)
    else:
        results.sort(key=lambda i: (i["membership"] or 0, i["mark"] or 0), reverse=True)
        results.sort(key=lambda i: i["last_activity"] or "", reverse=True)

    status_counts: dict[str, int] = {}
    for i in matching("status"):
        if i["status_group"]:
            status_counts[i["status_group"]] = status_counts.get(i["status_group"], 0) + 1
    type_counts: dict[str, int] = {}
    for i in matching("type"):
        if i["type_code"]:
            type_counts[i["type_code"]] = type_counts.get(i["type_code"], 0) + 1
    committees: dict[str, dict] = {}
    for i in matching("committee"):
        c = i["leading_committee"]
        if c:
            committees.setdefault(c["uuid"], {**c, "count": 0})["count"] += 1

    return {
        "total": len(results),
        "limit": limit,
        "offset": offset,
        "results": results[offset : offset + limit],
        "facets": {
            "status": {g: status_counts[g] for g in STATUS_GROUPS if g in status_counts},
            "type": dict(sorted(type_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
            "committee": sorted(committees.values(), key=lambda c: c["name"]),
        },
    }
