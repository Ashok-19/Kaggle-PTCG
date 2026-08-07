#!/usr/bin/env python3
"""Validate provenance, referential integrity, and coverage invariants for ptcg_gold.sqlite."""

from __future__ import annotations

import sqlite3
import sys
import hashlib
from pathlib import Path
from urllib.parse import urlparse


HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "ptcg_gold.sqlite"

VALID_CONFIDENCE = {"VERY_HIGH", "HIGH", "MEDIUM", "LOW", "HYPOTHESIS"}
VALID_TIERS = {"A", "B", "C", "D"}


def add_error(errors: list[str], message: str) -> None:
    errors.append(message)


def validate() -> tuple[list[str], list[str], dict[str, int]]:
    errors: list[str] = []
    warnings: list[str] = []
    counts: dict[str, int] = {}
    if not DB_PATH.exists():
        return [f"database cannot be opened because it does not exist: {DB_PATH}"], warnings, counts

    try:
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        return [f"database cannot be opened: {exc}"], warnings, counts

    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("SELECT 1").fetchone()
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            add_error(errors, f"SQLite integrity_check failed: {integrity}")

        fk_errors = db.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            add_error(errors, f"foreign key check failed for {len(fk_errors)} rows: {fk_errors[:3]}")

        duplicate_sources = db.execute(
            "SELECT canonical_url, COUNT(*) AS count FROM sources GROUP BY canonical_url HAVING count > 1"
        ).fetchall()
        if duplicate_sources:
            add_error(errors, f"duplicate canonical sources: {[row['canonical_url'] for row in duplicate_sources]}")

        missing_claim_sources = db.execute(
            "SELECT c.id FROM claims c LEFT JOIN claim_sources cs ON cs.claim_id=c.id "
            "GROUP BY c.id HAVING COUNT(cs.source_id)=0"
        ).fetchall()
        if missing_claim_sources:
            add_error(errors, f"claims without source links: {[row['id'] for row in missing_claim_sources]}")

        weak_high_claims = db.execute(
            "SELECT c.id, c.confidence, COALESCE(MAX(CASE s.credibility_tier WHEN 'A' THEN 4 WHEN 'B' THEN 3 WHEN 'C' THEN 2 WHEN 'D' THEN 1 ELSE 0 END),0) AS best_tier, c.justification "
            "FROM claims c LEFT JOIN claim_sources cs ON cs.claim_id=c.id LEFT JOIN sources s ON s.id=cs.source_id "
            "WHERE c.confidence IN ('HIGH','VERY_HIGH') GROUP BY c.id"
        ).fetchall()
        for row in weak_high_claims:
            if row["best_tier"] < 3 and not row["justification"]:
                add_error(errors, f"{row['confidence']} claim {row['id']} has only weak sources and no justification")

        invalid_confidence_rows = []
        for table, column in [
            ("claims", "confidence"), ("strategies", "confidence"), ("archetypes", "source_confidence"),
            ("matchups", "confidence"), ("decision_rules", "confidence"), ("anti_patterns", "confidence"),
            ("interactions", "confidence"), ("search_features", "confidence"), ("environment_facts", "confidence"),
            ("people", "credential_confidence"),
        ]:
            values = db.execute(f"SELECT DISTINCT {column} AS value FROM {table}").fetchall()
            invalid = [row["value"] for row in values if row["value"] not in VALID_CONFIDENCE]
            if invalid:
                invalid_confidence_rows.append(f"{table}.{column}: {invalid}")
        if invalid_confidence_rows:
            add_error(errors, "invalid confidence values: " + "; ".join(invalid_confidence_rows))

        invalid_tiers = db.execute(
            "SELECT DISTINCT credibility_tier FROM sources WHERE credibility_tier NOT IN ('A','B','C','D')"
        ).fetchall()
        if invalid_tiers:
            add_error(errors, f"invalid source tiers: {[row[0] for row in invalid_tiers]}")

        orphan_plans = db.execute(
            "SELECT p.id FROM matchup_plans p LEFT JOIN matchups m ON m.id=p.matchup_id WHERE m.id IS NULL"
        ).fetchall()
        if orphan_plans:
            add_error(errors, f"orphan matchup plans: {[row['id'] for row in orphan_plans]}")

        orphan_strategies = db.execute(
            "SELECT s.id FROM strategies s LEFT JOIN strategy_evidence e ON e.strategy_id=s.id "
            "GROUP BY s.id HAVING COUNT(e.claim_id)=0"
        ).fetchall()
        if orphan_strategies:
            add_error(errors, f"orphan strategies without evidence: {[row['id'] for row in orphan_strategies]}")

        for table, link_table, id_column in [
            ("decision_rules", "decision_rule_claims", "decision_rule_id"),
            ("anti_patterns", "anti_pattern_claims", "anti_pattern_id"),
            ("interactions", "interaction_claims", "interaction_id"),
            ("probability_models", "probability_model_claims", "probability_model_id"),
            ("search_features", "search_feature_claims", "search_feature_id"),
        ]:
            orphan_rows = db.execute(
                f"SELECT t.id FROM {table} t LEFT JOIN {link_table} l ON l.{id_column}=t.id "
                "GROUP BY t.id HAVING COUNT(l.claim_id)=0"
            ).fetchall()
            if orphan_rows:
                add_error(errors, f"{table} rows without evidence: {[row['id'] for row in orphan_rows]}")

        fts_entities = [
            ("claim", "claims"), ("strategy", "strategies"), ("decision_rule", "decision_rules"),
            ("anti_pattern", "anti_patterns"), ("matchup_plan", "matchup_plans"), ("research_question", "research_questions"),
        ]
        for entity_type, table in fts_entities:
            expected = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            actual = db.execute("SELECT COUNT(*) FROM knowledge_fts WHERE entity_type=?", (entity_type,)).fetchone()[0]
            counts[f"fts_{entity_type}"] = actual
            if expected != actual:
                add_error(errors, f"FTS count mismatch for {entity_type}: expected {expected}, got {actual}")
            duplicates = db.execute(
                "SELECT entity_id, COUNT(*) AS count FROM knowledge_fts WHERE entity_type=? GROUP BY entity_id HAVING count != 1",
                (entity_type,),
            ).fetchall()
            if duplicates:
                add_error(errors, f"FTS duplicate/missing rows for {entity_type}: {[row['entity_id'] for row in duplicates[:10]]}")

        unknown_fts = db.execute(
            "SELECT DISTINCT entity_type FROM knowledge_fts WHERE entity_type NOT IN ('claim','strategy','decision_rule','anti_pattern','matchup_plan','research_question')"
        ).fetchall()
        if unknown_fts:
            add_error(errors, f"unknown FTS entity types: {[row[0] for row in unknown_fts]}")

        malformed_urls = []
        for row in db.execute("SELECT id, url, canonical_url FROM sources"):
            for column in ("url", "canonical_url"):
                value = row[column]
                parsed = urlparse(value)
                valid = value.startswith("repo://") or (
                    parsed.scheme in {"http", "https"} and bool(parsed.netloc) and " " not in value
                )
                if not valid:
                    malformed_urls.append(f"{row['id']}.{column}={value}")
        if malformed_urls:
            add_error(errors, f"obviously malformed URLs: {malformed_urls[:10]}")

        stale_local_hashes = []
        for row in db.execute("SELECT id, url, content_hash_or_identifier FROM sources WHERE content_hash_or_identifier IS NOT NULL"):
            if not row["url"].startswith("repo://ptcg-rl/"):
                continue
            local_path = HERE.parent / row["url"].removeprefix("repo://ptcg-rl/")
            if not local_path.is_file():
                add_error(errors, f"hashed local source is missing or not a file: {row['id']} -> {local_path}")
                continue
            actual_hash = hashlib.sha256(local_path.read_bytes()).hexdigest()
            if actual_hash != row["content_hash_or_identifier"]:
                stale_local_hashes.append(row["id"])
        if stale_local_hashes:
            add_error(errors, f"local source hashes are stale: {stale_local_hashes}")

        solved_questions = db.execute(
            "SELECT q.id FROM research_questions q LEFT JOIN research_question_claims qc ON qc.research_question_id=q.id "
            "WHERE q.status='SOLVED' AND (q.best_current_answer IS NULL OR TRIM(q.best_current_answer)='' OR qc.claim_id IS NULL) "
            "GROUP BY q.id"
        ).fetchall()
        if solved_questions:
            add_error(errors, f"solved questions without answer/evidence: {[row['id'] for row in solved_questions]}")

        missing_competition_scope = db.execute(
            "SELECT id FROM claims WHERE competition_applicability='DIRECT' AND "
            "(TRIM(scope)='' OR TRIM(format_scope)='')"
        ).fetchall()
        if missing_competition_scope:
            add_error(errors, f"direct competition claims missing scope/version: {[row['id'] for row in missing_competition_scope]}")

        unsupported_question_links = db.execute(
            "SELECT qc.research_question_id, qc.claim_id FROM research_question_claims qc "
            "LEFT JOIN claims c ON c.id=qc.claim_id WHERE c.id IS NULL"
        ).fetchall()
        if unsupported_question_links:
            add_error(errors, "research question links reference missing claims")

        # These are expected unresolved gaps, not validation failures.
        unresolved_q = db.execute(
            "SELECT id FROM research_questions WHERE status IN ('OPEN','IN_REVIEW','BLOCKED') AND priority IN ('P0','P1')"
        ).fetchall()
        if unresolved_q:
            warnings.append(f"{len(unresolved_q)} P0/P1 research questions remain open/in review/blocked")
        unresolved_c = db.execute("SELECT COUNT(*) FROM contradictions WHERE unresolved=1").fetchone()[0]
        if unresolved_c:
            warnings.append(f"{unresolved_c} contradictions remain explicitly unresolved")

        for table in [
            "sources", "people", "claims", "strategies", "archetypes", "cards", "matchups", "matchup_plans",
            "decision_rules", "anti_patterns", "interactions", "probability_models", "search_features",
            "observed_replay_patterns", "contradictions", "research_questions",
        ]:
            counts[table] = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.Error as exc:
        add_error(errors, f"SQLite validation query failed: {exc}")
    finally:
        db.close()
    return errors, warnings, counts


def main() -> int:
    errors, warnings, counts = validate()
    print("PTCG KNOWLEDGE DB VALIDATION")
    print(f"database: {DB_PATH}")
    print("result: FAIL" if errors else "result: PASS")
    if errors:
        print("errors:")
        for error in errors:
            print(f"- {error}")
    if warnings:
        print("warnings:")
        for warning in warnings:
            print(f"- {warning}")
    print("counts:")
    for key in sorted(counts):
        print(f"- {key}: {counts[key]}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
