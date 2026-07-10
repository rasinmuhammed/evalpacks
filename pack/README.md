# Evalpack: northstar_retail

35 question/answer pairs over the CSV tables in `tables/`.
Every expected answer was **declared before the data was generated** and then
verified by executing the gold SQL with DuckDB against these exact files.

Re-verify yourself (30 seconds):

```bash
pip install duckdb
python verify.py
```

`certificate.json` records the verification run (DuckDB version, per-question
observed values, FK orphan counts). `manifest.json` records the generation
seed, the misata version, the spec hash, and every candidate question that
was dropped by the verification gate.

Regenerate the identical pack from `manifest.json`'s schema + seed with
[misata](https://github.com/rasinmuhammed/misata), or change the seed to get
a fresh database with the same declared answers where applicable.
