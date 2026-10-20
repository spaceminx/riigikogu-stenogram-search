"""Roadmap C1: Lemma links builder for compound heads, name forms, and aliases.

Extracts:
1. Compound heads: longest proper suffix at a root-token boundary (len >= 4, guarded by HEAD_STOPLIST and BOUND_PREFIXES).
2. Person name forms: inflected forms of persons' first and last names via Vabamorf synthesis.
3. Manual aliases: loaded from src/transform/lemma_aliases.csv.

Rebuilds lemma_links atomically in a single transaction.
"""

import csv
import logging
import time
from pathlib import Path

from estnltk.vabamorf.morf import Vabamorf
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.load.database import engine as default_engine

logger = logging.getLogger(__name__)

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

ALIASES_CSV_PATH = Path(__file__).resolve().parent / "lemma_aliases.csv"

SYNTHESIS_CASES = [
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


def load_manual_aliases(
    csv_path: Path | str | None = None,
) -> list[tuple[str, str, str]]:
    """Load manual lemma aliases from CSV (base_lemma, expanded_lemma, kind)."""
    path = Path(csv_path or ALIASES_CSV_PATH)
    if not path.exists():
        return []

    aliases: list[tuple[str, str, str]] = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            base = row.get("base_lemma", "").strip().lower()
            exp = row.get("expanded_lemma", "").strip().lower()
            kind = row.get("kind", "").strip() or "alias"
            if base and exp:
                aliases.append((base, exp, kind))
    return aliases


def compute_compound_heads(
    all_lemmas: list[tuple[int, str]],
    lemma_set: set[str],
    vm: Vabamorf,
    batch_size: int = 5000,
) -> tuple[dict[str, set[str]], dict[str, str], float]:
    """Extract compound heads using longest proper suffix rule with guards.

    Returns:
        (head_to_compounds, compound_to_head, elapsed_seconds)
    """
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


def get_person_lemmas(conn=None, engine: Engine | None = None) -> set[str]:
    """Retrieve distinct lowercase lemma stems of persons' first and last names."""
    eng = engine or default_engine

    def _query(c) -> set[str]:
        rows = c.execute(text("SELECT first_name, last_name FROM persons")).fetchall()
        lemmas: set[str] = set()
        for fn, ln in rows:
            for name_field in [fn, ln]:
                if not name_field:
                    continue
                for part in name_field.replace("-", " ").split():
                    clean = part.strip().lower()
                    if clean and len(clean) >= 2:
                        lemmas.add(clean)
        return lemmas

    if conn is not None:
        return _query(conn)

    with eng.connect() as c:
        return _query(c)


def compute_name_forms(
    conn,
    lemma_set: set[str],
    vm: Vabamorf,
) -> tuple[dict[str, set[str]], dict[str, str], set[str], float]:
    """Extract name inflected forms from persons table using Vabamorf synthesis.

    Works with both SQLAlchemy Connection and sqlite3 Connection/Cursor.

    Returns:
        (name_to_forms, form_to_name, person_lemmas, elapsed_seconds)
    """
    t0 = time.time()
    if hasattr(conn, "cursor") and not hasattr(conn, "begin"):
        # sqlite3 Connection
        cur = conn.cursor()
        cur.execute("SELECT uuid, first_name, last_name FROM persons")
        rows = cur.fetchall()
    elif hasattr(conn, "fetchall") and hasattr(conn, "execute"):
        # sqlite3 Cursor
        conn.execute("SELECT uuid, first_name, last_name FROM persons")
        rows = conn.fetchall()
    else:
        # SQLAlchemy Connection
        rows = conn.execute(text("SELECT uuid, first_name, last_name FROM persons")).fetchall()

    name_to_forms: dict[str, set[str]] = {}
    form_to_name: dict[str, str] = {}
    person_lemmas: set[str] = set()

    for _p_uuid, fn, ln in rows:
        for name_field in [fn, ln]:
            if not name_field:
                continue
            for part in name_field.replace("-", " ").split():
                clean_name = part.strip()
                if not clean_name or len(clean_name) < 3:
                    continue
                base_lower = clean_name.lower()
                if base_lower in lemma_set:
                    person_lemmas.add(base_lower)

                forms: list[str] = []
                for form in SYNTHESIS_CASES:
                    res = vm.synthesize(clean_name, form=form, partofspeech="H")
                    if not res:
                        res = vm.synthesize(clean_name, form=form, partofspeech="S")
                    forms.extend(res)

                # Consonant stem genitive / partitive suffixes
                if clean_name[-1].lower() not in "aeiouõäöü":
                    forms.append(clean_name + "i")
                    forms.append(clean_name + "it")

                for f in {f.lower() for f in forms if f}:
                    if f in lemma_set and f != base_lower:
                        if is_ambiguous_common_word(f, vm):
                            continue
                        if base_lower not in name_to_forms:
                            name_to_forms[base_lower] = set()
                        name_to_forms[base_lower].add(f)
                        form_to_name[f] = base_lower

    elapsed = time.time() - t0
    return name_to_forms, form_to_name, person_lemmas, elapsed


# POS preference order (higher index = lower priority)
_POS_PREFERENCE: list[str] = ["S", "H", "A", "Y"]


def pick_best_pos(analyses: list[dict], lemma_text: str) -> str | None:
    """Determine the best POS tag for a lemma given Vabamorf analyses.

    Preference order: S > H > A > Y > others.
    First tries analyses where the returned lemma matches the stored lemma (case-insensitive).
    Falls back to all analyses if no match is found.
    """
    lower_lemma = lemma_text.lower()

    def _rank(pos: str) -> int:
        try:
            return _POS_PREFERENCE.index(pos)
        except ValueError:
            return len(_POS_PREFERENCE)

    def _best_from(pos_list: list[str]) -> str | None:
        if not pos_list:
            return None
        return min(pos_list, key=_rank)

    matching_pos: list[str] = []
    all_pos: list[str] = []

    for item in analyses:
        for a in item.get("analysis", []):
            pos = a.get("partofspeech", "")
            if not pos:
                continue
            all_pos.append(pos)
            returned_lemma = a.get("lemma", "")
            if returned_lemma.lower() == lower_lemma:
                matching_pos.append(pos)

    best = _best_from(matching_pos)
    if best is not None:
        return best
    return _best_from(all_pos)


def update_lemma_pos(target_engine: Engine | None = None) -> float:
    """Analyse every lemma with Vabamorf and update lemmas.pos in bulk.

    Returns elapsed seconds.
    """
    t0 = time.time()
    eng = target_engine or default_engine
    vm = Vabamorf.instance()

    with eng.connect() as conn:
        rows = conn.execute(text("SELECT id, lemma FROM lemmas")).fetchall()

    if not rows:
        return time.time() - t0

    batch_size = 5000
    id_to_pos: dict[int, str | None] = {}

    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        words = [r[1] for r in batch]
        analyses = vm.analyze(words, disambiguate=False, guess=False)
        for (row_id, lemma_text), item_analyses in zip(batch, analyses, strict=False):
            pos = pick_best_pos([item_analyses], lemma_text)
            id_to_pos[row_id] = pos

    update_data = [{"lemma_id": lid, "pos": p} for lid, p in id_to_pos.items()]

    with eng.connect() as conn:
        with conn.begin():
            conn.execute(
                text("UPDATE lemmas SET pos = :pos WHERE id = :lemma_id"),
                update_data,
            )

    elapsed = time.time() - t0
    logger.info("Updated lemma POS for %d lemmas in %.2fs", len(id_to_pos), elapsed)
    return elapsed


def build_lemma_links(engine: Engine | None = None) -> dict[str, int]:
    """Perform a full atomic rebuild of the lemma_links table in one transaction.

    If an error occurs, the transaction rolls back and previous links are preserved.

    Returns:
        dict: Counts of generated links by kind and total.
    """
    eng = engine or default_engine
    vm = Vabamorf.instance()

    with eng.connect() as conn:
        conn.execute(text("PRAGMA busy_timeout = 30000;"))

        # 1. Load all lemmas
        rows = conn.execute(text("SELECT id, lemma FROM lemmas")).fetchall()
        lemma_to_id = {row[1]: row[0] for row in rows}
        lemma_set = set(lemma_to_id.keys())
        all_lemmas = [(row[0], row[1]) for row in rows]

        # 2. Compute compound heads
        _head_to_compounds, compound_to_head, _ = compute_compound_heads(all_lemmas, lemma_set, vm)

        # 3. Compute name forms
        name_to_forms, _, _, _ = compute_name_forms(conn, lemma_set, vm)

        # 4. Load manual aliases
        manual_aliases = load_manual_aliases()

        # Build records to insert
        records: set[tuple[int, int, str]] = set()

        # Compounds: compound word (lemma_id) -> head (target_lemma_id)
        for compound_word, head in compound_to_head.items():
            c_id = lemma_to_id.get(compound_word)
            h_id = lemma_to_id.get(head)
            if c_id and h_id and c_id != h_id:
                records.add((c_id, h_id, "compound_head"))

        # Name forms: bidirectional links between base name and inflected forms
        for base_name, forms in name_to_forms.items():
            base_id = lemma_to_id.get(base_name)
            if not base_id:
                continue
            for f in forms:
                form_id = lemma_to_id.get(f)
                if form_id and form_id != base_id:
                    # When searching base name, find inflected form
                    records.add((form_id, base_id, "name_form"))
                    # When searching inflected form, find base name
                    records.add((base_id, form_id, "name_form"))

        # Manual aliases: e.g. baltic <-> baltica
        for base, exp, kind in manual_aliases:
            base_id = lemma_to_id.get(base)
            exp_id = lemma_to_id.get(exp)
            if base_id and exp_id and base_id != exp_id:
                records.add((exp_id, base_id, kind))

        insert_data = [{"lemma_id": r[0], "target_lemma_id": r[1], "kind": r[2]} for r in records]

        if conn.in_transaction():
            conn.commit()

        # 5. Atomic transaction: delete + bulk insert
        with conn.begin():
            conn.execute(text("DELETE FROM lemma_links"))
            if insert_data:
                conn.execute(
                    text(
                        """
                        INSERT INTO lemma_links (lemma_id, target_lemma_id, kind)
                        VALUES (:lemma_id, :target_lemma_id, :kind)
                        """
                    ),
                    insert_data,
                )

        compound_count = sum(1 for r in records if r[2] == "compound_head")
        name_count = sum(1 for r in records if r[2] == "name_form")
        alias_count = sum(1 for r in records if r[2] == "alias")
        total_count = len(records)

        logger.info(
            "Rebuilt lemma_links: %d total (%d compound_head, %d name_form, %d alias)",
            total_count,
            compound_count,
            name_count,
            alias_count,
        )

        return {
            "compound_head": compound_count,
            "name_form": name_count,
            "alias": alias_count,
            "total": total_count,
        }
