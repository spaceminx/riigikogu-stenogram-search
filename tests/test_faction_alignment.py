"""Tests for member faction majority alignment statistics and endpoints."""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.api.main import app
from src.load.database import SessionLocal
from src.load.loader import create_tables
from src.load.migrations import apply_migrations
from src.load.models import Person, Speech, Vote, Voting

client = TestClient(app)


@pytest.fixture(autouse=True, scope="module")
def setup_faction_alignment_db():
    create_tables()
    apply_migrations()
    session = SessionLocal()

    # Create test persons
    test_members = [
        ("mp-main-1", "Mari", "Mänd", "Mari Mänd"),
        ("mp-fa-1", "Ants", "Kask", "Ants Kask"),
        ("mp-fa-2", "Berta", "Tamm", "Berta Tamm"),
        ("mp-fa-3", "Carl", "Kuusk", "Carl Kuusk"),
        ("mp-fa-4", "Diana", "Pärn", "Diana Pärn"),
        ("mp-switcher-1", "Siim", "Vahetaja", "Siim Vahetaja"),
        ("mp-fx-1", "Toomas", "Üks", "Toomas Üks"),
        ("mp-fx-2", "Tiina", "Kaks", "Tiina Kaks"),
        ("mp-fx-3", "Tarmo", "Kolm", "Tarmo Kolm"),
        ("mp-fy-1", "Urmas", "Neli", "Urmas Neli"),
        ("mp-fy-2", "Ulvi", "Viis", "Ulvi Viis"),
        ("mp-fy-3", "Uno", "Kuus", "Uno Kuus"),
    ]
    for p_uuid, fn, ln, full in test_members:
        if not session.query(Person).filter(Person.uuid == p_uuid).first():
            session.add(Person(uuid=p_uuid, first_name=fn, last_name=ln, full_name=full, active=1))

    # 1. Standard votings for same / different / absent / split
    # V1: Same (Faction A has 3 POOLT, main MP is POOLT)
    v1 = Voting(
        uuid="fa-v1-same",
        voting_number=1,
        type="AVALIK",
        description="Eelnõu 1",
        date="2026-05-10",
        start_time="2026-05-10T10:00:00",
        sitting_date="2026-05-10",
        sitting_datetime="2026-05-10T10:00:00",
        membership=15,
        in_favor=50,
        against=10,
        neutral=0,
        abstained=0,
    )
    session.add(v1)
    session.add(
        Vote(
            voting_uuid="fa-v1-same",
            member_uuid="mp-main-1",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v1-same",
            member_uuid="mp-fa-1",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v1-same",
            member_uuid="mp-fa-2",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v1-same",
            member_uuid="mp-fa-3",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )

    # V2: Different (Faction A has 3 POOLT, main MP is VASTU)
    v2 = Voting(
        uuid="fa-v2-diff",
        voting_number=2,
        type="AVALIK",
        description="Eelnõu 2",
        date="2026-05-11",
        start_time="2026-05-11T11:00:00",
        sitting_date="2026-05-11",
        sitting_datetime="2026-05-11T11:00:00",
        membership=15,
        in_favor=45,
        against=15,
        neutral=0,
        abstained=0,
    )
    session.add(v2)
    session.add(
        Vote(
            voting_uuid="fa-v2-diff",
            member_uuid="mp-main-1",
            faction="Fraktsioon A",
            decision="VASTU",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v2-diff",
            member_uuid="mp-fa-1",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v2-diff",
            member_uuid="mp-fa-2",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v2-diff",
            member_uuid="mp-fa-3",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )

    # V3: Absent (Faction A has 3 POOLT, main MP is PUUDUB)
    v3 = Voting(
        uuid="fa-v3-absent",
        voting_number=3,
        type="AVALIK",
        description="Eelnõu 3",
        date="2026-05-12",
        start_time="2026-05-12T12:00:00",
        sitting_date="2026-05-12",
        sitting_datetime="2026-05-12T12:00:00",
        membership=15,
        in_favor=40,
        against=10,
        neutral=0,
        abstained=10,
    )
    session.add(v3)
    session.add(
        Vote(
            voting_uuid="fa-v3-absent",
            member_uuid="mp-main-1",
            faction="Fraktsioon A",
            decision="PUUDUB",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v3-absent",
            member_uuid="mp-fa-1",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v3-absent",
            member_uuid="mp-fa-2",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v3-absent",
            member_uuid="mp-fa-3",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )

    # V4: Split/tie (Faction A has 2 POOLT, 2 VASTU among other members, main MP is POOLT)
    v4 = Voting(
        uuid="fa-v4-split",
        voting_number=4,
        type="AVALIK",
        description="Eelnõu 4",
        date="2026-05-13",
        start_time="2026-05-13T13:00:00",
        sitting_date="2026-05-13",
        sitting_datetime="2026-05-13T13:00:00",
        membership=15,
        in_favor=30,
        against=30,
        neutral=0,
        abstained=0,
    )
    session.add(v4)
    session.add(
        Vote(
            voting_uuid="fa-v4-split",
            member_uuid="mp-main-1",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v4-split",
            member_uuid="mp-fa-1",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v4-split",
            member_uuid="mp-fa-2",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v4-split",
            member_uuid="mp-fa-3",
            faction="Fraktsioon A",
            decision="VASTU",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v4-split",
            member_uuid="mp-fa-4",
            faction="Fraktsioon A",
            decision="VASTU",
        )
    )

    # V5: Too few (only 2 other members of Faction A with a position)
    v5 = Voting(
        uuid="fa-v5-toofew",
        voting_number=5,
        type="AVALIK",
        description="Eelnõu 5",
        date="2026-05-14",
        start_time="2026-05-14T14:00:00",
        sitting_date="2026-05-14",
        sitting_datetime="2026-05-14T14:00:00",
        membership=15,
        in_favor=20,
        against=10,
        neutral=0,
        abstained=0,
    )
    session.add(v5)
    session.add(
        Vote(
            voting_uuid="fa-v5-toofew",
            member_uuid="mp-main-1",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v5-toofew",
            member_uuid="mp-fa-1",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v5-toofew",
            member_uuid="mp-fa-2",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )

    # 2. Leave-one-out voting:
    # 3 other members: 2 POOLT, 1 VASTU.
    # Main MP votes VASTU.
    # Without leave-one-out: 2 POOLT vs 2 VASTU -> tie/split.
    # With leave-one-out: other members have 2 POOLT out of 3 -> POOLT strict majority!
    # Main MP is VASTU -> result: "different".
    v_loo = Voting(
        uuid="fa-v-loo",
        voting_number=6,
        type="AVALIK",
        description="Eelnõu Leave-One-Out",
        date="2026-05-15",
        start_time="2026-05-15T15:00:00",
        sitting_date="2026-05-15",
        sitting_datetime="2026-05-15T15:00:00",
        membership=15,
        in_favor=35,
        against=20,
        neutral=0,
        abstained=0,
    )
    session.add(v_loo)
    session.add(
        Vote(
            voting_uuid="fa-v-loo",
            member_uuid="mp-main-1",
            faction="Fraktsioon A",
            decision="VASTU",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v-loo",
            member_uuid="mp-fa-1",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v-loo",
            member_uuid="mp-fa-2",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v-loo",
            member_uuid="mp-fa-3",
            faction="Fraktsioon A",
            decision="VASTU",
        )
    )

    # 3. EI_HAALETANUD as collective faction position
    v_notvoted = Voting(
        uuid="fa-v-notvoted",
        voting_number=7,
        type="AVALIK",
        description="Eelnõu Mittehääletamine",
        date="2026-05-16",
        start_time="2026-05-16T16:00:00",
        sitting_date="2026-05-16",
        sitting_datetime="2026-05-16T16:00:00",
        membership=15,
        in_favor=10,
        against=5,
        neutral=0,
        abstained=50,
    )
    session.add(v_notvoted)
    session.add(
        Vote(
            voting_uuid="fa-v-notvoted",
            member_uuid="mp-main-1",
            faction="Fraktsioon A",
            decision="EI_HAALETANUD",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v-notvoted",
            member_uuid="mp-fa-1",
            faction="Fraktsioon A",
            decision="EI_HAALETANUD",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v-notvoted",
            member_uuid="mp-fa-2",
            faction="Fraktsioon A",
            decision="EI_HAALETANUD",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v-notvoted",
            member_uuid="mp-fa-3",
            faction="Fraktsioon A",
            decision="EI_HAALETANUD",
        )
    )

    # 4. Technical and SALAJANE votings
    v_tech = Voting(
        uuid="fa-v-tech",
        voting_number=8,
        type="AVALIK",
        description="Tehniline kirje",
        date="2026-05-17",
        start_time="2026-05-17T17:00:00",
        membership=15,
        in_favor=0,
        against=0,
        neutral=0,
        abstained=101,
    )
    session.add(v_tech)
    session.add(
        Vote(
            voting_uuid="fa-v-tech",
            member_uuid="mp-main-1",
            faction="Fraktsioon A",
            decision="EI_HAALETANUD",
        )
    )

    v_secret = Voting(
        uuid="fa-v-secret",
        voting_number=9,
        type="SALAJANE",
        description="Salajane hääletus",
        date="2026-05-18",
        start_time="2026-05-18T18:00:00",
        membership=15,
        in_favor=50,
        against=20,
        neutral=0,
        abstained=0,
    )
    session.add(v_secret)
    session.add(
        Vote(
            voting_uuid="fa-v-secret",
            member_uuid="mp-main-1",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )

    # 5. Mid-term faction switch and non-faction
    v_sw1 = Voting(
        uuid="fa-v-sw1",
        voting_number=10,
        type="AVALIK",
        description="Vahetuse hääletus 1",
        date="2026-06-01",
        start_time="2026-06-01T10:00:00",
        membership=15,
        in_favor=40,
        against=10,
        neutral=0,
        abstained=0,
    )
    session.add(v_sw1)
    # Faction X voted POOLT, switcher voted POOLT
    session.add(
        Vote(
            voting_uuid="fa-v-sw1",
            member_uuid="mp-switcher-1",
            faction="Fraktsioon X",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v-sw1",
            member_uuid="mp-fx-1",
            faction="Fraktsioon X",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v-sw1",
            member_uuid="mp-fx-2",
            faction="Fraktsioon X",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v-sw1",
            member_uuid="mp-fx-3",
            faction="Fraktsioon X",
            decision="POOLT",
        )
    )

    v_sw2 = Voting(
        uuid="fa-v-sw2",
        voting_number=11,
        type="AVALIK",
        description="Vahetuse hääletus 2",
        date="2026-06-02",
        start_time="2026-06-02T10:00:00",
        membership=15,
        in_favor=20,
        against=30,
        neutral=0,
        abstained=0,
    )
    session.add(v_sw2)
    # Switcher is now in Faction Y. Faction Y votes VASTU, switcher votes VASTU
    session.add(
        Vote(
            voting_uuid="fa-v-sw2",
            member_uuid="mp-switcher-1",
            faction="Fraktsioon Y",
            decision="VASTU",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v-sw2",
            member_uuid="mp-fy-1",
            faction="Fraktsioon Y",
            decision="VASTU",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v-sw2",
            member_uuid="mp-fy-2",
            faction="Fraktsioon Y",
            decision="VASTU",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v-sw2",
            member_uuid="mp-fy-3",
            faction="Fraktsioon Y",
            decision="VASTU",
        )
    )
    # Also Faction X was POOLT on this vote
    session.add(
        Vote(
            voting_uuid="fa-v-sw2",
            member_uuid="mp-fx-1",
            faction="Fraktsioon X",
            decision="POOLT",
        )
    )

    v_sw3 = Voting(
        uuid="fa-v-sw3",
        voting_number=12,
        type="AVALIK",
        description="Fraktsioonita hääletus",
        date="2026-06-03",
        start_time="2026-06-03T10:00:00",
        membership=15,
        in_favor=50,
        against=0,
        neutral=0,
        abstained=0,
    )
    session.add(v_sw3)
    session.add(
        Vote(
            voting_uuid="fa-v-sw3",
            member_uuid="mp-switcher-1",
            faction="Fraktsiooni mittekuuluvad Riigikogu liikmed",
            decision="POOLT",
        )
    )

    # 6. Membership filter voting (membership 14)
    v_mem14 = Voting(
        uuid="fa-v-mem14",
        voting_number=13,
        type="AVALIK",
        description="14. koosseisu eelnõu",
        date="2021-02-15",
        start_time="2021-02-15T10:00:00",
        membership=14,
        in_favor=55,
        against=10,
        neutral=0,
        abstained=0,
    )
    session.add(v_mem14)
    session.add(
        Vote(
            voting_uuid="fa-v-mem14",
            member_uuid="mp-main-1",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v-mem14",
            member_uuid="mp-fa-1",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v-mem14",
            member_uuid="mp-fa-2",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v-mem14",
            member_uuid="mp-fa-3",
            faction="Fraktsioon A",
            decision="POOLT",
        )
    )

    # Add a matching speech so session_source_file exists for fa-v2-diff
    session.add(
        Speech(
            id=999888,
            source_file="2026-05-11_1100.api",
            date="2026-05-11",
            time="11:00:00",
            source_url="https://api.riigikogu.ee/test",
            speaker="Mari Mänd",
            speaker_uuid="mp-main-1",
            text="Sõnavõtu tekst",
        )
    )

    session.commit()
    session.close()


def test_unknown_uuid_404():
    resp1 = client.get("/persons/non-existent-uuid/faction-alignment")
    assert resp1.status_code == 404
    assert resp1.json()["detail"] == "Saadikut ei leitud."

    resp2 = client.get("/persons/non-existent-uuid/faction-alignment/differences")
    assert resp2.status_code == 404
    assert resp2.json()["detail"] == "Saadikut ei leitud."


def test_faction_alignment_same_different_absent_split():
    # mp-main-1 has:
    # V1: same
    # V2: different
    # V3: absent
    # V4: split
    # V5: too_few
    # V_loo: different
    # V_notvoted: same
    # V_mem14: same (membership 14)
    # Technical & secret are ignored.
    resp = client.get("/persons/mp-main-1/faction-alignment?membership=15")
    assert resp.status_code == 200
    data = resp.json()

    # In membership 15:
    # same: V1, V_notvoted = 2
    # different: V2, V_loo = 2
    # share_same = 2 / (2 + 2) * 100 = 50.0
    assert data["same"] == 2
    assert data["different"] == 2
    assert data["share_same"] == 50.0

    # Excluded:
    # absent: V3 = 1
    # split: V4 = 1
    # too_few: V5 = 1
    # no_faction: 0
    assert data["excluded"]["absent"] == 1
    assert data["excluded"]["split"] == 1
    assert data["excluded"]["too_few"] == 1
    assert data["excluded"]["no_faction"] == 0


def test_leave_one_out():
    # On fa-v-loo: other members are 2 POOLT, 1 VASTU.
    # Strict majority among other members is POOLT (2/3 > 0.5).
    # mp-main-1 voted VASTU -> classified as different!
    # Without leave-one-out, it would be 2 POOLT vs 2 VASTU (split).
    # Since it is counted in differences, let's verify it appears in /differences:
    resp = client.get("/persons/mp-main-1/faction-alignment/differences?membership=15")
    assert resp.status_code == 200
    diffs = resp.json()
    uuids = [d["voting_uuid"] for d in diffs]
    assert "fa-v-loo" in uuids
    loo_item = next(d for d in diffs if d["voting_uuid"] == "fa-v-loo")
    assert loo_item["member_decision"] == "VASTU"
    assert loo_item["faction_position"] == "POOLT"


def test_ei_haaletanud_as_collective_faction_position():
    # On fa-v-notvoted: other members are 3 EI_HAALETANUD.
    # mp-main-1 is EI_HAALETANUD.
    # Faction position is EI_HAALETANUD, result is same.
    resp = client.get("/persons/mp-main-1/faction-alignment?membership=15")
    assert resp.status_code == 200
    data = resp.json()
    # If EI_HAALETANUD was not treated as a position, V_notvoted would have had 0 positions -> too_few.
    # But because it is a position, same is 2 (V1 + V_notvoted)
    assert data["same"] == 2


def test_technical_and_salajane_ignored():
    resp = client.get("/persons/mp-main-1/faction-alignment?membership=15")
    assert resp.status_code == 200
    data = resp.json()

    total_accounted = (
        data["same"]
        + data["different"]
        + data["excluded"]["absent"]
        + data["excluded"]["split"]
        + data["excluded"]["too_few"]
        + data["excluded"]["no_faction"]
    )
    # Membership 15 has 7 public non-technical votings for mp-main-1:
    # V1 (same), V2 (different), V3 (absent), V4 (split), V5 (too_few), V_loo (different), V_notvoted (same).
    # fa-v-tech and fa-v-secret are completely ignored.
    assert total_accounted == 7


def test_mid_term_faction_switch_and_no_faction():
    resp = client.get("/persons/mp-switcher-1/faction-alignment?membership=15")
    assert resp.status_code == 200
    data = resp.json()

    # V_sw1: Faction X voted POOLT, switcher voted POOLT -> same (1)
    # V_sw2: Faction Y voted VASTU, switcher voted VASTU -> same (1)
    # V_sw3: Fraktsiooni mittekuuluvad -> no_faction (1)
    assert data["same"] == 2
    assert data["different"] == 0
    assert data["share_same"] == 100.0
    assert data["excluded"]["no_faction"] == 1


def test_membership_filter():
    # mp-main-1 has 7 votings in 15, and 1 voting in 14 (fa-v-mem14 which is same).
    resp_all = client.get("/persons/mp-main-1/faction-alignment?membership=all")
    assert resp_all.status_code == 200
    data_all = resp_all.json()
    assert data_all["same"] == 3  # 2 in mem15 + 1 in mem14
    assert data_all["different"] == 2
    assert len(data_all["by_membership"]) == 2
    mems = [m["membership"] for m in data_all["by_membership"]]
    assert mems == [15, 14]

    resp_14 = client.get("/persons/mp-main-1/faction-alignment?membership=14")
    assert resp_14.status_code == 200
    data_14 = resp_14.json()
    assert data_14["same"] == 1
    assert data_14["different"] == 0
    assert data_14["share_same"] == 100.0

    # Unknown membership raises 422
    resp_bad = client.get("/persons/mp-main-1/faction-alignment?membership=999")
    assert resp_bad.status_code == 422


def test_differences_endpoint_order_and_paging():
    # mp-main-1 in mem 15 has 2 differences:
    # fa-v-loo (2026-05-15) and fa-v2-diff (2026-05-11).
    # Newest first: fa-v-loo should be first, then fa-v2-diff.
    resp = client.get(
        "/persons/mp-main-1/faction-alignment/differences?membership=15&limit=50&offset=0"
    )
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) == 2
    assert items[0]["voting_uuid"] == "fa-v-loo"
    assert items[1]["voting_uuid"] == "fa-v2-diff"
    assert items[1]["session_source_file"] == "2026-05-11_1100.api"
    assert items[1]["sitting_date"] == "2026-05-11"
    assert items[1]["member_decision"] == "VASTU"
    assert items[1]["faction_position"] == "POOLT"
    assert items[1]["faction"] == "Fraktsioon A"

    # Test paging limit=1 offset=0
    resp_p1 = client.get(
        "/persons/mp-main-1/faction-alignment/differences?membership=15&limit=1&offset=0"
    )
    assert len(resp_p1.json()) == 1
    assert resp_p1.json()[0]["voting_uuid"] == "fa-v-loo"

    # Test paging limit=1 offset=1
    resp_p2 = client.get(
        "/persons/mp-main-1/faction-alignment/differences?membership=15&limit=1&offset=1"
    )
    assert len(resp_p2.json()) == 1
    assert resp_p2.json()[0]["voting_uuid"] == "fa-v2-diff"


def test_voting_detail_majority_position():
    # Test /votings/{uuid} on fa-v1-same (Faction A has 4 POOLT)
    resp1 = client.get("/votings/fa-v1-same")
    assert resp1.status_code == 200
    by_faction = resp1.json()["by_faction"]
    fac_a = next(f for f in by_faction if f["faction"] == "Fraktsioon A")
    assert fac_a["majority_position"] == "POOLT"

    # Test on fa-v4-split: Faction A has 3 POOLT, 2 VASTU -> strict majority is POOLT (3/5 > 2.5)
    resp4 = client.get("/votings/fa-v4-split")
    assert resp4.status_code == 200
    fac_a_4 = next(f for f in resp4.json()["by_faction"] if f["faction"] == "Fraktsioon A")
    assert fac_a_4["majority_position"] == "POOLT"

    # Test on a voting where a faction is strictly split:
    session = SessionLocal()
    v_tie = Voting(
        uuid="fa-v-pure-tie",
        voting_number=99,
        type="AVALIK",
        description="Viigiline fraktsioon",
        date="2026-07-01",
        start_time="2026-07-01T10:00:00",
        membership=15,
        in_favor=2,
        against=2,
        neutral=0,
        abstained=0,
    )
    session.add(v_tie)
    session.add(
        Vote(
            voting_uuid="fa-v-pure-tie",
            member_uuid="mp-fa-1",
            faction="Viik Fraktsioon",
            decision="POOLT",
        )
    )
    session.add(
        Vote(
            voting_uuid="fa-v-pure-tie",
            member_uuid="mp-fa-2",
            faction="Viik Fraktsioon",
            decision="VASTU",
        )
    )
    session.commit()
    session.close()

    resp_tie = client.get("/votings/fa-v-pure-tie")
    assert resp_tie.status_code == 200
    fac_tie = next(f for f in resp_tie.json()["by_faction"] if f["faction"] == "Viik Fraktsioon")
    assert fac_tie["majority_position"] is None
