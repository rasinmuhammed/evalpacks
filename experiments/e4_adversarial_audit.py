#!/usr/bin/env python3
"""E4: adversarial audit of the evalpack's own shipped questions.

The UIUC audit found 52.8% annotation errors in BIRD Mini-Dev using an
agent that reviews each item plus expert adjudication. This applies the
same treatment to our own shipped questions: a strong model reviews every
(question, gold SQL, expected answer, schema) tuple and flags defects.
Flags are then adjudicated by hand and the confirmed rate is reported
next to BIRD's. Honesty rule: every flag ships in the results file with
the model's reasoning, adjudicated or not.
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

from run_closedbook import build_request

AUDIT_PROMPT = """You are auditing one item of a text-to-SQL style benchmark for annotation errors, the way the SAR-Agent audit of BIRD did. Be adversarial: your job is to find defects, not to approve.

Table schemas (column names as they appear in the CSV files):
{schemas}

Benchmark item:
Question: {question}
Gold SQL: {gold_sql}
Expected answer: {expected}

Check, in order:
1. SEMANTIC MISMATCH: does the gold SQL faithfully implement exactly what the question asks (boundaries, inclusivity, rounding, aggregation)?
2. AMBIGUITY: could a competent reader interpret the question in a materially different way that yields a different correct answer?
3. SCHEMA: does the SQL reference the right tables/columns for the question?
4. ANSWER TYPE: is the expected answer consistent with what the SQL returns?

Reply with ONLY a JSON object:
{{"defect": true/false, "category": "semantic_mismatch|ambiguity|schema|answer_type|none", "reason": "<one sentence>"}}"""


def load_schemas(pack):
    lines = []
    for csv_path in sorted((Path(pack) / "tables").glob("*.csv")):
        with open(csv_path) as fh:
            header = next(csv.reader(fh))
        lines.append(f"  {csv_path.stem}({', '.join(header)})")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", required=True)
    ap.add_argument("--model", default="gpt-5.1")
    ap.add_argument("--sleep", type=float, default=0.3)
    ap.add_argument("--out", default="e4_audit_results.json")
    args = ap.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("OPENAI_API_KEY not set")

    schemas = load_schemas(args.pack)
    questions = [json.loads(l) for l in
                 (Path(args.pack) / "questions.jsonl").read_text().splitlines()
                 if l.strip()]

    rows, flagged = [], 0
    for i, q in enumerate(questions, 1):
        prompt = AUDIT_PROMPT.format(
            schemas=schemas, question=q["question"],
            gold_sql=q["gold_sql"], expected=q["expected_answer"])
        req = build_request(args.model, "You audit benchmarks for defects.",
                            prompt, api_key)
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    raw = json.load(resp)["choices"][0]["message"]["content"].strip()
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    time.sleep(min(2 ** attempt * 2, 30))
                    continue
                raise
        try:
            verdict = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        except Exception:
            verdict = {"defect": None, "category": "unparseable", "reason": raw[:200]}
        if verdict.get("defect"):
            flagged += 1
        rows.append({"id": q["id"], "kind": q["source"]["kind"], **verdict})
        print(f"[{i}/{len(questions)}] {q['id']} defect={verdict.get('defect')} "
              f"{verdict.get('category')}: {str(verdict.get('reason'))[:80]}")
        time.sleep(args.sleep)

    summary = {"model": args.model, "n": len(rows), "flagged": flagged,
               "flag_rate": round(flagged / len(rows), 3)}
    Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
    print(f"\nflag rate: {flagged}/{len(rows)} — adjudicate each flag by hand; "
          f"results: {args.out}")


if __name__ == "__main__":
    main()
