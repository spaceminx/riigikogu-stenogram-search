import json
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient

from config import OUTPUT_DIR_PROCESSED
from src.api.main import app
from src.load.database import SessionLocal
from src.load.loader import create_tables
from src.load.models import Attendance, Lemma, Person, Speech, SpeechTerm

client = TestClient(app)


@pytest.fixture(autouse=True, scope="session")
def setup_test_database():
    """Ensure database schema and test data exist in CI environment."""
    create_tables()
    session = SessionLocal()
    if session.query(Attendance).count() == 0:
        test_records = [
            Attendance(
                session_date="2023-05-01T10:00:00",
                voting_uuid="test-uuid-1",
                member_name="Jaan Tamm",
                faction="Eesti 200 fraktsioon",
                status="KOHAL",
            ),
            Attendance(
                session_date="2023-05-01T10:00:00",
                voting_uuid="test-uuid-1",
                member_name="Kati Kask",
                faction="Isamaa fraktsioon",
                status="PUUDUB",
            ),
            Attendance(
                session_date="2021-05-01T10:00:00",
                voting_uuid="test-uuid-2",
                member_name="Jaan Tamm",
                faction="Eesti Keskerakonna fraktsioon",
                status="KOHAL",
            ),
        ]
        session.add_all(test_records)
        session.commit()

    factions_file = os.path.join(OUTPUT_DIR_PROCESSED, "factions_map.json")
    if not os.path.exists(factions_file):
        os.makedirs(OUTPUT_DIR_PROCESSED, exist_ok=True)
        mock_factions = {
            "Jaan Tamm": [
                {
                    "faction": "Eesti 200 fraktsioon",
                    "start": "2023-04-10",
                    "end": "2099-12-31",
                }
            ],
            "Kati Kask": [
                {
                    "faction": "Isamaa fraktsioon",
                    "start": "2023-04-10",
                    "end": "2099-12-31",
                }
            ],
        }
        with open(factions_file, "w", encoding="utf-8") as f:
            json.dump(mock_factions, f)

    if session.query(Speech).count() == 0:
        s1 = Speech(
            id=1,
            date="2024-01-15",
            time="1500",
            source_file="2024-01-15_1500.api",
            source_url="https://stenogrammid.riigikogu.ee/202401151500",
            speaker="Kaja Kallas",
            speaker_role="Peaminister",
            speaker_faction="Eesti Reformierakonna fraktsioon",
            text="Kliimamuutused ja energeetika on olulised.",
            text_lemmas="kliimamuutus ja energeetika olema oluline",
        )
        s2 = Speech(
            id=2,
            date="2021-02-10",
            time="1500",
            source_file="2021-02-10_1500.api",
            source_url="https://stenogrammid.riigikogu.ee/202102101500",
            speaker="Jüri Ratas",
            speaker_role="Riigikogu esimees",
            speaker_faction="Eesti Keskerakonna fraktsioon",
            text="Kliimamuutused nõuavad tähelepanu.",
            text_lemmas="kliimamuutus nõudma tähelepanu",
        )
        session.add_all([s1, s2])
        session.flush()

        l1 = Lemma(id=1, lemma="kliimamuutus")
        l2 = Lemma(id=2, lemma="energeetika")
        session.add_all([l1, l2])
        session.flush()

        t1 = SpeechTerm(speech_id=s1.id, lemma_id=l1.id, count=1)
        t2 = SpeechTerm(speech_id=s1.id, lemma_id=l2.id, count=1)
        t3 = SpeechTerm(speech_id=s2.id, lemma_id=l1.id, count=1)
        session.add_all([t1, t2, t3])
        session.commit()

    session.close()


def test_root_status():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_dashboard_overview_shape():
    response = client.get("/overview")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["speakers"], list)
    assert isinstance(data["sessions"], list)
    if data["speakers"]:
        assert {"speaker", "faction", "count"} <= data["speakers"][0].keys()
    if data["sessions"]:
        assert {"date", "source_url", "topics"} <= data["sessions"][0].keys()


def test_plenary_session_calendar_and_transcript():
    calendar_response = client.get("/sessions/dates")
    assert calendar_response.status_code == 200
    dates = calendar_response.json()["dates"]
    assert isinstance(dates, list)
    assert dates == sorted(dates, reverse=True)

    if dates:
        session_response = client.get(f"/sessions/{dates[0]}")
        assert session_response.status_code == 200
        session_data = session_response.json()
        assert session_data["date"] == dates[0]
        assert session_data["count"] == len(session_data["results"])
        if session_data["results"]:
            assert {
                "speaker",
                "date",
                "text",
                "source_url",
                "agenda_title",
                "video_url",
            } <= session_data["results"][0].keys()


