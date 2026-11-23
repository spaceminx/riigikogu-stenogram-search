"""The daily fetch saves an unedited sitting again when upstream changed it (audit A-1)."""

import json
from datetime import datetime, timedelta

import pytest

import scripts.fetch_stenograms_api as fsa

DAY = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
CODE = DAY.replace("-", "") + "1000"
SOURCE = f"{DAY}_1000.api"


def _meeting(video_links: bool) -> dict:
    return {
        "meetingStatus": "UNEDITED",
        "stenograph": {
            "agendaItems": [
                {
                    "id": 101,
                    "name": "Päevakorrapunkt 1",
                    "speeches": [
                        {
                            "id": 46000000 + i,
                            "emsId": None,
                            "name": f"Kõneleja {i}",
                            "speechType": "SPEECH",
                            "content": f"<p>Toimetamata tekst number {i}.</p>",
                            "startTime": f"{DAY}T10:0{i}:00.000",
                            "endTime": f"{DAY}T10:0{i}:30.000",
                            "parsedVideoLink": f"https://youtu.be/x?t={i}" if video_links else None,
                        }
                        for i in range(3)
                    ],
                }
            ]
        },
    }


@pytest.fixture
def fetch(tmp_path, monkeypatch):
    monkeypatch.setattr(fsa, "OUTPUT_DIR_PROCESSED", str(tmp_path))
    (tmp_path / "factions_map.json").write_text("{}", encoding="utf-8")
    (tmp_path / "persons.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr("time.sleep", lambda s: None)

    class NoVerbatims:
        status_code = 200

        def json(self):
            return []

    monkeypatch.setattr("requests.get", lambda *a, **k: NoVerbatims())

    first, _ = fsa.parse_meeting_speeches(
        rich_meeting=_meeting(video_links=False),
        verbatim=None,
        meeting_code=CODE,
        verbatim_link=f"https://stenogrammid.riigikogu.ee/et/{CODE}",
        date_formatted=DAY,
        time_formatted="1000",
        source_file_key=SOURCE,
        faction_map={},
    )
    fsa.save_session_to_jsonl(DAY[:4], SOURCE, first)

    saves = []
    real_save = fsa.save_session_to_jsonl
    monkeypatch.setattr(
        fsa, "save_session_to_jsonl", lambda *a: saves.append(a[1]) or real_save(*a)
    )

    def unchanged_text_is_not_lemmatized_again(text):
        raise AssertionError(f"lemmatized again: {text}")

    monkeypatch.setattr(fsa, "lemmatize_text", unchanged_text_is_not_lemmatized_again)

    def run(meeting):
        monkeypatch.setattr(fsa, "fetch_rich_meeting_data", lambda code: meeting)
        assert fsa.fetch_and_process_stenograms() is True
        lines = (tmp_path / f"{DAY[:4]}.jsonl").read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line]

    run.saves = saves
    return run


def test_video_links_published_later_reach_the_file(fetch):
    rows = fetch(_meeting(video_links=True))
    assert fetch.saves == [SOURCE]
    assert [r["video_url"] for r in rows] == [f"https://youtu.be/x?t={i}" for i in range(3)]
    assert all(r["status"] == "UNEDITED" and r["text_lemmas"] for r in rows)


def test_unchanged_sitting_is_not_rewritten(fetch):
    rows = fetch(_meeting(video_links=False))
    assert fetch.saves == []
    assert all(r["video_url"] is None for r in rows)
