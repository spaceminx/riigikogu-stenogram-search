from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from scripts.check_live_api import check_endpoint, compare_shapes


def _mock_response(status: int = 200, data: object = None) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    body = json.dumps(data).encode("utf-8") if data is not None else b"{}"
    resp.read.return_value = body
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def test_timeout_followed_by_success():
    fixture = {"total": 100, "status": "ok"}
    url = "https://api.riigivaade.me/test"

    timeout_err = URLError("timed out")
    success_resp = _mock_response(status=200, data=fixture)

    with (
        patch(
            "scripts.check_live_api.urlopen", side_effect=[timeout_err, success_resp]
        ) as mock_url,
        patch("scripts.check_live_api.time.sleep") as mock_sleep,
    ):
        status_str, _duration, failure = check_endpoint(url, fixture, timeout=10.0, retry_delay=5.0)

        assert status_str == "OK"
        assert failure is None
        assert mock_url.call_count == 2
        mock_sleep.assert_called_once_with(5.0)


def test_two_timeouts_result_in_failure():
    fixture = {"total": 100}
    url = "https://api.riigivaade.me/test"

    timeout_err1 = URLError("timed out")
    timeout_err2 = URLError("timed out again")

    with (
        patch(
            "scripts.check_live_api.urlopen", side_effect=[timeout_err1, timeout_err2]
        ) as mock_url,
        patch("scripts.check_live_api.time.sleep") as mock_sleep,
    ):
        status_str, _duration, failure = check_endpoint(url, fixture, timeout=10.0, retry_delay=5.0)

        assert status_str == "TIMEOUT"
        assert failure is not None
        assert "URLError" in failure
        assert "timed out again" in failure
        assert mock_url.call_count == 2
        mock_sleep.assert_called_once_with(5.0)


def test_shape_diff_results_in_failure():
    fixture = {"total": 100, "expected_key": "val"}
    live_data = {"total": 100}  # missing expected_key
    url = "https://api.riigivaade.me/test"

    success_resp = _mock_response(status=200, data=live_data)

    with (
        patch("scripts.check_live_api.urlopen", return_value=success_resp) as mock_url,
        patch("scripts.check_live_api.time.sleep") as mock_sleep,
    ):
        status_str, _duration, failure = check_endpoint(url, fixture)

        assert status_str == "DIFF"
        assert failure is not None
        assert "schema diffs:" in failure
        assert "missing key in live response" in failure
        assert mock_url.call_count == 1
        mock_sleep.assert_not_called()


def test_compare_shapes_details():
    assert compare_shapes({"a": 1}, {"a": 2}) == []
    diffs = compare_shapes({"a": 1}, {"a": "two"})
    assert len(diffs) == 1
    assert "type mismatch" in diffs[0]