def test_search_missing_query():
    # Calling /search without 'q' parameter should return 422 Unprocessable Entity
    response = client.get("/search")
    assert response.status_code == 422


def test_search_empty_query():
    # Calling /search with empty 'q' should return 422 (min_length=1)
    response = client.get("/search?q=")
    assert response.status_code == 422


def test_search_query_too_long():
    # Calling /search with >1000 characters should return 422 (max_length=1000)
    huge_query = "a" * 1001
    response = client.get(f"/search?q={huge_query}")
    assert response.status_code == 422


def test_search_activity_invalid_interval():
    # Invalid interval parameter should return 400 Bad Request
    response = client.get("/search/activity?q=mets&interval=hourly")
    assert response.status_code == 400
    assert "Intervall peab olema" in response.json()["detail"]


def test_search_only_stopwords():
    # Calling /search with only stopwords should return 400 Bad Request
    response = client.get("/search?q=ja")
    assert response.status_code == 400
    assert "liiga üldine" in response.json()["detail"]

    response_multi = client.get("/search?q=see on, ning")
    assert response_multi.status_code == 400
    assert "liiga üldine" in response_multi.json()["detail"]


def test_search_activity_only_stopwords():
    response = client.get("/search/activity?q=on")
    assert response.status_code == 400
    assert "liiga üldine" in response.json()["detail"]


def test_search_speakers_only_stopwords():
    response = client.get("/search/speakers?q=see")
    assert response.status_code == 400
    assert "liiga üldine" in response.json()["detail"]


def test_search_with_filters():
    # Search with membership filter (15 vs 14)
    res_xv = client.get("/search?q=kliimamuutus&membership=15")
    assert res_xv.status_code == 200
    data_xv = res_xv.json()
    assert "results" in data_xv
    assert "total_count" in data_xv
    if data_xv["results"]:
        assert {
            "id",
            "speaker",
            "speaker_role",
            "speaker_faction",
            "text",
            "count",
            "matched_words",
            "date",
            "time",
            "source_file",
            "source_url",
            "agenda_title",
            "video_url",
        } <= data_xv["results"][0].keys()
    for r in data_xv["results"]:
        assert r["date"] >= "2023-04-10"

    res_xiv = client.get("/search?q=kliimamuutus&membership=14")
    assert res_xiv.status_code == 200
    data_xiv = res_xiv.json()
    for r in data_xiv["results"]:
        assert r["date"] < "2023-04-10"


def test_search_with_speaker_and_faction_filter():
    res_speaker = client.get("/search?q=kliimamuutus&speaker=Kaja")
    assert res_speaker.status_code == 200
    data = res_speaker.json()
    for r in data["results"]:
        assert "Kaja" in r["speaker"]


def test_search_pagination():
    res = client.get("/search?q=kliimamuutus&limit=1&offset=0")
    assert res.status_code == 200
    data = res.json()
    assert len(data["results"]) <= 1
    assert data["limit"] == 1
    assert data["offset"] == 0


def test_search_sorting():
    # Sort date_desc (default)
    res_desc = client.get("/search?q=kliimamuutus&sort_by=date_desc")
    assert res_desc.status_code == 200
    data_desc = res_desc.json()["results"]
    if len(data_desc) >= 2:
        for i in range(len(data_desc) - 1):
            assert data_desc[i]["date"] >= data_desc[i + 1]["date"]

    # Sort date_asc
    res_asc = client.get("/search?q=kliimamuutus&sort_by=date_asc")
    assert res_asc.status_code == 200
    data_asc = res_asc.json()["results"]
    if len(data_asc) >= 2:
        for i in range(len(data_asc) - 1):
            assert data_asc[i]["date"] <= data_asc[i + 1]["date"]

    # Sort match_count_desc
    res_freq = client.get("/search?q=kliimamuutus, energeetika&sort_by=match_count_desc")
    assert res_freq.status_code == 200
    data_freq = res_freq.json()["results"]
    if len(data_freq) >= 2:
        for i in range(len(data_freq) - 1):
            assert data_freq[i]["count"] >= data_freq[i + 1]["count"]

    # Invalid sort_by returns 422
    res_invalid = client.get("/search?q=kliimamuutus&sort_by=invalid_sort")
    assert res_invalid.status_code == 422


