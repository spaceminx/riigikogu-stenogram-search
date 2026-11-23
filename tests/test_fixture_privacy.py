"""Committed fixtures carry no contact details and no exact dates of birth.

The upstream API returns e-mail, phone and date of birth for every MP. The site shows the birth
year only and never the contacts, so the repository must not hold them either.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIRS = [ROOT / "tests" / "fixtures", ROOT / "src" / "frontend" / "e2e" / "fixtures"]
CONTACT_KEYS = {"email", "phone", "upn"}
BIRTH_KEYS = {"dateOfBirth", "date_of_birth"}
YEAR_ONLY = re.compile(r"^\d{4}-01-01$")


def walk(node, path):
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}"
            if key in CONTACT_KEYS and value:
                yield f"{here}: contact field"
            if key in BIRTH_KEYS and value and not YEAR_ONLY.match(str(value)):
                yield f"{here}: full date of birth (use YYYY-01-01)"
            yield from walk(value, here)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from walk(value, f"{path}[{i}]")


def test_fixtures_hold_no_contacts_or_birth_dates():
    files = [f for d in FIXTURE_DIRS for f in sorted(d.rglob("*.json"))]
    assert files, "no fixture files found"
    problems = []
    for file in files:
        data = json.loads(file.read_text(encoding="utf-8"))
        # Report the location only, never the value
        problems += [f"{file.relative_to(ROOT)}{p}" for p in walk(data, "")]
    assert problems == []


def test_capture_script_scrubs_members():
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from capture_riigikogu_fixtures import trim_plenary_members

    member = {
        "uuid": "u-1",
        "fullName": "Mari Maasikas",
        "dateOfBirth": "1980-05-17",
        "email": "mari@example.ee",
        "phone": "+372 0000 0000",
        "upn": "mari",
    }
    (scrubbed,) = trim_plenary_members([member])
    assert scrubbed == {"uuid": "u-1", "fullName": "Mari Maasikas", "dateOfBirth": "1980-01-01"}
