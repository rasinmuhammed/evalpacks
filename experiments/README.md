# Experiments

Harnesses and raw results for the paper's experimental section. Every
result file preserves per-question model outputs, so adjudications can be
re-judged by anyone who disagrees.

| experiment | script | needs | approx cost |
|---|---|---|---|
| E1a closed-book answerability | `run_closedbook.py` | GROQ_API_KEY or OPENAI_API_KEY | cents |
| E1b completion (membership) probe | `run_completion_probe.py` | same | cents |
| E2 rotation invariance | `e2_seed_stability.py` | none (local) | free |
| E3 scale and cost | `e3_scale.py` | none (local, idle machine) | free |
| E4 adversarial audit | `e4_adversarial_audit.py` | OPENAI_API_KEY | ~$0.15 |
| E5 open-book evaluation | `run_openbook.py` | either key | cents |

Examples:

    python run_closedbook.py --pack ../pack --model gpt-5-mini
    python e2_seed_stability.py
    python e3_scale.py 10000 100000 1000000
    python e4_adversarial_audit.py --pack ../pack --model gpt-5.1

## The BIRD side of E1

BIRD Mini-Dev items are not redistributed here. `prepare_bird.py` rebuilds
the 120-question scalar subset from official sources: questions from the
HuggingFace dataset `birdsql/bird_mini_dev`, databases from the official
BIRD dev.zip, and gold answers computed locally by executing the official
gold SQL with sqlite3. BIRD is CC BY-SA 4.0; the result files in
`results/` contain per-item scalar values derived that way, with this
notice as attribution.

    python prepare_bird.py --bird-dev <path>/dev_databases --out bird_items.jsonl
    python run_closedbook.py --items bird_items.jsonl --model gpt-5.1

## Reading the results

`results/closedbook_*.json` and `results/bird_closedbook_*.json` hold one
row per question with the raw model reply and a correctness flag; the
paper's stratified table is computed from the `expected` field magnitudes.
`results/e4_audit_results.json` holds every audit flag with the model's
reasoning, including the flags rejected in adjudication. Timing numbers in
`results/e3_results.json` came from an otherwise idle laptop; wall-clock
benchmarks taken under load are how we found (and fixed) a real generator
defect, which the paper recounts.
