# PTCG Gold Knowledge Database

This directory contains the evidence-first SQLite source of truth for competitive Pokemon TCG decision research targeted at the CABT-based Kaggle competition. Research content belongs in the database; this file is operational documentation only.

## Contents

- `ptcg_gold.sqlite`: normalized knowledge database with provenance, claims, strategies, rules, matchup plans, anti-patterns, probability models, search features, replay observations, contradictions, research questions, tags, and SQLite FTS5.
- `schema.sql`: database schema.
- `build_db.py`: deterministic local builder and seed ingestion script. It stores hashes/counts for local evidence instead of copying private card/replay bodies.
- `query_db.py`: read-only inspection CLI.
- `validate_db.py`: integrity, provenance, URL, evidence-link, and FTS checks.
- `RESEARCH_STATUS.json`: machine-readable coverage, counts, open questions, and next research directions.

## Query

Run from the repository root (`ptcg-rl`):

```bash
python knowledge_base/query_db.py search "prize mapping dragapult"
python knowledge_base/query_db.py rules --context attack --archetype dragapult
python knowledge_base/query_db.py matchup "Mega Abomasnow" "Dragapult"
python knowledge_base/query_db.py sources --tier A --topic sequencing
python knowledge_base/query_db.py unresolved
python knowledge_base/query_db.py stats
python knowledge_base/query_db.py claims --type matchup_principle --confidence HIGH
```

## Validate

```bash
python knowledge_base/validate_db.py
```

Validation returns a non-zero status for integrity or evidence-coverage failures. Open questions and explicitly unresolved contradictions are reported as warnings, not treated as database errors.

## Refresh

After reviewing and updating the source/claim seed data in `build_db.py`, rebuild the generated database:

```bash
python knowledge_base/build_db.py
python knowledge_base/validate_db.py
```

The builder is intentionally local and bounded: it does not download sources, launch Kaggle jobs, alter production code, or copy full copyrighted pages/replay bodies.
