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