def test_speech_context():
    # Get first speech id from search
    search_res = client.get("/search?q=kliimamuutus&limit=1")
    if search_res.status_code == 200 and search_res.json()["results"]:
        speech_id = search_res.json()["results"][0]["id"]
        ctx_res = client.get(f"/speeches/{speech_id}/context")
        assert ctx_res.status_code == 200
        ctx_data = ctx_res.json()
        assert ctx_data["target_speech_id"] == speech_id
        assert {
            "target_speech_id",
            "date",
            "time",
            "source_file",
            "source_url",
            "agenda_title",
            "video_url",
            "total_speeches",
            "speeches",
        } <= ctx_data.keys()
        assert len(ctx_data["speeches"]) >= 1
        assert {
            "id",
            "date",
            "time",
            "speaker",
            "speaker_role",
            "speaker_faction",
            "text",
            "source_url",
            "agenda_title",
            "video_url",
            "matched_words",
        } <= ctx_data["speeches"][0].keys()

    # 404 test for non-existent speech
    not_found_res = client.get("/speeches/99999999/context")
    assert not_found_res.status_code == 404


def test_search_export():
    # Test CSV export
    res_csv = client.get("/search/export?q=kliimamuutus&format=csv")
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    assert "attachment" in res_csv.headers["content-disposition"]

    # Test JSON export
    res_json = client.get("/search/export?q=kliimamuutus&format=json")
    assert res_json.status_code == 200
    assert "application/json" in res_json.headers["content-type"]

    # Test invalid format
    res_inv = client.get("/search/export?q=kliimamuutus&format=xml")
    assert res_inv.status_code == 400


def test_attendance_stats_default():
    response = client.get("/attendance/stats")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        item = data[0]
        assert "member_name" in item
        assert "faction" in item
        assert "total_sessions" in item
        assert "present_sessions" in item
        assert "attendance_percentage" in item


def test_attendance_stats_membership_filter():
    response_xv = client.get("/attendance/stats?membership=15")
    assert response_xv.status_code == 200
    response_xiv = client.get("/attendance/stats?membership=14")
    assert response_xiv.status_code == 200
    response_all = client.get("/attendance/stats?membership=all")
    assert response_all.status_code == 200


def test_attendance_stats_faction_filter():
    response = client.get("/attendance/stats?faction=Isamaa fraktsioon")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    for item in data:
        assert item["faction"] == "Isamaa fraktsioon"


def test_attendance_stats_active_only():
    response = client.get("/attendance/stats?membership=15&active_only=true")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 101


def test_attendance_factions_stats():
    response = client.get("/attendance/factions?membership=15")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        item = data[0]
        assert "faction" in item
        assert "member_count" in item
        assert "total_sessions" in item
        assert "present_sessions" in item
        assert "attendance_percentage" in item


def test_attendance_factions_list():
    response = client.get("/attendance/factions/list?membership=15")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert "Eesti 200 fraktsioon" in data


