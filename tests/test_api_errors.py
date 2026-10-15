from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.main import app
from src.load.loader import create_tables

create_tables()
client = TestClient(app)


def test_speeches_overflow_int_returns_404():
    response = client.get("/speeches/99999999999999999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Kõnet ei leitud."


def test_speeches_by_external_id_overflow_int_returns_404():
    response = client.get("/speeches/by-external-id/99999999999999999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Kõnet ei leitud."


def test_speeches_by_external_id_unicode_digit_returns_404():
    response = client.get("/speeches/by-external-id/%C2%B2")
    assert response.status_code == 404
    assert response.json()["detail"] == "Kõnet ei leitud."


def test_search_offset_overflow_returns_422():
    response = client.get("/search?q=test&offset=99999999999999999999")
    assert response.status_code == 422


def test_persons_offset_overflow_returns_422():
    response = client.get("/persons?offset=99999999999999999999")
    assert response.status_code == 422


def test_votings_offset_overflow_returns_422():
    response = client.get("/votings?offset=99999999999999999999")
    assert response.status_code == 422


def test_person_speeches_offset_overflow_returns_422():
    response = client.get("/persons/fake-uuid/speeches?offset=99999999999999999999")
    assert response.status_code == 422


def test_person_votes_offset_overflow_returns_422():
    response = client.get("/persons/fake-uuid/votes?offset=99999999999999999999")
    assert response.status_code == 422


def test_search_nul_character_returns_400():
    response = client.get("/search?q=%00")
    assert response.status_code == 400
    assert response.json()["detail"] == "Vigane otsingupäring."


def test_search_nul_character_stripped_works():
    response = client.get("/search?q=%00kliimamuutus")
    assert response.status_code == 200


def test_search_activity_excessive_nesting_returns_400():
    response = client.get("/search/activity?q=" + "(" * 15)
    assert response.status_code == 400
    assert response.json()["detail"] == "Päring on liiga keeruline."


def test_lemmatizer_failure_returns_503():
    with patch("src.api.search.lemmatize_text", return_value=None):
        response = client.get("/search?q=riigikogu")
        assert response.status_code == 503
        assert response.json()["detail"] == "Otsingu keeletöötlus pole hetkel saadaval."


def test_speech_context_too_many_groups_returns_400():
    response = client.get("/speeches/1/context?q=k0,k1,k2,k3,k4,k5,k6,k7,k8,k9,k10")
    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Liiga palju otsingurühmi: lubatud kuni 10 komaga eraldatud rühma."
    )


def test_search_long_sentence_with_stopwords_returns_200():
    response = client.get("/search?q=ja see on üks väga pikk lause mis räägib riigi eelarvest täna")
    assert response.status_code == 200


def test_search_too_many_content_words_in_group_returns_400():
    response = client.get(
        "/search?q=üks kaks kolm neli viis kuus seitse kaheksa üheksa kümme üksteist"
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Liiga palju sõnu ühes rühmas: lubatud kuni 10 sisusõna."


def test_search_too_many_groups_returns_400():
    response = client.get("/search?q=k0,k1,k2,k3,k4,k5,k6,k7,k8,k9,k10")
    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Liiga palju otsingurühmi: lubatud kuni 10 komaga eraldatud rühma."
    )


def test_search_empty_groups_ignored():
    response = client.get("/search?q=eelarve,,")
    assert response.status_code == 200
