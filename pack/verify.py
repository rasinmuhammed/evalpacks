#!/usr/bin/env python3
"""Independently re-verify this evalpack: run every gold SQL with DuckDB
against the CSVs in tables/ and compare to the expected answers.

Usage: python verify.py     (exits 1 on any mismatch)
"""
import json
import sys
from pathlib import Path

import duckdb

HERE = Path(__file__).parent
con = duckdb.connect()
for csv in sorted((HERE / "tables").glob("*.csv")):
    path = str(csv.resolve()).replace("'", "''")
    con.execute(
        'CREATE VIEW "%s" AS SELECT * FROM read_csv_auto(\'%s\')'
        % (csv.stem, path)
    )

failures = 0
total = 0
for line in (HERE / "questions.jsonl").read_text().splitlines():
    if not line.strip():
        continue
    q = json.loads(line)
    total += 1
    row = con.execute(q["gold_sql"]).fetchone()
    observed = row[0] if row else None
    expected = q["expected_answer"]
    if q["answer_type"] == "string":
        ok = str(observed) == str(expected)
    else:
        nd = q.get("round_decimals", 0)
        try:
            ok = (
                observed is not None
                and abs(round(float(observed), nd) - round(float(expected), nd))
                < 1e-9
            )
        except (TypeError, ValueError):
            ok = False
    status = "OK  " if ok else "FAIL"
    if not ok:
        failures += 1
        print(f"{status} {q['id']}: expected={expected} observed={observed}")
        print(f"     {q['gold_sql']}")
    else:
        print(f"{status} {q['id']}: {expected}")

print(f"\n{total - failures}/{total} verified exactly")
sys.exit(1 if failures else 0)
