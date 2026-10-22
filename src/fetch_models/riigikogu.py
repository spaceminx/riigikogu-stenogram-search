"""Pydantic models for api.riigikogu.ee and stenogrammid.riigikogu.ee API responses.

Validation layer only - fetchers continue using raw dicts downstream.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError


class UpstreamSchemaError(Exception):
    """Raised when an upstream Riigikogu API response fails schema validation."""

    pass


# ---------------------------------------------------------------------------
# Base model allowing extra fields
# ---------------------------------------------------------------------------
class RiigikoguBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# 1. /api/memberships
# ---------------------------------------------------------------------------
class MembershipItem(RiigikoguBaseModel):
    # number is required and parsed via int(x["number"])
    number: int | str
    # startDate is required via x["startDate"]
    startDate: str
    endDate: str | None = None


# ---------------------------------------------------------------------------
# 2. /api/plenary-members?status=ALL&membership=...
# ---------------------------------------------------------------------------
class PhotoLinksDownload(RiigikoguBaseModel):
    href: str | None = None


class PhotoLinks(RiigikoguBaseModel):
    download: PhotoLinksDownload | None = None


class MemberPhoto(RiigikoguBaseModel):
    uuid: str | None = None
    _links: PhotoLinks | None = None


class FactionMembershipInterval(RiigikoguBaseModel):
    startDate: str | None = None
    endDate: str | None = None


class MemberFaction(RiigikoguBaseModel):
    name: str | None = None
    membership: FactionMembershipInterval | None = None


class ElectoralDistrictObj(RiigikoguBaseModel):
    value: str | None = None


class ElectoralDistrictHistoryItem(RiigikoguBaseModel):
    membership: int | str | None = None
    electoralDistrict: str | ElectoralDistrictObj | None = None


class PlenaryMembershipObj(RiigikoguBaseModel):
    membershipNumber: int | str | None = None


class PlenaryMember(RiigikoguBaseModel):
    uuid: str | None = None
    firstName: str | None = None
    lastName: str | None = None
    fullName: str | None = None
    gender: str | None = None
    dateOfBirth: str | None = None
    email: str | None = None
    parliamentSeniority: int | str | None = None
    active: bool | None = None
    factions: list[MemberFaction] | None = None
    photo: MemberPhoto | None = None
    electoralDistrict: str | ElectoralDistrictObj | None = None
    electoralDistrictHistory: list[ElectoralDistrictHistoryItem] | None = None
    plenaryMembership: PlenaryMembershipObj | None = None


# ---------------------------------------------------------------------------
# 3. /api/votings?startDate=...&endDate=...
# ---------------------------------------------------------------------------
class VotingTypeCode(RiigikoguBaseModel):
    code: str | None = None


class SittingVotingSummary(RiigikoguBaseModel):
    # In fetch_attendance: check_uuid = v["uuid"] (required)
    uuid: str
    votingNumber: int | str | None = None
    type: str | VotingTypeCode | None = None
    description: str | None = None
    startDateTime: str | None = None


class VotingsSitting(RiigikoguBaseModel):
    uuid: str | None = None
    title: str | None = None
    sittingDateTime: str | None = None
    membership: int | str | None = None
    votings: list[SittingVotingSummary] | None = None


# ---------------------------------------------------------------------------
# 4. /api/votings/{uuid}
# ---------------------------------------------------------------------------
class VoterDecision(RiigikoguBaseModel):
    code: str | None = None


class VoterFaction(RiigikoguBaseModel):
    name: str | None = None


class Voter(RiigikoguBaseModel):
    uuid: str | None = None
    fullName: str | None = None
    decision: str | VoterDecision | None = None
    faction: str | VoterFaction | None = None


class VotingSittingRef(RiigikoguBaseModel):
    uuid: str | None = None
    title: str | None = None


class VotingChairmanRef(RiigikoguBaseModel):
    uuid: str | None = None


class RelatedDocument(RiigikoguBaseModel):
    uuid: str | None = None
    reference: str | int | None = None
    mark: str | int | None = None
    title: str | None = None
    documentType: str | None = None
    type: str | None = None


class RelatedDraft(RiigikoguBaseModel):
    uuid: str | None = None
    reference: str | int | None = None
    mark: str | int | None = None
    title: str | None = None
    documentType: str | None = None


class VotingDetail(RiigikoguBaseModel):
    uuid: str | None = None
    votingNumber: int | str | None = None
    type: str | VotingTypeCode | None = None
    description: str | None = None
    startDateTime: str | None = None
    endDateTime: str | None = None
    sitting: VotingSittingRef | None = None
    chairman: VotingChairmanRef | None = None
    relatedDocument: RelatedDocument | None = None
    relatedDraft: RelatedDraft | None = None
    voters: list[Voter] | None = None
    inFavor: int | None = None
    against: int | None = None
    neutral: int | None = None
    abstained: int | None = None
    present: int | None = None
    absent: int | None = None


# ---------------------------------------------------------------------------
# 5. api.riigikogu.ee/api/steno/verbatims
# ---------------------------------------------------------------------------
class VerbatimEvent(RiigikoguBaseModel):
    type: str | None = None
    text: str | None = None
    speaker: str | None = None
    emsId: str | int | None = None


class VerbatimAgendaItem(RiigikoguBaseModel):
    title: str | None = None
    agendaItemUuid: str | None = None
    events: list[VerbatimEvent] | None = None


class VerbatimSitting(RiigikoguBaseModel):
    date: str | None = None
    startTime: str | None = None
    sittingDateTime: str | None = None
    link: str | None = None
    title: str | None = None
    edited: bool | None = None
    agendaItems: list[VerbatimAgendaItem] | None = None


# ---------------------------------------------------------------------------
# 6. stenogrammid.riigikogu.ee/api/meeting/{code}
# ---------------------------------------------------------------------------
class MeetingSpeech(RiigikoguBaseModel):
    name: str | None = None
    content: str | None = None
    speechType: str | None = None
    startTime: str | None = None
    endTime: str | None = None
    emsId: str | int | None = None
    parsedVideoLink: str | None = None
    id: str | int | None = None


class MeetingAgendaItem(RiigikoguBaseModel):
    id: str | int | None = None
    name: str | None = None
    speeches: list[MeetingSpeech] | None = None


class MeetingStenograph(RiigikoguBaseModel):
    agendaItems: list[MeetingAgendaItem] | None = None


class RichMeeting(RiigikoguBaseModel):
    meetingStatus: str | None = None
    stenograph: MeetingStenograph | None = None


# ---------------------------------------------------------------------------
# 7. /api/agenda/plenary
# ---------------------------------------------------------------------------
class AgendaItemVotingRef(RiigikoguBaseModel):
    uuid: str | None = None


class AgendaItemRelatedDraft(RiigikoguBaseModel):
    uuid: str | None = None
    mark: str | int | None = None
    title: str | None = None


class AgendaItemTypeObj(RiigikoguBaseModel):
    code: str | None = None


class AgendaItemDecisionObj(RiigikoguBaseModel):
    code: str | None = None
    value: str | None = None


class AgendaSittingItem(RiigikoguBaseModel):
    uuid: str | None = None
    order: int | str | None = None
    title: str | None = None
    documentType: str | None = None
    type: str | AgendaItemTypeObj | None = None
    stage: str | None = None
    decision: AgendaItemDecisionObj | None = None
    relatedDraft: AgendaItemRelatedDraft | None = None
    votings: list[AgendaItemVotingRef] | None = None


class AgendaSitting(RiigikoguBaseModel):
    uuid: str | None = None
    sittingDateTime: str | None = None
    agendaItems: list[AgendaSittingItem] | None = None


class AgendaPlenary(RiigikoguBaseModel):
    sittings: list[AgendaSitting] | None = None


# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------
def validate_response(model: type[BaseModel], data: Any, *, endpoint: str, ref: str) -> None:
    """Validate raw response dict or list using the given Pydantic model.

    Raises UpstreamSchemaError on validation failure.
    If data is a list, validates every item in the list.
    """
    try:
        if isinstance(data, list):
            for idx, item in enumerate(data):
                try:
                    model.model_validate(item)
                except ValidationError as ve:
                    # Enrich loc with index
                    errors_summary = []
                    for err in ve.errors()[:5]:
                        loc_str = ".".join(str(x) for x in (idx, *err["loc"]))
                        errors_summary.append(f"{loc_str}: {err['msg']}")
                    err_lines = ", ".join(errors_summary)
                    raise UpstreamSchemaError(
                        f"Validation failed for {endpoint} (ref: {ref}): {err_lines}. "
                        "api.riigikogu.ee response shape changed"
                    ) from ve
        else:
            model.model_validate(data)
    except ValidationError as ve:
        errors_summary = []
        for err in ve.errors()[:5]:
            loc_str = ".".join(str(x) for x in err["loc"])
            errors_summary.append(f"{loc_str}: {err['msg']}")
        err_lines = ", ".join(errors_summary)
        raise UpstreamSchemaError(
            f"Validation failed for {endpoint} (ref: {ref}): {err_lines}. "
            "api.riigikogu.ee response shape changed"
        ) from ve
