#!/usr/bin/env python3
"""Small read-only CLI for the local Pokemon TCG strategy knowledge DB."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "ptcg_gold.sqlite"


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}. Run build_db.py first.")
    db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def clean_query(text: str) -> str:
    terms = [term.replace('"', "") for term in text.split() if term.strip()]
    if not terms:
        raise SystemExit("Search text must contain at least one term.")
    return " AND ".join(f'"{term}"' for term in terms)


def print_rows(rows: list[sqlite3.Row], columns: list[str] | None = None) -> None:
    if not rows:
        print("No matching records.")
        return
    columns = columns or list(rows[0].keys())
    for row in rows:
        print("\n" + "-" * 80)
        for column in columns:
            value = row[column]
            if value is not None:
                print(f"{column}: {value}")


def command_search(db: sqlite3.Connection, text: str) -> None:
    terms = [term.replace('"', "") for term in text.split() if term.strip()]
    query = clean_query(text)
    rows = db.execute(
        "SELECT entity_type, entity_id, text FROM knowledge_fts WHERE knowledge_fts MATCH ? "
        "ORDER BY entity_type, entity_id LIMIT 100",
        (query,),
    ).fetchall()
    if not rows and len(terms) > 1:
        fallback = " OR ".join(f'"{term}"' for term in terms)
        rows = db.execute(
            "SELECT entity_type, entity_id, text FROM knowledge_fts WHERE knowledge_fts MATCH ? "
            "ORDER BY entity_type, entity_id LIMIT 100",
            (fallback,),
        ).fetchall()
        if rows:
            print("No single record matched every term; showing any-term matches.")
    print_rows(rows)


def command_rules(db: sqlite3.Connection, context: str | None, archetype: str | None) -> None:
    clauses = []
    values: list[str] = []
    if context:
        clauses.append("(decision_context LIKE ? OR scope LIKE ? OR name LIKE ?)")
        needle = f"%{context}%"
        values.extend([needle, needle, needle])
    if archetype:
        clauses.append("(name LIKE ? OR condition_text LIKE ? OR recommended_action_text LIKE ? OR scope LIKE ?)")
        needle = f"%{archetype}%"
        values.extend([needle, needle, needle, needle])
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    rows = db.execute(
        "SELECT id, priority, name, certainty_type, confidence, implementation_status, "
        "condition_text, recommended_action_text, avoid_action_text, scope "
        f"FROM decision_rules{where} ORDER BY priority, id",
        values,
    ).fetchall()
    if not rows and context and archetype:
        # A context label such as "main" may be a user's semantic category rather
        # than literal source text. The archetype-only fallback keeps the CLI useful
        # without changing the stored rule scope.
        rows = db.execute(
            "SELECT id, priority, name, certainty_type, confidence, implementation_status, "
            "condition_text, recommended_action_text, avoid_action_text, scope "
            "FROM decision_rules WHERE name LIKE ? OR condition_text LIKE ? OR "
            "recommended_action_text LIKE ? OR scope LIKE ? ORDER BY priority, id",
            tuple(f"%{archetype}%" for _ in range(4)),
        ).fetchall()
        if rows:
            print("No rule matched both filters; showing archetype matches.")
    print_rows(rows)


def command_matchup(db: sqlite3.Connection, our: str, opponent: str) -> None:
    rows = db.execute(
        "SELECT m.id, a.name AS our_archetype, b.name AS opponent_archetype, m.seat_or_turn_context, "
        "m.confidence, m.summary, p.id AS plan_id, p.phase, p.priority, p.condition, p.action_or_goal, "
        "p.evidence_strength "
        "FROM matchups m JOIN archetypes a ON a.id=m.our_archetype_id "
        "JOIN archetypes b ON b.id=m.opponent_archetype_id "
        "LEFT JOIN matchup_plans p ON p.matchup_id=m.id "
        "WHERE a.name LIKE ? AND b.name LIKE ? ORDER BY m.id, p.priority, p.id",
        (f"%{our}%", f"%{opponent}%"),
    ).fetchall()
    print_rows(rows)


def command_sources(db: sqlite3.Connection, tier: str | None, topic: str | None) -> None:
    clauses = []
    values: list[str] = []
    if tier:
        clauses.append("s.credibility_tier = ?")
        values.append(tier.upper())
    if topic:
        clauses.append("(s.title LIKE ? OR s.source_type LIKE ? OR s.format_scope LIKE ? OR s.notes LIKE ? OR t.name LIKE ?)")
        needle = f"%{topic}%"
        values.extend([needle, needle, needle, needle, needle])
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    rows = db.execute(
        "SELECT DISTINCT s.id, s.credibility_tier, s.title, s.publisher, s.author, s.source_type, "
        "s.format_scope, s.competition_specific, s.url, s.retrieved_at "
        "FROM sources s LEFT JOIN source_tags st ON st.source_id=s.id "
        "LEFT JOIN tags t ON t.id=st.tag_id "
        f"{where} ORDER BY CASE s.credibility_tier WHEN 'A' THEN 1 WHEN 'B' THEN 2 WHEN 'C' THEN 3 ELSE 4 END, s.id",
        values,
    ).fetchall()
    print_rows(rows)


def command_unresolved(db: sqlite3.Connection) -> None:
    print("CONTRADICTIONS")
    rows = db.execute(
        "SELECT id, topic, claim_a_id, claim_b_id, reason_for_difference, likely_resolution, "
        "format_or_matchup_dependency FROM contradictions WHERE unresolved=1 ORDER BY id"
    ).fetchall()
    print_rows(rows)
    print("\nRESEARCH QUESTIONS")
    rows = db.execute(
        "SELECT id, priority, status, question, best_current_answer, next_search_direction "
        "FROM research_questions WHERE status <> 'SOLVED' ORDER BY priority, id"
    ).fetchall()
    print_rows(rows)


def command_stats(db: sqlite3.Connection) -> None:
    tables = [
        "sources", "people", "claims", "strategies", "archetypes", "cards", "matchups", "matchup_plans",
        "decision_rules", "anti_patterns", "interactions", "probability_models", "search_features",
        "observed_replay_patterns", "contradictions", "research_questions",
    ]
    for table in tables:
        count = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table}: {count}")
    print("\nsource tiers:")
    for row in db.execute("SELECT credibility_tier, COUNT(*) AS count FROM sources GROUP BY credibility_tier ORDER BY credibility_tier"):
        print(f"{row['credibility_tier']}: {row['count']}")
    print("\nconfidence by claims:")
    for row in db.execute("SELECT confidence, COUNT(*) AS count FROM claims GROUP BY confidence ORDER BY confidence"):
        print(f"{row['confidence']}: {row['count']}")
    print("\nrule candidates:", db.execute("SELECT COUNT(*) FROM decision_rules WHERE empirically_test=1").fetchone()[0])
    print("\nsearch features:", db.execute("SELECT COUNT(*) FROM search_features").fetchone()[0])
    print("elite/research people:", db.execute("SELECT COUNT(*) FROM people").fetchone()[0])
    print("competition archetypes:", db.execute("SELECT COUNT(*) FROM archetypes WHERE competition_present=1").fetchone()[0])
    print("unresolved contradictions:", db.execute("SELECT COUNT(*) FROM contradictions WHERE unresolved=1").fetchone()[0])
    print("unresolved P0/P1 questions:", db.execute("SELECT COUNT(*) FROM research_questions WHERE priority IN ('P0','P1') AND status <> 'SOLVED'").fetchone()[0])


def command_claims(db: sqlite3.Connection, claim_type: str | None, confidence: str | None) -> None:
    clauses = []
    values: list[str] = []
    if claim_type:
        clauses.append("claim_type = ?")
        values.append(claim_type)
    if confidence:
        clauses.append("confidence = ?")
        values.append(confidence.upper())
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    rows = db.execute(
        "SELECT id, claim_type, scope, confidence, competition_applicability, format_scope, statement "
        f"FROM claims{where} ORDER BY id",
        values,
    ).fetchall()
    print_rows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="FTS search across claims, strategies, rules, anti-patterns, plans, and questions")
    search.add_argument("text")

    rules = sub.add_parser("rules", help="List decision rules")
    rules.add_argument("--context")
    rules.add_argument("--archetype")

    matchup = sub.add_parser("matchup", help="Show a matchup and its plan rows")
    matchup.add_argument("our")
    matchup.add_argument("opponent")

    sources = sub.add_parser("sources", help="List sources by tier/topic")
    sources.add_argument("--tier", choices=["A", "B", "C", "D"])
    sources.add_argument("--topic")

    sub.add_parser("unresolved", help="List unresolved contradictions and research questions")
    sub.add_parser("stats", help="Show database counts")

    claims = sub.add_parser("claims", help="List claims by type/confidence")
    claims.add_argument("--type", dest="claim_type")
    claims.add_argument("--confidence")

    args = parser.parse_args(argv)
    db = connect()
    try:
        if args.command == "search":
            command_search(db, args.text)
        elif args.command == "rules":
            command_rules(db, args.context, args.archetype)
        elif args.command == "matchup":
            command_matchup(db, args.our, args.opponent)
        elif args.command == "sources":
            command_sources(db, args.tier, args.topic)
        elif args.command == "unresolved":
            command_unresolved(db)
        elif args.command == "stats":
            command_stats(db)
        elif args.command == "claims":
            command_claims(db, args.claim_type, args.confidence)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
