#!/usr/bin/env python3
"""Rebuild the northstar_retail pack from its spec and seed.

The schema and seed fully determine the database. Running this produces
byte-identical answers to the shipped pack (a fresh seed produces a brand
new database that still satisfies the same declared aggregates).

    pip install 'misata[evalpack]'
    python regenerate.py            # same seed, same pack
    python regenerate.py --seed 99  # new database, same declared answers
"""
import argparse
import json

from misata.schema import SchemaConfig
from misata.evalpack import build_evalpack

parser = argparse.ArgumentParser()
parser.add_argument("--seed", type=int, default=None,
                    help="Override the generation seed (default: the shipped seed)")
parser.add_argument("--out", default="pack", help="Output directory")
args = parser.parse_args()

schema = SchemaConfig(**json.load(open("schema_northstar_retail.json")))
if args.seed is not None:
    schema.seed = args.seed

result = build_evalpack(schema, args.out)
print(result.summary())
print("all verified:", result.all_verified)
