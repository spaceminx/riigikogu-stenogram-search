#!/usr/bin/env python3
"""Roadmap C1 Phase 1 measurement script.

Measures lemma link extraction, recall improvements on a fixed 16-query test set,
precision sampling, and computational cost on a read-only copy of the Riigikogu database.
"""

import argparse
import itertools
import json
import random
import re
import sqlite3
import sys
import time
from collections import Counter
from typing import Any

from estnltk.vabamorf.morf import Vabamorf

# Fixed stoplist of non-compositional, fossilized, or overly general suffix stems
HEAD_STOPLIST = {
    "arve",
    "märk",
    "kiri",
    "kaal",
    "seis",
    "kord",
    "koht",
    "vaade",
    "salu",
    "organ",
    "koll",
    "kaar",
    "asi",
    "osa",
    "mees",
    "päev",
    "aeg",
    "aasta",
}

# Bound or non-compositional prefix stems that should not form loose compound links
BOUND_PREFIXES = {"eel", "all", "üle", "ees", "pea", "ala", "ise"}

# Names that are also ambiguous common nouns/verbs in Estonian dictionary
AMBIGUOUS_NAME_WORDS = {"kallas", "ratas", "aeg", "aru", "meri", "kütt", "kotkas", "kiik"}

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


def compute_compound_heads(
    all_lemmas: list[tuple[int, str]],
    lemma_set: set[str],
    vm: Vabamorf,
    batch_size: int = 5000,
) -> tuple[dict[str, set[str]], dict[str, str], float]:
    """Extract compound heads using longest proper suffix rule with guards."""
    t0 = time.time()
    lemma_analyses: dict[str, list[str]] = {}

    for i in range(0, len(all_lemmas), batch_size):
        batch = [row[1] for row in all_lemmas[i : i + batch_size]]
        analyses = vm.analyze(batch, disambiguate=False, guess=False)
        for word, item in zip(batch, analyses, strict=False):
            best_tokens: list[str] = []
            for a in item.get("analysis", []):
                tokens = a.get("root_tokens", [])
                if len(tokens) > len(best_tokens):
                    best_tokens = tokens
            lemma_analyses[word] = best_tokens

    compounds = {w: tokens for w, tokens in lemma_analyses.items() if len(tokens) >= 2}

    head_to_compounds: dict[str, set[str]] = {}
    compound_to_head: dict[str, str] = {}

    for word, tokens in compounds.items():
        candidates: list[str] = []
        for i in range(1, len(tokens)):
            suffix = "".join(tokens[i:])
            if (
                len(suffix) >= 4
                and suffix in lemma_set
                and suffix != word
                and suffix not in HEAD_STOPLIST
            ):
                prefix = word[: -len(suffix)]
                if len(prefix) < 4 and prefix in BOUND_PREFIXES:
                    continue
                candidates.append(suffix)
        if candidates:
            candidates.sort(key=len, reverse=True)
            chosen_head = candidates[0]
            compound_to_head[word] = chosen_head
            if chosen_head not in head_to_compounds:
                head_to_compounds[chosen_head] = set()
            head_to_compounds[chosen_head].add(word)

    elapsed = time.time() - t0
    return head_to_compounds, compound_to_head, elapsed


def is_ambiguous_common_word(word: str, vm: Vabamorf) -> bool:
    """Check if word is a common noun/verb/adverb/adjective in general vocabulary."""
    analyses = vm.analyze([word], disambiguate=False, guess=False)
    for it in analyses:
        for a in it.get("analysis", []):
            pos = a.get("partofspeech", "")
            if pos in {"V", "D", "P", "J", "K"} or (
                pos == "S" and a.get("lemma") in AMBIGUOUS_NAME_WORDS
            ):
                return True
    return False


