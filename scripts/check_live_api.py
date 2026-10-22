#!/usr/bin/env python3
"""Weekly Live API Shape Check.

Compares live production API responses against fixtures recorded in
src/frontend/e2e/fixtures/index.json to catch contract breakage early.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LIVE_BASE_URL = "https://api.riigivaade.me"
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "src" / "frontend" / "e2e" / "fixtures"
INDEX_PATH = FIXTURES_DIR / "index.json"
TIMEOUT_SECONDS = 10.0
SLEEP_BETWEEN_REQUESTS_SECONDS = 1.0
RETRY_DELAY_SECONDS = 5.0


def compare_shapes(live: object, fixture: object, path: str = "$") -> list[str]:
    """Recursively verify that live response matches or supersedes fixture shape."""
    diffs = []

    # Type comparison
    if type(live) is not type(fixture):
        # Allow int/float mismatch
        if isinstance(live, (int, float)) and isinstance(fixture, (int, float)):
            pass
        else:
            diffs.append(
                f"{path}: type mismatch - expected {type(fixture).__name__}, got {type(live).__name__}"
            )
            return diffs

    if isinstance(fixture, dict):
        # Ensure all keys in fixture exist in live
        for key in fixture:
            if key not in live:
                diffs.append(f"{path}.{key}: missing key in live response")
            else:
                # Compare value types / subshapes unless either is None
                if fixture[key] is not None and live[key] is not None:
                    diffs.extend(compare_shapes(live[key], fixture[key], f"{path}.{key}"))

    elif isinstance(fixture, list):
        if len(fixture) > 0:
            if len(live) == 0:
                diffs.append(f"{path}: fixture has {len(fixture)} items but live response is empty")
            else:
                # Check first item structure
                diffs.extend(compare_shapes(live[0], fixture[0], f"{path}[0]"))

    return diffs


def check_endpoint(
    url: str,
    fixture_json: object,
    timeout: float = TIMEOUT_SECONDS,
    retry_delay: float = RETRY_DELAY_SECONDS,
) -> tuple[str, int, str | None]:
    """Check a single endpoint against fixture_json, retrying once on network/timeout error.

    Returns:
        tuple of (status_str, duration_ms, failure_message or None)
    """
    req = Request(url, headers={"User-Agent": "Riigivaade-LiveApiCheck/1.0"})

    for attempt in range(2):
        start_time = time.monotonic()
        try:
            with urlopen(req, timeout=timeout) as resp:
                elapsed = time.monotonic() - start_time
                duration_ms = int(elapsed * 1000)
                status_code = resp.status
                if status_code != 200:
                    return f"HTTP {status_code}", duration_ms, f"{url}: returned HTTP {status_code}"

                body = resp.read()
                try:
                    live_json = json.loads(body.decode("utf-8"))
                    diffs = compare_shapes(live_json, fixture_json)
                    if diffs:
                        return (
                            "DIFF",
                            duration_ms,
                            f"{url}: schema diffs:\n  " + "\n  ".join(diffs[:5]),
                        )
                    return "OK", duration_ms, None
                except Exception as err:
                    return (
                        "JSON",
                        duration_ms,
                        f"{url}: invalid JSON response ({type(err).__name__}: {err})",
                    )

        except HTTPError as err:
            elapsed = time.monotonic() - start_time
            duration_ms = int(elapsed * 1000)
            return (
                f"HTTP {err.code}",
                duration_ms,
                f"{url}: HTTP error {err.code} ({type(err).__name__}: {err})",
            )

        except (URLError, TimeoutError) as err:
            elapsed = time.monotonic() - start_time
            duration_ms = int(elapsed * 1000)
            if attempt == 0:
                time.sleep(retry_delay)
                continue

            status_str = "TIMEOUT" if "timed out" in str(err).lower() else "NET_ERR"
            return status_str, duration_ms, f"{url}: {type(err).__name__}: {err}"

        except Exception as err:
            elapsed = time.monotonic() - start_time
            duration_ms = int(elapsed * 1000)
            return "ERR", duration_ms, f"{url}: {type(err).__name__}: {err}"

    return "ERR", 0, f"{url}: unexpected check state"


def run_checks(
    index_path: Path = INDEX_PATH,
    fixtures_dir: Path = FIXTURES_DIR,
    live_base_url: str = LIVE_BASE_URL,
    sleep_between: float = SLEEP_BETWEEN_REQUESTS_SECONDS,
) -> int:
    if not index_path.exists():
        print(f"Error: Fixtures index not found at {index_path}", file=sys.stderr)
        return 1

    with open(index_path, encoding="utf-8") as f:
        index_data = json.load(f)

    endpoints = index_data.get("endpoints", [])
    print(f"Checking {len(endpoints)} endpoints against live API: {live_base_url}\n")
    print(f"{'Status':<8} {'Time':<8} {'Path & Query':<60}")
    print("-" * 80)

    failures: list[str] = []

    for i, entry in enumerate(endpoints):
        if i > 0 and sleep_between > 0:
            time.sleep(sleep_between)

        path = entry["path"]
        fixture_file = entry["fixture"]
        query_params = entry.get("queryParams")

        url = f"{live_base_url}{path}"
        if query_params:
            url += f"?{urlencode(query_params)}"

        fixture_path = fixtures_dir / fixture_file
        if not fixture_path.exists():
            failures.append(f"Fixture file missing: {fixture_file}")
            print(f"{'MISS':<8} {'-':<8} {url:<60}")
            continue

        with open(fixture_path, encoding="utf-8") as f:
            fixture_json = json.load(f)

        status_str, duration_ms, failure_msg = check_endpoint(url, fixture_json)
        if failure_msg:
            failures.append(failure_msg)

        print(f"{status_str:<8} {f'{duration_ms}ms':<8} {url:<60}")

    print("\n" + "=" * 80)
    if failures:
        print(f"FAILED: {len(failures)} endpoint check(s) failed:\n", file=sys.stderr)
        for fail in failures:
            print(f"- {fail}", file=sys.stderr)
        return 1

    print("SUCCESS: All live API endpoint responses match expected shapes.")
    return 0


def main() -> int:
    return run_checks()


if __name__ == "__main__":
    sys.exit(main())
