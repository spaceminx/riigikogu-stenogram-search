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


def main() -> int:
    if not INDEX_PATH.exists():
        print(f"Error: Fixtures index not found at {INDEX_PATH}", file=sys.stderr)
        return 1

    with open(INDEX_PATH, encoding="utf-8") as f:
        index_data = json.load(f)

    endpoints = index_data.get("endpoints", [])
    print(f"Checking {len(endpoints)} endpoints against live API: {LIVE_BASE_URL}\n")
    print(f"{'Status':<8} {'Time':<8} {'Path & Query':<60}")
    print("-" * 80)

    failures: list[str] = []

    for entry in endpoints:
        path = entry["path"]
        fixture_file = entry["fixture"]
        query_params = entry.get("queryParams")

        url = f"{LIVE_BASE_URL}{path}"
        if query_params:
            url += f"?{urlencode(query_params)}"

        fixture_path = FIXTURES_DIR / fixture_file
        if not fixture_path.exists():
            failures.append(f"Fixture file missing: {fixture_file}")
            print(f"{'MISS':<8} {'-':<8} {url:<60}")
            continue

        with open(fixture_path, encoding="utf-8") as f:
            fixture_json = json.load(f)

        req = Request(url, headers={"User-Agent": "Riigivaade-LiveApiCheck/1.0"})
        start_time = time.monotonic()
        status_str = "OK"
        duration_ms = 0

        try:
            with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                elapsed = time.monotonic() - start_time
                duration_ms = int(elapsed * 1000)
                status_code = resp.status
                if status_code != 200:
                    status_str = f"HTTP {status_code}"
                    failures.append(f"{url}: returned HTTP {status_code}")
                else:
                    body = resp.read()
                    try:
                        live_json = json.loads(body.decode("utf-8"))
                        diffs = compare_shapes(live_json, fixture_json)
                        if diffs:
                            status_str = "DIFF"
                            failures.append(f"{url}: schema diffs:\n  " + "\n  ".join(diffs[:5]))
                    except Exception as err:
                        status_str = "JSON"
                        failures.append(f"{url}: invalid JSON response ({err})")

        except HTTPError as err:
            elapsed = time.monotonic() - start_time
            duration_ms = int(elapsed * 1000)
            status_str = f"HTTP {err.code}"
            failures.append(f"{url}: HTTP error {err.code}")
        except URLError as err:
            elapsed = time.monotonic() - start_time
            duration_ms = int(elapsed * 1000)
            status_str = "TIMEOUT" if "timed out" in str(err) else "NET_ERR"
            failures.append(f"{url}: network error ({err})")
        except Exception as err:
            elapsed = time.monotonic() - start_time
            duration_ms = int(elapsed * 1000)
            status_str = "ERR"
            failures.append(f"{url}: error ({err})")

        print(f"{status_str:<8} {f'{duration_ms}ms':<8} {url:<60}")

    print("\n" + "=" * 80)
    if failures:
        print(f"FAILED: {len(failures)} endpoint check(s) failed:\n", file=sys.stderr)
        for fail in failures:
            print(f"- {fail}", file=sys.stderr)
        return 1

    print("SUCCESS: All live API endpoint responses match expected shapes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
