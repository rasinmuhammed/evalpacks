# Evalpacks: eval databases generated from the answer key

A recent VLDB 2026 audit found that **52.8% of BIRD Mini-Dev and 62.8% of
Spider 2.0-Snow answer keys are wrong** ([Jin et al., arXiv:2601.08778](https://arxiv.org/abs/2601.08778)).
Correcting just 100 examples moved agent leaderboard rankings by up to 9
positions. The root cause is structural: benchmarks take a database as given
and annotate question/answer pairs afterwards, and that annotation step is
where the errors creep in.

This repo demonstrates the inverted construction. **Declare the answers
first, then generate the database to match.**

The pack in [`pack/`](pack/) is a 75,000-row e-commerce database (customers,
products, orders) generated from a spec that declared, before any row
existed:

- exact monthly revenue for all of 2025 ($410,000.00 in January through
  $905,000.00 in December, with a post-holiday dip and a Black Friday ramp)
- a fraud rate rising from 2% to 3.5% across the year
- two foreign-key relationships with zero orphans

From that spec, 35 question/answer pairs were derived and shipped, for
example: *"In the orders table, what is the total of amount during November
2025?"* The expected answer is not something a human annotated by reading
the data. It is the number the data was constructed to satisfy.

## Verify it yourself, ~30 seconds

```bash
pip install duckdb
python pack/verify.py
```

Every question's gold SQL is executed by DuckDB against the shipped CSV
files and compared to the declared answer. DuckDB shares no code with the
generator, so this is not the generator grading its own homework. Expected
output: `35/35 verified exactly`.

Change one value in one CSV and `verify.py` fails. That is the entire trust
model: no claims, just a check you can run.

## What is in the pack

| File | What it is |
|---|---|
| `tables/*.csv` | the database (customers, products, orders) |
| `questions.jsonl` | 35 verified questions with gold SQL and expected answers |
| `certificate.json` | per-question DuckDB verification results, FK proof, seed, spec hash |
| `manifest.json` | full generation spec, plus every candidate question that was **dropped** |
| `verify.py` | standalone re-verification script |

The `dropped_questions` section of the manifest is worth reading. Declared
fraud rates are subject to count rounding (you cannot have exactly 3.1818%
of 437 rows), so rate questions that failed exact verification were dropped
and logged rather than shipped. Nothing inexact ships.

## Why fictional data is the point

Every entity in this database is plausible fiction. A model cannot answer
"which month had the highest revenue" from memorized world knowledge; it has
to query the data. And because the spec plus a seed fully determine the
pack, you can regenerate a **brand new database with the same declared
answers** any time contamination is a concern:

```bash
pip install 'misata[evalpack]'
python regenerate.py --seed 99
```

Same declared aggregates, same verified guarantee, entirely different rows.

## What is guaranteed and what is not

Guaranteed by construction and verified by execution:

- period aggregate totals, exact to the cent
- grand totals and per-period row counts
- argmax questions (only emitted when the declared maximum is unique)
- foreign-key integrity (zero orphans)
- rate anchors, only when exactly achievable (the rest are dropped and logged)

Not claimed:

- semantic realism of names and labels (they are deliberate fiction)
- coverage of arbitrary SQL: current question families are aggregates,
  counts, rates, argmax, and integrity checks
- that this replaces human-authored benchmarks; it complements them for the
  error classes where annotation-after-the-fact fails

## How it works

Generated with [misata](https://github.com/rasinmuhammed/misata)
(`pip install 'misata[evalpack]'`), an open-source engine for
outcome-conformant synthetic data: declare aggregate curves, rates, and
relationships, and it generates multi-table data that satisfies them exactly
(method paper: [arXiv:2606.08736](https://arxiv.org/abs/2606.08736)). The
evalpack layer derives questions from the declared spec and gates every one
through independent DuckDB verification against the written files.

```bash
misata evalpack --config your_schema.yaml -o your_pack --seed 42
```

MIT licensed. Issues and skepticism welcome; the fastest way to make this
better is to break it.
