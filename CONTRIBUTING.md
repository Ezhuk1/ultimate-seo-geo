# Contributing to ultimate-seo-geo

Thank you for contributing to `ultimate-seo-geo`!

## Architectural Principles

1. **Zero External Dependencies:**
   All core inspection engine code in `engine/` MUST use Python 3.10+ standard library only. Do not add external `pip` dependencies to `dependencies` in `pyproject.toml`.
2. **"Unknown != Failure" Invariant:**
   Unobserved signals (e.g. absent API keys, local files without wire headers) must evaluate to `UNKNOWN` or `NOT_MEASURED` with 0 score penalty.
3. **6-Tier Epistemic Hierarchy:**
   Never inflate practical heuristics to protocol standards. All rules in `rules/*.json` must cite verified sources in `references/sources.json`.
4. **Zero Fabrication:**
   Never generate or accept synthetic metrics, fake case studies, or unverified quotes.

## Development & Testing Workflow

Before submitting a Pull Request, run all evaluation suites locally:

```bash
# 1. Autonomous Engine Integration Suite
python evals/test_engine.py

# 2. Hardening & Capability Rounds (2 through 6)
python evals/test_engine_round2.py
python evals/test_engine_round3.py
python evals/test_engine_round4.py
python evals/test_engine_round5.py
python evals/test_engine_round6.py

# 3. Canonical Evals & Mutation Defense Harness
python evals/run_evals.py

# 4. Packaging smoke test
pip install .
python -c "from engine.rules import get_rule_registry; assert len(get_rule_registry()) > 50"
```

All suites must pass with 100% green status.
