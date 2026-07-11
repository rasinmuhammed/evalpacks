#!/usr/bin/env python3
"""Prepare the BIRD Mini-Dev side of E1.

Loads the Mini-Dev question set (HuggingFace), executes each gold SQL
against the local BIRD dev SQLite databases to obtain the gold answer,
keeps only questions whose gold result is a single scalar value (the
apples-to-apples subset against the evalpack numeric/count families),
and writes them in the evalpack questions.jsonl format so the same
closed-book runner scores both sides identically.

Output classes mirror the evalpack probe:
  numeric_exact  scalar float answers
  count          scalar integer answers

Usage:
  python prepare_bird.py --bird-dev bird_dev/dev_20240627/dev_databases \
                         --out bird_items.jsonl --limit 120
"""

import argparse
import json
import sqlite3
from pathlib import Path

from huggingface_hub import hf_hub_download


def load_minidev():
    path = hf_hub_download(
        "birdsql/bird_mini_dev",
        "data/mini_dev_sqlite-00000-of-00001.json",
        repo_type="dataset",
    )
    return json.load(open(path))


def gold_answer(db_path, sql, timeout_s=20):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=timeout_s)
    try:
        con.execute(f"PRAGMA busy_timeout = {timeout_s * 1000}")
        rows = con.execute(sql).fetchall()
    finally:
        con.close()
    return rows


def scalar_of(rows):
    """Return (value, kind) when the result is a single scalar, else None."""
    if len(rows) != 1 or len(rows[0]) != 1:
        return None
    v = rows[0][0]
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return (v, "count")
    if isinstance(v, float):
        return (round(v, 2), "numeric_exact")
    return None  # strings excluded: name answers are often world knowledge


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bird-dev", required=True,
                    help="path to dev_databases directory")
    ap.add_argument("--out", default="bird_items.jsonl")
    ap.add_argument("--limit", type=int, default=120)
    args = ap.parse_args()

    dev_root = Path(args.bird_dev)
    items = load_minidev()
    kept, skipped_exec, skipped_shape = [], 0, 0

    for it in items:
        db_id = it["db_id"]
        db_path = dev_root / db_id / f"{db_id}.sqlite"
        if not db_path.exists():
            skipped_exec += 1
            continue
        sql = it.get("SQL") or it.get("sql")
        try:
            rows = gold_answer(db_path, sql)
        except Exception:
            skipped_exec += 1
            continue
        scalar = scalar_of(rows)
        if scalar is None:
            skipped_shape += 1
            continue
        value, kind = scalar
        kept.append({
            "id": f"bird{it.get('question_id', len(kept)):04d}",
            "question": it["question"],
            "gold_sql": sql,
            "expected_answer": value,
            "answer_type": "number",
            "round_decimals": 2 if kind == "numeric_exact" else 0,
            "tags": [it.get("difficulty", "unknown")],
            "source": {"kind": kind, "db_id": db_id, "origin": "bird_mini_dev"},
        })
        if len(kept) >= args.limit:
            break

    with open(args.out, "w") as fh:
        for row in kept:
            fh.write(json.dumps(row) + "\n")
    print(f"kept {len(kept)} scalar-answer questions "
          f"(skipped: {skipped_exec} exec-fail/missing-db, {skipped_shape} non-scalar)")
    from collections import Counter
    print(Counter(r["source"]["kind"] for r in kept))


if __name__ == "__main__":
    main()