def test_attendance_stats_active_only_faction_filter():
    response = client.get(
        "/attendance/stats?membership=15&active_only=true&faction=Eesti 200 fraktsioon"
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    for item in data:
        assert item["faction"] == "Eesti 200 fraktsioon"
        assert "total_sessions" in item
        assert "present_sessions" in item
        assert "attendance_percentage" in item


def test_attendance_factions_stats_active_only():
    response = client.get("/attendance/factions?membership=15&active_only=true")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    for item in data:
        assert "faction" in item
        assert "member_count" in item
        assert item["member_count"] >= 1
        assert "total_sessions" in item
        assert "present_sessions" in item
        assert "attendance_percentage" in item


def test_clean_html_unescapes_entities():
    from scripts.fetch_stenograms_api import clean_html

    raw = "<p>P&auml;evakord &amp; arutelu&nbsp;punkt &quot;Eeln&otilde;u 123&quot;</p>"
    cleaned = clean_html(raw)
    assert cleaned == 'Päevakord & arutelu punkt "Eelnõu 123"'


def test_format_stenogram_url_and_normalization():
    from scripts.fetch_stenograms_api import format_stenogram_url
    from src.api.search import normalize_source_url

    url = format_stenogram_url("202609171000", agenda_id=1319712)
    assert url == "https://stenogrammid.riigikogu.ee/et/202609171000#PKP-1319712"

    raw_url = "https://stenogrammid.riigikogu.ee/202609171000#PKP-1319712"
    normalized = normalize_source_url(raw_url)
    assert normalized == "https://stenogrammid.riigikogu.ee/et/202609171000#PKP-1319712"


def test_search_export_special_characters():
    # Test CSV export with Estonian umlauts and special characters
    res_csv = client.get("/search/export?q=õpetaja&format=csv")
    assert res_csv.status_code == 200
    assert "filename*=UTF-8''" in res_csv.headers["content-disposition"]

    # Test JSON export with special characters (š, ž)
    res_json = client.get("/search/export?q=šüžee&format=json")
    assert res_json.status_code == 200
    assert "filename*=UTF-8''" in res_json.headers["content-disposition"]


def test_search_date_validation():
    # Invalid date format should return 422
    res_invalid_format = client.get("/search?q=kliimamuutus&start_date=2024-1-1")
    assert res_invalid_format.status_code == 422

    # start_date > end_date should return 400
    res_invalid_range = client.get(
        "/search?q=kliimamuutus&start_date=2024-05-01&end_date=2024-01-01"
    )
    assert res_invalid_range.status_code == 400
    assert "hilisem" in res_invalid_range.json()["detail"]


def test_alphanumeric_lemmatization():
    from src.transform.lemmatizer import lemmatize_text

    text = "COVID-19 kriis ja 5G võrk ning e-riik."
    lemmas = lemmatize_text(text)
    assert "5g" in lemmas
    assert "riik" in lemmas


def test_speech_type_filtering():
    from scripts.fetch_stenograms_api import IGNORED_SPEAKER_NAMES, IGNORED_SPEECH_TYPES

    assert "PRESENCE_CHECK" in IGNORED_SPEECH_TYPES
    assert "SESSION_END" in IGNORED_SPEECH_TYPES
    assert "SPEECH" not in IGNORED_SPEECH_TYPES
    assert "istung lõppes" in IGNORED_SPEAKER_NAMES


def test_split_speaker_role():
    from scripts.fetch_stenograms_api import split_speaker_role

    name, role = split_speaker_role("Õiguskantsler Ülle Madise")
    assert name == "Ülle Madise"
    assert role == "Õiguskantsler"

    name, role = split_speaker_role("Riigikontrolör Janar Holm")
    assert name == "Janar Holm"
    assert role == "Riigikontrolör"

    name, role = split_speaker_role("Peaminister Kaja Kallas")
    assert name == "Kaja Kallas"
    assert role == "Peaminister"

    name, role = split_speaker_role("Jüri Ratas")
    assert name == "Jüri Ratas"
    assert role is None


def test_session_speeches_ordering():
    from src.api.search import get_session_speeches

    session = SessionLocal()
    s_early = Speech(
        id=999,
        date="2025-05-20",
        time="1000",
        source_file="2025-05-20_1000.api",
        source_url="https://stenogrammid.riigikogu.ee/202505201000",
        speaker="Test Speaker",
        text="Hommikune kõne.",
    )
    s_late = Speech(
        id=555,
        date="2025-05-20",
        time="1400",
        source_file="2025-05-20_1400.api",
        source_url="https://stenogrammid.riigikogu.ee/202505201400",
        speaker="Test Speaker",
        text="Pärastlõunane kõne.",
    )
    session.add_all([s_early, s_late])
    session.commit()
    session.close()

    speeches = get_session_speeches("2025-05-20")
    assert len(speeches) == 2
    assert speeches[0]["time"] == "1000"
    assert speeches[0]["id"] == 999
    assert speeches[1]["time"] == "1400"
    assert speeches[1]["id"] == 555


def test_attendance_membership_end_date_cutoff():
    from src.api.attendance import get_faction_attendance_stats

    session = SessionLocal()
    att = Attendance(
        session_date="2023-04-09T15:00:00",
        voting_uuid="test-uuid-cutoff",
        member_name="Jüri Ratas",
        faction="Eesti Keskerakonna fraktsioon",
        status="KOHAL",
    )
    session.add(att)
    session.commit()
    session.close()

    stats = get_faction_attendance_stats(membership="14", active_only=False)
    kesk = next((s for s in stats if "Keskerakonna" in s["faction"]), None)
    assert kesk is not None
    assert kesk["total_sessions"] == 2


def test_list_memberships():
    res = client.get("/memberships")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    m15 = next((m for m in data if m["id"] == "15"), None)
    m14 = next((m for m in data if m["id"] == "14"), None)
    assert m15 is not None
    assert m14 is not None
    assert m15["start_date"] == "2023-04-10"
    assert m14["start_date"] == "2019-04-04"


def test_list_and_get_persons():
    session = SessionLocal()
    p1 = Person(
        uuid="uuid-person-1",
        first_name="Kaja",
        last_name="Kallas",
        full_name="Kaja Kallas",
        gender="FEMALE",
        date_of_birth="1977-06-18",
        email="kaja.kallas@riigikogu.ee",
        photo_url="https://api.riigikogu.ee/api/files/kaja/download",
        electoral_district="Harju- ja Raplamaa",
        seniority_days=1800,
        active=0,
    )
    p2 = Person(
        uuid="uuid-person-2",
        first_name="Hanno",
        last_name="Pevkur",
        full_name="Hanno Pevkur",
        gender="MALE",
        date_of_birth="1977-04-02",
        email="hanno.pevkur@riigikogu.ee",
        photo_url="https://api.riigikogu.ee/api/files/hanno/download",
        electoral_district="Võru-, Valga- ja Põlvamaa",
        seniority_days=2500,
        active=1,
    )
    session.merge(p1)
    session.merge(p2)
    session.commit()
    session.close()

    # List all
    res = client.get("/persons")
    assert res.status_code == 200
    data = res.json()
    assert data["total_count"] >= 2
    names = [p["full_name"] for p in data["results"]]
    assert "Kaja Kallas" in names
    assert "Hanno Pevkur" in names

    # Filter active_only
    res_active = client.get("/persons?active_only=true")
    assert res_active.status_code == 200
    active_names = [p["full_name"] for p in res_active.json()["results"]]
    assert "Hanno Pevkur" in active_names
    assert "Kaja Kallas" not in active_names

    # Search filter
    res_search = client.get("/persons?search=kallas")
    assert res_search.status_code == 200
    search_names = [p["full_name"] for p in res_search.json()["results"]]
    assert "Kaja Kallas" in search_names

    # Get single person
    res_single = client.get("/persons/uuid-person-1")
    assert res_single.status_code == 200
    p_data = res_single.json()
    assert p_data["uuid"] == "uuid-person-1"
    assert p_data["full_name"] == "Kaja Kallas"
    assert p_data["electoral_district"] == "Harju- ja Raplamaa"
    assert "factions" in p_data
    assert "speeches_count" in p_data

    # Not found
    res_404 = client.get("/persons/non-existent-uuid")
    assert res_404.status_code == 404


def test_get_speech_by_id_and_external_id():
    session = SessionLocal()
    sp = Speech(
        id=777888,
        date="2026-06-01",
        time="1100",
        source_file="2026-06-01_1100.api",
        source_url="https://stenogrammid.riigikogu.ee/et/202606011100",
        agenda_title="Oluline teema",
        speaker="Hanno Pevkur",
        speaker_uuid="uuid-person-2",
        speech_type="SPEECH",
        external_id=98765432,
        start_time="2026-06-01T11:00:10.000",
        end_time="2026-06-01T11:02:10.000",
        duration_seconds=120,
        text="Kõne kaitsepoliitikast riigikogus.",
        text_lemmas="kõne kaitsepoliitika riigikogu",
        status="EDITED",
    )
    session.merge(sp)
    session.commit()
    session.close()

    # Lookup by internal id
    res_id = client.get("/speeches/777888")
    assert res_id.status_code == 200
    data_id = res_id.json()
    assert data_id["id"] == 777888
    assert data_id["external_id"] == 98765432
    assert data_id["speaker_uuid"] == "uuid-person-2"
    assert data_id["speech_type"] == "SPEECH"
    assert data_id["duration_seconds"] == 120

    # Lookup by external_id (permalink)
    res_ext = client.get("/speeches/98765432")
    assert res_ext.status_code == 200
    data_ext = res_ext.json()
    assert data_ext["id"] == 777888
    assert data_ext["external_id"] == 98765432

    # Not found
    res_404 = client.get("/speeches/111111111")
    assert res_404.status_code == 404


def test_system_status():
    res = client.get("/system/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "data_as_of" in data
    assert "totals" in data
    assert "methodology" in data
    assert "attendance" in data["methodology"]
    assert "impartiality" in data["methodology"]
