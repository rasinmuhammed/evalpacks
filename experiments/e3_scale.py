#!/usr/bin/env python3
"""E3: generation and verification cost as pack size grows.

One schema family, row count driven by the declared totals: a 12-month
curve summing to (N * 62) dollars at avg transaction 62 yields ~N fact
rows. Reports wall-clock for (a) building the verified pack and (b) a
consumer re-running verify.py, plus pack size on disk.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

from misata.schema import SchemaConfig, Table, Column, Relationship
from misata import OutcomeCurveBuilder
from misata.evalpack import build_evalpack


def make_schema(n_rows):
    total = n_rows * 62
    monthly = [round(total / 12 * (0.7 + 0.05 * i), 2) for i in range(12)]
    scale = total / sum(monthly)
    monthly = [round(m * scale, 2) for m in monthly]

    schema = SchemaConfig(
        name=f"scale_{n_rows}",
        seed=7,
        tables=[
            Table(name="customers", row_count=max(100, n_rows // 50)),
            Table(name="orders", row_count=n_rows),
        ],
        columns={
            "customers": [
                Column(name="customer_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 50_000_000}),
                Column(name="name", type="text"),
            ],
            "orders": [
                Column(name="order_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 500_000_000}),
                Column(name="customer_id", type="foreign_key"),
                Column(name="amount", type="float",
                       distribution_params={"min": 1, "max": 5000}),
                Column(name="order_date", type="datetime",
                       distribution_params={"start": "2025-01-01",
                                            "end": "2025-12-31"}),
            ],
        },
        relationships=[
            Relationship(parent_table="customers", child_table="orders",
                         parent_key="customer_id", child_key="customer_id"),
        ],
    )
    b = OutcomeCurveBuilder("orders", column="amount", time_column="order_date")
    for i, m in enumerate(monthly, 1):
        b = b.anchor(f"2025-{i:02d}", m)
    curve = b.avg_value(62.0).row_bounds(1, 50_000_000).build()
    return OutcomeCurveBuilder.attach(schema, curve)


def dir_size_mb(path):
    return sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file()) / 1e6


def main():
    sizes = [int(s) for s in (sys.argv[1:] or ["10000", "100000", "1000000"])]
    results = []
    for n in sizes:
        out = Path(f"/tmp/e3_pack_{n}")
        t0 = time.perf_counter()
        result = build_evalpack(make_schema(n), out)
        t_build = time.perf_counter() - t0

        t0 = time.perf_counter()
        proc = subprocess.run([sys.executable, str(out / "verify.py")],
                              capture_output=True, text=True)
        t_verify = time.perf_counter() - t0

        actual_rows = json.load(open(out / "manifest.json"))["tables"]
        row = {
            "target_rows": n,
            "actual_fact_rows": actual_rows["orders"],
            "questions": len(result.questions),
            "all_verified": result.all_verified,
            "consumer_verify_ok": proc.returncode == 0,
            "build_s": round(t_build, 1),
            "verify_s": round(t_verify, 1),
            "size_mb": round(dir_size_mb(out), 1),
        }
        results.append(row)
        print(row)

    Path("e3_results.json").write_text(json.dumps(results, indent=2))
    print("written: e3_results.json")


if __name__ == "__main__":
    main()
