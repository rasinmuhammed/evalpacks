#!/usr/bin/env python3
"""E2: rotation invariance. Same spec, five seeds.

Claims under test:
  1. Every rotated pack verifies (the guarantee is seed-independent).
  2. The declared answer key is identical across seeds for the
     deterministic families (period totals, grand total, plan row counts,
     argmax, FK). Rate anchors may gate differently per seed and are
     reported separately.
  3. The underlying rows are essentially disjoint (rotation actually
     produces a new database, not a shuffled one).
"""
import json
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).parent))

SEEDS = [11, 222, 3333, 44444, 20260710]
DETERMINISTIC = {"outcome_curve_period", "outcome_curve_total",
                 "plan_row_count", "outcome_curve_argmax", "fk_integrity"}


def main():
    from misata.schema import SchemaConfig
    from misata.evalpack import build_evalpack

    base = json.load(open(
        Path(__file__).parent.parent / "schema_northstar_retail.json"))

    packs = {}
    for seed in SEEDS:
        schema = SchemaConfig(**base)
        schema.seed = seed
        out = Path(f"/tmp/e2_pack_{seed}")
        result = build_evalpack(schema, out)
        packs[seed] = (out, result)
        print(f"seed {seed}: shipped={len(result.questions)} "
              f"dropped={len(result.dropped)} verified={result.all_verified}")

    # 1. all verified
    all_ok = all(r.all_verified for _, r in packs.values())

    # 2. deterministic answer keys identical across seeds
    keys = {}
    rate_counts = {}
    for seed, (out, result) in packs.items():
        det = {}
        for q in result.questions:
            kind = q.source["kind"]
            if kind in DETERMINISTIC:
                label = (kind, q.source.get("period"),
                         q.source.get("table"), q.source.get("relationship"))
                det[label] = q.expected_answer
        keys[seed] = det
        rate_counts[seed] = sum(
            1 for q in result.questions
            if q.source["kind"] == "rate_curve_anchor")
    first = keys[SEEDS[0]]
    identical = all(keys[s] == first for s in SEEDS[1:])

    # 3. row disjointness on the fact table
    con = duckdb.connect()
    for seed, (out, _) in packs.items():
        con.execute(
            f"CREATE VIEW o{seed} AS SELECT * FROM "
            f"read_csv_auto('{out}/tables/orders.csv')")
    a, b = SEEDS[0], SEEDS[1]
    shared = con.execute(
        f"SELECT COUNT(*) FROM o{a} JOIN o{b} USING (order_id)").fetchone()[0]
    total = con.execute(f"SELECT COUNT(*) FROM o{a}").fetchone()[0]

    summary = {
        "seeds": SEEDS,
        "all_packs_verified": all_ok,
        "deterministic_keys_identical": identical,
        "deterministic_questions_per_pack": len(first),
        "rate_anchors_shipped_per_seed": rate_counts,
        "shared_order_ids_seed_pair": shared,
        "fact_rows": total,
        "shared_fraction": round(shared / total, 5),
    }
    Path("e2_results.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
