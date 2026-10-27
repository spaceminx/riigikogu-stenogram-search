#!/usr/bin/env python3
"""Check live api.riigikogu.ee and stenogrammid.riigikogu.ee endpoints against Pydantic models.

Fetches a small live sample:
- votings for the last 14 days + 1 voting detail
- verbatims for the last 14 days + 1 meeting
- memberships
- plenary-members for the current membership
- agenda for the last 14 days
- faction user groups + 1 faction with its members

Validates each response with the corresponding Pydantic models.
Sleeps 1s between requests, with 1 retry on timeout or network error.
Exits 1 on any validation/request failure.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.fetch_models import (
    AgendaPlenary,
    MembershipItem,
    PlenaryMember,
    RichMeeting,
    UpstreamSchemaError,
    UserGroupDetail,
    UserGroupItem,
    VerbatimSitting,
    VotingDetail,
    VotingsSitting,
    validate_response,
)

TIMEOUT_SECONDS = 10.0
SLEEP_BETWEEN_REQUESTS_SECONDS = 1.0
RETRY_DELAY_SECONDS = 5.0
USER_AGENT = "Riigivaade-UpstreamApiCheck/1.0"


def fetch_and_validate(
    url: str,
    model: type,
    ref: str,
    timeout: float = TIMEOUT_SECONDS,
    retry_delay: float = RETRY_DELAY_SECONDS,
) -> tuple[str, int, str | None, object]:
    """Fetch URL and validate against model, retrying once on timeout/network error.

    Returns (status_str, duration_ms, error_msg or None, parsed_json or None).
    """
    req = Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(2):
        start_time = time.monotonic()
        try:
            with urlopen(req, timeout=timeout) as resp:
                elapsed = time.monotonic() - start_time
                duration_ms = int(elapsed * 1000)
                status_code = resp.status
                if status_code != 200:
                    return (
                        f"HTTP {status_code}",
                        duration_ms,
                        f"{url}: returned HTTP {status_code}",
                        None,
                    )

                body = resp.read()
                try:
                    data = json.loads(body.decode("utf-8"))
                except Exception as err:
                    return (
                        "JSON",
                        duration_ms,
                        f"{url}: invalid JSON response ({type(err).__name__}: {err})",
                        None,
                    )

                try:
                    validate_response(model, data, endpoint=url, ref=ref)
                    return "OK", duration_ms, None, data
                except UpstreamSchemaError as err:
                    return "DIFF", duration_ms, str(err), None

        except HTTPError as err:
            elapsed = time.monotonic() - start_time
            duration_ms = int(elapsed * 1000)
            return (
                f"HTTP {err.code}",
                duration_ms,
                f"{url}: HTTP error {err.code} ({type(err).__name__}: {err})",
                None,
            )

        except (URLError, TimeoutError) as err:
            elapsed = time.monotonic() - start_time
            duration_ms = int(elapsed * 1000)
            if attempt == 0:
                time.sleep(retry_delay)
                continue

            status_str = "TIMEOUT" if "timed out" in str(err).lower() else "NET_ERR"
            return status_str, duration_ms, f"{url}: {type(err).__name__}: {err}", None

        except Exception as err:
            elapsed = time.monotonic() - start_time
            duration_ms = int(elapsed * 1000)
            return "ERR", duration_ms, f"{url}: {type(err).__name__}: {err}", None

    return "ERR", 0, f"{url}: unexpected check state", None


def run_upstream_checks() -> int:
    now = datetime.now()
    two_weeks_ago = (now - timedelta(days=14)).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")

    print(f"Checking live Riigikogu upstream endpoints ({two_weeks_ago} to {today})\n")
    print(f"{'Status':<8} {'Time':<8} {'Endpoint / Description':<60}")
    print("-" * 80)

    failures: list[str] = []

    # 1. Memberships
    status, dur, err, memberships_data = fetch_and_validate(
        "https://api.riigikogu.ee/api/memberships",
        MembershipItem,
        "memberships",
    )
    print(f"{status:<8} {f'{dur}ms':<8} /api/memberships")
    if err:
        failures.append(err)

    time.sleep(SLEEP_BETWEEN_REQUESTS_SECONDS)

    # Determine current membership number (highest number)
    current_membership = 15
    if memberships_data and isinstance(memberships_data, list):
        try:
            current_membership = max(int(m["number"]) for m in memberships_data if "number" in m)
        except Exception:
            pass

    # 2. Plenary members
    status, dur, err, _ = fetch_and_validate(
        f"https://api.riigikogu.ee/api/plenary-members?status=ALL&membership={current_membership}",
        PlenaryMember,
        f"membership={current_membership}",
    )
    print(f"{status:<8} {f'{dur}ms':<8} /api/plenary-members (membership={current_membership})")
    if err:
        failures.append(err)

    time.sleep(SLEEP_BETWEEN_REQUESTS_SECONDS)

    # 3. Votings list
    votings_url = f"https://api.riigikogu.ee/api/votings?startDate={two_weeks_ago}&endDate={today}"
    status, dur, err, votings_data = fetch_and_validate(
        votings_url,
        VotingsSitting,
        f"{two_weeks_ago}..{today}",
    )
    print(f"{status:<8} {f'{dur}ms':<8} /api/votings (last 14 days)")
    if err:
        failures.append(err)

    time.sleep(SLEEP_BETWEEN_REQUESTS_SECONDS)

    # 4. Voting detail
    sample_voting_uuid = None
    if votings_data and isinstance(votings_data, list):
        for s in votings_data:
            if isinstance(s, dict) and s.get("votings"):
                for v in s["votings"]:
                    if isinstance(v, dict) and v.get("uuid"):
                        sample_voting_uuid = v["uuid"]
                        break
            if sample_voting_uuid:
                break

    # Fallback to a known recent voting if period had no sittings
    if not sample_voting_uuid:
        sample_voting_uuid = "688c290c-cd08-48a1-8d47-e10f8db9d5a8"

    status, dur, err, _ = fetch_and_validate(
        f"https://api.riigikogu.ee/api/votings/{sample_voting_uuid}",
        VotingDetail,
        sample_voting_uuid,
    )
    print(f"{status:<8} {f'{dur}ms':<8} /api/votings/{sample_voting_uuid}")
    if err:
        failures.append(err)

    time.sleep(SLEEP_BETWEEN_REQUESTS_SECONDS)

    # 5. Verbatims list
    steno_url = (
        f"https://api.riigikogu.ee/api/steno/verbatims?startDate={two_weeks_ago}&endDate={today}"
    )
    status, dur, err, verbatims_data = fetch_and_validate(
        steno_url,
        VerbatimSitting,
        f"{two_weeks_ago}..{today}",
    )
    print(f"{status:<8} {f'{dur}ms':<8} /api/steno/verbatims (last 14 days)")
    if err:
        failures.append(err)

    time.sleep(SLEEP_BETWEEN_REQUESTS_SECONDS)

    # 6. Meeting detail
    sample_meeting_code = None
    if verbatims_data and isinstance(verbatims_data, list):
        for vb in verbatims_data:
            if isinstance(vb, dict) and vb.get("link"):
                code = vb["link"].rstrip("/").split("/")[-1].split("?")[0]
                if code and code.isdigit():
                    sample_meeting_code = code
                    break

    # Fallback if no verbatim in 14-day window
    if not sample_meeting_code:
        sample_meeting_code = "202610191500"

    status, dur, err, _ = fetch_and_validate(
        f"https://stenogrammid.riigikogu.ee/api/meeting/{sample_meeting_code}",
        RichMeeting,
        sample_meeting_code,
    )
    print(
        f"{status:<8} {f'{dur}ms':<8} stenogrammid.riigikogu.ee/api/meeting/{sample_meeting_code}"
    )
    if err:
        failures.append(err)

    time.sleep(SLEEP_BETWEEN_REQUESTS_SECONDS)

    # 7. Agenda
    agenda_url = f"https://api.riigikogu.ee/api/agenda/plenary?startDate={two_weeks_ago}&endDate={today}&lang=et"
    status, dur, err, _ = fetch_and_validate(
        agenda_url,
        AgendaPlenary,
        f"{two_weeks_ago}..{today}",
    )
    print(f"{status:<8} {f'{dur}ms':<8} /api/agenda/plenary (last 14 days)")
    if err:
        failures.append(err)

    time.sleep(SLEEP_BETWEEN_REQUESTS_SECONDS)

    # 8. Faction user groups and the members of one faction
    status, dur, err, groups = fetch_and_validate(
        "https://api.riigikogu.ee/api/usergroups?typeCode=FRAKTSIOON&hideInactive=true&lang=ET",
        UserGroupItem,
        "FRAKTSIOON",
    )
    print(f"{status:<8} {f'{dur}ms':<8} /api/usergroups (active factions)")
    if err:
        failures.append(err)

    if groups and isinstance(groups, list):
        time.sleep(SLEEP_BETWEEN_REQUESTS_SECONDS)
        group = groups[0]
        status, dur, err, _ = fetch_and_validate(
            f"https://api.riigikogu.ee/api/usergroups/{group['uuid']}?lang=ET",
            UserGroupDetail,
            group.get("name", group["uuid"]),
            timeout=30.0,
        )
        print(f"{status:<8} {f'{dur}ms':<8} /api/usergroups/{{uuid}} ({group.get('name')})")
        if err:
            failures.append(err)

    print("\n" + "=" * 80)
    if failures:
        print(f"FAILED: {len(failures)} upstream check(s) failed:\n", file=sys.stderr)
        for fail in failures:
            print(f"- {fail}", file=sys.stderr)
        return 1

    print("SUCCESS: All live upstream Riigikogu endpoints match Pydantic schemas.")
    return 0


def main() -> int:
    return run_upstream_checks()


if __name__ == "__main__":
    sys.exit(main())
