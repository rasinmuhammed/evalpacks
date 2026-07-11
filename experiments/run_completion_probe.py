#!/usr/bin/env python3
"""E1b: question-text membership probe (completion test).

Closed-book answer recall (E1a) came back near zero on BIRD for open
models, so this probes the channel where benchmark contamination actually
lives: verbatim familiarity with the question text itself. The model gets
the first ~60% of a benchmark question and is asked to continue the text
at temperature 0. A continuation that reproduces the true suffix is
membership evidence: the item was in training data.

Scoring: token-level overlap between the model continuation and the true
suffix, plus a strict "verbatim start" flag (first 6 tokens of the true
suffix reproduced exactly). Reported as distributions, not a single
number, because English is predictable and some overlap is expected by
fluency alone. The evalpack side is a *control for the probe itself*:
those questions were generated after the model's training cutoff, so any
overlap measured there is the fluency baseline, not membership.

Usage:
  python run_completion_probe.py --items bird_items.jsonl --model ... --n 60
  python run_completion_probe.py --pack /path/to/pack --model ... --n 35
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

SYSTEM = (
    "Continue the text exactly as it appeared in the original source. "
    "Output only the continuation, nothing else."
)


def call_model(model, prefix, api_key, max_retries=5):
    from run_closedbook import build_request
    req = build_request(model, SYSTEM, prefix, api_key)
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                time.sleep(min(2 ** attempt * 2, 30))
                continue
            raise
    raise RuntimeError("rate-limited beyond retries")


def tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def overlap_f1(pred, true):
    p, t = tokens(pred), tokens(true)
    if not p or not t:
        return 0.0
    common = 0
    t_pool = list(t)
    for tok in p:
        if tok in t_pool:
            t_pool.remove(tok)
            common += 1
    prec = common / len(p)
    rec = common / len(t)
    return 2 * prec * rec / (prec + rec) if prec + rec else 0.0


def verbatim_start(pred, true, k=6):
    return tokens(pred)[:k] == tokens(true)[:k] and len(tokens(true)) >= k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items")
    ap.add_argument("--pack")
    ap.add_argument("--model", default="llama-3.3-70b-versatile")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--split", type=float, default=0.6)
    ap.add_argument("--sleep", type=float, default=1.2)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from run_closedbook import is_openai
    key_var = "OPENAI_API_KEY" if is_openai(args.model) else "GROQ_API_KEY"
    api_key = os.environ.get(key_var)
    if not api_key:
        sys.exit(f"{key_var} not set")

    src = Path(args.pack) / "questions.jsonl" if args.pack else Path(args.items)
    questions = [json.loads(l)["question"]
                 for l in src.read_text().splitlines() if l.strip()]
    questions = [q for q in questions if len(q.split()) >= 12][:args.n]

    rows = []
    for i, q in enumerate(questions, 1):
        words = q.split()
        cut = max(6, int(len(words) * args.split))
        prefix, suffix = " ".join(words[:cut]), " ".join(words[cut:])
        pred = call_model(args.model, prefix, api_key)
        f1 = overlap_f1(pred, suffix)
        vb = verbatim_start(pred, suffix)
        rows.append({"prefix": prefix, "true_suffix": suffix,
                     "continuation": pred, "overlap_f1": round(f1, 3),
                     "verbatim_start": vb})
        print(f"[{i}/{len(questions)}] f1={f1:.2f} verbatim={vb}")
        time.sleep(args.sleep)

    f1s = sorted(r["overlap_f1"] for r in rows)
    n = len(f1s)
    summary = {
        "model": args.model,
        "source": str(src),
        "n": n,
        "mean_f1": round(sum(f1s) / n, 3),
        "median_f1": round(f1s[n // 2], 3),
        "p90_f1": round(f1s[int(n * 0.9)], 3),
        "verbatim_start_rate": round(sum(r["verbatim_start"] for r in rows) / n, 3),
    }
    Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
    print("\n== completion probe summary ==")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
