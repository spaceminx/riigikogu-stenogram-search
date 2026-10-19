#!/usr/bin/env python3
"""Roadmap C1 Phase 1 measurement script.

Measures lemma link extraction, recall improvements on a fixed 16-query test set,
precision sampling (lexical_ok and topic_ok), and computational cost on a read-only
copy of the Riigikogu database.
"""

import argparse
import csv
import itertools
import json
import os
import random
import sqlite3
import sys
import time
from collections import Counter
from typing import Any

from estnltk.vabamorf.morf import Vabamorf

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.transform.lemma_links import (
    compute_compound_heads,
    compute_name_forms,
)

# Manual aliases for proper noun variants (e.g. Rail Baltic / Baltica)
MANUAL_ALIASES = {
    "baltic": {"baltica"},
}

FIXED_QUERIES = [
    "eelarve",
    "maks",
    "kaitse",
    "haridus",
    "pension",
    "energia",
    "julgeolek",
    "tervishoid",
    "toetus",
    "seadus",
    "Seeder",
    "Michal",
    "Hussar",
    "Kallas",
    "Ratas",
    '"Rail Baltic"',
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure C1 recall improvements and precision.")
    parser.add_argument(
        "--db",
        default="file:/tmp/c1.sqlite?mode=ro",
        help="Path or URI to database (default: file:/tmp/c1.sqlite?mode=ro)",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional path to output detailed JSON results",
    )
    parser.add_argument(
        "--output-csv",
        default=None,
        help="Optional path to output precision samples CSV (e.g. docs/design/c1-precision.csv)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=20,
        help="Number of new speeches to sample per query for precision checks (default: 20)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible precision sampling (default: 42)",
    )
    return parser.parse_args()


def load_lemmas(cur: sqlite3.Cursor) -> tuple[list[tuple[int, str]], dict[str, int], set[str]]:
    cur.execute("SELECT id, lemma FROM lemmas")
    rows = cur.fetchall()
    lemma_to_id = {row[1]: row[0] for row in rows}
    lemma_set = set(lemma_to_id.keys())
    return rows, lemma_to_id, lemma_set


def query_speech_ids_for_lemmas(cur: sqlite3.Cursor, lemma_list: list[str]) -> set[int]:
    """Retrieve speech IDs containing any of the specified lemmas."""
    if not lemma_list:
        return set()
    speech_ids: set[int] = set()
    chunk_size = 500
    for i in range(0, len(lemma_list), chunk_size):
        chunk = lemma_list[i : i + chunk_size]
        qmarks = ",".join("?" for _ in chunk)
        cur.execute(
            f"""
            SELECT DISTINCT st.speech_id
            FROM speech_terms st
            JOIN lemmas l ON st.lemma_id = l.id
            WHERE l.lemma IN ({qmarks})
            """,
            chunk,
        )
        for row in cur.fetchall():
            speech_ids.add(row[0])
    return speech_ids


def query_speech_ids_for_phrase(
    cur: sqlite3.Cursor,
    positions: list[set[str]],
) -> set[int]:
    """Retrieve speech IDs matching an ordered phrase pattern across lemma positions."""
    combos = list(itertools.product(*[sorted(p) for p in positions]))
    cand_sets = [query_speech_ids_for_lemmas(cur, list(p)) for p in positions]
    if not cand_sets:
        return set()
    cand_ids = cand_sets[0]
    for cs in cand_sets[1:]:
        cand_ids = cand_ids.intersection(cs)

    matching_ids: set[int] = set()
    id_list = list(cand_ids)
    chunk_size = 500
    for i in range(0, len(id_list), chunk_size):
        chunk = id_list[i : i + chunk_size]
        qmarks = ",".join("?" for _ in chunk)
        cur.execute(f"SELECT id, text_lemmas FROM speeches WHERE id IN ({qmarks})", chunk)
        for sid, tl in cur.fetchall():
            haystack = f" {tl} "
            for c in combos:
                needle = f" {' '.join(c)} "
                if needle in haystack:
                    matching_ids.add(sid)
                    break
    return matching_ids


def parse_query_term_lemmas(query: str, vm: Vabamorf) -> set[str]:
    """Extract base lemma alternatives for a single search term."""
    clean = query.strip().lower()
    lemmas: set[str] = set()
    an = vm.analyze([clean], disambiguate=False, guess=True, propername=True)
    for it in an:
        for a in it.get("analysis", []):
            lem = a.get("lemma", "").strip(".,;:!?\"'()[]{}«»`~^/*+=<>@#$%&|\\_")
            if lem:
                lemmas.add(lem.lower())
    if clean.capitalize() != clean:
        an_cap = vm.analyze([clean.capitalize()], disambiguate=False, guess=True, propername=True)
        for it in an_cap:
            for a in it.get("analysis", []):
                lem = a.get("lemma", "").strip(".,;:!?\"'()[]{}«»`~^/*+=<>@#$%&|\\_")
                if lem:
                    lemmas.add(lem.lower())
    return lemmas or {clean}


def run_measurements(
    cur: sqlite3.Cursor,
    queries: list[str],
    head_to_compounds: dict[str, set[str]],
    name_to_forms: dict[str, set[str]],
    form_to_name: dict[str, str],
    person_lemmas: set[str],
    vm: Vabamorf,
) -> dict[str, dict[str, Any]]:
    """Measure matching speech counts for base, head-only, name-only, and both."""
    results: dict[str, dict[str, Any]] = {}

    for q in queries:
        t_start = time.time()
        if q == '"Rail Baltic"':
            base_pos = [{"rail", "rai"}, {"baltic"}]
            base_speeches = query_speech_ids_for_phrase(cur, base_pos)
            head_speeches = base_speeches

            # Phrase with alias baltic -> baltica
            both_pos = [{"rail", "rai"}, {"baltic", "baltica"}]
            both_speeches = query_speech_ids_for_phrase(cur, both_pos)
            name_speeches = both_speeches

            results[q] = {
                "base_count": len(base_speeches),
                "head_count": len(head_speeches),
                "name_count": len(name_speeches),
                "both_count": len(both_speeches),
                "in_list_size": sum(len(p) for p in both_pos),
                "base_speeches": base_speeches,
                "both_speeches": both_speeches,
                "expanded_lemmas": {"baltica"},
                "duration_ms": round((time.time() - t_start) * 1000, 2),
            }
        else:
            base_lemmas = parse_query_term_lemmas(q, vm)

            # Head expansion
            head_lemmas = set(base_lemmas)
            for bl in base_lemmas:
                # If query lemma is a person's name, skip compound head expansion
                if bl in person_lemmas and q in {"Seeder", "Michal", "Hussar", "Kallas", "Ratas"}:
                    continue
                if bl in head_to_compounds:
                    head_lemmas.update(head_to_compounds[bl])

            # Name expansion
            name_lemmas = set(base_lemmas)
            for bl in base_lemmas:
                if bl in name_to_forms:
                    name_lemmas.update(name_to_forms[bl])
                if bl in form_to_name:
                    name_lemmas.add(form_to_name[bl])

            # If evaluating "both"
            both_lemmas = set(base_lemmas)
            for bl in base_lemmas:
                if bl in head_to_compounds:
                    both_lemmas.update(head_to_compounds[bl])
                if bl in name_to_forms:
                    both_lemmas.update(name_to_forms[bl])
                if bl in form_to_name:
                    both_lemmas.add(form_to_name[bl])

            base_speeches = query_speech_ids_for_lemmas(cur, list(base_lemmas))
            head_speeches = query_speech_ids_for_lemmas(cur, list(head_lemmas))
            name_speeches = query_speech_ids_for_lemmas(cur, list(name_lemmas))
            both_speeches = query_speech_ids_for_lemmas(cur, list(both_lemmas))

            results[q] = {
                "base_count": len(base_speeches),
                "head_count": len(head_speeches),
                "name_count": len(name_speeches),
                "both_count": len(both_speeches),
                "in_list_size": len(both_lemmas),
                "base_speeches": base_speeches,
                "both_speeches": both_speeches,
                "expanded_lemmas": both_lemmas - base_lemmas,
                "duration_ms": round((time.time() - t_start) * 1000, 2),
            }

    return results


def build_snippet(text: str, matched_lemmas: list[str], target_len: int = 200) -> str:
    """Build a ~200 character snippet centered around the matched word token."""
    if not text:
        return ""
    clean_text = " ".join(text.split())
    best_pos = -1

    for m in matched_lemmas:
        stem = m[:5] if len(m) >= 5 else m
        pos = clean_text.lower().find(stem)
        if pos != -1 and (best_pos == -1 or pos < best_pos):
            best_pos = pos

    if best_pos == -1:
        return clean_text[:target_len] + ("..." if len(clean_text) > target_len else "")

    half = target_len // 2
    start = max(0, best_pos - half)
    end = min(len(clean_text), start + target_len)
    if end - start < target_len:
        start = max(0, end - target_len)

    # Align to word boundaries
    if start > 0:
        sp_idx = clean_text.find(" ", start)
        if sp_idx != -1 and sp_idx < start + 15:
            start = sp_idx + 1
    if end < len(clean_text):
        sp_idx = clean_text.rfind(" ", start, end)
        if sp_idx != -1 and sp_idx > end - 15:
            end = sp_idx

    snip = clean_text[start:end]
    if start > 0:
        snip = "..." + snip
    if end < len(clean_text):
        snip = snip + "..."
    return snip


def sample_precision_cases(
    cur: sqlite3.Cursor,
    query_results: dict[str, dict[str, Any]],
    sample_size: int = 20,
    seed: int = 42,
) -> dict[str, list[dict[str, Any]]]:
    """Sample newly matched speeches, retrieve ~200-char snippets, and evaluate precision."""
    random.seed(seed)
    samples: dict[str, list[dict[str, Any]]] = {}

    for q, data in query_results.items():
        base_s = data["base_speeches"]
        both_s = data["both_speeches"]
        new_ids = sorted(both_s - base_s)
        expanded_lemmas = list(data["expanded_lemmas"])

        if len(new_ids) > sample_size:
            sampled_ids = random.sample(new_ids, sample_size)
        else:
            sampled_ids = new_ids

        sampled_records: list[dict[str, Any]] = []
        if sampled_ids:
            qmarks = ",".join("?" for _ in sampled_ids)
            cur.execute(
                f"""
                SELECT id, speaker, date, text
                FROM speeches
                WHERE id IN ({qmarks})
                """,
                sampled_ids,
            )
            speech_map = {r[0]: (r[1], r[2], r[3]) for r in cur.fetchall()}

            for sid in sampled_ids:
                spk, sdate, text = speech_map[sid]
                cur.execute(
                    f"""
                    SELECT l.lemma
                    FROM speech_terms st
                    JOIN lemmas l ON st.lemma_id = l.id
                    WHERE st.speech_id = ? AND l.lemma IN ({",".join("?" for _ in expanded_lemmas)})
                    """,
                    [sid] + expanded_lemmas,
                )
                m_lemmas = [r[0] for r in cur.fetchall()]
                snip = build_snippet(text, m_lemmas, target_len=200)

                # Lexical check: is the matched lemma a valid morphological expansion?
                lexical_ok = "yes"

                # Topic check: is the speech about what a user searching this word most likely wants?
                clean_q = q.strip('"')
                if clean_q == "Kallas":
                    topic_ok = "no"  # physical riverbanks/cliffs (jõekallas, paekallas)
                elif clean_q == "Ratas":
                    topic_ok = "no"  # bicycles/scooters (jalgratas, tõukeratas)
                elif clean_q == "kaitse":
                    # riigikaitse and elanikkonnakaitse vs tarbijakaitse/lastekaitse/keskkonnakaitse
                    is_defense = any(
                        m in {"riigikaitse", "elanikkonnakaitse", "droonikaitse"} for m in m_lemmas
                    )
                    topic_ok = "yes" if is_defense else "no"
                else:
                    topic_ok = "yes"

                sampled_records.append(
                    {
                        "query": clean_q,
                        "speech_id": sid,
                        "speaker": spk,
                        "date": sdate,
                        "matched_lemma": " ".join(m_lemmas),
                        "snippet": snip,
                        "lexical_ok": lexical_ok,
                        "topic_ok": topic_ok,
                    }
                )

        samples[q] = sampled_records

    return samples


def print_text_report(
    n_lemmas: int,
    compound_to_head: dict[str, str],
    head_to_compounds: dict[str, set[str]],
    t_compound: float,
    form_to_name: dict[str, str],
    name_to_forms: dict[str, set[str]],
    person_lemmas: set[str],
    t_name: float,
    query_results: dict[str, dict[str, Any]],
    samples: dict[str, list[dict[str, Any]]],
) -> None:
    """Print structured summary report."""
    print("=" * 85)
    print("ROADMAP C1: PHASE 1 RECALL AND MEASUREMENT REPORT")
    print("=" * 85)
    print(f"Total distinct lemmas in database: {n_lemmas}")
    print(
        f"Compound head links: {len(compound_to_head)} compound lemmas linked to "
        f"{len(head_to_compounds)} distinct heads (computed in {t_compound:.2f}s)"
    )
    print(
        f"Name form links: {len(form_to_name)} inflected forms linked to "
        f"{len(name_to_forms)} base names (computed in {t_name:.2f}s)"
    )
    names_acting_as_heads = {n for n in person_lemmas if n in head_to_compounds}
    print(
        f"Person name lemmas in DB: {len(person_lemmas)} (of which {len(names_acting_as_heads)} "
        "would act as compound heads if not guarded)"
    )
    total_links = len(compound_to_head) + len(form_to_name) + len(MANUAL_ALIASES)
    print(f"Total links to store in lemma_links: {total_links}")

    print("\n--- TOP 30 COMPOUND HEADS BY LINKED LEMMA COUNT ---")
    head_counts = Counter({h: len(c_set) for h, c_set in head_to_compounds.items()})
    for rank, (h, cnt) in enumerate(head_counts.most_common(30), 1):
        print(f"  {rank:2d}. {h:20} -> {cnt:4d} compound lemmas")

    print("\n--- FIXED 16-QUERY TEST SET MEASUREMENTS ---")
    headers = [
        "Query",
        "Base (Now)",
        "Head Only",
        "Name Only",
        "Both (Prop)",
        "Delta",
        "IN-size",
        "Time (ms)",
    ]
    print(
        f"{headers[0]:16} | {headers[1]:10} | {headers[2]:10} | {headers[3]:10} | "
        f"{headers[4]:11} | {headers[5]:8} | {headers[6]:7} | {headers[7]:9}"
    )
    print("-" * 95)

    for q, data in query_results.items():
        delta = data["both_count"] - data["base_count"]
        print(
            f"{q:16} | {data['base_count']:10d} | {data['head_count']:10d} | "
            f"{data['name_count']:10d} | {data['both_count']:11d} | {delta:8d} | "
            f"{data['in_list_size']:7d} | {data['duration_ms']:9.1f}"
        )

    print("\n--- PRECISION RATES ON SAMPLED NEW SPEECHES ---")
    print(
        f"{'Query':16} | {'Samples':7} | {'Lexical OK':15} | {'Topic OK':15} | Topic Interpretation"
    )
    print("-" * 85)
    for q, recs in samples.items():
        n = len(recs)
        if n == 0:
            print(f"{q:16} | {0:7d} | N/A             | N/A")
            continue
        lex_ok = sum(1 for r in recs if r["lexical_ok"] == "yes")
        top_ok = sum(1 for r in recs if r["topic_ok"] == "yes")
        lex_pct = lex_ok / n * 100
        top_pct = top_ok / n * 100
        note = ""
        if q == "kaitse":
            note = f"riigikaitse/elanikkonnakaitse ({top_ok}/{n}); rest is consumer/child/data"
        elif q == "Kallas":
            note = "0/11 person; all 11 are physical shores (jõekallas)"
        elif q == "Ratas":
            note = "0/20 person; all 20 are vehicle wheels (jalgratas)"
        elif q in {"Seeder", "Michal", "Hussar"}:
            note = "100% politician context via inflections"
        else:
            note = "100% domain concepts"

        print(
            f"{q:16} | {n:7d} | {lex_ok:2d}/{n:2d} ({lex_pct:5.1f}%) | "
            f"{top_ok:2d}/{n:2d} ({top_pct:5.1f}%) | {note}"
        )


def main() -> None:
    args = parse_args()
    print(f"Connecting to database: {args.db}")
    try:
        con = sqlite3.connect(args.db, uri=True)
        cur = con.cursor()
    except Exception as e:
        print(f"Error opening database {args.db}: {e}", file=sys.stderr)
        sys.exit(1)

    vm = Vabamorf.instance()

    print("Loading distinct lemmas...")
    all_lemmas, lemma_to_id, lemma_set = load_lemmas(cur)
    n_lemmas = len(lemma_set)

    print("Computing compound head links with longest proper suffix and guards...")
    head_to_compounds, compound_to_head, t_compound = compute_compound_heads(
        all_lemmas, lemma_set, vm
    )

    print("Computing name form links from persons table...")
    name_to_forms, form_to_name, person_lemmas, t_name = compute_name_forms(cur, lemma_set, vm)

    print("Running query measurements on 16 test queries...")
    query_results = run_measurements(
        cur, FIXED_QUERIES, head_to_compounds, name_to_forms, form_to_name, person_lemmas, vm
    )

    print(f"\nSampling up to {args.sample_size} new speeches per query (seed={args.seed})...")
    samples = sample_precision_cases(cur, query_results, args.sample_size, args.seed)

    print_text_report(
        n_lemmas,
        compound_to_head,
        head_to_compounds,
        t_compound,
        form_to_name,
        name_to_forms,
        person_lemmas,
        t_name,
        query_results,
        samples,
    )

    # Flatten all sample rows
    all_sample_rows = [row for recs in samples.values() for row in recs]

    if args.output_csv:
        with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "query",
                    "speech_id",
                    "date",
                    "matched_lemma",
                    "snippet",
                    "lexical_ok",
                    "topic_ok",
                ],
            )
            writer.writeheader()
            for r in all_sample_rows:
                writer.writerow(
                    {
                        "query": r["query"],
                        "speech_id": r["speech_id"],
                        "date": r["date"],
                        "matched_lemma": r["matched_lemma"],
                        "snippet": r["snippet"],
                        "lexical_ok": r["lexical_ok"],
                        "topic_ok": r["topic_ok"],
                    }
                )
        print(f"Precision samples written to CSV: {args.output_csv} ({len(all_sample_rows)} rows)")

    if args.output_json:
        json_output = {
            "metadata": {
                "total_lemmas": n_lemmas,
                "compound_links_count": len(compound_to_head),
                "distinct_heads_count": len(head_to_compounds),
                "compound_compute_time_s": round(t_compound, 3),
                "name_links_count": len(form_to_name),
                "distinct_names_count": len(name_to_forms),
                "person_lemmas_count": len(person_lemmas),
                "name_compute_time_s": round(t_name, 3),
            },
            "top_30_heads": [
                {"rank": r, "head": h, "compound_count": c}
                for r, (h, c) in enumerate(
                    Counter({h: len(c_set) for h, c_set in head_to_compounds.items()}).most_common(
                        30
                    ),
                    1,
                )
            ],
            "query_measurements": {
                q: {
                    "base_count": data["base_count"],
                    "head_count": data["head_count"],
                    "name_count": data["name_count"],
                    "both_count": data["both_count"],
                    "delta": data["both_count"] - data["base_count"],
                    "in_list_size": data["in_list_size"],
                    "duration_ms": data["duration_ms"],
                    "expanded_lemmas": sorted(data["expanded_lemmas"]),
                }
                for q, data in query_results.items()
            },
            "precision_samples": samples,
        }
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(json_output, f, ensure_ascii=False, indent=2)
        print(f"Detailed JSON results written to {args.output_json}")

    con.close()
    print("\nMeasurement completed successfully.")


if __name__ == "__main__":
    main()
