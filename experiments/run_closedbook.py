#!/usr/bin/env python3
"""E1: closed-book contamination probe.

Ask a model the benchmark questions WITHOUT providing the database. On a
public benchmark, above-chance closed-book accuracy is evidence the items
(or the underlying data) leaked into training. On a freshly generated
evalpack, closed-book accuracy on the numeric families is chance-level by
construction: the entities and totals do not exist outside the pack.

Question classes are scored separately because they differ in guessability:

  numeric_exact   period totals, grand totals, rates: continuous answer
                  space, no informative prior. The contamination-sensitive
                  class.
  count           per-period row counts: integer space, weak priors.
  guessable       fk_integrity (the natural guess is 0) and argmax (seasonal
                  priors make December a good guess for retail). Closed-book
                  hits here measure priors, not memorization, and the paper
                  must not count them as contamination evidence either way.

Usage:
  python run_closedbook.py --pack /path/to/pack --model llama-3.3-70b-versatile
  python run_closedbook.py --bird bird_items.jsonl --model ...   # same format

Reads GROQ_API_KEY from the environment. Results are written next to the
pack as closedbook_results.json, one row per question with the raw model
output preserved for audit.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def is_openai(model):
    return model.startswith(("gpt-", "o3", "o4"))


def build_request(model, system, user, api_key):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if is_openai(model):
        # gpt-5 family: reasoning models reject temperature/max_tokens;
        # minimal effort keeps cost down and answers terse.
        payload["max_completion_tokens"] = 1500
        if model.startswith("gpt-5.1"):
            payload["reasoning_effort"] = "none"
        elif model.startswith("gpt-5"):
            payload["reasoning_effort"] = "minimal"
        else:
            payload["temperature"] = 0.0
        url = OPENAI_URL
    else:
        payload["temperature"] = 0.0
        payload["max_tokens"] = 64
        url = GROQ_URL
    return urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json",
                 "User-Agent": "evalpack-e1/0.1"},
    )

GUESSABLE_KINDS = {"fk_integrity", "outcome_curve_argmax"}
COUNT_KINDS = {"plan_row_count", "count"}

SYSTEM = (
    "You are being evaluated closed-book. You will be asked a question about "
    "a specific database table, but you are NOT given the data. Answer from "
    "your own knowledge or best estimate. Reply with ONLY the final answer: "
    "a single number (no thousands separators, no currency symbol) or the "
    "requested string. Never refuse; always produce your best answer."
)


def classify(q):
    kind = q.get("source", {}).get("kind", "")
    if kind in GUESSABLE_KINDS:
        return "guessable"
    if kind in COUNT_KINDS:
        return "count"
    return "numeric_exact"


def call_model(model, question, api_key, max_retries=5):
    req = build_request(model, SYSTEM, question, api_key)
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                out = json.load(resp)
            return out["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                wait = min(2 ** attempt * 2, 30)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("rate-limited beyond retries")


_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def parse_number(text):
    m = _NUM_RE.search(text.replace("$", ""))
    if not m:
        return None
    try:
        return float(m.group().replace(",", ""))
    except ValueError:
        return None


def is_correct(q, raw):
    if q["answer_type"] == "string":
        return str(q["expected_answer"]).lower() in raw.lower()
    got = parse_number(raw)
    if got is None:
        return False
    nd = q.get("round_decimals", 0)
    return abs(round(got, nd) - round(float(q["expected_answer"]), nd)) < 1e-9


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", help="evalpack directory (reads questions.jsonl)")
    ap.add_argument("--items", help="alternatively: a questions.jsonl-format file")
    ap.add_argument("--model", default="llama-3.3-70b-versatile")
    ap.add_argument("--out", default=None)
    ap.add_argument("--sleep", type=float, default=1.0,
                    help="seconds between calls (free-tier pacing)")
    args = ap.parse_args()

    key_var = "OPENAI_API_KEY" if is_openai(args.model) else "GROQ_API_KEY"
    api_key = os.environ.get(key_var)
    if not api_key:
        sys.exit(f"{key_var} not set")

    src = Path(args.pack) / "questions.jsonl" if args.pack else Path(args.items)
    questions = [json.loads(l) for l in src.read_text().splitlines() if l.strip()]

    rows = []
    for i, q in enumerate(questions, 1):
        raw = call_model(args.model, q["question"], api_key)
        ok = is_correct(q, raw)
        rows.append({
            "id": q["id"],
            "class": classify(q),
            "kind": q.get("source", {}).get("kind"),
            "expected": q["expected_answer"],
            "model_raw": raw,
            "correct": ok,
        })
        print(f"[{i}/{len(questions)}] {q['id']} {classify(q):13s} "
              f"expected={q['expected_answer']} got={raw[:40]!r} "
              f"{'HIT' if ok else 'miss'}")
        time.sleep(args.sleep)

    by_class = {}
    for r in rows:
        by_class.setdefault(r["class"], []).append(r["correct"])
    summary = {
        "model": args.model,
        "source": str(src),
        "n": len(rows),
        "per_class": {
            c: {"n": len(v), "hits": sum(v), "accuracy": sum(v) / len(v)}
            for c, v in sorted(by_class.items())
        },
    }
    out_path = Path(args.out) if args.out else src.parent / f"closedbook_{args.model.replace('/', '_')}.json"
    out_path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
    print("\n== closed-book summary ==")
    for c, s in summary["per_class"].items():
        print(f"  {c:13s} {s['hits']}/{s['n']}  ({s['accuracy']:.1%})")
    print(f"written: {out_path}")


if __name__ == "__main__":
    main()
