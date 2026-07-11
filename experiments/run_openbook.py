#!/usr/bin/env python3
"""E5-lite: open-book evaluation of models against a verified pack.

The payoff of a provably-correct answer key is attribution: when a model
misses, the error is the model's. Each model receives the table schemas
and a question, writes one DuckDB SQL query, and the query is executed
against the shipped CSVs; the result is scored exactly like the pack's
own verifier. Every generated query and its execution result is stored.

Hypothesis worth testing: questions state half-open windows explicitly
("on or after X and strictly before Y"); models that reach for BETWEEN
on timestamps include the right boundary and miss.
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

import duckdb

from run_closedbook import build_request

SYSTEM = (
    "You are a SQL analyst working with DuckDB. Given table schemas and a "
    "question, reply with ONLY one DuckDB SQL query that answers it. "
    "No explanation, no markdown fences, just the SQL."
)


def load_schemas(pack):
    lines = []
    for csv_path in sorted((Path(pack) / "tables").glob("*.csv")):
        with open(csv_path) as fh:
            header = next(csv.reader(fh))
        lines.append(f"{csv_path.stem}({', '.join(header)})")
    return "\n".join(lines)


def extract_sql(raw):
    raw = raw.strip()
    fence = re.search(r"```(?:sql)?\s*(.+?)```", raw, re.S | re.I)
    if fence:
        raw = fence.group(1).strip()
    return raw.split(";")[0].strip()


def answers_match(q, observed):
    if observed is None:
        return False
    if q["answer_type"] == "string":
        return str(observed) == str(q["expected_answer"])
    try:
        got, want = float(observed), float(q["expected_answer"])
    except (TypeError, ValueError):
        return False
    nd = q.get("round_decimals", 0)
    return abs(round(got, nd) - round(want, nd)) < 1e-9


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", required=True)
    ap.add_argument("--model", default="gpt-5.1")
    ap.add_argument("--sleep", type=float, default=0.3)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    key_var = "OPENAI_API_KEY" if args.model.startswith(("gpt-", "o")) else "GROQ_API_KEY"
    api_key = os.environ.get(key_var)
    if not api_key:
        sys.exit(f"{key_var} not set")

    schemas = load_schemas(args.pack)
    questions = [json.loads(l) for l in
                 (Path(args.pack) / "questions.jsonl").read_text().splitlines()
                 if l.strip()]

    con = duckdb.connect()
    for csv_path in (Path(args.pack) / "tables").glob("*.csv"):
        con.execute(
            f'CREATE VIEW "{csv_path.stem}" AS '
            f"SELECT * FROM read_csv_auto('{csv_path.resolve()}')")

    rows = []
    for i, q in enumerate(questions, 1):
        prompt = f"Tables:\n{schemas}\n\nQuestion: {q['question']}"
        req = build_request(args.model, SYSTEM, prompt, api_key)
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    raw = json.load(resp)["choices"][0]["message"]["content"]
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    time.sleep(min(2 ** attempt * 2, 30))
                    continue
                raise
        sql = extract_sql(raw)
        try:
            row = con.execute(sql).fetchone()
            observed = row[0] if row else None
            exec_error = None
        except Exception as exc:  # noqa: BLE001 - any failure scores as wrong
            observed, exec_error = None, str(exc)[:200]
        ok = answers_match(q, observed)
        rows.append({"id": q["id"], "kind": q["source"]["kind"],
                     "expected": q["expected_answer"],
                     "model_sql": sql, "observed": _jsonable(observed),
                     "exec_error": exec_error, "correct": ok,
                     "used_between": "between" in sql.lower()})
        print(f"[{i}/{len(questions)}] {q['id']} {'OK ' if ok else 'MISS'} "
              f"{'(exec error)' if exec_error else ''}")
        time.sleep(args.sleep)

    n = len(rows)
    correct = sum(r["correct"] for r in rows)
    misses = [r for r in rows if not r["correct"]]
    summary = {
        "model": args.model, "n": n, "correct": correct,
        "accuracy": round(correct / n, 3),
        "exec_errors": sum(1 for r in rows if r["exec_error"]),
        "between_usage": sum(r["used_between"] for r in rows),
        "misses_by_kind": {},
    }
    for r in misses:
        summary["misses_by_kind"][r["kind"]] = \
            summary["misses_by_kind"].get(r["kind"], 0) + 1
    Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows},
                                         indent=2))
    print(f"\n{correct}/{n} correct ({summary['accuracy']:.1%}); "
          f"misses by kind: {summary['misses_by_kind']}")


def _jsonable(v):
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    return str(v)


if __name__ == "__main__":
    main()