def compute_name_forms(
    cur: sqlite3.Cursor,
    lemma_set: set[str],
    vm: Vabamorf,
) -> tuple[dict[str, set[str]], dict[str, str], float]:
    """Extract name inflected forms from persons table using Vabamorf synthesis."""
    t0 = time.time()
    cur.execute("SELECT uuid, first_name, last_name FROM persons")
    persons = cur.fetchall()

    name_to_forms: dict[str, set[str]] = {}
    form_to_name: dict[str, str] = {}

    synthesis_cases = [
        "sg g",
        "sg p",
        "sg ill",
        "sg in",
        "sg el",
        "sg all",
        "sg ad",
        "sg abl",
        "sg tr",
        "sg ter",
        "sg es",
        "sg ab",
        "sg kom",
    ]

    for _p_uuid, fn, ln in persons:
        for name in [fn, ln]:
            if not name or len(name) < 3:
                continue
            base_lower = name.lower()
            if base_lower not in lemma_set:
                continue

            forms: list[str] = []
            for form in synthesis_cases:
                res = vm.synthesize(name, form=form, partofspeech="H")
                if not res:
                    res = vm.synthesize(name, form=form, partofspeech="S")
                forms.extend(res)

            # Consonant stem genitive / partitive suffixes
            if name[-1].lower() not in "aeiouõäöü":
                forms.append(name + "i")
                forms.append(name + "it")

            for f in {f.lower() for f in forms if f}:
                if f in lemma_set and f != base_lower:
                    if is_ambiguous_common_word(f, vm):
                        continue
                    if base_lower not in name_to_forms:
                        name_to_forms[base_lower] = set()
                    name_to_forms[base_lower].add(f)
                    form_to_name[f] = base_lower

    elapsed = time.time() - t0
    return name_to_forms, form_to_name, elapsed


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
                if bl in head_to_compounds:
                    head_lemmas.update(head_to_compounds[bl])

            # Name expansion
            name_lemmas = set(base_lemmas)
            for bl in base_lemmas:
                if bl in name_to_forms:
                    name_lemmas.update(name_to_forms[bl])
                if bl in form_to_name:
                    name_lemmas.add(form_to_name[bl])

            both_lemmas = set(head_lemmas).union(name_lemmas)

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


def sample_precision_cases(
    cur: sqlite3.Cursor,
    query_results: dict[str, dict[str, Any]],
    sample_size: int = 20,
    seed: int = 42,
) -> dict[str, list[dict[str, Any]]]:
    """Sample newly matched speeches and retrieve surrounding context snippets."""
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
            for sid, spk, sdate, text in cur.fetchall():
                # Query matching lemma for this speech
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

                words = text.split() if text else []
                snippet = ""
                for idx, w in enumerate(words):
                    clean_w = re.sub(r"[^\w]", "", w.lower())
                    if any(m in clean_w for m in m_lemmas) or any(
                        m[:4] in clean_w for m in m_lemmas if len(m) >= 4
                    ):
                        start = max(0, idx - 6)
                        end = min(len(words), idx + 7)
                        snippet = " ".join(words[start:end])
                        break
                if not snippet and words:
                    snippet = " ".join(words[:15])

                sampled_records.append(
                    {
                        "speech_id": sid,
                        "speaker": spk,
                        "date": sdate,
                        "matched_lemmas": m_lemmas,
                        "snippet": snippet,
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
    t_name: float,
    query_results: dict[str, dict[str, Any]],
) -> None:
    """Print structured summary report."""
    print("=" * 80)
    print("ROADMAP C1: PHASE 1 RECALL AND MEASUREMENT REPORT")
    print("=" * 80)
    print(f"Total distinct lemmas in database: {n_lemmas}")
    print(
        f"Compound head links: {len(compound_to_head)} compound lemmas linked to "
        f"{len(head_to_compounds)} distinct heads (computed in {t_compound:.2f}s)"
    )
    print(
        f"Name form links: {len(form_to_name)} inflected forms linked to "
        f"{len(name_to_forms)} base names (computed in {t_name:.2f}s)"
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
    name_to_forms, form_to_name, t_name = compute_name_forms(cur, lemma_set, vm)

    print("Running query measurements on 16 test queries...")
    query_results = run_measurements(
        cur, FIXED_QUERIES, head_to_compounds, name_to_forms, form_to_name, vm
    )

    print_text_report(
        n_lemmas,
        compound_to_head,
        head_to_compounds,
        t_compound,
        form_to_name,
        name_to_forms,
        t_name,
        query_results,
    )

    print(f"\nSampling up to {args.sample_size} new speeches per query (seed={args.seed})...")
    samples = sample_precision_cases(cur, query_results, args.sample_size, args.seed)

    if args.output_json:
        # Prepare clean JSON structure without sets
        json_output = {
            "metadata": {
                "total_lemmas": n_lemmas,
                "compound_links_count": len(compound_to_head),
                "distinct_heads_count": len(head_to_compounds),
                "compound_compute_time_s": round(t_compound, 3),
                "name_links_count": len(form_to_name),
                "distinct_names_count": len(name_to_forms),
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
