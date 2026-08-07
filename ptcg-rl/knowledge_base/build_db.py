#!/usr/bin/env python3
"""Build the local evidence-first Pokemon TCG strategy knowledge database."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DB_PATH = HERE / "ptcg_gold.sqlite"
SCHEMA_PATH = HERE / "schema.sql"
STATUS_PATH = HERE / "RESEARCH_STATUS.json"
TODAY = "2026-08-08"


def local_hash(relative_path: str) -> str | None:
    path = REPO / relative_path
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_card_count() -> int | None:
    path = REPO / "private/assets/official/EN_Card_Data.csv"
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as handle:
        return max(sum(1 for _ in csv.reader(handle)) - 1, 0)


def local_card_id_count() -> int | None:
    path = REPO / "private/assets/official/EN_Card_Data.csv"
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as handle:
        return len({row["Card ID"] for row in csv.DictReader(handle)})


def source(
    sid: str,
    url: str,
    title: str,
    publisher: str,
    author: str | None,
    source_type: str,
    tier: str,
    format_scope: str,
    competition_specific: bool,
    notes: str = "",
    published_at: str | None = None,
    updated_at: str | None = None,
    elite_player_id: str | None = None,
    path: str | None = None,
) -> dict:
    return {
        "id": sid,
        "url": url,
        "canonical_url": url,
        "title": title,
        "publisher": publisher,
        "author": author,
        "source_type": source_type,
        "credibility_tier": tier,
        "published_at": published_at,
        "updated_at": updated_at,
        "retrieved_at": TODAY,
        "language": "en",
        "format_scope": format_scope,
        "competition_specific": int(competition_specific),
        "elite_player_id": elite_player_id,
        "notes": notes,
        "content_hash_or_identifier": local_hash(path) if path else None,
    }


PEOPLE = [
    ("PER-001", "Tord Reklev", "TordTCG", "Norway", "elite Pokemon TCG player", "Five-time International Champion; 2022 Latin America International Champion; repeated Worlds and Regional success.", "VERY_HIGH", "SRC-022"),
    ("PER-002", "Stephane Ivanoff", "lubyllule", None, "elite Pokemon TCG player and commentator", "Former National Champion, seven-time Worlds competitor, and 2018/2019 North America International Champion.", "VERY_HIGH", "SRC-022"),
    ("PER-003", "Ellis Longhurst", None, "Australia", "elite Pokemon TCG player and commentator", "High-level competitor since 2006 and official International/World Championship commentator.", "HIGH", "SRC-022"),
    ("PER-004", "Natalie Millar", "nataliem9999", "Australia", "elite Pokemon TCG player and commentator", "Regional Champion and recurring major-event competitor.", "HIGH", "SRC-022"),
    ("PER-005", "Jason Klaczynski", None, "United States", "World Champion and strategy author", "Credited in the strategy source as the 2006 World Champion whose deck construction illustrated thinning value.", "MEDIUM", "SRC-028"),
    ("PER-006", "Ciaran Farah", None, None, "competitive Pokemon TCG writer", "Worlds-testing writer who published board-state planning and opponent-response analysis.", "MEDIUM", "SRC-025"),
    ("PER-007", "Sam VerNooy", None, "United States", "competitive Pokemon TCG writer", "Competitive player and author of a detailed prize-trade planning article; credentials are not independently tournament-verified here.", "MEDIUM", "SRC-024"),
    ("PER-008", "Dries @ Tufa Labs", None, None, "Kaggle competitor", "Current-rank-1 snapshot and exact Grimmsnarl teacher metadata in local project evidence; not an official Pokemon TCG credential.", "MEDIUM", "SRC-016"),
    ("PER-009", "Luca", None, None, "Kaggle competitor", "Gold-region public score/rank and exact Mega Lucario teacher metadata in local project evidence; not an official Pokemon TCG credential.", "MEDIUM", "SRC-017"),
    ("PER-010", "Majkel1337", None, None, "Kaggle competitor", "Current-rank-1 snapshot and exact Mega Lucario teacher metadata in local project evidence; not an official Pokemon TCG credential.", "MEDIUM", "SRC-018"),
    ("PER-011", "Ryan Rumble", None, None, "Kaggle community participant", "Public competition discussion author reporting a self-play/meta approach; no Pokemon TCG credential claimed.", "LOW", "SRC-037"),
]


SOURCES = [
    source("SRC-001", "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/description", "PTCG AI Battle Challenge Simulation description", "Kaggle / The Pokemon Company", None, "official_competition", "A", "CABT competition 2026", True, "Current competition page; retrieved 2026-08-08."),
    source("SRC-002", "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/rules", "PTCG AI Battle Challenge rules", "Kaggle / The Pokemon Company", None, "official_competition_rules", "A", "CABT competition 2026", True),
    source("SRC-003", "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/how-to-play", "PTCG AI Battle how to play", "Kaggle / The Pokemon Company", None, "official_competition", "A", "CABT competition 2026", True),
    source("SRC-004", "repo://ptcg-rl/research-docs/competition_overview.md", "Repository competition overview", "Project repository", None, "repository_contract", "A", "CABT competition 2026", True, "Local synthesis cross-checked against official pages.", path="research-docs/competition_overview.md"),
    source("SRC-005", "repo://ptcg-rl/research-docs/game_engine_and_agent_api.md", "Repository CABT engine and agent API notes", "Project repository", None, "repository_contract", "A", "CABT competition 2026", True, path="research-docs/game_engine_and_agent_api.md"),
    source("SRC-006", "https://matsuoinstitute.github.io/cabt/api.html", "cabt Engine API module documentation", "Matsuo Institute", None, "technical_documentation", "A", "CABT competition 2026", True, "Official API reference for enums, legal selections, observations, and search."),
    source("SRC-007", "repo://ptcg-rl/research-docs/game_rules_and_simulator_quirks.md", "Repository game rules and simulator quirks", "Project repository", None, "repository_contract", "A", "CABT competition 2026 versus tabletop", True, path="research-docs/game_rules_and_simulator_quirks.md"),
    source("SRC-008", "repo://ptcg-rl/configs/official.json", "Verified competition runtime contract", "Project repository", None, "repository_contract", "A", "CABT competition 2026", True, path="configs/official.json"),
    source("SRC-009", "repo://ptcg-rl/private/assets/official/EN_Card_Data.csv", "Official English competition card table", "Competition package", None, "official_card_data", "A", "CABT card pool; competition-use-only local asset", True, "Stored only as hash/count metadata; card text is not copied into the database.", path="private/assets/official/EN_Card_Data.csv"),
    source("SRC-010", "repo://ptcg-rl/private/assets/official/sample_submission/sample_submission/deck.csv", "Official sample submission deck", "Competition package", None, "official_deck_asset", "A", "CABT sample deck", True, "Stored as hash and derived archetype metadata only.", path="private/assets/official/sample_submission/sample_submission/deck.csv"),
    source("SRC-011", "repo://ptcg-rl/private/baselines/", "Local native rule-anchor receipts", "Project repository", None, "replay_or_baseline_evidence", "A", "CABT competition 2026", True, "Four exact local rule-baseline receipts; private deck bodies are not copied."),
    source("SRC-012", "repo://ptcg-rl/configs/g3b_competence_plan_v1.json", "Frozen G3b competence plan", "Project repository", None, "evaluation_contract", "A", "CABT competition 2026", True, "Plan/evaluation evidence, not policy-strength evidence.", path="configs/g3b_competence_plan_v1.json"),
    source("SRC-013", "repo://ptcg-rl/PROJECT_STATUS.md", "Current project status", "Project repository", None, "project_status", "A", "CABT competition 2026", True, "Current checkpoint and authorization boundaries.", path="PROJECT_STATUS.md"),
    source("SRC-014", "repo://ptcg-rl/research-docs/replay_data_and_meta.md", "Repository replay and public-meta synthesis", "Project repository", None, "research_synthesis", "B", "CABT competition 2026", True, "Clearly labels selection bias and unresolved parser issues.", path="research-docs/replay_data_and_meta.md"),
    source("SRC-015", "repo://ptcg-rl/reports/artifacts/e01-teacher-deck-metadata-review-v1.json", "Teacher deck metadata review", "Project repository", None, "replay_metadata", "A", "CABT competition 2026", True, "Metadata-only review; raw replay bodies are not reproduced.", path="reports/artifacts/e01-teacher-deck-metadata-review-v1.json"),
    source("SRC-016", "repo://ptcg-rl/reports/artifacts/e01-dries-confirmation-teacher-probe-review-v1.json", "Dries Grimmsnarl teacher probe review", "Project repository", "Dries @ Tufa Labs", "replay_metadata", "A", "CABT competition 2026", True, "Exact deck/action-contract metadata; not causal strategy proof.", elite_player_id="PER-008", path="reports/artifacts/e01-dries-confirmation-teacher-probe-review-v1.json"),
    source("SRC-017", "repo://ptcg-rl/reports/artifacts/e01-luca-gold-teacher-probe-review-v1.json", "Luca Mega Lucario teacher probe review", "Project repository", "Luca", "replay_metadata", "A", "CABT competition 2026", True, "Exact deck/action-contract metadata; not causal strategy proof.", elite_player_id="PER-009", path="reports/artifacts/e01-luca-gold-teacher-probe-review-v1.json"),
    source("SRC-018", "repo://ptcg-rl/reports/artifacts/e01-majkel-live-gold-teacher-probe-review-v1.json", "Majkel live gold teacher probe review", "Project repository", "Majkel1337", "replay_metadata", "A", "CABT competition 2026", True, "Two exact-deck wins across opposite seats; mixed module versions; not causal strategy proof.", elite_player_id="PER-010", path="reports/artifacts/e01-majkel-live-gold-teacher-probe-review-v1.json"),
    source("SRC-019", "https://www.pokemon.com/static-assets/content-assets/cms2/pdf/trading-card-game/rulebook/par_rulebook_en.pdf", "Pokemon Trading Card Game rulebook", "The Pokemon Company", None, "official_rules", "A", "Pokemon TCG tabletop rules", False, published_at="2025-10-01"),
    source("SRC-020", "https://play.pokemon.com/en-us/resources/rules/", "Competitive rules and formats", "Play! Pokemon", None, "official_rules", "A", "Pokemon TCG Standard and tournament rules", False),
    source("SRC-021", "https://www.pokemon-card.com/info/2021/20210714_003027.html", "My Favorite Pokemon TCG: Tord Reklev", "Pokemon Card Game official site", "Tord Reklev", "elite_interview", "A", "2019 historical Standard-era deck", False, published_at="2021-07-14", elite_player_id="PER-001"),
    source("SRC-022", "https://worlds.2024.pokemon.com/en-us/news/2024-worlds-tcg-power-rankings/", "2024 Worlds Pokemon TCG power rankings", "Pokemon.com", "Stephane Ivanoff, Ellis Longhurst, Tord Reklev, et al.", "elite_analysis", "A", "2024 Standard; not CABT-equivalent", False, published_at="2024-08-01", elite_player_id="PER-002"),
    source("SRC-023", "https://www.videogameschronicle.com/features/the-games-in-a-very-good-spot-pokemon-tcg-legend-tord-reklev-talks-euic-2026-and-the-upcoming-rotation/", "Tord Reklev talks EUIC 2026 and rotation", "Video Games Chronicle", "Jordan Middler", "elite_interview", "B", "2026 post-rotation Standard; not CABT proof", False, published_at="2026-02-18", elite_player_id="PER-001"),
    source("SRC-024", "https://www.pokebeach.com/2018/10/finding-your-path", "Finding Your Path: How To Win at the Pokemon TCG", "PokeBeach", "Sam VerNooy", "competitive_strategy", "B", "2018 Standard; transferable principles only", False, published_at="2018-10-31", elite_player_id="PER-007"),
    source("SRC-025", "https://www.pokebeach.com/2024/07/the-player-with-a-plan-how-to-approach-your-turns-with-board-state-examples", "The Player with a Plan", "PokeBeach", "Ciaran Farah", "competitive_strategy", "B", "2024 Standard; transferable principles only", False, published_at="2024-07-19", elite_player_id="PER-006"),
    source("SRC-026", "https://www.pokebeach.com/2026/04/a-phantom-deep-dive-handling-the-bdif", "A Phantom Deep Dive: Handling the BDIF", "PokeBeach", None, "competitive_strategy", "B", "2026 Standard post-rotation; not CABT proof", False, published_at="2026-04-01"),
    source("SRC-027", "https://www.pokebeach.com/2026/05/tank-decks-are-back-why-lopunny-is-hopping-to-the-top", "Tank Decks Are Back: Why Lopunny is Hopping to the Top", "PokeBeach", "Andrew Martin", "matchup_analysis", "B", "2026 Standard; not CABT proof", False, published_at="2026-05-18"),
    source("SRC-028", "https://sixprizes.com/2014/10/02/deft-decisions/", "Deft Decisions: In-Game Skill, Part 1", "SixPrizes", None, "competitive_strategy", "B", "2014 historical Standard; transferable information principles", False, published_at="2014-10-02", elite_player_id="PER-005"),
    source("SRC-029", "https://www.tcgplayer.com/content/article/How-to-Sequence-Correctly-In-The-Pokemon-TCG/d5eb5c78-de9d-47b6-b5da-30b65f3b837b/", "How to Sequence Correctly in the Pokemon TCG", "TCGplayer", "Natalie Millar", "competitive_strategy", "B", "2025 Standard; transferable sequencing principles", False, published_at="2025-04-01", elite_player_id="PER-004"),
    source("SRC-030", "https://www.tcgplayer.com/content/article/The-3-Principles-of-Prize-Checking/a015ad58-7ec5-41ea-ba50-56db0ee9d67f", "The 3 Principles of Prize Checking", "TCGplayer", "Natalie Millar", "competitive_strategy", "B", "2025 Standard; transferable information principles", False, published_at="2025-01-01", elite_player_id="PER-004"),
    source("SRC-031", "https://www.justinbasil.com/guide/deck-strategy", "Deck Strategy", "JustInBasil", "Justin Basil", "competitive_strategy", "B", "Modern Pokemon TCG strategy taxonomy; format-specific examples vary", False),
    source("SRC-032", "https://www.limitlesstcg.com/tools", "Limitless player tools", "Limitless TCG", None, "competitive_tool", "B", "Current and historical Standard/Expanded tools", False),
    source("SRC-033", "https://limitlesstcg.com/?time=all", "Limitless tournament and deck database", "Limitless TCG", None, "competitive_meta", "B", "Current Standard/TEF-CRI snapshot; not CABT distribution", False),
    source("SRC-034", "https://deckinsider.com/pokemon-tcg-tournament-prep-deckbuilding-and-matchup-plan-for-2026/", "Pokemon TCG Tournament Prep: Deckbuilding and Matchup Plan for 2026", "Deck Insider", "Ethan Cole", "competitive_strategy", "C", "2026 Standard; not CABT proof", False, published_at="2026-03-17"),
    source("SRC-035", "https://itl.nist.gov/div898/software/dataplot/refman2/ch8/hypcdf.pdf", "HYPCDF hypergeometric distribution reference", "NIST", None, "probability_reference", "A", "General probability", False),
    source("SRC-036", "https://www.smogon.com/articles/pokemon-tcg", "1,2,3, DRAW! How to Play the Pokemon TCG", "Smogon University", "rileydelete", "rules_and_strategy", "C", "Older tabletop rules guide; not CABT authority", False),
    source("SRC-037", "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/727816", "How'd you pick your deck?", "Kaggle discussion", "Ryan Rumble", "competition_meta_discussion", "C", "CABT public meta, early July 2026", True, published_at="2026-07-01", elite_player_id="PER-011"),
    source("SRC-038", "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709263", "Daily public meta notes", "Kaggle discussion", None, "competition_meta_discussion", "C", "CABT visible top-ten snapshots, June 2026", True),
    source("SRC-039", "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709554", "Public Top-100 Meta Snapshot", "Kaggle discussion", None, "competition_meta_discussion", "C", "CABT visible top-100 snapshot, June 2026", True),
    source("SRC-040", "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/716557", "Clarification on Episode JSON Action/Observation Alignment", "Kaggle discussion", None, "replay_methodology", "B", "CABT replay schema; question/answer status unresolved", True),
    source("SRC-041", "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/717279", "Replay action alignment correction", "Kaggle discussion", None, "replay_methodology", "C", "CABT replay parser report; participant validation", True),
    source("SRC-042", "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/708586", "Differences Between Official Rules and Simulator Behavior", "Kaggle discussion", "PTCGABC Team", "simulator_rules", "A", "CABT engine versus tabletop", True),
    source("SRC-043", "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/714920", "Deck Search blind behavior", "Kaggle discussion", None, "simulator_rules", "C", "CABT search option semantics", True),
    source("SRC-044", "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/715644", "search_step error reports", "Kaggle discussion", None, "simulator_rules", "C", "CABT search debugging report", True),
    source("SRC-045", "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/724362", "Analysis of 30,000 top-team games", "Kaggle discussion", None, "competition_meta_discussion", "C", "CABT timing observation; inferred algorithms explicitly unproven", True),
    source("SRC-046", "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709498", "Public matchup matrix", "Kaggle discussion", None, "competition_meta_discussion", "C", "CABT 11-agent, 550-game screening sample", True),
    source("SRC-047", "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/716207", "Archaludon meta counter discoveries", "Kaggle discussion", None, "competition_meta_discussion", "C", "CABT deck/counter hypothesis", True),
    source("SRC-048", "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712481", "Live meta dashboard and API", "Kaggle discussion", None, "competition_meta_discussion", "C", "CABT observed top-episode dashboard; selection-biased", True),
    source("SRC-049", "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/717141", "Game engine source code", "Kaggle discussion", "PTCGABC Team", "competition_policy", "A", "CABT engine source and competition-use scope", True),
    source("SRC-050", "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/729644", "Late competition discussion 729644", "Kaggle discussion", None, "competition_meta_discussion", "C", "Anonymous access did not expose full text during this refresh; retained as a refresh target, not used for strong claims.", True),
    source("SRC-051", "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/731739", "Late competition discussion 731739", "Kaggle discussion", None, "competition_meta_discussion", "C", "Anonymous access did not expose full text during this refresh; retained as a refresh target, not used for strong claims.", True),
    source("SRC-052", "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/731352", "Late competition discussion 731352", "Kaggle discussion", None, "competition_meta_discussion", "C", "Anonymous access did not expose full text during this refresh; retained as a refresh target, not used for strong claims.", True),
    source("SRC-053", "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/726708", "Per-game time limit", "Kaggle discussion", "PTCGABC Team", "competition_runtime", "A", "CABT runtime discussion; local official runtime config overrides if newer.", True),
    source("SRC-054", "https://www.pokemon.com/uk/strategy/pokemon-tcg-deck-list-and-strategy-building-a-mega-lucario-ex-deck", "Building a Mega Lucario ex deck", "Pokemon.com", None, "official_deck_strategy", "A", "2026 Standard; exact card guidance is not automatically CABT-equivalent", False, published_at="2026-01-01"),
    source("SRC-055", "https://arxiv.org/abs/2607.08692", "From Rules to Nash Equilibria: A Lean 4 Case Study", "arXiv", None, "competitive_meta_research", "B", "2026 Standard tournament data; not CABT distribution", False, published_at="2026-07-01"),
    source("SRC-056", "https://www.reddit.com/r/pkmntcg/comments/1sdkjyb/advice_for_beating_pult_with_marnies_grimmsnarl_post_rotation/", "Advice for beating Dragapult with Marnie's Grimmsnarl", "Reddit r/pkmntcg", None, "community_matchup_discussion", "C", "2026 Standard anecdote; hypothesis only for CABT", False, published_at="2026-04-06"),
]


def link(source_id: str, support_type: str = "supports", excerpt: str = "", location: str = "") -> dict:
    return {"source_id": source_id, "support_type": support_type, "short_excerpt": excerpt, "source_location": location}


def claim(
    cid: str,
    statement: str,
    claim_type: str,
    scope: str,
    confidence: str,
    evidence_strength: str,
    competition_applicability: str,
    format_scope: str,
    sources: list[dict],
    tags: list[str],
    justification: str = "",
    valid_from: str | None = None,
    valid_to: str | None = None,
) -> dict:
    return {
        "id": cid,
        "statement": statement,
        "claim_type": claim_type,
        "scope": scope,
        "confidence": confidence,
        "evidence_strength": evidence_strength,
        "competition_applicability": competition_applicability,
        "format_scope": format_scope,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "created_at": TODAY,
        "justification": justification,
        "sources": sources,
        "tags": tags,
    }


CLAIMS = [
    claim("CLM-001", "The target is a Kaggle simulation using CABT, not an unconstrained tabletop implementation; official competition behavior and the current engine are operational truth.", "rule", "competition_environment", "VERY_HIGH", "official_competition_and_local_contract", "DIRECT", "CABT competition 2026 / current engine", [link("SRC-001", "primary_rule_evidence", "The competition uses a simulator and explicitly notes simulator-rule differences.", "description and how-to-play sections"), link("SRC-004", "supports", "Local overview separates CABT behavior from tabletop rules.", "Game and simulator")], ["competition", "format"], "Official competition page plus local contract.", valid_from="2026-06-16"),
    claim("CLM-002", "The agent receives public logs/state plus a current legal option list and returns option indices; the legal option list is variable and already legality-filtered.", "rule", "competition_interface", "VERY_HIGH", "official_api_and_competition_docs", "DIRECT", "CABT competition 2026", [link("SRC-001", "primary_rule_evidence", "Each turn supplies observation and legal options; the agent returns indices.", "how-to-play"), link("SRC-006", "primary_rule_evidence", "SelectType, SelectContext, and OptionType define the legal selection contract.", "Enums and data classes")], ["competition", "actions", "api"], "Two primary sources agree."),
    claim("CLM-003", "A valid competition deck has exactly 60 cards; the local engine also checks valid IDs, at least one Basic Pokemon, at most one ACE SPEC, and same-name limits with Basic Energy exempt.", "rule", "deck_legality", "VERY_HIGH", "local_engine_contract", "DIRECT", "CABT competition 2026", [link("SRC-007", "primary_rule_evidence", "The repository records the engine validation rules.", "Deck legality"), link("SRC-005", "supports", "battle_start requires exactly 60 cards and engine validation.", "Battle wrapper")], ["competition", "deck", "legality"], "Local engine notes are the exact competition-specific source."),
    claim("CLM-004", "Standard Pokemon TCG win conditions are taking all six Prize cards, leaving the opponent with no Pokemon in play, or making the opponent fail to draw at the beginning of its turn.", "rule", "win_conditions", "VERY_HIGH", "official_rulebook", "TRANSFERABLE", "Pokemon TCG tabletop rules; verify CABT result handling", [link("SRC-019", "primary_rule_evidence", "Rulebook lists all three win paths.", "How to Win"), link("SRC-031", "supports", "Deck strategy guide lists the same three paths.", "lines 14-20")], ["rules", "prizes", "deckout"], "Official rulebook governs tabletop; CABT result handling must still be checked."),
    claim("CLM-005", "Opponent hand, deck order, and face-down Prizes are hidden unless revealed by an effect; an actor must not read or assume them as facts.", "rule", "hidden_information", "VERY_HIGH", "official_rulebook_and_local_api", "DIRECT", "CABT public-information actor", [link("SRC-019", "primary_rule_evidence", "Players cannot look at the opponent hand or deck order without an effect.", "Basic concepts"), link("SRC-005", "supports", "The public state does not expose hidden opponent zones.", "State and logs")], ["hidden-information", "belief", "competition"], "Official rules and local observation contract agree."),
    claim("CLM-006", "Only one Energy normally attaches per turn, only one Supporter is normally played per turn, and retreat consumes attached Energy unless a card effect changes that.", "rule", "turn_actions", "HIGH", "official_rules_and_secondary_rules", "TRANSFERABLE", "Pokemon TCG tabletop rules; CABT card effects may differ", [link("SRC-019", "primary_rule_evidence", "Rulebook turn-action restrictions.", "What You Can Do During Your Turn"), link("SRC-036", "supports", "Guide summarizes Energy, Supporter, and retreat restrictions.", "lines 38-42, 164-185")], ["rules", "resources", "sequencing"], "Use CABT legal options for any simulator-specific exception."),
    claim("CLM-007", "The conservative submission envelope is CPU-only with no network/GPU at inference; local project evidence records roughly two vCPUs and about 12 GiB exposed resources, while engineering uses a stricter internal reserve.", "rule", "runtime", "HIGH", "official_competition_page_and_local_config", "DIRECT", "CABT competition 2026", [link("SRC-001", "primary_rule_evidence", "Submission resources include vCPUs, RAM, and no network expectation.", "Submissions and resources"), link("SRC-008", "supports", "Versioned runtime fields and conservative project limits.", "runtime")], ["competition", "runtime", "search"], "Use current official/package measurements at final packaging."),
    claim("CLM-008", "A legal tabletop action can be absent from CABT when its effect cannot resolve in the simulator; the agent should score the supplied legal options rather than reconstruct tabletop legality.", "rule", "simulator_difference", "VERY_HIGH", "host_clarification_and_local_synthesis", "DIRECT", "CABT competition 2026", [link("SRC-042", "primary_rule_evidence", "Host clarification lists absent unresolved attacks and sequential KO behavior.", "Differences Between Official Rules and Simulator Behavior"), link("SRC-007", "supports", "Repository preserves the examples and test implications.", "Simulator behavior")], ["competition", "rules", "actions"], "Host clarification is higher authority than generic strategy sources."),
    claim("CLM-009", "CABT search requires a coherent hypothesis for hidden zones with correct lengths and without-replacement allocation; manual coin control is not fair competition behavior.", "rule", "search_contract", "VERY_HIGH", "local_api_and_engine_notes", "DIRECT", "CABT competition 2026", [link("SRC-005", "primary_rule_evidence", "search_begin requires observation-consistent hidden predictions.", "Search API"), link("SRC-007", "supports", "Manual coin and hidden allocation constraints.", "Search and hidden information")], ["search", "hidden-information", "competition"], "Local docs bind implementation; no omniscient determinization."),
    claim("CLM-010", "The native engine uses internal randomness without a normal Python/NumPy/PyTorch seed hook, so battles should be evaluated by distributions and invariants rather than claimed exact trajectories.", "rule", "randomness", "HIGH", "local_engine_notes", "DIRECT", "CABT competition 2026", [link("SRC-007", "primary_rule_evidence", "Random device and missing wrapper seed hook are recorded.", "Randomness and reproducibility"), link("SRC-004", "supports", "Competition overview warns that engine randomness is internal.", "Game and simulator")], ["competition", "probability", "evaluation"], "Treat any future engine-level seed path as a new verified fact."),
    claim("CLM-011", "The local official English card table contains 2,022 CSV data rows and 1,267 unique card IDs and is bound by SHA-256 a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373; this file, not Standard legality, defines the available card universe for local work.", "rule", "card_pool", "VERY_HIGH", "local_asset_hash_and_count", "DIRECT", "CABT card pool asset version", [link("SRC-009", "primary_rule_evidence", "Local CSV is parsed with its quoted multiline fields, hashed, and row-counted by the builder.", "asset metadata"), link("SRC-004", "supports", "Competition data page and local card data are separated from tournament legality.", "Card data")], ["competition", "cards", "format"], "Exact asset evidence is local and private; no card text is reproduced."),
    claim("CLM-012", "The repository's engineering/sample deck is a 60-card Mega Abomasnow ex deck with Kyogre and Snover and hash 42068a1803902756badcfd418f6f348b7901365a281d78af0692cbf2589f0799; it is a candidate, not a frozen submission.", "observed_behavior", "candidate_deck", "VERY_HIGH", "local_asset_hash_and_card_mapping", "DIRECT", "CABT competition 2026", [link("SRC-010", "primary_rule_evidence", "Sample deck hash and card IDs are local asset evidence.", "deck.csv"), link("SRC-012", "supports", "G3b plan labels the engineering deck and says deck freeze is unauthorized.", "assets and authorization")], ["competition", "deck", "mega-abomasnow"], "Exact deck identity is evidenced; strategic strength is not."),
    claim("CLM-013", "The local evaluation population has four exact native rule anchors: Dragapult ex, Iono, Mega Abomasnow ex, and Mega Lucario ex.", "observed_behavior", "competition_baselines", "VERY_HIGH", "local_receipts_and_evaluation_contract", "DIRECT", "CABT competition 2026", [link("SRC-011", "primary_rule_evidence", "Four baseline receipts are retained.", "baseline IDs"), link("SRC-012", "supports", "Evaluation population names the four rule anchors.", "evaluation")], ["competition", "archetypes", "evaluation"], "Anchor identity is not evidence of current hidden meta share."),
    claim("CLM-014", "Public daily episode collections and top-team replay samples are rating/recency/availability biased and must not be treated as an unbiased opponent distribution.", "observed_behavior", "replay_sampling", "VERY_HIGH", "local_replay_policy_and_kaggle_context", "DIRECT", "CABT public replay data", [link("SRC-014", "primary_rule_evidence", "Repository explicitly labels top-episode selection bias.", "Official episode access"), link("SRC-048", "qualifies", "Observed top-episode dashboard is not hidden matchmaker truth.", "discussion summary")], ["competition", "replays", "meta"], "This is a data-use constraint, not a matchup estimate."),
    claim("CLM-015", "The visible competition meta changed rapidly across June: Crustle, Iono, Psychic, Lucario, Hop, Grass/Fire/Spread, Starmie, and Archaludon each appeared in top-ten snapshots at different dates.", "observed_behavior", "competition_meta", "HIGH", "repeated_public_snapshots", "DIRECT", "CABT visible public meta June 2026", [link("SRC-014", "supports", "Date-stamped public snapshot table.", "Public meta observations"), link("SRC-038", "example", "Daily top-ten thread is the original public source.", "discussion")], ["competition", "meta", "archetypes"], "Snapshots are evidence of movement, not prevalence or causal matchup strength.", valid_from="2026-06-17", valid_to="2026-06-28"),
    claim("CLM-016", "The public competition page says rule-based programming alone may not reach a high rank and emphasizes forward planning, adaptation, hidden information, and random outcomes.", "expert_opinion", "agent_design", "HIGH", "official_competition_guidance", "DIRECT", "CABT competition 2026", [link("SRC-001", "primary_rule_evidence", "Official description contrasts fixed rules with adaptation and forward planning.", "description")], ["competition", "search", "planning"], "This is guidance, not a measured guarantee."),
    claim("CLM-017", "A prize trade is the phase where both players can chain relevant attacks; entering that exchange is correct when the projected route wins, and dangerous when the opponent's route wins.", "strategic_principle", "prize_trade", "HIGH", "multiple_strong_sources", "TRANSFERABLE", "Pokemon TCG strategy across multiple Standard formats", [link("SRC-024", "supports", "Defines prize trade and warns against entering a losing one.", "lines 70-82"), link("SRC-031", "supports", "Aggression requires streaming attackers to win the Prize Trade.", "lines 29-34")], ["prize-map", "tempo", "matchups"], "The idea transfers, but exact prize values/card effects remain format-dependent."),
    claim("CLM-018", "Before starting a prize trade, establish enough future attackers and their Energy/support resources, or delay the first KO while stabilizing.", "strategic_principle", "attacker_sequencing", "HIGH", "multiple_strong_sources", "TRANSFERABLE", "Pokemon TCG strategy across formats", [link("SRC-024", "supports", "Leave attacker benched, spread Energy, and stabilize before trading.", "lines 76-82"), link("SRC-025", "supports", "Map later attackers and resources before taking a big KO.", "lines 62-69")], ["prize-map", "resources", "tempo"], "Exceptions include lethal wins, forced KOs, or a clearly favorable race."),
    claim("CLM-019", "Prize mapping should name the target sequence, attacker sequence, required gust/boost effects, and resources remaining after each KO; a large immediate KO is not automatically the best route.", "strategic_principle", "prize_mapping", "HIGH", "multiple_strong_sources", "TRANSFERABLE", "Pokemon TCG strategy across formats", [link("SRC-025", "supports", "Map six Prizes, attackers, targets, and required resources.", "lines 62-64"), link("SRC-034", "supports", "Track routes such as 2-2-2 and count required pieces and denial points.", "lines 104-121")], ["prize-map", "search", "matchups"], "Use exact engine damage/prize values when implementing."),
    claim("CLM-020", "When ahead, reduce the opponent's comeback outs by repairing exposed support Pokemon, hand quality, bench liabilities, and resource holes instead of maximizing damage at any cost.", "strategic_principle", "playing_ahead", "HIGH", "multiple_strong_sources", "TRANSFERABLE", "Pokemon TCG strategy across formats", [link("SRC-024", "supports", "Ahead players should patch holes and prepare for disruption.", "lines 85-91"), link("SRC-025", "supports", "Stress-test the opponent's response and preserve response resources.", "lines 65-70")], ["risk", "bench", "disruption"], "An immediate forced win overrides risk reduction."),
    claim("CLM-021", "If the normal prize race is unfavorable, a player can pivot to denial, disruption, deck-out, or a board-elimination line; the pivot must be tied to a concrete opponent resource or threat.", "strategic_principle", "losing_position", "HIGH", "multiple_strong_sources", "TRANSFERABLE", "Pokemon TCG strategy across formats", [link("SRC-024", "supports", "Avoid a losing prize trade through disruption or alternate win conditions.", "lines 83-91 and 184-202"), link("SRC-031", "supports", "Control, mill, and stall use different resource/Prize denial plans.", "lines 25-51")], ["risk", "deckout", "control"], "Do not convert every behind state into random variance."),
    claim("CLM-022", "Prize cards are actionable information: once a search/reveal establishes that key copies are prized, the feasible route and resource ledger must change.", "strategic_principle", "prize_checking", "HIGH", "multiple_strong_sources", "TRANSFERABLE", "Pokemon TCG strategy across formats", [link("SRC-028", "supports", "Prize deduction changes the picture of the deck and game.", "lines 150-154"), link("SRC-030", "supports", "Use prize information to choose routes and accept calculated risk.", "search extract and article summary")], ["belief", "prize-map", "resources"], "In CABT, only revealed/public information may update the actor belief."),
    claim("CLM-023", "A lower-variance prize route can be superior when it uses fewer specific pieces, even if a higher-ceiling route takes a larger immediate prize.", "strategic_principle", "risk_management", "HIGH", "strong_competitive_source", "TRANSFERABLE", "Pokemon TCG strategy across formats", [link("SRC-034", "supports", "Count exact pieces and prefer a stable lower-variance route when appropriate.", "lines 104-121"), link("SRC-025", "supports", "A big two-Prize KO without follow-up can collapse the position.", "lines 62-64")], ["risk", "prize-map", "probability"], "The correct route depends on current board and opponent outs."),
    claim("CLM-024", "Bench space is a resource: leave room for required attackers/support, and do not bench a two-Prize or spread-vulnerable liability without a plan.", "strategic_principle", "bench_management", "HIGH", "multiple_strong_sources", "TRANSFERABLE", "Pokemon TCG strategy across formats", [link("SRC-025", "supports", "Bench space can be needed for future attackers/support.", "lines 62-64"), link("SRC-036", "supports", "Benched Pokemon are targets and should not be placed automatically.", "lines 31-35")], ["bench", "prize-map", "threats"], "Some engines require filling the bench; model role-specific value instead of a blanket cap."),
    claim("CLM-025", "A strong turn is stress-tested by asking what the opponent can do in response, what resources they have, and what board remains after that response.", "strategic_principle", "opponent_modeling", "HIGH", "strong_competitive_source", "TRANSFERABLE", "Pokemon TCG strategy across formats", [link("SRC-025", "supports", "The article explicitly recommends opponent-response stress testing and resource capability checks.", "lines 62-70")], ["belief", "search", "risk"], "Use probability rather than certainty for unknown cards."),
    claim("CLM-026", "Opponent capability should be conditioned on revealed list/board, known discard, hand size, draw engine, and remaining outs; a convoluted line with no support should receive lower probability than a one-card line.", "strategic_principle", "opponent_outs", "HIGH", "strong_competitive_source", "TRANSFERABLE", "Pokemon TCG strategy across formats", [link("SRC-025", "supports", "Ask what resources are available and how likely a line is.", "lines 65-69"), link("SRC-028", "supports", "Anticipate likely deck cards from observed archetype behavior.", "lines 167-174")], ["belief", "probability", "threats"], "This is a belief update, not hidden-hand reconstruction."),
    claim("CLM-027", "Spreading Energy and preserving a backup attacker can prevent one opposing attack or effect from deleting the entire future attack chain.", "strategic_principle", "energy_management", "HIGH", "strong_competitive_source", "TRANSFERABLE", "Pokemon TCG strategy across formats", [link("SRC-024", "supports", "Spread Energy and keep a second attacker before starting a trade.", "lines 76-82")], ["resources", "attackers", "risk"], "Do not spread if the deck's attack requires concentrated Energy or the opponent cannot punish it."),
    claim("CLM-028", "Deck thinning can improve later draw quality and resilience to hand disruption when the removed cards are genuinely dead or replaceable.", "strategic_principle", "deck_thinning", "HIGH", "strong_competitive_source", "TRANSFERABLE", "Pokemon TCG strategy across formats", [link("SRC-028", "supports", "Thinning removes dead cards and improves later disruption outcomes.", "lines 155-165"), link("SRC-032", "supports", "Limitless provides opening-hand/draw tools built around without-replacement odds.", "Opening Hand Calculator")], ["sequencing", "probability", "resources"], "Thinning is not free; preserve tutor value and future targets."),
    claim("CLM-029", "Sequencing has no universal fixed order: the correct order depends on the turn objective, target cards, information gained, and whether a search effect is itself a valuable out.", "sequencing_rule", "turn_sequencing", "HIGH", "strong_competitive_source", "TRANSFERABLE", "Pokemon TCG strategy across formats", [link("SRC-029", "supports", "The author explicitly rejects hard-and-fast sequencing rules and uses dynamic order.", "search extract"), link("SRC-025", "supports", "Set a goal, then sequence around future responses.", "lines 60-70")], ["sequencing", "information", "probability"], "Implement constraints and lookahead rather than a fixed card-order script."),
    claim("CLM-030", "A first deck search should inspect important copies and update a prize/resource ledger; midgame checks can change whether a route is feasible.", "sequencing_rule", "prize_checking", "HIGH", "multiple_strong_sources", "TRANSFERABLE", "Pokemon TCG strategy across formats", [link("SRC-028", "supports", "Practice deducing Prize cards and use the information strategically.", "lines 150-154"), link("SRC-030", "supports", "Prize checks can be revisited and should drive route decisions.", "search extract")], ["belief", "sequencing", "prizes"], "Check only accessible/revealed information in CABT."),
    claim("CLM-031", "The value of an action depends on public card counts and discard/recovery state, not simply hand size; used-up or inaccessible copies must be removed from future-out calculations.", "strategic_principle", "resource_accounting", "HIGH", "multiple_strong_sources", "TRANSFERABLE", "Pokemon TCG strategy across formats", [link("SRC-025", "supports", "Opponent capability depends on resources and board state.", "lines 65-70"), link("SRC-036", "supports", "Discard is public and commonly a recoverable resource.", "lines 27-28")], ["resources", "belief", "probability"], "Track card identity, counts, zones, and recovery path separately."),
    claim("CLM-032", "A deterministic belief state should separate known facts, logical deductions, probabilistic beliefs, and speculative hypotheses; a missing action is evidence with likelihood, not proof of a missing card.", "search_design", "belief_tracking", "MEDIUM", "derived_from_rules_and_expert_reasoning", "DIRECT", "CABT public-information actor", [link("SRC-005", "supports", "Only public state and revealed effects are actor inputs.", "State and logs"), link("SRC-025", "supports", "Reason in terms of capability and likelihood, not certainty.", "lines 65-70"), link("SRC-028", "supports", "Infer likely deck contents but remain alert to the individual list.", "lines 167-174")], ["belief", "hidden-information", "search"], "This is an implementation translation; validate with replay holdouts."),
    claim("CLM-033", "Bench placement, evolution timing, attack timing, and discard choices reveal opponent intent only probabilistically because multiple lists and goals can produce the same public action.", "search_design", "opponent_inference", "MEDIUM", "expert_reasoning_and_partial_observability", "DIRECT", "CABT public-information actor", [link("SRC-025", "supports", "Use board state and opponent capability to infer likely plans.", "lines 65-70"), link("SRC-005", "qualifies", "The API exposes public state, not private intent.", "State and logs")], ["belief", "opponent-model", "replays"], "Do not claim causal hidden implementation from timing alone."),
    claim("CLM-034", "An attack should normally be the final irreversible action of the turn; before committing, finish legal setup, search, bench, attachment, and information-gathering choices.", "sequencing_rule", "turn_sequencing", "HIGH", "rules_and_strategy_sources", "TRANSFERABLE", "Pokemon TCG tabletop and CABT legal-action flow", [link("SRC-019", "primary_rule_evidence", "Turn ends after attack in the rulebook flow.", "What You Can Do During Your Turn"), link("SRC-036", "supports", "No other actions occur after attack declaration; attack last.", "lines 38-42 and 61")], ["sequencing", "irreversible", "information"], "Engine may expose effects differently; legal options remain authoritative."),
    claim("CLM-035", "Overbenching increases exposure to gust, spread, and future forced-Prize routes; underbenching can also strand a deck that needs support, so bench value is role- and matchup-dependent.", "anti_pattern", "bench_management", "HIGH", "multiple_strong_sources", "TRANSFERABLE", "Pokemon TCG strategy across formats", [link("SRC-024", "supports", "Bench and support threats alter the opponent's best attack.", "lines 85-91"), link("SRC-036", "supports", "Many attacks target the Bench; do not bench automatically.", "lines 31-35")], ["bench", "risk", "matchups"], "The exception is an engine whose consistency requires a full board."),
    claim("CLM-036", "Stage 1/Stage 2 evolution timing creates a setup vulnerability; protect the basic/evolution chain and value effects that compress turns, but do not delay a legal lethal line for ideal setup.", "strategic_principle", "evolution_timing", "MEDIUM", "rules_and_strategy_sources", "TRANSFERABLE", "Pokemon TCG strategy across formats", [link("SRC-036", "supports", "Evolution cannot normally happen on the first turn played and Stage 2 needs support.", "lines 95-111"), link("SRC-034", "supports", "Opening consistency and turn-one setup access should be measured.", "lines 25-40")], ["setup", "evolution", "tempo"], "Exact CABT evolution effects are card/engine-specific."),
    claim("CLM-037", "Special Energy can compress attack costs but is a concentrated resource vulnerable to removal or card-specific punishment; attach it only after checking the opponent's relevant answers.", "strategic_principle", "special_energy", "MEDIUM", "rules_and_strategy_sources", "TRANSFERABLE", "Pokemon TCG strategy across formats", [link("SRC-036", "supports", "Special Energy has benefits and risks because it is limited and punishable.", "lines 194-200"), link("SRC-025", "supports", "Stress-test opponent resources and available responses.", "lines 65-70")], ["resources", "risk", "hidden-information"], "Exact special-energy interactions need card-table verification."),
    claim("CLM-038", "Control, mill, and stall are different strategic plans: deny resources, reduce the opponent's deck, or deny Prize-taking; the evaluator must not label all non-KO play as one category.", "strategic_principle", "alternate_win_conditions", "HIGH", "strong_strategy_source", "TRANSFERABLE", "Pokemon TCG strategy across formats", [link("SRC-031", "supports", "Defines aggression, control, mill, and stall separately.", "lines 23-51"), link("SRC-019", "primary_rule_evidence", "Deck-out is an official win condition.", "How to Win")], ["control", "deckout", "search"], "CABT card pool determines whether each plan is viable."),
    claim("CLM-039", "When ahead, variance reduction means preserving a robust win route and shrinking the opponent's immediate outs; when behind, a higher-variance line can be correct only if it increases total win probability.", "strategic_principle", "risk_management", "MEDIUM", "competitive_guidance_and_reasoned_translation", "TRANSFERABLE", "Pokemon TCG strategy; validate in CABT", [link("SRC-025", "supports", "Stress-test opponent responses and choose lines based on capability.", "lines 62-70"), link("SRC-034", "supports", "Time, prize route, and lower-resource lines change the choice.", "lines 104-121 and 202-215")], ["risk", "search", "probability"], "No sourced universal numeric risk threshold exists."),
    claim("CLM-040", "High-HP healing loops can erase prior damage and alter a matchup's prize race; spread/low-damage plans should be evaluated against healing and reset resources.", "matchup_principle", "damage_and_healing", "HIGH", "current_competitive_analysis", "TRANSFERABLE", "2026 Standard example; CABT card pool must be checked", [link("SRC-027", "supports", "Mega Lopunny uses healing and retreat-looping to reset damage and position the Prize trade.", "lines 57-62"), link("SRC-026", "supports", "Prize denial/healing complicates efficient Prize maps.", "lines 71-74")], ["matchups", "prize-map", "damage"], "The card names are not automatically present in CABT."),
    claim("CLM-041", "Spread damage is valuable when it converts later attacks or effects into multiple knockouts, but it is a liability if it delays the first meaningful attack or cannot survive the opponent's response.", "strategic_principle", "spread_damage", "HIGH", "official_competitive_analysis", "TRANSFERABLE", "Pokemon TCG strategy across formats", [link("SRC-031", "supports", "Spread is a distinct aggression plan built around later multi-KOs.", "lines 29-34"), link("SRC-022", "supports", "Expert analysis highlights spreading damage and toolbox attacks for multi-KO pressure.", "lines 34-42")], ["spread", "prize-map", "attack"], "Model damage counters and KO thresholds exactly from CABT card data."),
    claim("CLM-042", "Three-Prize Mega Pokemon complicate prize exchanges; a target's prize value, HP, liability, and ability to be one-hit should be part of target selection.", "strategic_principle", "prize_values", "HIGH", "current_competitive_analysis", "TRANSFERABLE", "2026 Standard examples; CABT card pool may differ", [link("SRC-026", "supports", "High-HP three-Prize Megas complicate prize exchanges.", "line 71"), link("SRC-034", "supports", "Target and prize route should account for retaliation and required pieces.", "lines 104-121")], ["prize-map", "threats", "matchups"], "Do not assume every current Standard Mega is legal in CABT."),
    claim("CLM-043", "Tord Reklev's 2026 interview emphasizes that losing broad hand disruption changes the cost of rushing ahead and increases the importance of knockout timing; this is format-dependent expert opinion, not a universal rule.", "expert_opinion", "elite_player_strategy", "HIGH", "direct_elite_interview", "TRANSFERABLE", "2026 post-rotation Standard; not CABT proof", [link("SRC-023", "supports", "Tord connects loss of Iono/Counter Catcher with aggression and knockout timing.", "lines 46-56")], ["elite", "prize-map", "risk"], "Transfer only the reasoning pattern; verify whether CABT includes the same cards."),
    claim("CLM-044", "Tord's historical deck explanation links card choice, high Energy count, and the need to hit large knockouts while preserving a recovery component; a prized key card can invalidate the ideal line.", "expert_opinion", "elite_player_strategy", "HIGH", "official_elite_interview", "TRANSFERABLE", "2019 historical Standard; not CABT-equivalent", [link("SRC-021", "supports", "Tord explains Energy count, acceleration, large knockouts, and a key prized card.", "English lines 114-134")], ["elite", "resources", "prize-check"], "Use as a resource-ledger example, not as a current card rule."),
    claim("CLM-045", "Official Mega Lucario strategy advice selects a single-Prize opener against single-Prize decks and a Mega Lucario opener when the matchup demands setup for its main attack; single-Prize attackers can prevent an easy 2-2-2 route.", "matchup_principle", "mega_lucario", "HIGH", "official_deck_strategy", "INDIRECT", "2026 Standard article; competition rule anchor has same archetype but exact list is local", [link("SRC-054", "supports", "Official guide describes Solrock versus Mega Lucario opening choices and one-Prize sequencing.", "article summary")], ["mega-lucario", "prize-map", "matchups"], "Verify exact CABT card IDs and attacks before implementation."),
    claim("CLM-046", "Repeated practice with a single deck can improve decisions because the player can recognize prize routes, setup thresholds, and recovery patterns faster; deck mastery is not evidence that one list is universally best.", "expert_opinion", "specialist_mastery", "MEDIUM", "official_expert_analysis", "TRANSFERABLE", "Pokemon TCG competitive play", [link("SRC-022", "supports", "Official panel says some decks reward repeated play and familiarity.", "lines 38-42"), link("SRC-034", "supports", "Narrow, reliable deck plans outperform unresolved breadth in tournament preparation.", "lines 21-30")], ["elite", "specialist", "deck"], "Supports exact-deck specialization, not universal deck selection."),
    claim("CLM-047", "CABT deck-search options expose the candidate cards and their semantic references; the actor should choose from that list and maintain a public ledger rather than infer a hidden deck order.", "rule", "deck_search", "VERY_HIGH", "local_api_and_simulator_notes", "DIRECT", "CABT competition 2026", [link("SRC-005", "primary_rule_evidence", "Search option list and select.deck semantics.", "Search API"), link("SRC-043", "supports", "Deck-search discussion notes actual candidate exposure.", "discussion")], ["competition", "search", "belief"], "Do not use private card data as a proxy for the current hidden opponent deck."),
    claim("CLM-048", "CABT resolves simultaneous knockouts sequentially and reports a draw if both players complete the win condition; terminal ordering must be modeled by the engine transition, not guessed from tabletop intuition.", "rule", "terminal_resolution", "HIGH", "host_clarification", "DIRECT", "CABT competition 2026", [link("SRC-042", "primary_rule_evidence", "Host clarification describes sequential KO resolution and draw handling.", "Differences Between Official Rules and Simulator Behavior")], ["competition", "terminal", "search"], "Retain engine-version provenance for any regression."),
    claim("CLM-049", "Replay action/observation alignment was not answered authoritatively in the original thread; a participant's 22-episode correction found 1,277/1,277 matches after forward-searching active steps, but this remains a parser hypothesis to revalidate.", "hypothesis", "replay_alignment", "HIGH", "local_replay_audit_plus_participant_validation", "DIRECT", "CABT replay schema versioned by episode", [link("SRC-040", "qualifies", "Original clarification request did not settle alignment.", "discussion"), link("SRC-041", "supports", "Participant reports 1,277/1,277 corrected matches.", "discussion"), link("SRC-014", "supports", "Repository preserves the fail-closed parser procedure.", "Episode/action alignment")], ["replays", "data", "uncertainty"], "Do not use public replay actions as labels until exact alignment and authorization pass."),
    claim("CLM-050", "Timing or startup observations from top-team episodes can motivate a search hypothesis, but they do not identify an agent's algorithm or prove that search caused the result.", "observed_behavior", "competition_meta", "HIGH", "local_audit_and_source_qualification", "DIRECT", "CABT public replays", [link("SRC-045", "qualifies", "Timing analysis is explicitly inferential.", "discussion"), link("SRC-014", "qualifies", "Local meta synthesis records survivorship and causal limits.", "Small matchup studies")], ["competition", "replays", "search"], "Record observed behavior separately from inferred algorithm."),
    claim("CLM-051", "A small public matchup matrix can reveal candidate matchup holes, but its win rates are not stable estimates unless games, seats, versions, and populations are controlled.", "observed_behavior", "competition_evaluation", "HIGH", "local_audit_and_small_public_sample", "DIRECT", "CABT public matchup evidence", [link("SRC-046", "supports", "The 11-agent matrix has only 550 games and is a screening tool.", "discussion"), link("SRC-014", "supports", "Repository recommends matchup-stratified evaluation.", "Small matchup studies")], ["competition", "evaluation", "matchups"], "Use for hypothesis generation only."),
    claim("CLM-052", "Visible option order may be a predictive shortcut in CABT, but it must be tested under option-order permutation and semantic controls before being used as a policy feature.", "hypothesis", "option_order", "MEDIUM", "local_audit_of_public_reports", "DIRECT", "CABT current engine", [link("SRC-014", "supports", "Audit records participant reports of high option-0 performance and requires ablation.", "Architecture audit"), link("SRC-006", "qualifies", "API defines semantic fields independent of list position.", "Option data classes")], ["competition", "actions", "search"], "No numeric weight is stored; only an experiment candidate."),
    claim("CLM-053", "Public replay teacher metadata can establish exact deck identity, seat balance, module/schema compatibility, and action-contract alignment, but positive outcomes and high rank do not prove that any observed action is optimal.", "observed_behavior", "teacher_evidence", "VERY_HIGH", "local_independent_review", "DIRECT", "CABT public replay metadata", [link("SRC-016", "supports", "Dries review separates consistency from blocked competence confirmation.", "qualification"), link("SRC-018", "supports", "Majkel review records two wins but explicitly denies policy competence.", "qualification"), link("SRC-013", "supports", "Current status keeps training/competence claims blocked.", "G3b")], ["competition", "replays", "teacher"], "Use metadata for provenance and sampling, not causal rule extraction."),
    claim("CLM-054", "Standard-format deck lists and matchup advice are useful for transferable strategic concepts, but they are not direct evidence of CABT card legality, engine semantics, or hidden-ladder prevalence.", "rule", "format_boundary", "VERY_HIGH", "official_format_rules_and_local_contract", "INDIRECT", "Standard/Expanded versus CABT competition card pool", [link("SRC-020", "primary_rule_evidence", "Standard legality is defined by regulation marks and tournament rules.", "Card legality"), link("SRC-009", "primary_rule_evidence", "CABT uses its own local official card table.", "asset metadata"), link("SRC-033", "qualifies", "Limitless database is a tournament database, not CABT evidence.", "current deck snapshot")], ["format", "competition", "cards"], "Every imported strategy record keeps its source format."),
    claim("CLM-055", "The hypergeometric distribution is the correct baseline for sampling known successes without replacement from a finite deck; independent-draw binomial shortcuts are wrong for ordinary deck draws.", "probability_fact", "draw_probability", "VERY_HIGH", "primary_math_reference", "TRANSFERABLE", "Finite-deck sampling", [link("SRC-035", "primary_rule_evidence", "NIST defines the hypergeometric CDF for sampling without replacement.", "HYPCDF"), link("SRC-032", "example", "Limitless provides an opening-hand calculator using deck draw probabilities.", "Opening Hand Calculator")], ["probability", "outs", "deck"], "Card effects that shuffle/recycle require a state transition before recomputing."),
    claim("CLM-056", "A combined-out calculation must account for overlap and conditional search effects; adding individual out percentages is only an approximation when outs are not mutually exclusive.", "probability_fact", "outs", "HIGH", "mathematical_translation", "TRANSFERABLE", "Finite-deck card search", [link("SRC-035", "supports", "Hypergeometric model supplies exact finite-population baseline.", "HYPCDF"), link("SRC-032", "example", "Opening-hand tool distinguishes target categories and cards seen.", "Opening Hand Calculator")], ["probability", "outs", "search"], "Represent each out as a state transition or set of reachable cards."),
    claim("CLM-057", "The official competition page uses Gaussian skill ratings and a win/draw/loss outcome, not prize margin; local research should optimize game wins and avoid drawing conclusions from Prize margin.", "rule", "competition_evaluation", "VERY_HIGH", "official_competition_page", "DIRECT", "CABT ladder 2026", [link("SRC-001", "primary_rule_evidence", "Evaluation uses skill rating updates from wins, losses, and draws; score margin does not affect rating.", "Evaluation")], ["competition", "evaluation", "prizes"], "Internal search can use Prize progress, but promotion must use game outcome."),
    claim("CLM-058", "The competition's public meta reports and exact teacher runs are snapshots; late engine/module changes, deck shifts, and selection bias require time/version stratification.", "observed_behavior", "meta_temporality", "HIGH", "local_project_evidence", "DIRECT", "CABT 2026", [link("SRC-014", "supports", "Meta changes quickly and runtime evidence can become stale.", "Public meta observations"), link("SRC-018", "qualifies", "The two teacher replays span module versions 1.32.2 and 1.32.3.", "consistency")], ["competition", "meta", "versioning"], "Always bind strategy evidence to date and engine/module version."),
    claim("CLM-059", "A deck-out plan is only credible when the opponent's draw obligation, remaining deck, recursion, and alternate win route are all modeled; merely seeing a low deck count is not enough.", "strategic_principle", "deckout", "HIGH", "official_rules_and_strategy", "TRANSFERABLE", "Pokemon TCG strategy across formats", [link("SRC-019", "primary_rule_evidence", "Failure to draw at turn start is a win condition.", "How to Win"), link("SRC-031", "supports", "Mill and stall explicitly use deck-out or Prize denial plans.", "lines 43-51"), link("SRC-024", "supports", "Alternate win conditions require a concrete resource plan.", "lines 198-202")], ["deckout", "control", "search"], "Treat deck-out as a terminal objective only when robust against opponent recovery."),
    claim("CLM-060", "A tabletop assumption such as first-player turn-one attack legality must not be hard-coded into the CABT agent; inspect current legal options and engine-version evidence because replay misreadings and simulator differences have occurred.", "rule", "turn_order", "HIGH", "local_engine_audit", "DIRECT", "CABT current engine", [link("SRC-007", "primary_rule_evidence", "Repository records a first-player attack report as a replay-reading error.", "Resolved reports"), link("SRC-042", "qualifies", "Host documents simulator differences.", "discussion")], ["competition", "turn-order", "actions"], "Use the legal option list and current engine, not memory of tabletop rules."),
    claim("CLM-061", "The retained Mega Lucario, Grimmsnarl, Dragapult, and public-meta observations are evidence of competition archetype presence, while Standard tournament popularity is only an external prior.", "observed_behavior", "competition_archetypes", "HIGH", "local_replay_and_public_meta", "DIRECT", "CABT competition 2026", [link("SRC-013", "supports", "Status records exact teacher archetype labels and four rule anchors.", "G3b"), link("SRC-037", "supports", "Kaggle discussion lists public competition archetypes and a current-format Limitless filter.", "discussion"), link("SRC-033", "qualifies", "Limitless is external tournament data.", "current deck snapshot")], ["competition", "archetypes", "meta"], "Do not silently use external Standard metagame shares as CABT frequencies."),
    claim("CLM-062", "The candidate Mega Abomasnow deck is especially valuable as a deterministic-research target because its exact card list, local engine compatibility, and rule-agent receipt are available; competence still requires held-out games.", "search_design", "candidate_deck", "HIGH", "local_asset_and_evaluation_contract", "DIRECT", "CABT competition 2026", [link("SRC-010", "supports", "Exact sample deck and hash.", "deck.csv"), link("SRC-011", "supports", "Exact Mega Abomasnow rule baseline receipt.", "baseline"), link("SRC-012", "qualifies", "Frozen evaluation contract requires actual game evidence.", "evaluation")], ["competition", "mega-abomasnow", "evaluation"], "This is a research prioritization claim, not a strength claim."),
]


def strategy(
    sid: str,
    name: str,
    category: str,
    description: str,
    preconditions: str,
    recommended_action: str,
    rationale: str,
    expected_benefit: str,
    failure_modes: str,
    exceptions: str,
    deterministic_rule_candidate: bool,
    search_feature_candidate: bool,
    confidence: str,
    competition_relevance: str,
    claims: list[str],
    tags: list[str],
) -> dict:
    return {
        "id": sid,
        "name": name,
        "category": category,
        "description": description,
        "preconditions": preconditions,
        "recommended_action": recommended_action,
        "rationale": rationale,
        "expected_benefit": expected_benefit,
        "failure_modes": failure_modes,
        "exceptions": exceptions,
        "deterministic_rule_candidate": int(deterministic_rule_candidate),
        "search_feature_candidate": int(search_feature_candidate),
        "confidence": confidence,
        "competition_relevance": competition_relevance,
        "claims": claims,
        "tags": tags,
    }


STRATEGIES = [
    strategy("STR-001", "Prize-route planning", "prize_mapping", "Compare complete multi-turn Prize routes rather than the largest immediate damage event.", "A KO, gust line, or alternate win is available and the game is not already terminal.", "Enumerate plausible target and attacker sequences, then prefer the route with the shortest robust completion and acceptable opponent retaliation.", "The first KO changes the opponent's available targets and the remaining resource burden.", "Fewer required pieces, less forced exposure, clearer search objective.", "Overfitting to a nominal route when a key piece is prized or the opponent has a forcing response.", "Take a guaranteed immediate win or forced KO when no later route can improve the outcome.", True, True, "HIGH", "Directly useful for CABT action ranking.", ["CLM-017", "CLM-018", "CLM-019", "CLM-023", "CLM-042"], ["prize-map", "search", "matchups"]),
    strategy("STR-002", "Avoid an unfavourable prize trade", "risk_management", "Do not begin a conventional attacker-for-attacker exchange when the opponent's projected route is faster or more reliable.", "Opponent can answer the intended attacker and our next attacker is not ready, or the target exposes a superior retaliation.", "Develop, deny, or pivot to a concrete alternate route before taking a non-forcing KO.", "A visible KO can still lose if it hands the opponent the only efficient route.", "Preserves tempo and reduces self-created forced prizes.", "Over-defending can miss a lethal or give the opponent time to stabilize.", "Ignore this when the attack wins immediately or blocks the opponent's only win.", True, True, "HIGH", "Universal guard with matchup overrides.", ["CLM-017", "CLM-018", "CLM-021", "CLM-023"], ["prize-map", "risk", "tempo"]),
    strategy("STR-003", "Build the next attacker before trading", "attacker_sequencing", "Treat the next usable attacker and its Energy/support threshold as a prerequisite for a non-terminal KO.", "Current attack does not win the game and the next opponent turn can KO or strand the active.", "Bench or evolve the next attacker, attach the required Energy, and preserve its access before attacking.", "A KO without follow-up can give back the initiative.", "Maintains an attack chain and raises future legal-action quality.", "Bench space, Energy, or search spent on a threat that the opponent can immediately remove.", "A forced gust KO or a turn that must be spent on disruption can supersede development.", True, True, "HIGH", "Core exact-deck specialist feature.", ["CLM-018", "CLM-027", "CLM-024"], ["attackers", "resources", "bench"]),
    strategy("STR-004", "Public resource ledger", "resource_accounting", "Track remaining attackers, Energy, recovery, gust, switching, evolution, and disruption as named counts rather than hand-size proxies.", "The action spends a card, attach, discard, bench slot, or finite once-per-game effect.", "Before spending, decrement the relevant ledger and check whether the planned future route still has legal outs.", "Different cards with the same count have very different recoverability and role value.", "Prevents premature recovery/gust use and makes future attack feasibility explicit.", "Ledger errors, hidden prize uncertainty, and card effects that create new resources.", "Use a confidence interval or particle belief for unknown zones; never label an unknown as spent.", True, True, "HIGH", "Direct bridge to deterministic state evaluation.", ["CLM-022", "CLM-027", "CLM-031", "CLM-044"], ["resources", "belief", "prize-check"]),
    strategy("STR-005", "Role-aware bench management", "bench_management", "Value each bench slot by future attacker, draw engine, pivot, liability, and target-denial roles.", "Bench has free slots and multiple legal bench candidates, or an effect forces a bench choice.", "Reserve slots for the minimum board needed by the prize route and avoid liabilities unless their immediate value exceeds exposure.", "Bench space is a finite future resource and can be converted into opponent gust value.", "Less forced-prize exposure and more room for the chosen line.", "Under-benching can reduce consistency or fail a card's setup requirement.", "Deck engines with a proven full-bench requirement and terminal attack lines.", True, True, "HIGH", "Applicable to every competition archetype after card-role annotation.", ["CLM-024", "CLM-035", "CLM-041"], ["bench", "prize-map", "threats"]),
    strategy("STR-006", "Convert gust into route progress", "target_selection", "Use Boss-like effects when the selected target materially shortens the Prize route or removes an imminent threat.", "Gust is available and at least two legal targets differ in Prize value, retaliation, or future attack access.", "Score target identity by route distance, KO certainty, opponent threat removal, and post-gust board rather than damage alone.", "Gust is finite; a high-damage target can be strategically worse than a low-HP support target.", "Turns a scarce resource into a forced target or threat denial.", "Gusting a support Pokemon may enable a better attacker or leave the active attacker untouched.", "Use freely only when it is the only winning or terminal line.", True, True, "HIGH", "Direct action-rule candidate.", ["CLM-019", "CLM-020", "CLM-024", "CLM-025", "CLM-042"], ["gust", "prize-map", "targets"]),
    strategy("STR-007", "Opponent-response stress test", "opponent_modeling", "For each candidate action, enumerate the opponent's strongest public-resource response and the board after it.", "The action is not forced and opponent has multiple plausible attackers, gust effects, or disruption lines.", "Prefer a line whose worst credible response still leaves a positive route, unless behind-state variance is required.", "A good present state can collapse when the opponent's next turn is omitted from evaluation.", "Reduces blind tactical blunders and highlights robust lines.", "Unknown hand modelling can become overconfident or too conservative.", "Keep unknowns probabilistic and keep multiple worlds when action likelihood is close.", True, True, "HIGH", "Core tactical search extension.", ["CLM-025", "CLM-026", "CLM-032", "CLM-039"], ["belief", "risk", "search"]),
    strategy("STR-008", "Information-first sequencing", "turn_sequencing", "Order actions to obtain relevant information before making irreversible or resource-consuming commitments.", "A search/reveal/draw action changes the feasible candidate set and an attach, discard, bench, retreat, or attack would narrow future options.", "Define the turn objective, obtain information that can change it, then commit only after the new state is scored.", "Sequencing has no universal script; the value of information depends on which branch it can change.", "Preserves optionality and avoids paying for a line invalidated by a later reveal.", "Information action itself may consume a supporter, shuffle a known target, or expose a tell.", "Take a terminal line immediately; do not delay a forced win for marginal information.", True, True, "HIGH", "Directly maps to action sequencing search.", ["CLM-029", "CLM-030", "CLM-034"], ["sequencing", "information", "irreversible"]),
    strategy("STR-009", "Conditional deck thinning", "deck_thinning", "Thin dead or replaceable cards only when the marginal draw improvement exceeds the lost tutor, shuffle, recovery, or future-target value.", "A search effect can remove a card and at least one future draw/disruption event matters.", "Compare keep-versus-thin states using finite-deck outs and future searchable roles; do not auto-thin.", "Thinning improves later draws but the card and effect used to thin are resources.", "Higher late-turn out probability and better disruption resilience when the removed cards are dead.", "Greedy thinning removes a needed target, burns a shuffle, or increases vulnerability to a known disruption.", "If a card is dead in every reachable line and the search has no opportunity cost, thinning is usually safe.", True, True, "HIGH", "Should be a tested feature, not a fixed ordering rule.", ["CLM-028", "CLM-029", "CLM-055", "CLM-056"], ["sequencing", "probability", "deck"]),
    strategy("STR-010", "Prize and inaccessible-copy ledger", "hidden_information", "Record revealed Prizes, discarded copies, searched cards, and unreachable cards separately from unknown cards.", "A route depends on one or more copies whose location has been revealed or constrained.", "Update route probabilities and required resources after every public reveal; maintain alternate routes when a key copy may be prized.", "Prize checks are information, not just a setup action.", "Avoids planning with cards that cannot be accessed and quantifies dead-route risk.", "Incorrect parsing of search/reveal effects or conflating deck count with card identity.", "Until the effect resolves, keep the card in the appropriate belief set.", True, True, "HIGH", "Essential for deterministic belief tracking.", ["CLM-022", "CLM-030", "CLM-031", "CLM-032"], ["prize-check", "belief", "resources"]),
    strategy("STR-011", "Ahead-state variance reduction", "risk_management", "When the current line wins with margin, choose the line that leaves fewer immediate opponent outs rather than the line with more damage.", "Our projected game result is favourable and at least one lower-variance legal action preserves the win route.", "Reduce exposed liabilities, preserve gust/recovery, and deny the opponent's simplest comeback before attacking.", "The competition rewards game outcomes; gratuitous variance turns a winning state into a coin flip.", "Higher robustness to unknown hands and future draws.", "Passing a forced win or allowing the opponent to develop a better board.", "Terminal win and forced KO override risk reduction.", True, True, "MEDIUM", "Requires CABT ablation; no numeric risk threshold is sourced.", ["CLM-020", "CLM-025", "CLM-039", "CLM-057"], ["risk", "ahead", "search"]),
    strategy("STR-012", "Behind-state variance selection", "risk_management", "When the nominal route is losing, choose a higher-variance line only when its best-case branches add more win probability than the robust-looking alternatives.", "Normal prize route is behind and a disruption, gust, spread, or unusual out can change the race.", "Preserve lines that create multiple winning branches and explicitly price the failure probability.", "A losing player cannot always preserve a safe route that does not exist.", "Improves comeback potential while keeping variance deliberate rather than random.", "Throwing away recovery or making an impossible line; confusing low probability with no probability.", "If a concrete denial line has a higher expected result, prefer it over a flashy coin flip.", True, True, "MEDIUM", "Search policy candidate, not a fixed heuristic.", ["CLM-021", "CLM-023", "CLM-039", "CLM-056"], ["risk", "behind", "probability"]),
    strategy("STR-013", "Alternate-win validation", "deckout_control", "Treat deck-out, board elimination, and denial as explicit objectives with their own resource and opponent-response checks.", "Prize route is losing or a card effect makes an alternate win plausible.", "Estimate the opponent's remaining draw, recursion, recovery, and legal escape actions before pivoting.", "Non-KO play can win, but only if the alternative route is real and robust.", "Stops the evaluator from mis-scoring control and mill states as passive losses.", "Low deck count alone, ignoring opponent's alternate win or shuffle/recovery.", "Do not prioritize an alternate route when a forced Prize win is available.", True, True, "HIGH", "Relevant if exact CABT card effects support the plan.", ["CLM-004", "CLM-021", "CLM-038", "CLM-059"], ["deckout", "control", "terminal"]),
    strategy("STR-014", "Spread threshold planning", "damage_planning", "Use spread only when the damage counters create a future KO or force a resource response that is better than a direct attack.", "Spread attack is legal and at least two future targets can cross a meaningful KO/retreat threshold.", "Track exact damage by target and compare direct KO, spread, and opponent reset lines.", "Spread is a route to multiple Prizes, not damage for its own sake.", "Creates multi-KO threats and can deny the opponent's preferred board.", "The opponent heals/resets, the first attack is too slow, or spread creates more liabilities than threats.", "Prefer direct KO when it is terminal or when spread cannot be converted before retaliation.", True, True, "HIGH", "Card-pool-dependent matchup feature.", ["CLM-040", "CLM-041", "CLM-042"], ["spread", "damage", "prize-map"]),
    strategy("STR-015", "Exact-deck specialist policy", "competition_design", "Bind strategic priors and resource counts to one exact submitted deck while training/evaluating against diverse opponents.", "Candidate deck and its full list are known, but opponent deck is not.", "Build card-role, attack-threshold, prize, and recovery logic from the exact deck; retain universal opponent models separately.", "Mastery of a fixed deck is more reliable than a universal policy with weak card semantics.", "Smaller state/action model and clearer regression coverage.", "Overfitting to an obsolete meta or confusing teacher deck evidence with candidate-deck competence.", "Freeze only with explicit authorization and fresh current-engine evidence.", True, True, "HIGH", "Matches the current project architecture but is not a submission decision.", ["CLM-012", "CLM-013", "CLM-046", "CLM-062"], ["competition", "specialist", "deck"]),
    strategy("STR-016", "Semantic legal-option scoring", "agent_interface", "Score every current legal option by its semantic source/target/role rather than list position or a fixed global action vocabulary.", "CABT supplies a selection and one or more legal options.", "Parse the exact option type, score all options, validate the final index sequence, and fail closed on unknown semantics.", "The legal option list is the current engine's ground truth and can vary by state.", "Legality, full option coverage, and reproducible action semantics.", "Truncated options, stale positions, option-order leakage, or a tabletop-only branch.", "A deterministic fallback may select a legal option only in submission mode; development must fail loudly.", True, False, "VERY_HIGH", "Exact competition interface requirement.", ["CLM-002", "CLM-008", "CLM-047", "CLM-060"], ["competition", "actions", "legality"]),
    strategy("STR-017", "Belief-particle route evaluation", "hidden_information", "Evaluate hidden-opponent possibilities as weighted legal worlds and aggregate action outcomes without treating any one guess as fact.", "Opponent hand/deck/Prizes are partially hidden and multiple archetype/list hypotheses remain legal.", "Update particles from revealed actions and effects, score candidate actions across the posterior, and track hidden-state sensitivity.", "Information-set decisions need robustness across plausible hidden states.", "Avoids omniscient determinization and identifies actions that are fragile to one hidden card.", "Particle collapse, strategy fusion, computational cost, or invalid hidden allocations.", "Use public facts as hard constraints and keep a broad prior when evidence is sparse.", True, True, "MEDIUM", "Algorithm hypothesis; requires CABT validation.", ["CLM-005", "CLM-009", "CLM-010", "CLM-032", "CLM-033"], ["belief", "search", "probability"]),
    strategy("STR-018", "Selective tactical search", "search_design", "Search only irreversible or high-swing branches around the policy's proposed action, with terminal and legality checks first.", "A competent policy exists and the state contains a KO, gust, disruption, retreat lock, or forced response.", "Order branches by terminal value, immediate threat, route distance, and policy prior; prune dominated actions only after exact legality checks.", "Full-tree search is too expensive under CABT CPU limits; tactical search concentrates effort where a mistake changes the game.", "Improved tactical precision at bounded runtime.", "Search overhead, stale recurrent state, hidden-state strategy fusion, or pruning a low-probability comeback.", "Remove search if held-out games do not improve under the strict time budget.", True, True, "HYPOTHESIS", "Candidate for later, not current production.", ["CLM-007", "CLM-016", "CLM-025", "CLM-039", "CLM-050"], ["search", "runtime", "tactics"]),
    strategy("STR-019", "Replay evidence firewall", "evidence_discipline", "Use replay data to establish observed choices and metadata, not hidden implementation or causal optimality without aligned, authorized evidence.", "Public replay actions or timing are available but alignment, sampling, or competence gates are incomplete.", "Store observation, sample size, version, and inference strength separately; keep action supervision out of policy evidence unless approved.", "Winning actions can reflect draws, matchups, or misalignment rather than a reusable rule.", "Prevents overfitting and preserves provenance.", "Discarding useful hypotheses because evidence is not causal proof.", "Promote only after independent alignment/competence validation and held-out comparison.", True, False, "VERY_HIGH", "Repository safety and research-quality requirement.", ["CLM-014", "CLM-049", "CLM-050", "CLM-051", "CLM-053", "CLM-058"], ["replays", "evidence", "competition"]),
    strategy("STR-020", "Outcome-aligned evaluation", "evaluation", "Use win/draw/loss and matchup-stratified distributions for promotion while retaining Prize progress as an internal feature.", "Comparing candidate agents or strategic rules.", "Balance natural seat assignment, retain raw traces, report confidence intervals, and do not promote on Prize margin or tiny matrices.", "CABT rating is outcome-based and internal proxies can reward the wrong behavior.", "Validates actual competition objective and exposes catastrophic matchups.", "Unbalanced seats, engine-version mixing, insufficient sample size, or hidden population shift.", "Use forced-seat diagnostics separately from natural deployment estimates.", True, False, "VERY_HIGH", "Exact evaluation discipline from local contract.", ["CLM-010", "CLM-051", "CLM-057", "CLM-058"], ["evaluation", "competition", "evidence"]),
]


ARCHETYPES = [
    {"id": "ARC-001", "name": "Mega Abomasnow ex", "format_scope": "CABT local sample/rule anchor", "competition_present": 1, "description": "Exact local engineering/sample deck built around Mega Abomasnow ex, Kyogre, and Snover; list identity is verified locally.", "primary_game_plan": "Research exact-deck setup, Energy/attacker sequencing, Prize route, and spread/bench tradeoffs from the local card table.", "source_confidence": "VERY_HIGH", "tags": ["competition", "candidate", "mega-abomasnow"]},
    {"id": "ARC-002", "name": "Mega Lucario ex", "format_scope": "CABT rule anchor and retained teacher archetype", "competition_present": 1, "description": "Competition archetype represented by a native rule anchor and exact Mega Lucario teacher metadata.", "primary_game_plan": "Fighting pressure with one-Prize setup alternatives and Mega Lucario Prize sequencing; exact CABT list must govern details.", "source_confidence": "VERY_HIGH", "tags": ["competition", "mega-lucario", "rule-anchor"]},
    {"id": "ARC-003", "name": "Dragapult ex", "format_scope": "CABT rule anchor and retained teacher archetype", "competition_present": 1, "description": "Competition archetype represented by a native rule anchor; exact local card IDs are recorded for the line.", "primary_game_plan": "Build the Dragapult line, convert spread into Prize progress, and preserve the draw/attacker engine.", "source_confidence": "VERY_HIGH", "tags": ["competition", "dragapult", "rule-anchor"]},
    {"id": "ARC-004", "name": "Iono", "format_scope": "CABT rule anchor", "competition_present": 1, "description": "Competition archetype represented by the native Iono rule anchor and its local card mappings.", "primary_game_plan": "Develop the Bellibolt line and evaluate disruption, Energy, and bench targets under the actual engine.", "source_confidence": "VERY_HIGH", "tags": ["competition", "iono", "rule-anchor"]},
    {"id": "ARC-005", "name": "Marnie's Grimmsnarl ex", "format_scope": "CABT retained teacher archetype", "competition_present": 1, "description": "Exact teacher deck metadata exists in local evidence; competence remains unproven.", "primary_game_plan": "Dark-type pressure and resilient attacker sequencing; treat detailed matchup claims as hypotheses until exact card list is analyzed.", "source_confidence": "HIGH", "tags": ["competition", "grimmsnarl", "teacher"]},
    {"id": "ARC-006", "name": "Cynthia's Garchomp ex", "format_scope": "CABT public-meta observation", "competition_present": 1, "description": "Repeatedly visible in public competition meta observations; no unbiased prevalence estimate.", "primary_game_plan": "Fighting pressure and target selection; exact list and observed frequency require current replay evidence.", "source_confidence": "HIGH", "tags": ["competition", "public-meta"]},
    {"id": "ARC-007", "name": "Alakazam", "format_scope": "CABT public-meta observation", "competition_present": 1, "description": "Publicly observed competition archetype and matchup-screening target.", "primary_game_plan": "Evaluate unusual damage/bench pressure and resource denial from exact local cards.", "source_confidence": "MEDIUM", "tags": ["competition", "public-meta"]},
    {"id": "ARC-008", "name": "Crustle", "format_scope": "CABT public-meta observation", "competition_present": 1, "description": "Early and repeated public competition meta archetype; frequency is snapshot-biased.", "primary_game_plan": "Assess durable or defensive Prize route and efficient target selection.", "source_confidence": "MEDIUM", "tags": ["competition", "crustle", "public-meta"]},
    {"id": "ARC-009", "name": "Starmie", "format_scope": "CABT public-meta observation", "competition_present": 1, "description": "Visible late-June public top-ten archetype; no direct local deck list in this corpus.", "primary_game_plan": "Evaluate fast tempo and low/variable Prize exchanges from observed list evidence.", "source_confidence": "MEDIUM", "tags": ["competition", "starmie", "public-meta"]},
    {"id": "ARC-010", "name": "Typhlosion", "format_scope": "CABT public-meta observation", "competition_present": 1, "description": "Early public competition archetype reported in Kaggle discussion and local synthesis.", "primary_game_plan": "Test setup tempo, Energy acceleration, and attacker sequencing.", "source_confidence": "MEDIUM", "tags": ["competition", "typhlosion", "public-meta"]},
    {"id": "ARC-011", "name": "Team Rocket's Mewtwo", "format_scope": "CABT public-meta observation", "competition_present": 1, "description": "Appeared in later public meta observations; exact deck evidence is incomplete.", "primary_game_plan": "Model disruption, resource denial, and target selection only after local list confirmation.", "source_confidence": "MEDIUM", "tags": ["competition", "mewtwo", "public-meta"]},
    {"id": "ARC-012", "name": "Festival Lead", "format_scope": "CABT public-meta observation", "competition_present": 1, "description": "Observed public competition archetype with a distinct setup/engine plan.", "primary_game_plan": "Test board development and engine denial against the candidate deck.", "source_confidence": "MEDIUM", "tags": ["competition", "festival", "public-meta"]},
    {"id": "ARC-013", "name": "Archaludon", "format_scope": "CABT public-meta observation", "competition_present": 1, "description": "Publicly observed archetype and subject of a community counter discussion.", "primary_game_plan": "Evaluate high-HP attacker sequencing, Energy requirements, and counter-target priorities.", "source_confidence": "MEDIUM", "tags": ["competition", "archaludon", "public-meta"]},
    {"id": "ARC-014", "name": "Psychic", "format_scope": "CABT public-meta observation", "competition_present": 1, "description": "Public meta label covering several Psychic decks; it is not a canonical exact list.", "primary_game_plan": "Use only as a coarse prior until archetype/card identity is resolved.", "source_confidence": "LOW", "tags": ["competition", "psychic", "public-meta"]},
    {"id": "ARC-015", "name": "Hop", "format_scope": "CABT public-meta observation", "competition_present": 1, "description": "Public top-ten snapshot archetype; exact composition and prevalence remain uncertain.", "primary_game_plan": "Identify the concrete attacker/engine before writing matchup rules.", "source_confidence": "LOW", "tags": ["competition", "hop", "public-meta"]},
    {"id": "ARC-016", "name": "Mega Lopunny ex", "format_scope": "2026 Standard external only", "competition_present": 0, "description": "Current Standard external example used for healing/prize-race concepts; not verified as CABT-legal.", "primary_game_plan": "Tank/heal and reset damage; use only as transferable principle evidence.", "source_confidence": "LOW", "tags": ["external-standard", "healing"]},
    {"id": "ARC-017", "name": "Random engineering deck", "format_scope": "CABT local evaluation population", "competition_present": 1, "description": "Repository smoke/evaluation deck label, not a competitive archetype; retained to distinguish test population from meta.", "primary_game_plan": "Contract and reliability testing only.", "source_confidence": "HIGH", "tags": ["competition", "evaluation", "not-archetype"]},
]


CARDS = [
    {"id": "CARD-0003", "canonical_card_id": "3", "name": "Basic Water Energy", "card_type": "Energy", "relevant_archetypes": "Mega Abomasnow ex", "strategic_role": "basic Energy count and attack-cost resource", "competition_present": 1, "notes": "Exact local card identifier; no full card text copied.", "archetypes": [("ARC-001", "core-resource")]},
    {"id": "CARD-0119", "canonical_card_id": "119", "name": "Dreepy", "card_type": "Pokemon", "relevant_archetypes": "Dragapult ex", "strategic_role": "basic evolution-line setup", "competition_present": 1, "notes": "Local rule-anchor mapping.", "archetypes": [("ARC-003", "evolution-line")]},
    {"id": "CARD-0120", "canonical_card_id": "120", "name": "Drakloak", "card_type": "Pokemon", "relevant_archetypes": "Dragapult ex", "strategic_role": "evolution and draw-line setup", "competition_present": 1, "notes": "Local rule-anchor mapping.", "archetypes": [("ARC-003", "evolution-line")]},
    {"id": "CARD-0121", "canonical_card_id": "121", "name": "Dragapult ex", "card_type": "Pokemon", "relevant_archetypes": "Dragapult ex", "strategic_role": "main attacker and spread threat", "competition_present": 1, "notes": "Local rule-anchor mapping.", "archetypes": [("ARC-003", "main-attacker")]},
    {"id": "CARD-0140", "canonical_card_id": "140", "name": "Fezandipiti ex", "card_type": "Pokemon", "relevant_archetypes": "Dragapult ex", "strategic_role": "support/draw liability and target", "competition_present": 1, "notes": "Local rule-anchor mapping.", "archetypes": [("ARC-003", "support")]},
    {"id": "CARD-0184", "canonical_card_id": "184", "name": "Latias ex", "card_type": "Pokemon", "relevant_archetypes": "Dragapult ex", "strategic_role": "mobility/pivot role", "competition_present": 1, "notes": "Local rule-anchor mapping.", "archetypes": [("ARC-003", "pivot")]},
    {"id": "CARD-0235", "canonical_card_id": "235", "name": "Budew", "card_type": "Pokemon", "relevant_archetypes": "Dragapult ex", "strategic_role": "early utility and tempo option", "competition_present": 1, "notes": "Local rule-anchor mapping.", "archetypes": [("ARC-003", "utility")]},
    {"id": "CARD-0265", "canonical_card_id": "265", "name": "Iono's Voltorb", "card_type": "Pokemon", "relevant_archetypes": "Iono", "strategic_role": "basic evolution-line setup", "competition_present": 1, "notes": "Local rule-anchor mapping.", "archetypes": [("ARC-004", "evolution-line")]},
    {"id": "CARD-0268", "canonical_card_id": "268", "name": "Tadbulb", "card_type": "Pokemon", "relevant_archetypes": "Iono", "strategic_role": "basic evolution-line setup", "competition_present": 1, "notes": "Local rule-anchor mapping.", "archetypes": [("ARC-004", "evolution-line")]},
    {"id": "CARD-0269", "canonical_card_id": "269", "name": "Bellibolt ex", "card_type": "Pokemon", "relevant_archetypes": "Iono", "strategic_role": "main attacker and engine", "competition_present": 1, "notes": "Local rule-anchor mapping.", "archetypes": [("ARC-004", "main-attacker")]},
    {"id": "CARD-0270", "canonical_card_id": "270", "name": "Wattrel", "card_type": "Pokemon", "relevant_archetypes": "Iono", "strategic_role": "bench/setup role", "competition_present": 1, "notes": "Local rule-anchor mapping.", "archetypes": [("ARC-004", "setup")]},
    {"id": "CARD-0271", "canonical_card_id": "271", "name": "Kilowattrel", "card_type": "Pokemon", "relevant_archetypes": "Iono", "strategic_role": "evolution-line utility", "competition_present": 1, "notes": "Local rule-anchor mapping.", "archetypes": [("ARC-004", "utility")]},
    {"id": "CARD-0673", "canonical_card_id": "673", "name": "Makuhita", "card_type": "Pokemon", "relevant_archetypes": "Mega Lucario ex", "strategic_role": "one-Prize setup attacker", "competition_present": 1, "notes": "Local rule-anchor mapping.", "archetypes": [("ARC-002", "one-prizer")]},
    {"id": "CARD-0674", "canonical_card_id": "674", "name": "Hariyama", "card_type": "Pokemon", "relevant_archetypes": "Mega Lucario ex", "strategic_role": "one-Prize attacker/tempo", "competition_present": 1, "notes": "Local rule-anchor mapping.", "archetypes": [("ARC-002", "one-prizer")]},
    {"id": "CARD-0675", "canonical_card_id": "675", "name": "Lunatone", "card_type": "Pokemon", "relevant_archetypes": "Mega Lucario ex", "strategic_role": "utility setup", "competition_present": 1, "notes": "Local rule-anchor mapping.", "archetypes": [("ARC-002", "utility")]},
    {"id": "CARD-0676", "canonical_card_id": "676", "name": "Solrock", "card_type": "Pokemon", "relevant_archetypes": "Mega Lucario ex", "strategic_role": "one-Prize opener", "competition_present": 1, "notes": "Local rule-anchor mapping and official strategy source.", "archetypes": [("ARC-002", "one-prizer")]},
    {"id": "CARD-0677", "canonical_card_id": "677", "name": "Riolu", "card_type": "Pokemon", "relevant_archetypes": "Mega Lucario ex", "strategic_role": "Mega Lucario evolution setup", "competition_present": 1, "notes": "Local rule-anchor mapping.", "archetypes": [("ARC-002", "evolution-line")]},
    {"id": "CARD-0678", "canonical_card_id": "678", "name": "Mega Lucario ex", "card_type": "Pokemon", "relevant_archetypes": "Mega Lucario ex", "strategic_role": "main attacker and high-Prize target", "competition_present": 1, "notes": "Local rule-anchor mapping.", "archetypes": [("ARC-002", "main-attacker")]},
    {"id": "CARD-0721", "canonical_card_id": "721", "name": "Kyogre", "card_type": "Pokemon", "relevant_archetypes": "Mega Abomasnow ex", "strategic_role": "secondary attacker/resource branch", "competition_present": 1, "notes": "Exact sample-deck mapping.", "archetypes": [("ARC-001", "secondary-attacker")]},
    {"id": "CARD-0722", "canonical_card_id": "722", "name": "Snover", "card_type": "Pokemon", "relevant_archetypes": "Mega Abomasnow ex", "strategic_role": "main evolution-line setup", "competition_present": 1, "notes": "Exact sample-deck mapping.", "archetypes": [("ARC-001", "evolution-line")]},
    {"id": "CARD-0723", "canonical_card_id": "723", "name": "Mega Abomasnow ex", "card_type": "Pokemon", "relevant_archetypes": "Mega Abomasnow ex", "strategic_role": "main attacker and high-Prize target", "competition_present": 1, "notes": "Exact sample-deck mapping.", "archetypes": [("ARC-001", "main-attacker")]},
    {"id": "CARD-1071", "canonical_card_id": "1071", "name": "Meowth ex", "card_type": "Pokemon", "relevant_archetypes": "CABT mixed", "strategic_role": "engine/attacker interaction", "competition_present": 1, "notes": "Local exact card mapping; use card-table effects for interaction tests."},
    {"id": "CARD-1079", "canonical_card_id": "1079", "name": "Rare Candy", "card_type": "Trainer", "relevant_archetypes": "CABT mixed", "strategic_role": "evolution turn compression", "competition_present": 1, "notes": "Important timing/engine interaction; no full text copied."},
    {"id": "CARD-1080", "canonical_card_id": "1080", "name": "Unfair Stamp", "card_type": "Trainer", "relevant_archetypes": "CABT mixed", "strategic_role": "hand disruption and comeback lever", "competition_present": 1, "notes": "Important risk/hand-quality interaction."},
    {"id": "CARD-1086", "canonical_card_id": "1086", "name": "Buddy-Buddy Poffin", "card_type": "Trainer", "relevant_archetypes": "CABT mixed", "strategic_role": "basic bench development", "competition_present": 1, "notes": "Bench-space and thinning timing candidate."},
    {"id": "CARD-1097", "canonical_card_id": "1097", "name": "Night Stretcher", "card_type": "Trainer", "relevant_archetypes": "CABT mixed", "strategic_role": "recovery and resource conversion", "competition_present": 1, "notes": "Recovery ledger candidate."},
    {"id": "CARD-1102", "canonical_card_id": "1102", "name": "Dusk Ball", "card_type": "Trainer", "relevant_archetypes": "CABT mixed", "strategic_role": "search and prize-check interaction", "competition_present": 1, "notes": "Search sequencing candidate."},
    {"id": "CARD-1110", "canonical_card_id": "1110", "name": "Max Rod", "card_type": "Trainer", "relevant_archetypes": "CABT mixed", "strategic_role": "late-game recovery", "competition_present": 1, "notes": "Do not spend before route feasibility is checked."},
    {"id": "CARD-1118", "canonical_card_id": "1118", "name": "Energy Retrieval", "card_type": "Trainer", "relevant_archetypes": "CABT mixed", "strategic_role": "Energy recovery", "competition_present": 1, "notes": "Resource ledger candidate."},
    {"id": "CARD-1120", "canonical_card_id": "1120", "name": "Crushing Hammer", "card_type": "Trainer", "relevant_archetypes": "CABT mixed", "strategic_role": "opponent Energy denial with variance", "competition_present": 1, "notes": "Risk/variance candidate; exact coin outcome is engine-controlled."},
    {"id": "CARD-1121", "canonical_card_id": "1121", "name": "Ultra Ball", "card_type": "Trainer", "relevant_archetypes": "CABT mixed", "strategic_role": "universal search with discard cost", "competition_present": 1, "notes": "Discard ordering and resource-cost candidate."},
    {"id": "CARD-1123", "canonical_card_id": "1123", "name": "Switch", "card_type": "Trainer", "relevant_archetypes": "CABT mixed", "strategic_role": "mobility and attack sequencing", "competition_present": 1, "notes": "Preserve for retreat/attack chain when required."},
    {"id": "CARD-1126", "canonical_card_id": "1126", "name": "Precious Trolley", "card_type": "Trainer", "relevant_archetypes": "CABT mixed", "strategic_role": "bench development and search", "competition_present": 1, "notes": "Bench-space timing candidate."},
    {"id": "CARD-1141", "canonical_card_id": "1141", "name": "Premium Power Pro", "card_type": "Trainer", "relevant_archetypes": "CABT mixed", "strategic_role": "damage/attack threshold modifier", "competition_present": 1, "notes": "Exact effect must be read from local card table before use."},
    {"id": "CARD-1142", "canonical_card_id": "1142", "name": "Fighting Gong", "card_type": "Trainer", "relevant_archetypes": "Mega Lucario ex", "strategic_role": "Fighting setup/energy support", "competition_present": 1, "notes": "Local card mapping; exact timing is card-table dependent."},
    {"id": "CARD-1156", "canonical_card_id": "1156", "name": "Lucky Helmet", "card_type": "Trainer", "relevant_archetypes": "CABT mixed", "strategic_role": "draw/value tool attachment", "competition_present": 1, "notes": "Attachment opportunity-cost candidate."},
    {"id": "CARD-1158", "canonical_card_id": "1158", "name": "Maximum Belt", "card_type": "ACE SPEC Tool", "relevant_archetypes": "Mega Abomasnow ex", "strategic_role": "damage threshold and Prize-route modifier", "competition_present": 1, "notes": "Exact sample-deck mapping; ACE SPEC is finite and high impact."},
    {"id": "CARD-1159", "canonical_card_id": "1159", "name": "Hero's Cape", "card_type": "Tool", "relevant_archetypes": "CABT mixed", "strategic_role": "HP/liability modifier", "competition_present": 1, "notes": "High-impact attachment and Prize liability interaction."},
    {"id": "CARD-1182", "canonical_card_id": "1182", "name": "Boss's Orders", "card_type": "Supporter", "relevant_archetypes": "CABT mixed", "strategic_role": "gust and target selection", "competition_present": 1, "notes": "Scarce route-conversion resource."},
    {"id": "CARD-1192", "canonical_card_id": "1192", "name": "Carmine", "card_type": "Supporter", "relevant_archetypes": "CABT mixed", "strategic_role": "draw/setup timing", "competition_present": 1, "notes": "Supporter sequencing candidate."},
    {"id": "CARD-1198", "canonical_card_id": "1198", "name": "Crispin", "card_type": "Supporter", "relevant_archetypes": "CABT mixed", "strategic_role": "Energy search/acceleration", "competition_present": 1, "notes": "Resource and information sequencing candidate."},
    {"id": "CARD-1205", "canonical_card_id": "1205", "name": "Cyrano", "card_type": "Supporter", "relevant_archetypes": "Mega Abomasnow ex", "strategic_role": "Pokemon search and setup", "competition_present": 1, "notes": "Exact sample-deck mapping."},
    {"id": "CARD-1210", "canonical_card_id": "1210", "name": "Brock's Scouting", "card_type": "Supporter", "relevant_archetypes": "CABT mixed", "strategic_role": "information/search and route setup", "competition_present": 1, "notes": "Potential prize-check interaction."},
    {"id": "CARD-1227", "canonical_card_id": "1227", "name": "Lillie's Determination", "card_type": "Supporter", "relevant_archetypes": "Mega Abomasnow ex", "strategic_role": "hand reset/draw", "competition_present": 1, "notes": "Exact sample-deck mapping."},
    {"id": "CARD-1235", "canonical_card_id": "1235", "name": "Waitress", "card_type": "Supporter", "relevant_archetypes": "Mega Abomasnow ex", "strategic_role": "draw/setup", "competition_present": 1, "notes": "Exact sample-deck mapping."},
    {"id": "CARD-1252", "canonical_card_id": "1252", "name": "Gravity Mountain", "card_type": "Stadium", "relevant_archetypes": "CABT mixed", "strategic_role": "HP/KO threshold and board-state modifier", "competition_present": 1, "notes": "Stadium timing candidate."},
    {"id": "CARD-1254", "canonical_card_id": "1254", "name": "Levincia", "card_type": "Stadium", "relevant_archetypes": "CABT mixed", "strategic_role": "bench/retreat or engine modifier", "competition_present": 1, "notes": "Exact local effect required."},
    {"id": "CARD-1256", "canonical_card_id": "1256", "name": "Team Rocket's Watchtower", "card_type": "Stadium", "relevant_archetypes": "CABT mixed", "strategic_role": "opponent engine/bench interaction", "competition_present": 1, "notes": "Stadium timing and denial candidate."},
    {"id": "CARD-1262", "canonical_card_id": "1262", "name": "Surfing Beach", "card_type": "Stadium", "relevant_archetypes": "CABT mixed", "strategic_role": "mobility/resource modifier", "competition_present": 1, "notes": "Exact local effect required."},
]


MATCHUPS = [
    {"id": "MU-001", "our_archetype_id": "ARC-001", "opponent_archetype_id": "ARC-003", "seat_or_turn_context": "natural_deployment; going-first/going-second split required", "summary": "Mega Abomasnow versus Dragapult is a high-priority spread/Prize-route hypothesis. Compare direct KO timing, bench liability, and whether the opponent can convert spread before the next attack.", "confidence": "LOW", "tags": ["competition", "mega-abomasnow", "dragapult", "priority"]},
    {"id": "MU-002", "our_archetype_id": "ARC-001", "opponent_archetype_id": "ARC-002", "seat_or_turn_context": "natural_deployment; one-Prize and Mega Lucario lines", "summary": "Mega Abomasnow versus Mega Lucario should be evaluated as a high-Prize target race with possible one-Prize sequencing. Preserve the attack chain and compare 2-2-2 exposure against lower-Prize denial routes.", "confidence": "LOW", "tags": ["competition", "mega-abomasnow", "mega-lucario", "priority"]},
    {"id": "MU-003", "our_archetype_id": "ARC-001", "opponent_archetype_id": "ARC-004", "seat_or_turn_context": "natural_deployment; disruption-sensitive", "summary": "Mega Abomasnow versus Iono requires explicit hand-quality, bench, and Energy-race modelling. Do not assume current Standard disruption advice transfers without exact CABT effects.", "confidence": "LOW", "tags": ["competition", "mega-abomasnow", "iono", "priority"]},
    {"id": "MU-004", "our_archetype_id": "ARC-001", "opponent_archetype_id": "ARC-001", "seat_or_turn_context": "mirror; first-player assignment and setup quality", "summary": "The mirror should be decided by setup consistency, Prize information, first meaningful attack, and which player preserves the stronger next-attacker chain. Exact empirical evaluation is missing.", "confidence": "HYPOTHESIS", "tags": ["competition", "mega-abomasnow", "mirror"]},
    {"id": "MU-005", "our_archetype_id": "ARC-001", "opponent_archetype_id": "ARC-005", "seat_or_turn_context": "natural_deployment; exact teacher list pending", "summary": "Grimmsnarl is represented by exact teacher metadata but detailed cards and action evidence are not yet sufficient for a high-confidence plan. Use general Prize-route and target-denial rules only.", "confidence": "HYPOTHESIS", "tags": ["competition", "mega-abomasnow", "grimmsnarl"]},
    {"id": "MU-006", "our_archetype_id": "ARC-001", "opponent_archetype_id": "ARC-006", "seat_or_turn_context": "natural_deployment; public-meta observation", "summary": "Garchomp is a material public archetype, but its exact local list is unresolved. Treat target priority and Fighting matchup details as experiments, not facts.", "confidence": "HYPOTHESIS", "tags": ["competition", "mega-abomasnow", "garchomp"]},
    {"id": "MU-007", "our_archetype_id": "ARC-001", "opponent_archetype_id": "ARC-008", "seat_or_turn_context": "natural_deployment; public-meta observation", "summary": "Crustle was repeatedly visible early and should be screened for durability and Prize-trade denial. No stable CABT win rate is available.", "confidence": "LOW", "tags": ["competition", "mega-abomasnow", "crustle"]},
    {"id": "MU-008", "our_archetype_id": "ARC-001", "opponent_archetype_id": "ARC-007", "seat_or_turn_context": "natural_deployment; public-meta observation", "summary": "Alakazam is a public matchup target whose unusual attack/bench interactions must be read from the exact card table before rules are promoted.", "confidence": "HYPOTHESIS", "tags": ["competition", "mega-abomasnow", "alakazam"]},
    {"id": "MU-009", "our_archetype_id": "ARC-001", "opponent_archetype_id": "ARC-009", "seat_or_turn_context": "natural_deployment; late-June public snapshot", "summary": "Starmie is a speed/tempo screen target. Compare its first-attack clock against Mega Abomasnow setup and avoid making external Standard assumptions.", "confidence": "HYPOTHESIS", "tags": ["competition", "mega-abomasnow", "starmie"]},
    {"id": "MU-010", "our_archetype_id": "ARC-001", "opponent_archetype_id": "ARC-013", "seat_or_turn_context": "natural_deployment; public-meta observation", "summary": "Archaludon should be tested for high-HP attacker and Energy-threshold pressure; community counter reports are hypothesis evidence only.", "confidence": "HYPOTHESIS", "tags": ["competition", "mega-abomasnow", "archaludon"]},
    {"id": "MU-011", "our_archetype_id": "ARC-001", "opponent_archetype_id": "ARC-012", "seat_or_turn_context": "natural_deployment; public-meta observation", "summary": "Festival Lead is a distinct engine/setup matchup with insufficient exact-list evidence. Evaluate bench denial, setup clock, and target selection.", "confidence": "HYPOTHESIS", "tags": ["competition", "mega-abomasnow", "festival"]},
    {"id": "MU-012", "our_archetype_id": "ARC-001", "opponent_archetype_id": "ARC-016", "seat_or_turn_context": "external Standard transfer test only", "summary": "Mega Lopunny is included only to isolate a transferable healing/prize-race concept; it is explicitly not a CABT matchup until card-pool evidence appears.", "confidence": "LOW", "tags": ["external-standard", "healing", "not-cabt"]},
]


def matchup_plan(
    pid: str,
    matchup_id: str,
    phase: str,
    priority: int,
    condition: str,
    action_or_goal: str,
    rationale: str,
    evidence_strength: str,
    deterministic_rule_candidate: bool,
    claims: list[str],
) -> dict:
    return {
        "id": pid,
        "matchup_id": matchup_id,
        "phase": phase,
        "priority": priority,
        "condition": condition,
        "action_or_goal": action_or_goal,
        "rationale": rationale,
        "evidence_strength": evidence_strength,
        "deterministic_rule_candidate": int(deterministic_rule_candidate),
        "claims": claims,
    }


MATCHUP_PLANS = [
    matchup_plan("MUP-001", "MU-001", "setup", 1, "Opening board has a legal evolution/search line and the opponent's spread line is not yet active.", "Prioritize the least fragile path to the first meaningful attacker while reserving a bench slot for the next attacker.", "Spread matchups punish a slow first turn, but overbenching can supply future targets.", "hypothesis_from_transferable_principles", True, ["CLM-018", "CLM-024", "CLM-041"]),
    matchup_plan("MUP-002", "MU-001", "early", 2, "A direct KO and a spread/bench-damage line are both legal but neither is terminal.", "Compare exact Prize-route distance and opponent retaliation; choose spread only if it creates a reachable follow-up KO before reset/healing.", "Spread is valuable only when it converts into route progress.", "hypothesis_from_external_format_and_general_strategy", True, ["CLM-019", "CLM-040", "CLM-041"]),
    matchup_plan("MUP-003", "MU-001", "mid", 3, "Opponent has a damaged support Pokemon or exposed bench liability and a gust effect is available.", "Prefer the gust target that removes a future attacker or shortens the route, unless it gives the opponent a faster retaliation.", "Gust is a finite route-conversion resource.", "general_principle_only", True, ["CLM-019", "CLM-024", "CLM-025"]),
    matchup_plan("MUP-004", "MU-001", "behind", 4, "Normal Prize race is losing and opponent's next attack is likely.", "Preserve or create a disruption/spread branch that changes the race; do not take a cosmetic damage attack.", "Behind-state play needs a concrete alternate route.", "general_principle_only", True, ["CLM-021", "CLM-039", "CLM-041"]),
    matchup_plan("MUP-005", "MU-002", "setup", 1, "Opponent can reach a Mega Lucario attack before Mega Abomasnow or a backup attacker is ready.", "Value the smallest legal setup sequence that makes the next attacker live; do not spend bench/Recovery resources on non-route pieces.", "Mega-versus-Mega races are decided by attack-chain readiness and Prize exposure.", "hypothesis_from_prize_and_attacker_principles", True, ["CLM-018", "CLM-019", "CLM-027"]),
    matchup_plan("MUP-006", "MU-002", "early", 2, "A one-Prize or support target is available instead of a high-Prize attacker.", "Score the lower-Prize target by resulting route length and retaliation; do not assume the largest target is correct.", "Official Mega Lucario advice demonstrates matchup-dependent one-Prize sequencing.", "one_strong_format-specific_source_plus_transfer", True, ["CLM-019", "CLM-023", "CLM-045"]),
    matchup_plan("MUP-007", "MU-002", "ahead", 3, "Mega Abomasnow has a favourable route but exposed support/bench liabilities.", "Reduce the opponent's gust/retaliation outs before taking a non-terminal high-Prize KO.", "Ahead-state variance reduction and bench management matter more than overkill.", "general_principle_only", True, ["CLM-020", "CLM-024", "CLM-039"]),
    matchup_plan("MUP-008", "MU-003", "setup", 1, "Opponent's public board indicates a Bellibolt/engine development line.", "Preserve the search and Energy sequence that produces a first attacker while tracking disruption-sensitive hand quality.", "The exact CABT disruption effects must be read from legal options; Standard advice cannot substitute.", "local archetype presence plus unresolved card effects", True, ["CLM-031", "CLM-054", "CLM-061"]),
    matchup_plan("MUP-009", "MU-003", "early", 2, "Opponent's engine is exposed and a gust target is available.", "Choose between engine denial and direct attacker KO using route distance and opponent next-attack probability.", "Target selection should remove either a future Prize path or the resource that enables it.", "general principle plus matchup hypothesis", True, ["CLM-019", "CLM-025", "CLM-026"]),
    matchup_plan("MUP-010", "MU-003", "behind", 3, "A hand-reset/disruption line is available but leaves the board without a backup attacker.", "Use disruption only if the resulting opponent outs fall enough to justify the lost setup; otherwise build the next attacker.", "Hand size is not hand quality and disruption has opportunity cost.", "general principle only", True, ["CLM-020", "CLM-031", "CLM-039"]),
    matchup_plan("MUP-011", "MU-004", "setup", 1, "Both players have comparable openings and no forced KO exists.", "Preserve the stronger future attacker/bench role and inspect accessible Prize information before committing.", "Mirror races magnify small setup and Prize-route differences.", "hypothesis", True, ["CLM-022", "CLM-024", "CLM-030"]),
    matchup_plan("MUP-012", "MU-004", "mid", 2, "A direct attack would expose a reciprocal high-Prize KO.", "Compare a lower-Prize or denial line against the immediate damage line.", "A mirror is not automatically a 2-2-2 race.", "hypothesis", True, ["CLM-017", "CLM-019", "CLM-023"]),
    matchup_plan("MUP-013", "MU-005", "early", 1, "Grimmsnarl list identity is unresolved but a legal target is available.", "Apply universal route and next-attacker rules; do not encode a Grimmsnarl-specific card assumption.", "Teacher metadata proves presence, not exact causal strategy.", "metadata_only", False, ["CLM-053", "CLM-061"]),
    matchup_plan("MUP-014", "MU-006", "early", 1, "Garchomp identity is observed but card effects/list are incomplete.", "Collect public evidence and run a controlled screen before assigning Fighting-specific target priorities.", "Public meta labels are insufficient for a deterministic rule.", "observed_presence_only", False, ["CLM-051", "CLM-061"]),
    matchup_plan("MUP-015", "MU-007", "early", 1, "Crustle board develops a durable active or a high-value support engine.", "Measure route distance and KO certainty; preserve gust for the target that changes the future route.", "Public matrix observations can generate a hole hypothesis but not settle the matchup.", "screening_hypothesis", True, ["CLM-019", "CLM-051"]),
    matchup_plan("MUP-016", "MU-008", "early", 1, "Alakazam presents an unusual bench/damage interaction.", "Read the exact local card effect and classify target roles before writing a counter rule.", "Card interaction semantics outrank generic archetype names.", "card-data-gated", False, ["CLM-008", "CLM-054"]),
    matchup_plan("MUP-017", "MU-009", "setup", 1, "Starmie can attack before the sample deck's intended attacker is ready.", "Compare a tempo-preserving setup line against a slower high-ceiling line with explicit first-attack probabilities.", "Fast archetypes change the value of turn compression.", "hypothesis", True, ["CLM-018", "CLM-034", "CLM-061"]),
    matchup_plan("MUP-018", "MU-010", "mid", 1, "Archaludon presents a high-HP/large-resource attacker.", "Track Energy and KO thresholds, then preserve recovery and gust for the route that avoids an unfavorable retaliation.", "High-HP target selection is a resource and Prize problem, not only damage.", "community hypothesis plus transferable principles", True, ["CLM-031", "CLM-042", "CLM-047"]),
    matchup_plan("MUP-019", "MU-011", "setup", 1, "Festival Lead requires multiple support pieces to become threatening.", "Evaluate whether early gust/denial removes its engine or merely spends a resource while the attacker survives.", "Support-target value depends on future route and replacement resources.", "hypothesis", True, ["CLM-019", "CLM-025", "CLM-026"]),
    matchup_plan("MUP-020", "MU-012", "external-only", 1, "An external Standard healing/tank example is used to test a generic feature.", "Treat healing/reset as a possible damage-counter transition, not as a CABT matchup rule.", "This row is a transferability control and must not contaminate competition priors.", "external-format-example", False, ["CLM-040", "CLM-054"]),
]


def decision_rule(
    rid: str,
    name: str,
    decision_context: str,
    priority: int,
    condition_text: str,
    recommended_action_text: str,
    avoid_action_text: str,
    rationale: str,
    inputs_required: str,
    certainty_type: str,
    scope: str,
    exceptions: str,
    conflict_group: str,
    confidence: str,
    claims: list[str],
    tags: list[str],
    implementation_status: str = "research_only",
    empirically_test: bool = True,
) -> dict:
    return {
        "id": rid,
        "name": name,
        "decision_context": decision_context,
        "priority": priority,
        "condition_text": condition_text,
        "recommended_action_text": recommended_action_text,
        "avoid_action_text": avoid_action_text,
        "rationale": rationale,
        "inputs_required": inputs_required,
        "certainty_type": certainty_type,
        "scope": scope,
        "exceptions": exceptions,
        "conflict_group": conflict_group,
        "confidence": confidence,
        "implementation_status": implementation_status,
        "empirically_test": int(empirically_test),
        "claims": claims,
        "tags": tags,
    }


DECISION_RULES = [
    decision_rule("DR-001", "Resolve terminal outcomes first", "every transition", 1, "engine reports terminal win/draw/loss", "Return the terminal result before reading selection-local fields or stale entities.", "Do not inspect or act on a selection after terminal resolution.", "Terminal ordering is an engine contract and prevents stale-state actions.", "terminal status; transition result", "forced", "CABT interface", "None.", "terminal-order", "VERY_HIGH", ["CLM-001", "CLM-048"], ["competition", "terminal"], empirically_test=False),
    decision_rule("DR-002", "Use only current legal options", "selection response", 1, "obs.select is not None", "Score and return unique indexes from the complete current option list, with count/type/legality revalidated at the adapter boundary.", "Never synthesize a tabletop action or truncate options to a fixed prefix.", "CABT legal options are state-dependent and the engine is operational truth.", "selection type; min/max; full option semantics; current observation", "forced", "CABT interface", "Submission fallback may choose a legal option; development should fail closed.", "legality", "VERY_HIGH", ["CLM-002", "CLM-008", "CLM-047", "CLM-060"], ["competition", "actions", "legality"], empirically_test=False),
    decision_rule("DR-003", "Return exact deck only on deck request", "initial deck request", 1, "obs.select is None and request asks for deck", "Return the exact submitted 60-card list in the required order/identifier format.", "Do not return a policy action or mutate the deck per game.", "The deck request is a separate interface branch.", "deck list; deck hash; request identity", "forced", "CABT interface", "Deck freeze requires separate authorization; this rule concerns adapter correctness.", "deck-contract", "VERY_HIGH", ["CLM-003", "CLM-012"], ["competition", "deck", "legality"], empirically_test=False),
    decision_rule("DR-004", "Map the route before a non-terminal KO", "attack/target selection", 2, "candidate action is not a forced terminal win", "Compare immediate prizes, remaining required KOs, attacker sequence, gust needs, and opponent retaliation before choosing the target/attack.", "Do not maximize damage or card text output without scoring the post-KO route.", "The first KO can create or destroy the rest of the Prize plan.", "board; prizes; target Prize value; attacks; Energy; gust; recovery; opponent threats", "deterministic", "universal Pokemon strategy translated to CABT", "Forced KO, terminal attack, or exact matchup override.", "prize-route", "HIGH", ["CLM-017", "CLM-018", "CLM-019", "CLM-023"], ["prize-map", "search", "attack"]),
    decision_rule("DR-005", "Prefer the robust route over nominal immediate value", "target/attack selection", 3, "two lines have immediate value but one uses fewer uncertain pieces and survives more opponent responses", "Choose the shorter/robuster route even when another line takes a larger immediate Prize.", "Do not select the highest immediate Prize solely by value.", "Lower-variance routes can have higher actual win probability.", "route distance; required pieces; hidden-state sensitivity; opponent responses", "probabilistic", "universal, with matchup context", "A high-variance line is correct when behind and it materially increases win probability.", "prize-route", "HIGH", ["CLM-023", "CLM-025", "CLM-039"], ["risk", "prize-map", "probability"]),
    decision_rule("DR-006", "Do not initiate a losing Prize trade", "attack selection", 4, "our next attacker is not ready AND opponent can answer current attacker or produce a faster route", "Develop, disrupt, or take a concrete alternate route instead of a cosmetic KO.", "Avoid starting a chain that hands the opponent a favourable retaliation.", "A KO without follow-up can lose tempo.", "next attacker; opponent KO threat; route distance; alternate win options", "deterministic", "universal guard", "Terminal win, forced KO, or denial of opponent terminal line.", "trade-entry", "HIGH", ["CLM-017", "CLM-018", "CLM-021"], ["prize-map", "tempo", "risk"]),
    decision_rule("DR-007", "Prepare the next attacker", "post-attack setup", 5, "current attack is non-terminal and opponent can take a Prize or strand active next turn", "Bench/evolve the next attacker and attach/retain its required resources before committing to the attack when legal.", "Do not spend the turn on a current attack while leaving no live follow-up.", "Future attack readiness is a resource feature, not an afterthought.", "attacker readiness; Energy; evolution; recovery; bench slots; switch/retreat outs", "deterministic", "universal, exact-deck resource ledger", "Do not delay immediate win or spend a scarce card that makes the next route worse.", "next-attacker", "HIGH", ["CLM-018", "CLM-027", "CLM-024"], ["attackers", "resources", "bench"]),
    decision_rule("DR-008", "Preserve a backup attacker when a trade begins", "bench/attachment", 6, "planned route needs at least two future attacks and only one attacker is currently live", "Allocate Energy/search/bench resources to a backup before starting the trade when the opportunity cost is acceptable.", "Do not concentrate the entire attack chain in a single target that one effect can remove.", "Backup attackers reduce catastrophic response risk.", "attacker count; attached Energy; recovery; opponent gust/KO/spread outs", "heuristic", "universal with deck-specific exceptions", "Concentrate Energy when the attack is terminal or the deck's attack requires it.", "attacker-chain", "HIGH", ["CLM-018", "CLM-027"], ["attackers", "resources", "risk"]),
    decision_rule("DR-009", "Attack after irreversible setup", "turn sequencing", 7, "attack ends the turn and at least one legal setup/search/bench/attachment decision can still change the route", "Complete information-gathering, search, bench, attachment, retreat, and disruption decisions before declaring the attack.", "Do not attack early merely because damage is available.", "Attack is normally the final irreversible action.", "legal action sequence; objective; search results; route evaluation", "deterministic", "universal sequencing", "Forced attack effect or terminal win.", "attack-last", "HIGH", ["CLM-029", "CLM-034"], ["sequencing", "irreversible"]),
    decision_rule("DR-010", "Search before committing when information can change the route", "search/sequence", 8, "a legal search/reveal can change target availability, prize knowledge, or attack feasibility and a later commitment is not terminal", "Perform the informative action first, then rescore all legal commitments.", "Do not discard/bench/attach based on an obsolete pre-search assumption.", "Sequencing is goal- and information-dependent, not fixed.", "search options; reveal semantics; route candidates; card-role ledger", "deterministic", "universal sequencing", "Skip marginal information for a forced terminal line.", "information-first", "HIGH", ["CLM-029", "CLM-030", "CLM-047"], ["sequencing", "information", "search"]),
    decision_rule("DR-011", "Thin only when marginal odds exceed opportunity cost", "search/deck thinning", 9, "search can remove a dead/replaceable card and there is a future draw/disruption decision", "Compare keep-versus-thin finite-deck outs and preserve the search/recovery target if it has future value.", "Do not auto-thin every searchable dead card.", "Thinning improves draws but spending the effect can reduce future route flexibility.", "deck counts; out categories; searchable targets; discard/recovery; future shuffle/disruption", "probabilistic", "universal sequencing", "Thin when the card is dead in all reachable routes and the effect has no relevant opportunity cost.", "thinning", "HIGH", ["CLM-028", "CLM-029", "CLM-055", "CLM-056"], ["sequencing", "probability", "deck"]),
    decision_rule("DR-012", "Update the Prize/resource ledger after every reveal", "search/reveal/discard", 10, "an effect reveals or constrains card identity/location", "Move the card into known deck/hand/board/discard/Prize/inaccessible categories and recompute route feasibility.", "Do not count revealed Prizes or inaccessible copies as live outs.", "Prize information changes the feasible action plan.", "revealed cards; known zone; inaccessible count; recovery effects; route requirements", "deterministic", "public-information belief state", "Unknown cards remain probabilistic; do not infer identity from absence alone.", "ledger", "HIGH", ["CLM-022", "CLM-030", "CLM-031", "CLM-032"], ["belief", "prize-check", "resources"]),
    decision_rule("DR-013", "Spend gust for route conversion", "gust target selection", 11, "multiple legal gust targets exist and gust is not terminal by itself", "Prefer the target that shortens the robust Prize route or removes the opponent's imminent attacker, after scoring the resulting board.", "Avoid gusting solely for highest HP/damage or because the target is easy to KO.", "Gust is scarce and target identity changes the opponent's future options.", "gust count; target Prize value; KO certainty; retaliation; support role; route distance", "deterministic", "universal target selection", "Immediate terminal win or forced response.", "gust", "HIGH", ["CLM-019", "CLM-020", "CLM-024", "CLM-025"], ["gust", "targets", "prize-map"]),
    decision_rule("DR-014", "Prefer threat denial when it changes the route", "target priority", 12, "an opponent support/engine Pokemon enables the next attack or a future forced Prize and can be removed with acceptable cost", "Target the enabling threat if its removal reduces opponent route probability more than taking a larger target.", "Do not chase support damage with no route or threat effect.", "Target value is future capability, not only current HP.", "opponent engine; support role; future attack probability; gust; own route", "probabilistic", "universal with matchup override", "If the threat is replaceable or direct KO is terminal, take the terminal route.", "threat-denial", "HIGH", ["CLM-019", "CLM-025", "CLM-026", "CLM-035"], ["targets", "threats", "belief"]),
    decision_rule("DR-015", "Reserve bench capacity for route-critical roles", "bench placement", 13, "bench has limited slots and current action would add a support/liability not needed by the chosen route", "Do not bench the card unless its immediate consistency/value exceeds its future slot and Prize liability.", "Avoid filling the board automatically or exposing a two-Prize/spread target.", "Bench space is a finite resource with both positive and negative value.", "bench occupancy; role labels; targetability; future attacker requirements; route", "heuristic", "universal with exact-deck exceptions", "A proven engine requirement can justify a full bench.", "bench", "HIGH", ["CLM-024", "CLM-035", "CLM-041"], ["bench", "risk", "prize-map"]),
    decision_rule("DR-016", "Attach for the next attack, not just the current active", "Energy attachment", 14, "current active can attack but future attacker is not at threshold and opponent can remove/retreat the active", "Attach to the highest-value future attacker or preserve the resource for a route-critical effect after comparing retreat/attack feasibility.", "Do not attach to an active that is likely to be KO'd or has no route after attacking.", "Energy is both attack fuel and a recoverable/deniable resource.", "attack costs; attached Energy; recovery; retreat; opponent removal; route", "heuristic", "universal exact-deck ledger", "Current attack is terminal or future attacker cannot be developed.", "energy", "HIGH", ["CLM-006", "CLM-018", "CLM-027", "CLM-031"], ["resources", "energy", "attackers"]),
    decision_rule("DR-017", "Protect irreplaceable resources", "discard/recovery", 15, "candidate discard includes a unique/low-count attacker, Energy, gust, recovery, or evolution piece needed by the route", "Choose a discard that preserves route feasibility; use known dead/replaceable cards first.", "Do not discard an irreplaceable resource to increase hand size or search access without route accounting.", "Card count and recoverability matter more than raw hand size.", "card roles; counts; known Prizes; discard; recovery; route requirements", "deterministic", "universal ledger", "Discarding the card is necessary for a forced terminal line or no alternative exists.", "discard", "HIGH", ["CLM-022", "CLM-027", "CLM-031", "CLM-044"], ["resources", "discard", "prize-check"]),
    decision_rule("DR-018", "Price opponent outs instead of assuming them", "opponent threat evaluation", 16, "opponent response requires one or more hidden cards or a low-probability sequence", "Estimate the response from revealed list/board/discard/hand size/draw engine and preserve multiple worlds when uncertainty is material.", "Do not treat an unseen Boss, Energy, switch, or evolution as certain or impossible.", "Expert play uses capability and likelihood, not hidden-hand certainty.", "opponent archetype prior; revealed cards; discard; hand size; draw/search; known counts", "probabilistic", "public-information belief model", "Logical impossibility can be hard-zero; unknown remains a belief.", "opponent-outs", "HIGH", ["CLM-025", "CLM-026", "CLM-032", "CLM-033"], ["belief", "probability", "threats"]),
    decision_rule("DR-019", "Reduce variance while ahead", "ahead-state planning", 17, "current line is favourable and a lower-variance legal action preserves a winning route", "Reduce immediate opponent outs, preserve recovery/gust, and avoid unnecessary high-variance effects.", "Do not take a flashy line merely for extra damage or Prize margin.", "CABT rewards game outcome, not margin.", "win probability estimate; opponent outs; route robustness; recovery/gust; terminal status", "probabilistic", "universal; test in CABT", "Forced terminal win or no lower-variance line preserves the win.", "risk", "MEDIUM", ["CLM-020", "CLM-039", "CLM-057"], ["risk", "ahead", "evaluation"]),
    decision_rule("DR-020", "Increase variance only to escape a losing state", "behind-state planning", 18, "all low-variance routes have lower win probability and a higher-variance branch creates a concrete winning route", "Choose the branch with the best aggregate win probability, including failure and opponent response, rather than random variance.", "Do not burn resources on a low-probability line that cannot alter the Prize route.", "Behind-state decisions require upside but still need a route model.", "route probabilities; opponent response; outs; resource cost; terminal alternatives", "probabilistic", "universal; test in CABT", "A robust denial route can dominate the high-variance line.", "risk", "MEDIUM", ["CLM-021", "CLM-023", "CLM-039", "CLM-056"], ["risk", "behind", "probability"]),
    decision_rule("DR-021", "Require a complete deck-out proof", "alternate win", 19, "candidate line aims to win by opponent deck-out", "Verify opponent draw obligation, remaining deck, shuffle/recovery, self-deck risk, and alternate win route before prioritizing it.", "Do not infer a deck-out win from a small deck count alone.", "Deck-out is a real win condition but needs a robust route.", "opponent deck count; draw effects; recursion; turn horizon; self-deck; Prize route", "deterministic", "control/mill-capable decks only", "Immediate Prize/board terminal win overrides.", "alternate-win", "HIGH", ["CLM-004", "CLM-038", "CLM-059"], ["deckout", "control", "terminal"]),
    decision_rule("DR-022", "Do not truncate legal options", "adapter/search", 2, "legal option list has more entries than a heuristic prefix size", "Encode and score every legal option and preserve all valid multi-select choices.", "Never use first-N options or silently drop a legal candidate.", "Option completeness is a correctness invariant and matters for rare winning lines.", "full option list; semantic encoding; count constraints", "forced", "CABT interface", "None; performance must be solved by compact scoring/search, not omission.", "option-completeness", "VERY_HIGH", ["CLM-002", "CLM-047"], ["competition", "actions", "legality"], empirically_test=False),
    decision_rule("DR-023", "Keep hidden facts probabilistic", "belief update", 3, "opponent card identity/location is not directly revealed", "Store a weighted set/distribution of legal hypotheses and update it only from public evidence.", "Do not hard-code a guessed hand, deck order, or Prize card as fact.", "Hidden-information decisions require an information set, not omniscience.", "public logs; legal hidden allocations; archetype/list prior; action likelihood", "forced", "CABT public-information actor", "A simulator error/explicit reveal can create a hard fact.", "hidden-belief", "VERY_HIGH", ["CLM-005", "CLM-009", "CLM-032"], ["belief", "hidden-information", "competition"]),
    decision_rule("DR-024", "Allocate hidden cards without replacement", "belief/search", 4, "sampling or determinization proposes opponent deck/hand/Prize worlds", "Generate only worlds consistent with deck counts, revealed cards, and zone lengths; update posterior after public transitions.", "Do not sample independent cards or manually control random outcomes.", "Finite-deck constraints and engine randomness define the legal belief space.", "known counts; zone lengths; revealed cards; card pool; transition observations", "forced", "CABT search/belief", "Approximation may prune particles only with a documented unbiased/robust policy.", "hidden-allocation", "VERY_HIGH", ["CLM-009", "CLM-010", "CLM-055"], ["belief", "probability", "search"]),
    decision_rule("DR-025", "Prefer simulator semantics over tabletop memory", "all card/action decisions", 5, "tabletop rule and current CABT legal options or transition differ", "Follow current engine result and legal option semantics, then create a versioned regression if surprising.", "Do not add an intuitive tabletop action that CABT does not expose.", "The competition is evaluated by the engine, including documented quirks.", "engine version; current legal options; transition result; card table", "forced", "CABT competition", "Verify any suspected engine bug and do not exploit unapproved behavior.", "format-boundary", "VERY_HIGH", ["CLM-001", "CLM-008", "CLM-060"], ["competition", "format", "legality"], empirically_test=False),
    decision_rule("DR-026", "Treat option order as an ablation candidate", "selection scoring", 20, "semantic features are unavailable or a report suggests option index is predictive", "Use option order only as an isolated experiment with permutation control; semantic policy remains the default.", "Do not promote a raw index shortcut from observed correlation.", "Option ordering can reflect engine generation order rather than strategy.", "option index; option semantics; permutation; held-out games", "heuristic", "CABT research-only", "If permutation testing proves stable and causal enough, keep it as a low-level feature with version binding.", "option-order", "MEDIUM", ["CLM-052", "CLM-060"], ["competition", "actions", "experiment"]),
    decision_rule("DR-027", "Dragapult matchup spread gate", "Mega Abomasnow versus Dragapult", 21, "spread attack is available but direct KO or setup line is also available", "Use spread only if exact damage thresholds create a near-term multi-KO or remove the opponent's next attacker before retaliation.", "Do not spread for damage counters that the opponent can reset or convert into a faster Prize route.", "External analysis supports the general spread condition; exact CABT matchup is unresolved.", "exact damage counters; Dragapult bench; healing/reset; route distance; next attacker", "matchup_specific", "ARC-001 versus ARC-003", "Must be validated by controlled natural-deployment games.", "mega-abomasnow-dragapult", "LOW", ["CLM-040", "CLM-041", "CLM-061"], ["matchups", "spread", "mega-abomasnow"]),
    decision_rule("DR-028", "Mega Lucario one-Prize gate", "Mega Abomasnow versus Mega Lucario", 22, "a one-Prize or support target can be taken without losing the Mega Abomasnow setup", "Compare the lower-Prize line against taking Mega Lucario; select lower Prize when it creates a shorter/safer route or denies the next attack.", "Do not assume every Mega matchup is a 2-2-2 race.", "Official Mega Lucario strategy supplies a format-specific one-Prize example; CABT transfer is a hypothesis.", "target Prize value; route distance; attacker readiness; gust; retaliation", "matchup_specific", "ARC-001 versus ARC-002", "Exact CABT effects/list and held-out games required.", "mega-abomasnow-lucario", "LOW", ["CLM-019", "CLM-023", "CLM-045"], ["matchups", "prize-map", "mega-lucario"]),
    decision_rule("DR-029", "Use exact teacher metadata only for provenance", "replay-derived strategy", 6, "teacher has high public rank or positive episode outcome but competence/action alignment is not independently closed", "Use deck identity, seat, module, and alignment metadata for sampling; do not promote observed choices as optimal rules.", "Avoid converting survivorship and selection bias into policy labels.", "Local project evidence explicitly separates metadata consistency from competence.", "teacher metadata; episode version; action alignment; competence status", "forced", "CABT replay evidence", "Promote only after authorized held-out competence evidence.", "teacher-evidence", "VERY_HIGH", ["CLM-014", "CLM-049", "CLM-053", "CLM-058"], ["replays", "evidence", "competition"], empirically_test=False),
    decision_rule("DR-030", "Bind evidence to engine/module version", "research/evaluation", 7, "source, replay, card table, or rule receipt has a version/date field", "Partition or downweight evidence across engine/module/card versions and record the actual asset hash.", "Do not pool old and new behavior as if the contract were unchanged.", "Current status records module changes and meta drift.", "engine/module version; source date; card-table hash; deck hash", "forced", "CABT evidence handling", "If semantic contract is proven invariant, preserve provenance but may pool for universal principles.", "version-binding", "HIGH", ["CLM-011", "CLM-058", "CLM-061"], ["competition", "versioning", "evidence"], empirically_test=False),
    decision_rule("DR-031", "Balance natural seat evaluation", "agent evaluation", 8, "comparing candidate agents under CABT randomness", "Use natural deployment with seat assignment handled by the policy and report balanced seat distributions; keep forced-seat diagnostics separate.", "Seat and internal RNG confounds can bias small matrices.", "Natural deployment estimates the actual competition objective.", "seat assignment; game outcome; engine version; independent games; confidence intervals", "forced", "CABT evaluation", "A diagnostic can force first/second but must not be mixed into the primary estimate.", "evaluation", "VERY_HIGH", ["CLM-010", "CLM-051", "CLM-057", "CLM-058"], ["evaluation", "competition", "probability"], empirically_test=False),
    decision_rule("DR-032", "Evaluate game outcome, not Prize margin", "promotion", 9, "candidate wins more Prizes but has no higher game win/draw probability", "Promote only on approved win/draw/loss and reliability criteria; retain Prize progress as an internal evaluator feature.", "Official competition rating is outcome-based.", "Prevents a proxy objective from selecting the wrong policy.", "game outcome; draws; matchup floors; runtime; confidence intervals", "forced", "CABT competition", "Internal experiments may analyze Prize margin separately.", "evaluation", "VERY_HIGH", ["CLM-057", "CLM-062"], ["evaluation", "competition", "prize-map"], empirically_test=False),
    decision_rule("DR-033", "Use exact card IDs and local effects", "card interaction", 10, "a rule or matchup depends on a named card", "Resolve the local canonical card identifier/effect and create a regression before treating the interaction as executable.", "Do not import Standard/Pocket card text or archetype assumptions silently.", "Format boundaries and simulator semantics are explicit.", "canonical card ID; local card table; engine transition; format scope", "forced", "CABT card research", "A generic strategic principle may survive with low confidence but not a card-specific rule.", "card-semantics", "VERY_HIGH", ["CLM-009", "CLM-011", "CLM-054"], ["cards", "format", "competition"], empirically_test=False),
    decision_rule("DR-034", "Search only after policy competence", "tactical search", 23, "a proposed search layer has no competent base policy or cannot meet CPU/time bounds", "Keep search research-only; first validate a policy and measure search on held-out games with strict latency accounting.", "Do not let search hide representation or opponent-curriculum weakness.", "Local project architecture explicitly gates search after competence.", "base policy; held-out games; CPU time; p99 latency; fallback count", "forced", "project-specific search authorization", "An approved tactical smoke may still test mechanics without promotion.", "search-gate", "VERY_HIGH", ["CLM-007", "CLM-016", "CLM-050"], ["search", "runtime", "evaluation"], empirically_test=False),
    decision_rule("DR-035", "Keep replay observations non-causal", "replay analysis", 11, "a top team repeatedly chooses an action in a public replay sample", "Store the pattern with sample size, version, and inference strength; use it to form a testable hypothesis rather than an optimality rule.", "Do not infer hidden algorithm or causal strategy from timing/wins alone.", "Replay samples are selected and often partially observed.", "episode ID; team/deck; context; action; outcome; sample count; alignment status", "forced", "CABT public replay research", "Independent controlled games can raise confidence but still need causal framing.", "replay-causality", "VERY_HIGH", ["CLM-014", "CLM-049", "CLM-050", "CLM-051", "CLM-053"], ["replays", "evidence", "uncertainty"], empirically_test=False),
    decision_rule("DR-036", "Mark non-CABT evidence explicitly", "source ingestion", 12, "source uses Pocket, older Standard, Expanded, or current external Standard rules/cards", "Store the format scope and use only the transferable principle unless local card/engine evidence confirms direct applicability.", "Do not merge external card legality or metagame frequency into CABT facts.", "Format mismatch is a primary source of strategic errors.", "source format; local card pool; engine version; transferability rationale", "forced", "all imported research", "Official rule or general probability source can remain broadly transferable with scope labels.", "format-boundary", "VERY_HIGH", ["CLM-004", "CLM-054", "CLM-061"], ["format", "sources", "competition"], empirically_test=False),
]


def anti_pattern(
    aid: str,
    name: str,
    condition: str,
    bad_action: str,
    why_bad: str,
    exceptions: str,
    severity: str,
    confidence: str,
    claims: list[str],
    tags: list[str],
) -> dict:
    return {
        "id": aid,
        "name": name,
        "condition": condition,
        "bad_action": bad_action,
        "why_bad": why_bad,
        "exceptions": exceptions,
        "severity": severity,
        "confidence": confidence,
        "claims": claims,
        "tags": tags,
    }


ANTI_PATTERNS = [
    anti_pattern("AP-001", "Start a losing Prize trade", "Current attack is non-terminal, next attacker is not ready, and opponent has a faster credible route.", "Take a cosmetic KO because it is available.", "It gives the opponent initiative and may expose a forced Prize sequence.", "Forced terminal win, unavoidable KO, or attack blocks the opponent's win.", "critical", "HIGH", ["CLM-017", "CLM-018", "CLM-021"], ["prize-map", "risk", "tempo"]),
    anti_pattern("AP-002", "Overbench without role value", "A bench slot is filled by a support/liability not required by the current route.", "Bench every searchable Basic or support Pokemon automatically.", "Creates gust/spread targets and can consume the slot needed for the next attacker.", "Known engine setup requirement or immediate consistency value exceeds exposure.", "high", "HIGH", ["CLM-024", "CLM-035"], ["bench", "risk"]),
    anti_pattern("AP-003", "Spend gust prematurely", "Boss-like effect is available but no route/denial threshold changes.", "Gust the easiest or highest-damage target without comparing post-gust routes.", "Gust is finite and may be needed for a decisive future target.", "Gust is the only winning or terminal line.", "high", "HIGH", ["CLM-019", "CLM-020", "CLM-025"], ["gust", "targets", "prize-map"]),
    anti_pattern("AP-004", "Discard an irreplaceable resource", "A low-count attacker, Energy, recovery, evolution, or gust card is needed by the remaining route.", "Discard it for hand size or generic search value without a route calculation.", "The apparent hand improvement can remove the only future line.", "No alternative exists or discard creates an immediate forced win.", "critical", "HIGH", ["CLM-027", "CLM-031", "CLM-044"], ["resources", "discard"]),
    anti_pattern("AP-005", "Attach to a doomed active", "Active is likely to be KO'd/stranded and future attacker lacks threshold.", "Attach to the active because it can attack now.", "Energy is lost or stranded and the next attack chain fails.", "Current attack is terminal or attachment is required to escape a forced loss.", "high", "HIGH", ["CLM-018", "CLM-027", "CLM-031"], ["energy", "attackers", "risk"]),
    anti_pattern("AP-006", "Retreat without a route", "Retreat costs Energy/switch and no target/attack/Prize improvement follows.", "Retreat merely to move damage or follow an aesthetic preference.", "Consumes mobility and can make the active/next attacker infeasible.", "Retreat prevents a terminal KO, removes a forced liability, or unlocks a better route.", "medium", "MEDIUM", ["CLM-006", "CLM-019", "CLM-031"], ["retreat", "resources", "prize-map"]),
    anti_pattern("AP-007", "Greedy deck thinning", "Search can remove a card but the card/effect has future value or the out improvement is marginal.", "Thin automatically whenever a dead-looking card is searchable.", "It can remove future targets, burn search/shuffle value, or worsen a later hand reset.", "Card is dead in every reachable line and effect has no opportunity cost.", "high", "HIGH", ["CLM-028", "CLM-029", "CLM-055", "CLM-056"], ["sequencing", "deck", "probability"]),
    anti_pattern("AP-008", "Optimize damage instead of route", "A high-damage action does not shorten the remaining Prize/terminal route.", "Choose the biggest number or most damaged target by default.", "Damage without conversion can leave the opponent's best attacker untouched.", "Damage crosses a decisive KO/lock threshold or is terminal.", "high", "HIGH", ["CLM-019", "CLM-041", "CLM-042"], ["damage", "prize-map", "targets"]),
    anti_pattern("AP-009", "Assume a hidden card is present/absent", "Opponent action is consistent with multiple hands/lists.", "Treat an unseen Boss, Energy, switch, evolution, or Prize card as certain.", "It causes brittle decisions and hidden-state strategy fusion.", "Public reveal or logical card-count deduction establishes the fact.", "critical", "VERY_HIGH", ["CLM-005", "CLM-025", "CLM-032", "CLM-033"], ["belief", "hidden-information", "probability"]),
    anti_pattern("AP-010", "Import a different format silently", "Evidence comes from Pocket, older Standard, Expanded, or external 2026 Standard.", "Use card legality, card text, metagame share, or matchup as if it were CABT fact.", "CABT uses a separate card pool and simulator contract.", "Transfer only a clearly universal principle and preserve source scope.", "critical", "VERY_HIGH", ["CLM-001", "CLM-008", "CLM-054", "CLM-061"], ["format", "competition", "sources"]),
    anti_pattern("AP-011", "Use raw option prefix as strategy", "Option index correlates with a report or a few replay samples.", "Always choose option 0/first N without semantic and permutation controls.", "Option generation order can change with engine/version and hides rare legal wins.", "Only as an explicitly isolated, version-bound experiment after ablation.", "high", "MEDIUM", ["CLM-002", "CLM-047", "CLM-052"], ["actions", "competition", "experiment"]),
    anti_pattern("AP-012", "Treat teacher rank as policy proof", "Teacher has strong public rank or positive selected episodes but competence gate is open/blocked.", "Promote replay action patterns as optimal or train on them without authorization.", "Selection bias, draws, version drift, and alignment uncertainty confound the result.", "Independent aligned held-out competence evidence closes the gate.", "critical", "VERY_HIGH", ["CLM-014", "CLM-049", "CLM-053", "CLM-058"], ["replays", "evidence", "teacher"]),
    anti_pattern("AP-013", "Declare deck-out from low deck count", "Opponent deck appears small but recursion, draw obligation, or Prize route is unknown.", "Pivot to mill/stall solely because the opponent has few cards.", "The opponent may shuffle, recover, or win by Prizes first.", "Complete deck-out proof with no faster opponent terminal route.", "high", "HIGH", ["CLM-038", "CLM-059"], ["deckout", "control", "terminal"]),
    anti_pattern("AP-014", "Control randomness manually", "Coin/random outcome is engine-controlled.", "Choose or overwrite a favourable random result during planning/search.", "It violates competition semantics and creates an invalid evaluator.", "Never; only model outcome probabilities or branch on engine results.", "critical", "VERY_HIGH", ["CLM-009", "CLM-010", "CLM-055"], ["probability", "competition", "search"]),
]


def interaction(
    iid: str,
    entity_a: str,
    entity_b: str,
    interaction_type: str,
    description: str,
    strategic_implication: str,
    conditions: str,
    confidence: str,
    claims: list[str],
) -> dict:
    return {
        "id": iid,
        "entity_a": entity_a,
        "entity_b": entity_b,
        "interaction_type": interaction_type,
        "description": description,
        "strategic_implication": strategic_implication,
        "conditions": conditions,
        "confidence": confidence,
        "claims": claims,
    }


INTERACTIONS = [
    interaction("INT-001", "Mega Abomasnow ex", "Maximum Belt", "damage_threshold", "The exact sample deck contains both the main Mega attacker and an ACE SPEC damage/threshold tool.", "Treat the tool as a finite route resource; compare attach-now, preserve-for-later, and Prize-risk branches against exact local attack/HP data.", "Use only after reading local card effects and current board damage.", "MEDIUM", ["CLM-012", "CLM-019", "CLM-042"]),
    interaction("INT-002", "Mega Abomasnow ex", "Kyogre", "attacker_chain", "The sample deck includes a named secondary attacker alongside the Mega evolution line.", "Score Energy split and backup-attacker value rather than assuming every attachment belongs on the main attacker.", "Exact attack costs, recovery, and bench effects must come from local card data.", "LOW", ["CLM-012", "CLM-018", "CLM-027"]),
    interaction("INT-003", "Dragapult evolution line", "spread damage", "matchup_role", "The local Dragapult anchor includes Dreepy/Drakloak/Dragapult ex and public strategy sources describe spread as a route to later multi-KOs.", "Evaluate evolution timing, bench target count, and whether spread converts before retaliation or reset.", "CABT card effects and exact opponent board are required.", "MEDIUM", ["CLM-041", "CLM-061"]),
    interaction("INT-004", "Mega Lucario ex", "Solrock/Hariyama", "prize_trade", "Official Mega Lucario guidance describes one-Prize setup/attack choices against different Prize structures.", "Use one-Prize lines as a candidate route when they deny an easy high-Prize chain, not as a universal opener.", "Exact local list, attack thresholds, and matchup determine the choice.", "MEDIUM", ["CLM-045", "CLM-019", "CLM-023"]),
    interaction("INT-005", "Rare Candy", "evolution timing", "turn_compression", "Rare Candy is a local card of interest because it can change when an evolution line becomes an attacker/engine.", "Search/evolution order must account for whether using it now creates a live attack or merely consumes a route resource.", "Verify exact legal options and local card effect; do not import external wording.", "MEDIUM", ["CLM-011", "CLM-029", "CLM-034"]),
    interaction("INT-006", "Boss's Orders", "bench support", "gust_target", "Boss's Orders converts a finite Supporter into target selection and can expose support or liability Pokemon.", "Score target by Prize route and threat denial; preserve it when no target changes the route.", "Only when the card is legal and the post-gust attack/retreat line is feasible.", "HIGH", ["CLM-019", "CLM-024", "CLM-025"]),
    interaction("INT-007", "Unfair Stamp/Iono", "hand quality", "disruption", "Local hand-disruption cards can change opponent outs, but effect timing and legality are format/engine-dependent.", "Evaluate reduced opponent hand quality as a probability change, not as a guaranteed lock; compare lost setup value.", "Use exact CABT legal options and public card counts.", "MEDIUM", ["CLM-031", "CLM-039", "CLM-054"]),
    interaction("INT-008", "Energy Retrieval/Max Rod/Night Stretcher", "resource ledger", "recovery", "Recovery cards convert discard/known resources back into future attackers and Energy.", "Preserve at least one recovery path when the remaining Prize route depends on finite copies; spend only after checking inaccessible copies.", "Exact target types and counts come from the local card table.", "HIGH", ["CLM-022", "CLM-027", "CLM-031"]),
    interaction("INT-009", "Crushing Hammer", "variance policy", "coin_flip", "Coin-flip Energy denial can improve a losing position but also consumes an action/resource with stochastic value.", "Model both outcomes and use risk policy: more upside behind, less unnecessary variance ahead.", "Engine controls outcome; no manual coin selection.", "MEDIUM", ["CLM-010", "CLM-039", "CLM-055"]),
    interaction("INT-010", "Buddy-Buddy Poffin/Precious Trolley", "bench space", "setup", "Basic search/development effects improve setup but consume deck/search and bench capacity.", "Search the minimum route-critical board before adding optional liabilities; compare thinning gain to bench cost.", "Exact search candidates and bench legality are current-state inputs.", "HIGH", ["CLM-024", "CLM-028", "CLM-047"]),
    interaction("INT-011", "Gravity Mountain", "KO threshold", "stadium_modifier", "A local Stadium can change HP/KO thresholds and therefore target priority.", "Recompute damage and Prize route after Stadium play; do not evaluate target selection from printed HP alone.", "Read exact local effect and account for replacement Stadiums.", "MEDIUM", ["CLM-019", "CLM-042", "CLM-054"]),
    interaction("INT-012", "Search API", "hidden information", "information_contract", "CABT search exposes candidate cards and constrains hidden-zone predictions without exposing opponent private information.", "Treat search as a public information transition and preserve legal hidden allocation; do not infer deck order.", "Current engine version and selection context must be validated.", "VERY_HIGH", ["CLM-009", "CLM-047", "CLM-060"]),
]


def probability_model(
    pid: str,
    name: str,
    description: str,
    formula: str,
    variables: str,
    assumptions: str,
    example: str,
    competition_use: str,
    claims: list[str],
) -> dict:
    return {
        "id": pid,
        "name": name,
        "description": description,
        "formula": formula,
        "variables": variables,
        "assumptions": assumptions,
        "example": example,
        "competition_use": competition_use,
        "claims": claims,
    }


PROBABILITY_MODELS = [
    probability_model("PM-001", "Hypergeometric exact draw", "Probability of seeing exactly k successes when drawing n cards without replacement from a finite deck.", "P(X=k) = C(K,k) * C(N-K,n-k) / C(N,n)", "N=population; K=successes; n=cards seen; k=successes seen.", "Cards are sampled without replacement and card identities/eligibility are known.", "For a 60-card deck, compute the chance of at least one copy after the opening hand plus draw steps.", "Opening consistency and exact-deck out calculation.", ["CLM-055"]),
    probability_model("PM-002", "At least one out", "Complement form for finding one or more copies of a target in a finite draw.", "P(X>=1) = 1 - C(N-K,n) / C(N,n)", "N,K,n as in PM-001.", "All K cards are equally eligible and no search/recycle transition occurs during the draw.", "Use a new N/K state after a search, discard, shuffle, or reveal changes the population.", "Draw/outs feature and route feasibility.", ["CLM-055", "CLM-056"]),
    probability_model("PM-003", "Overlapping combined outs", "Union/set calculation for multiple out categories whose cards overlap or unlock one another.", "P(A union B) = P(A) + P(B) - P(A intersection B); for search chains use state transitions instead of naive addition.", "A/B=event that an out category reaches the target; overlap=cards/effects satisfying both.", "Out definitions are explicit and card effects are resolved in sequence.", "Ultra Ball plus a Basic search card should not be counted as independent copies if one can search the other.", "Avoid overestimating route completion and prioritize legal search graphs.", ["CLM-056"]),
    probability_model("PM-004", "Prize-card exposure", "Prior probability that at least one of K key copies is in six face-down Prizes before public information.", "P(prized>=1) = 1 - C(N-K,6) / C(N,6)", "N=60; K=key copies; six=initial Prize count unless competition contract differs.", "Prizes are a uniformly sampled subset and no card identity has been revealed.", "Recompute after a known copy is in hand/discard/board or a Prize is revealed.", "Initial route robustness and candidate card-count analysis.", ["CLM-004", "CLM-022", "CLM-055"]),
    probability_model("PM-005", "Sequence-completion recursion", "Dynamic without-replacement probability for completing a multi-step route with conditional search and attacks.", "F(state, step) = sum_a P(a | state) * F(next_state(state,a), step+1); terminal success=1, dead route=0.", "state includes counts/zones/resources; a is a legal draw/search/random outcome.", "Transition model exactly matches CABT and random branches are not manually chosen.", "Compute the probability that an evolution, Energy, switch, and gust sequence is live by a specified turn.", "Route ranking and tactical expectimax candidate.", ["CLM-009", "CLM-010", "CLM-055", "CLM-056"]),
    probability_model("PM-006", "Action line expected outcome", "Expected game result for an action across opponent responses and stochastic outcomes, with robustness recorded separately.", "EV(a)=sum_h P(h|public) * sum_o P(o|a,h) * V(transition(a,o,h)); V in [-1,0,1] for loss/draw/win.", "a=action; h=hidden world; o=opponent/random outcome; V=terminal or backed-up value.", "Hidden worlds are legal and weighted; no privileged private input enters the policy.", "Compare a guaranteed 1-Prize KO with a 2-Prize line that needs a gust out and survives fewer opponent worlds.", "Deterministic/search evaluator; weights must be experimentally calibrated, not invented.", ["CLM-025", "CLM-032", "CLM-039", "CLM-057"]),
    probability_model("PM-007", "Belief posterior update", "Bayesian-style update for hidden-world weights after a public observation or opponent action.", "w_i' proportional to w_i * P(observation | h_i); normalize over legal h_i.", "h_i=legal hidden world; w_i=prior weight; observation=public action/effect/absence.", "Likelihood model is explicit; logically impossible worlds receive zero; non-actions are weak evidence unless opportunity was available.", "A missed evolution is evidence against some worlds but does not prove the card is absent.", "Opponent modeling and hidden-state sensitivity.", ["CLM-025", "CLM-026", "CLM-032", "CLM-033"]),
]


def search_feature(
    fid: str,
    name: str,
    description: str,
    direction: str,
    calculation_hint: str,
    scope: str,
    terminal_override: bool,
    confidence: str,
    claims: list[str],
) -> dict:
    return {
        "id": fid,
        "name": name,
        "description": description,
        "direction": direction,
        "calculation_hint": calculation_hint,
        "scope": scope,
        "terminal_override": int(terminal_override),
        "confidence": confidence,
        "claims": claims,
    }


SEARCH_FEATURES = [
    search_feature("SF-001", "prize_map_distance", "Estimated number/identity of future Prizes and required target/attacker transitions to finish.", "minimize", "Enumerate target sequences; penalize inaccessible or low-confidence required pieces.", "all non-terminal states", True, "HIGH", ["CLM-019", "CLM-023"]),
    search_feature("SF-002", "immediate_ko_threat", "Whether the active or a bench target can be KO'd by the opponent on its next legal turn.", "minimize", "Exact damage/HP/attack/target/access calculation from public state and opponent beliefs.", "threat model", True, "HIGH", ["CLM-025", "CLM-026", "CLM-042"]),
    search_feature("SF-003", "opponent_ko_threat", "Probability/robustness that the opponent can take a decisive Prize or terminal action next turn.", "minimize", "Aggregate legal opponent actions across hidden particles; keep hard terminal threats separate.", "threat model", True, "HIGH", ["CLM-025", "CLM-039"]),
    search_feature("SF-004", "next_attacker_ready", "Readiness of the best future attacker after this action, including Energy/evolution/retreat/search thresholds.", "maximize", "Binary plus distance-to-threshold features; do not reduce to attacker count alone.", "attacker chain", False, "HIGH", ["CLM-018", "CLM-027"]),
    search_feature("SF-005", "backup_attacker_count", "Number and quality of live backup attackers after an opponent response.", "maximize", "Count route-compatible attackers weighted by Energy/recovery/accessibility.", "attacker chain", False, "HIGH", ["CLM-018", "CLM-027"]),
    search_feature("SF-006", "bench_liability", "Expected opponent Prize/target value created by each benched Pokemon.", "minimize", "Combine Prize value, gust access, spread thresholds, and role necessity.", "bench management", False, "HIGH", ["CLM-024", "CLM-035", "CLM-041"]),
    search_feature("SF-007", "gust_coverage", "Number/quality of future target routes enabled by remaining gust effects.", "maximize", "Map each gust copy to legal targets and route reduction; discount unreachable targets.", "resource ledger", False, "HIGH", ["CLM-019", "CLM-025"]),
    search_feature("SF-008", "resource_exhaustion", "Remaining route-critical Energy, recovery, evolution, switch, gust, disruption, and search resources.", "minimize", "Role-aware counts plus recoverability and known Prize/inaccessible status.", "resource ledger", False, "HIGH", ["CLM-022", "CLM-027", "CLM-031"]),
    search_feature("SF-009", "deckout_risk", "Risk that either player reaches a deck-out terminal condition before the planned route.", "minimize", "Track deck count, mandatory draws, recursion/shuffle, and turn horizon.", "alternate-win and long games", True, "HIGH", ["CLM-004", "CLM-038", "CLM-059"]),
    search_feature("SF-010", "expected_outs", "Finite-deck probability of completing a target action/route by the next decision horizon.", "maximize", "Use hypergeometric or transition recursion after updating zone counts.", "draw/search and route completion", False, "HIGH", ["CLM-055", "CLM-056"]),
    search_feature("SF-011", "hidden_state_sensitivity", "Spread of action value across plausible hidden opponent worlds.", "minimize", "Variance/range of V(action,h) across weighted legal particles; do not confuse with EV.", "information-set search", False, "MEDIUM", ["CLM-032", "CLM-033", "CLM-039"]),
    search_feature("SF-012", "turn_compression", "Number and value of required future turns/actions before first attack, next KO, or route completion.", "minimize", "Count legal setup transitions and reward effects that combine steps without sacrificing route robustness.", "setup/tempo", False, "HIGH", ["CLM-016", "CLM-034", "CLM-036"]),
    search_feature("SF-013", "irreversible_commitment", "Whether an action consumes a unique resource, ends the turn, changes target exposure, or removes future options.", "minimize", "Flag attack, discard, retreat, gust, ACE SPEC, and irreversible search choices before branch ordering.", "action sequencing", False, "HIGH", ["CLM-029", "CLM-034", "CLM-031"]),
    search_feature("SF-014", "information_gain", "Expected change in feasible route/action set from a search, reveal, draw, or opponent observation.", "maximize", "Compare posterior route uncertainty before/after public transition minus action opportunity cost.", "sequencing", False, "MEDIUM", ["CLM-029", "CLM-030", "CLM-032"]),
    search_feature("SF-015", "option_order_ablation", "Diagnostic feature recording raw option position separately from semantic action features.", "contextual", "Run option-order permutation and version-stratified held-out evaluation; no default weight.", "competition interface research", False, "MEDIUM", ["CLM-002", "CLM-052"]),
    search_feature("SF-016", "terminal_outcome", "Exact engine terminal win/draw/loss status and game result.", "maximize", "Terminal override before heuristic features; backed-up value in {-1,0,1}.", "all search/evaluation states", True, "VERY_HIGH", ["CLM-048", "CLM-057"]),
]


OBSERVED_REPLAYS = [
    {"id": "OBS-001", "team_or_player": "Public top-ten snapshots", "submission_or_deck": None, "archetype_id": None, "episode_id": None, "decision_context": "June 17-28 2026 visible ladder snapshots", "observation": "Crustle, Iono, Psychic, Mega Lucario, Hop, Grass/Fire/Spread, Starmie, and Archaludon labels appeared at different dates; composition changed quickly.", "action": None, "outcome": None, "pattern_name": "rapid_visible_meta_shift", "frequency_count": 8, "inference_strength": "observed_behavior", "notes": "Selected public snapshots; not a hidden matchmaker distribution."},
    {"id": "OBS-002", "team_or_player": "Public top-100 snapshot", "submission_or_deck": None, "archetype_id": None, "episode_id": None, "decision_context": "June 19 2026 visible top-100", "observation": "Local synthesis estimated fast Fighting about 43%, Psychic 20%, Lightning 19%, sustain 7%, grass 4%, fire 2%, other 5%.", "action": None, "outcome": None, "pattern_name": "selected_top100_composition", "frequency_count": 1, "inference_strength": "observed_behavior", "notes": "Snapshot estimate; archetype labels and sample bias limit use as prior."},
    {"id": "OBS-003", "team_or_player": "Dries @ Tufa Labs", "submission_or_deck": "exact Marnie's Grimmsnarl ex teacher", "archetype_id": "ARC-005", "episode_id": "local-review-e01-dries", "decision_context": "teacher metadata qualification", "observation": "Current rank-1 snapshot and exact deck/action-contract metadata were consistent; competence was not established.", "action": None, "outcome": None, "pattern_name": "teacher_metadata_only", "frequency_count": 128, "inference_strength": "metadata_only", "notes": "Do not infer strategy or optimality."},
    {"id": "OBS-004", "team_or_player": "Luca", "submission_or_deck": "exact Mega Lucario ex teacher", "archetype_id": "ARC-002", "episode_id": "local-review-e01-luca", "decision_context": "teacher metadata qualification", "observation": "Gold-region public rank and exact Mega Lucario deck metadata were retained; no policy competence claim.", "action": None, "outcome": None, "pattern_name": "teacher_metadata_only", "frequency_count": 357, "inference_strength": "metadata_only", "notes": "Selected replay metadata, not representative matchups."},
    {"id": "OBS-005", "team_or_player": "Majkel1337", "submission_or_deck": "exact Mega Lucario ex teacher", "archetype_id": "ARC-002", "episode_id": "local-review-e01-majkel", "decision_context": "teacher probe across opposite seats", "observation": "Two teacher-won exact-deck episodes across opposite seats were observed; 35 active teacher requests and module transition 1.32.2 to 1.32.3 were recorded.", "action": None, "outcome": "2 teacher wins", "pattern_name": "positive_but_noncausal_teacher_sample", "frequency_count": 2, "inference_strength": "metadata_only", "notes": "Small, version-mixed, and not competence proof."},
    {"id": "OBS-006", "team_or_player": "Local replay corpus V3", "submission_or_deck": "public replay metadata", "archetype_id": None, "episode_id": "corpus-v3", "decision_context": "alignment/provenance audit", "observation": "362 episodes and 25,056 action targets were retained for metadata/alignment audit; public actions were not promoted into PPO or strategic truth.", "action": None, "outcome": None, "pattern_name": "alignment_audit_population", "frequency_count": 362, "inference_strength": "metadata_only", "notes": "Exact alignment and authorization remain gating conditions."},
    {"id": "OBS-007", "team_or_player": "Public top-team timing analysis", "submission_or_deck": None, "archetype_id": None, "episode_id": "discussion-724362", "decision_context": "startup/decision-time observations", "observation": "Long startup/decision times were reported in top-team games and used to motivate a search hypothesis; no algorithm identity or causal result was established.", "action": None, "outcome": None, "pattern_name": "timing_search_hypothesis", "frequency_count": 30000, "inference_strength": "inferred_algorithm", "notes": "Timing is an observation; algorithm inference is explicitly unproven."},
    {"id": "OBS-008", "team_or_player": "Public 11-agent matrix", "submission_or_deck": "screening matrix", "archetype_id": None, "episode_id": "discussion-709498", "decision_context": "small matchup screen", "observation": "A public matrix used 550 games across 11 agents and was useful for candidate holes but too small/controlled differently for stable win-rate claims.", "action": None, "outcome": None, "pattern_name": "small_matrix_screen", "frequency_count": 550, "inference_strength": "observed_behavior", "notes": "Use as hypothesis generation only."},
    {"id": "OBS-009", "team_or_player": "Kaggle public meta discussion", "submission_or_deck": None, "archetype_id": None, "episode_id": "discussion-727816", "decision_context": "early July deck selection", "observation": "A participant listed Abomasnow, Lucario, Crustle, Typhlosion, Starmie, Alakazam, then Rocket Mewtwo, Grimmsnarl, Garchomp, and Festival Lead as observed meta families.", "action": None, "outcome": None, "pattern_name": "community_archetype_list", "frequency_count": 1, "inference_strength": "hypothesis", "notes": "Community report; not an unbiased list or official archetype taxonomy."},
    {"id": "OBS-010", "team_or_player": "Public episode access", "submission_or_deck": None, "archetype_id": None, "episode_id": None, "decision_context": "source/replay acquisition", "observation": "Late discussions 729644, 731739, and 731352 were retained as refresh targets because anonymous web access did not expose their full nested text during this pass.", "action": None, "outcome": None, "pattern_name": "unread_discussion_target", "frequency_count": 3, "inference_strength": "metadata_only", "notes": "No strong claim in this database relies on these unresolved pages."},
]


CONTRADICTIONS = [
    {"id": "CON-001", "topic": "Prize trade versus immediate Prize", "claim_a_id": "CLM-017", "claim_b_id": "CLM-023", "reason_for_difference": "Entering a trade can be correct when the race is favourable, while a lower-variance route can be better than a larger immediate Prize.", "likely_resolution": "Evaluate full route and opponent response; neither claim says immediate value is universally wrong/right.", "format_or_matchup_dependency": "matchup, board, and resource state", "unresolved": 1},
    {"id": "CON-002", "topic": "Deck thinning", "claim_a_id": "CLM-028", "claim_b_id": "CLM-029", "reason_for_difference": "Thinning can improve later draws, but sequencing source rejects a fixed auto-thin order.", "likely_resolution": "Use conditional thinning with explicit opportunity cost.", "format_or_matchup_dependency": "deck list, search effects, disruption timing", "unresolved": 1},
    {"id": "CON-003", "topic": "Tabletop action versus CABT legal action", "claim_a_id": "CLM-004", "claim_b_id": "CLM-008", "reason_for_difference": "Tabletop rules describe a general game, while CABT may omit unresolved actions or resolve events differently.", "likely_resolution": "CABT engine/legal option wins for agent behavior; tabletop remains transferable context only.", "format_or_matchup_dependency": "CABT engine version", "unresolved": 0},
    {"id": "CON-004", "topic": "Option order versus semantic legality", "claim_a_id": "CLM-002", "claim_b_id": "CLM-052", "reason_for_difference": "Semantic options define correctness, but raw list position may correlate with engine generation order.", "likely_resolution": "Keep semantic scoring default and test option order under permutation/version controls.", "format_or_matchup_dependency": "engine version, selection type, option permutation", "unresolved": 1},
    {"id": "CON-005", "topic": "Teacher outcome versus competence", "claim_a_id": "CLM-053", "claim_b_id": "CLM-062", "reason_for_difference": "Positive teacher/anchor evidence establishes a research population and exact deck, not a strong policy.", "likely_resolution": "Require held-out games and an authorized competence gate before causal strategy extraction.", "format_or_matchup_dependency": "CABT evaluation and replay provenance", "unresolved": 0},
    {"id": "CON-006", "topic": "External meta versus CABT meta", "claim_a_id": "CLM-054", "claim_b_id": "CLM-061", "reason_for_difference": "Standard tournament popularity can inform a prior, but local CABT archetype presence is a separate observation.", "likely_resolution": "Use external data for transferable principles only; source local prevalence from current CABT evidence.", "format_or_matchup_dependency": "card pool, engine, ladder sampling", "unresolved": 0},
]


RESEARCH_QUESTIONS = [
    {"id": "RQ-001", "question": "What exact CABT engine/module and card-data version will the final competition host use after the July package and before submission?", "priority": "P0", "why_it_matters": "Rules, legal options, card effects, and replay behavior can change with the host version.", "status": "OPEN", "best_current_answer": "Local evidence binds current research to a July official package and records module drift, but final host parity is not proven.", "confidence": "MEDIUM", "next_search_direction": "Refresh official competition package, engine/library hashes, and hosted runtime documentation immediately before packaging.", "claims": ["CLM-011", "CLM-058", "CLM-060"]},
    {"id": "RQ-002", "question": "Is the local 2,022-row/1,267-ID official card table exactly the legal card universe exposed by the hosted CABT service?", "priority": "P0", "why_it_matters": "Every card role, interaction, and deck prior depends on the actual competition pool.", "status": "OPEN", "best_current_answer": "Local card asset is hashed/count-verified; hosted parity remains unverified.", "confidence": "MEDIUM", "next_search_direction": "Compare official hosted card data or legal deck/search observations without copying private assets.", "claims": ["CLM-011", "CLM-054"]},
    {"id": "RQ-003", "question": "What is the current hidden opponent distribution after the final meta shift, rather than the selected public top-episode distribution?", "priority": "P0", "why_it_matters": "Matchup priorities and league sampling can be badly biased by public replay selection.", "status": "OPEN", "best_current_answer": "Only selected public snapshots and rule-anchor populations are available; hidden matchmaker prevalence is unknown.", "confidence": "LOW", "next_search_direction": "Use approved balanced natural-deployment evaluation and current public observations stratified by date/version.", "claims": ["CLM-014", "CLM-015", "CLM-061"]},
    {"id": "RQ-004", "question": "Which Mega Abomasnow Prize routes and first-attacker choices maximize win probability against each native rule anchor under natural deployment?", "priority": "P0", "why_it_matters": "The candidate exact deck needs matchup-specific rules rather than generic card advice.", "status": "OPEN", "best_current_answer": "The database supplies route hypotheses and required features, but no controlled held-out game evidence.", "confidence": "HYPOTHESIS", "next_search_direction": "Run approved exact-deck, seat-balanced, native-engine matchup experiments with raw traces.", "claims": ["CLM-012", "CLM-013", "CLM-019", "CLM-062"]},
    {"id": "RQ-005", "question": "Do prize-map distance, next-attacker readiness, and gust conversion improve held-out CABT games over a simpler rule baseline?", "priority": "P1", "why_it_matters": "These are the highest-value translation candidates and should be validated before adding broad search.", "status": "OPEN", "best_current_answer": "Strong strategic evidence supports the concepts, but no CABT ablation has been run in this research task.", "confidence": "MEDIUM", "next_search_direction": "Implement isolated evaluator ablations in a future authorized engineering phase.", "claims": ["CLM-017", "CLM-018", "CLM-019", "CLM-057"]},
    {"id": "RQ-006", "question": "Is visible option order predictive after semantic-option and permutation controls?", "priority": "P1", "why_it_matters": "A raw index shortcut could appear strong in selected data but fail under engine/version changes.", "status": "OPEN", "best_current_answer": "Community reports motivate the hypothesis; semantic legality remains the default.", "confidence": "LOW", "next_search_direction": "Run option-order permutation and version-stratified held-out evaluation.", "claims": ["CLM-002", "CLM-052"]},
    {"id": "RQ-007", "question": "Which local card interactions involving Rare Candy, evolution effects, recovery, Stadiums, and special Energy differ from tabletop assumptions?", "priority": "P1", "why_it_matters": "A single card-semantic error can invalidate an otherwise good route evaluator.", "status": "OPEN", "best_current_answer": "Local docs identify simulator differences and exact card IDs, but interaction regression coverage is incomplete.", "confidence": "MEDIUM", "next_search_direction": "Build small local engine transition capsules for every route-critical card before promotion.", "claims": ["CLM-008", "CLM-009", "CLM-054"]},
    {"id": "RQ-008", "question": "Does selective tactical search improve held-out game outcomes within the conservative CPU/cumulative-time budget?", "priority": "P1", "why_it_matters": "Search can help tactical choices but can also make the submission slower or brittle.", "status": "OPEN", "best_current_answer": "Search is a gated hypothesis; no policy-competence or search-benefit evidence is established here.", "confidence": "HYPOTHESIS", "next_search_direction": "Measure p50/p95/p99 latency, fallbacks, and balanced held-out wins against a frozen anchor.", "claims": ["CLM-007", "CLM-016", "CLM-050", "CLM-057"]},
    {"id": "RQ-009", "question": "Does a public-information particle belief model improve robust target selection versus a single deterministic opponent guess?", "priority": "P1", "why_it_matters": "Hidden-hand and Prize uncertainty is central to expert target/route decisions.", "status": "OPEN", "best_current_answer": "The information-set translation is principled but untested and must use legal without-replacement worlds.", "confidence": "HYPOTHESIS", "next_search_direction": "Evaluate calibration, hidden-state sensitivity, and held-out matchup outcomes with public-only inputs.", "claims": ["CLM-005", "CLM-009", "CLM-032", "CLM-033"]},
    {"id": "RQ-010", "question": "Do public teacher action patterns transfer to a held-out exact-deck competent policy?", "priority": "P1", "why_it_matters": "Teacher actions could accelerate competence but replay data/action alignment and authorization gates are not closed.", "status": "BLOCKED", "best_current_answer": "No; current evidence supports metadata only and explicitly leaves competence/training unauthorized.", "confidence": "VERY_HIGH", "next_search_direction": "Only after explicit approval, exact alignment closure, provenance isolation, and equal-budget from-scratch control.", "claims": ["CLM-049", "CLM-053", "CLM-062"]},
    {"id": "RQ-011", "question": "Do long-think or startup timing patterns identify state classes where search is beneficial?", "priority": "P2", "why_it_matters": "Timing may help selective search triggers, but causal interpretation is unsafe.", "status": "OPEN", "best_current_answer": "Timing observations motivate a hypothesis only; they do not identify algorithms.", "confidence": "LOW", "next_search_direction": "Join timing with aligned public state and outcome, then test predictive value prospectively.", "claims": ["CLM-050", "CLM-058"]},
    {"id": "RQ-012", "question": "How often do deck-out and denial routes win or avert losses in the exact CABT card pool?", "priority": "P2", "why_it_matters": "The evaluator needs to recognize alternate terminal routes without overvaluing low deck counts.", "status": "OPEN", "best_current_answer": "Rules and strategy sources establish deck-out as a win condition; local frequency is unknown.", "confidence": "MEDIUM", "next_search_direction": "Instrument terminal route labels in controlled games and public traces.", "claims": ["CLM-004", "CLM-038", "CLM-059"]},
    {"id": "RQ-013", "question": "Can public action/board state classify opponent archetypes reliably enough to affect matchup policy without hidden deck access?", "priority": "P2", "why_it_matters": "Matchup-specific rules need an uncertainty-aware trigger and must not overfit early actions.", "status": "OPEN", "best_current_answer": "Archetype presence is known for several anchors, but classification accuracy and priors are not measured.", "confidence": "LOW", "next_search_direction": "Use aligned, versioned public traces and report calibration/confusion by archetype.", "claims": ["CLM-032", "CLM-033", "CLM-061"]},
    {"id": "RQ-014", "question": "What strategic or runtime information is contained in discussions 729644, 731739, and 731352, including nested replies?", "priority": "P1", "why_it_matters": "User-identified late competition threads may contain current meta/runtime evidence.", "status": "IN_REVIEW", "best_current_answer": "Full text was not exposed by anonymous web access during this refresh, so no material claim relies on them.", "confidence": "LOW", "next_search_direction": "Refresh through an authorized Kaggle session/API and read the complete thread before extraction.", "claims": []},
    {"id": "RQ-015", "question": "What final deadline, submission-count, active-submission, archive-size, and runtime values are currently enforceable?", "priority": "P0", "why_it_matters": "Packaging and evaluation can fail on a stale competition contract.", "status": "OPEN", "best_current_answer": "Local official config records Aug 16 deadline, Aug 9 entry/merger, five submissions/day, two active, and a 202,400 KiB archive ceiling; final recheck is still required.", "confidence": "HIGH", "next_search_direction": "Re-read official overview/rules immediately before any submission or package decision.", "claims": ["CLM-001", "CLM-007", "CLM-057"]},
]


TAGS = [
    ("TAG-001", "competition", "CABT-specific facts and interface."),
    ("TAG-002", "format", "Format/version boundary."),
    ("TAG-003", "rules", "Game rules and terminal conditions."),
    ("TAG-004", "cards", "Card identity/effect research."),
    ("TAG-005", "archetypes", "Deck/archetype identity."),
    ("TAG-006", "matchups", "Matchup-specific strategy."),
    ("TAG-007", "prize-map", "Prize route and target selection."),
    ("TAG-008", "resources", "Resource ledger and opportunity cost."),
    ("TAG-009", "sequencing", "Within-turn action order."),
    ("TAG-010", "bench", "Bench-space and liability."),
    ("TAG-011", "attackers", "Attacker chain and Energy readiness."),
    ("TAG-012", "gust", "Gust/target conversion."),
    ("TAG-013", "belief", "Hidden-information belief state."),
    ("TAG-014", "hidden-information", "Unknown opponent state."),
    ("TAG-015", "probability", "Finite-deck and stochastic reasoning."),
    ("TAG-016", "outs", "Search/draw outs."),
    ("TAG-017", "risk", "Variance and robustness."),
    ("TAG-018", "deckout", "Deck-out terminal route."),
    ("TAG-019", "control", "Denial/control plan."),
    ("TAG-020", "spread", "Spread/damage-counter planning."),
    ("TAG-021", "search", "Tactical search and route evaluation."),
    ("TAG-022", "runtime", "Inference/search runtime."),
    ("TAG-023", "evaluation", "Outcome and evidence evaluation."),
    ("TAG-024", "replays", "Replay-derived observations."),
    ("TAG-025", "evidence", "Provenance and causal limits."),
    ("TAG-026", "elite", "Elite-player decision evidence."),
    ("TAG-027", "external-standard", "External Standard-only evidence."),
    ("TAG-028", "not-cabt", "Explicitly not competition-equivalent."),
    ("TAG-029", "teacher", "Teacher metadata/evidence."),
    ("TAG-030", "experiment", "Experiment candidate."),
    ("TAG-031", "terminal", "Terminal result and win condition."),
    ("TAG-032", "legality", "Legal action/deck constraints."),
    ("TAG-033", "versioning", "Engine/module/date binding."),
    ("TAG-034", "uncertainty", "Unresolved or probabilistic evidence."),
    ("TAG-035", "actions", "Action selection and semantic option handling."),
    ("TAG-036", "ahead", "Playing from a favourable state."),
    ("TAG-037", "alakazam", "Alakazam public-meta archetype."),
    ("TAG-038", "api", "CABT API contract."),
    ("TAG-039", "archaludon", "Archaludon public-meta archetype."),
    ("TAG-040", "attack", "Attack choice and timing."),
    ("TAG-041", "behind", "Playing from a losing state."),
    ("TAG-042", "candidate", "Candidate deck or research target."),
    ("TAG-043", "crustle", "Crustle public-meta archetype."),
    ("TAG-044", "damage", "Damage counters and KO thresholds."),
    ("TAG-045", "data", "Data/replay provenance."),
    ("TAG-046", "deck", "Deck identity and card counts."),
    ("TAG-047", "discard", "Discard ordering and costs."),
    ("TAG-048", "disruption", "Hand/board/resource disruption."),
    ("TAG-049", "dragapult", "Dragapult public/anchor archetype."),
    ("TAG-050", "energy", "Energy attachment and recovery."),
    ("TAG-051", "evolution", "Evolution timing and line readiness."),
    ("TAG-052", "festival", "Festival Lead public-meta archetype."),
    ("TAG-053", "garchomp", "Cynthia's Garchomp public-meta archetype."),
    ("TAG-054", "grimmsnarl", "Marnie's Grimmsnarl teacher archetype."),
    ("TAG-055", "healing", "Healing/reset damage interaction."),
    ("TAG-056", "hop", "Hop public-meta archetype."),
    ("TAG-057", "information", "Information-gathering and value of information."),
    ("TAG-058", "iono", "Iono public/anchor archetype."),
    ("TAG-059", "irreversible", "Irreversible action/commitment."),
    ("TAG-060", "mega-abomasnow", "Mega Abomasnow candidate/anchor."),
    ("TAG-061", "mega-lucario", "Mega Lucario anchor/teacher archetype."),
    ("TAG-062", "meta", "Observed competition meta."),
    ("TAG-063", "mewtwo", "Team Rocket's Mewtwo public-meta archetype."),
    ("TAG-064", "mirror", "Mirror matchup."),
    ("TAG-065", "not-archetype", "Evaluation label that is not a competitive archetype."),
    ("TAG-066", "opponent-model", "Opponent model and response inference."),
    ("TAG-067", "planning", "Forward planning."),
    ("TAG-068", "priority", "Research or matchup priority."),
    ("TAG-069", "prize-check", "Prize checking and inaccessible-copy ledger."),
    ("TAG-070", "prizes", "Prize cards and win conditions."),
    ("TAG-071", "psychic", "Psychic public-meta label."),
    ("TAG-072", "public-meta", "Publicly observed meta only."),
    ("TAG-073", "rule-anchor", "Native rule-anchor evidence."),
    ("TAG-074", "setup", "Board/setup development."),
    ("TAG-075", "sources", "Source provenance and source scope."),
    ("TAG-076", "specialist", "Exact-deck specialist design."),
    ("TAG-077", "starmie", "Starmie public-meta archetype."),
    ("TAG-078", "tactics", "Tactical search and tactical choice."),
    ("TAG-079", "targets", "Target selection."),
    ("TAG-080", "tempo", "Tempo and initiative."),
    ("TAG-081", "threats", "Threat modeling."),
    ("TAG-082", "turn-order", "Turn order and seat context."),
    ("TAG-083", "typhlosion", "Typhlosion public-meta archetype."),
]


def insert_rows(db: sqlite3.Connection, table: str, columns: list[str], rows: list[tuple]) -> None:
    if not rows:
        return
    marks = ",".join("?" for _ in columns)
    names = ",".join(columns)
    db.executemany(f"INSERT INTO {table} ({names}) VALUES ({marks})", rows)


def build_database() -> dict:
    DB_PATH.unlink(missing_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        source_columns = [
            "id", "url", "canonical_url", "title", "publisher", "author", "source_type",
            "credibility_tier", "published_at", "updated_at", "retrieved_at", "language",
            "format_scope", "competition_specific", "elite_player_id", "notes",
            "content_hash_or_identifier",
        ]
        source_rows = [tuple(item[column] for column in source_columns) for item in SOURCES]
        insert_rows(db, "sources", source_columns, source_rows)

        insert_rows(db, "people", [
            "id", "name", "aliases", "country", "role", "credential_summary",
            "credential_confidence", "evidence_source_id",
        ], PEOPLE)

        insert_rows(db, "tags", ["id", "name", "description"], TAGS)
        tag_id_by_name = {name: tag_id for tag_id, name, _ in TAGS}

        db.execute(
            "INSERT INTO environments (id,name,status,format_scope,description,as_of,source_id) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                "ENV-CABT-2026",
                "Kaggle Pokemon TCG AI Battle / CABT",
                "active_research_contract",
                "CABT competition 2026; not tabletop/Standard/Pocket",
                "Exact local competition environment assembled from official competition material, local engine/API notes, current card data, evaluation contracts, and replay metadata.",
                TODAY,
                "SRC-001",
            ),
        )

        card_count = local_card_count()
        card_id_count = local_card_id_count()
        environment_facts = [
            ("ENV-CABT-2026", "deck_size", "60", "integer", "VERY_HIGH", "SRC-007", "Local engine deck validation."),
            ("ENV-CABT-2026", "initial_prize_count", "6", "integer", "VERY_HIGH", "SRC-019", "Official tabletop rule; CABT result handling still version-bound."),
            ("ENV-CABT-2026", "card_data_rows", str(card_count) if card_count is not None else "unknown", "integer", "VERY_HIGH", "SRC-009", "Local official EN card table data-row count."),
            ("ENV-CABT-2026", "card_data_unique_ids", str(card_id_count) if card_id_count is not None else "unknown", "integer", "VERY_HIGH", "SRC-009", "Unique Card ID count; multiple rows can represent multiple prints/variants."),
            ("ENV-CABT-2026", "card_data_sha256", local_hash("private/assets/official/EN_Card_Data.csv") or "missing", "sha256", "VERY_HIGH", "SRC-009", "Hash of local asset actually present at build time."),
            ("ENV-CABT-2026", "sample_deck_sha256", local_hash("private/assets/official/sample_submission/sample_submission/deck.csv") or "missing", "sha256", "VERY_HIGH", "SRC-010", "Hash of local sample deck actually present at build time."),
            ("ENV-CABT-2026", "sample_deck_archetype", "Mega Abomasnow ex with Kyogre/Snover", "text", "VERY_HIGH", "SRC-010", "Derived from local card-ID mapping; not a strength claim."),
            ("ENV-CABT-2026", "rule_anchor_archetypes", "Dragapult ex; Iono; Mega Abomasnow ex; Mega Lucario ex", "text", "VERY_HIGH", "SRC-012", "Native local rule-anchor population."),
            ("ENV-CABT-2026", "agent_contract", "agent(obs_dict) -> list[int]; obs.select=None requests exact deck; otherwise unique legal option indexes", "text", "VERY_HIGH", "SRC-005", "Current local API contract."),
            ("ENV-CABT-2026", "selection_contract", "Variable legal option lists; complete option set; min/max counts; semantic selection types", "text", "VERY_HIGH", "SRC-006", "Never use a global action vocabulary or option prefix."),
            ("ENV-CABT-2026", "hidden_information", "Opponent hand/deck order/face-down Prizes hidden; public logs/state only", "text", "VERY_HIGH", "SRC-005", "Hidden-world reasoning must remain probabilistic."),
            ("ENV-CABT-2026", "randomness", "Native engine randomness; ordinary Python seed does not establish exact trajectory reproduction", "text", "HIGH", "SRC-007", "Evaluate distributions/invariants rather than paired-seed claims."),
            ("ENV-CABT-2026", "inference_runtime", "CPU-only/no-network/no-GPU; local project uses conservative approximately 1.6 vCPU/8 GiB reserve", "text", "HIGH", "SRC-008", "Final package must be rechecked against current official envelope."),
            ("ENV-CABT-2026", "deadline", "2026-08-16T23:59:00Z", "timestamp", "HIGH", "SRC-008", "Local versioned config; reverify before submission."),
            ("ENV-CABT-2026", "entry_merger_deadline", "2026-08-09T23:59:00Z", "timestamp", "HIGH", "SRC-008", "Local versioned config; reverify before submission."),
            ("ENV-CABT-2026", "submission_policy", "At most five submissions/day; only two newest eligible submissions active/scored", "text", "HIGH", "SRC-008", "Local versioned config; reverify before submission."),
            ("ENV-CABT-2026", "archive_contract", ".tar.gz with main.py and deck.csv at archive root; 202400 KiB exposed ceiling; target below 190 MiB", "text", "HIGH", "SRC-008", "Packaging contract, not strategy evidence."),
            ("ENV-CABT-2026", "promotion_objective", "Win/draw/loss outcome under natural deployment; Prize margin is an internal feature only", "text", "VERY_HIGH", "SRC-001", "Rating/evaluation objective."),
        ]
        insert_rows(db, "environment_facts", [
            "environment_id", "fact_key", "fact_value", "value_type", "confidence", "source_id", "notes",
        ], environment_facts)

        claim_rows = [
            (
                item["id"], item["statement"], item["claim_type"], item["scope"], item["confidence"],
                item["evidence_strength"], item["competition_applicability"], item["format_scope"],
                item["valid_from"], item["valid_to"], item["created_at"], item["justification"],
            )
            for item in CLAIMS
        ]
        insert_rows(db, "claims", [
            "id", "statement", "claim_type", "scope", "confidence", "evidence_strength",
            "competition_applicability", "format_scope", "valid_from", "valid_to", "created_at", "justification",
        ], claim_rows)

        claim_source_rows = [
            (item["id"], evidence["source_id"], evidence["support_type"], evidence["short_excerpt"], evidence["source_location"], None)
            for item in CLAIMS
            for evidence in item["sources"]
        ]
        insert_rows(db, "claim_sources", [
            "claim_id", "source_id", "support_type", "short_excerpt", "source_location", "video_timestamp",
        ], claim_source_rows)
        insert_rows(db, "claim_tags", [
            "claim_id", "tag_id",
        ], [(item["id"], tag_id_by_name[tag]) for item in CLAIMS for tag in item["tags"]])

        strategy_rows = [
            (
                item["id"], item["name"], item["category"], item["description"], item["preconditions"],
                item["recommended_action"], item["rationale"], item["expected_benefit"], item["failure_modes"],
                item["exceptions"], item["deterministic_rule_candidate"], item["search_feature_candidate"],
                item["confidence"], item["competition_relevance"],
            )
            for item in STRATEGIES
        ]
        insert_rows(db, "strategies", [
            "id", "name", "category", "description", "preconditions", "recommended_action", "rationale",
            "expected_benefit", "failure_modes", "exceptions", "deterministic_rule_candidate",
            "search_feature_candidate", "confidence", "competition_relevance",
        ], strategy_rows)
        insert_rows(db, "strategy_evidence", [
            "strategy_id", "claim_id", "relationship",
        ], [(item["id"], claim_id, "derived_from") for item in STRATEGIES for claim_id in item["claims"]])
        insert_rows(db, "strategy_tags", [
            "strategy_id", "tag_id",
        ], [(item["id"], tag_id_by_name[tag]) for item in STRATEGIES for tag in item["tags"]])

        insert_rows(db, "archetypes", [
            "id", "name", "format_scope", "competition_present", "description", "primary_game_plan", "source_confidence",
        ], [(
            item["id"], item["name"], item["format_scope"], item["competition_present"], item["description"],
            item["primary_game_plan"], item["source_confidence"],
        ) for item in ARCHETYPES])
        insert_rows(db, "archetype_tags", [
            "archetype_id", "tag_id",
        ], [(item["id"], tag_id_by_name[tag]) for item in ARCHETYPES for tag in item["tags"]])

        insert_rows(db, "cards", [
            "id", "canonical_card_id", "name", "card_type", "relevant_archetypes", "strategic_role", "competition_present", "notes",
        ], [(
            item["id"], item["canonical_card_id"], item["name"], item["card_type"], item["relevant_archetypes"],
            item["strategic_role"], item["competition_present"], item["notes"],
        ) for item in CARDS])
        archetype_card_rows = [
            (archetype_id, item["id"], relationship)
            for item in CARDS
            for archetype_id, relationship in item.get("archetypes", [])
        ]
        insert_rows(db, "archetype_cards", ["archetype_id", "card_id", "relationship"], archetype_card_rows)

        insert_rows(db, "matchups", [
            "id", "our_archetype_id", "opponent_archetype_id", "seat_or_turn_context", "summary", "confidence",
        ], [(
            item["id"], item["our_archetype_id"], item["opponent_archetype_id"], item["seat_or_turn_context"],
            item["summary"], item["confidence"],
        ) for item in MATCHUPS])
        insert_rows(db, "matchup_tags", [
            "matchup_id", "tag_id",
        ], [(item["id"], tag_id_by_name[tag]) for item in MATCHUPS for tag in item["tags"]])

        insert_rows(db, "matchup_plans", [
            "id", "matchup_id", "phase", "priority", "condition", "action_or_goal", "rationale",
            "evidence_strength", "deterministic_rule_candidate",
        ], [(
            item["id"], item["matchup_id"], item["phase"], item["priority"], item["condition"], item["action_or_goal"],
            item["rationale"], item["evidence_strength"], item["deterministic_rule_candidate"],
        ) for item in MATCHUP_PLANS])
        insert_rows(db, "matchup_plan_claims", [
            "matchup_plan_id", "claim_id", "relationship",
        ], [(item["id"], claim_id, "derived_from") for item in MATCHUP_PLANS for claim_id in item["claims"]])

        insert_rows(db, "decision_rules", [
            "id", "name", "decision_context", "priority", "condition_text", "recommended_action_text",
            "avoid_action_text", "rationale", "inputs_required", "certainty_type", "scope", "exceptions",
            "conflict_group", "confidence", "implementation_status", "empirically_test",
        ], [(
            item["id"], item["name"], item["decision_context"], item["priority"], item["condition_text"],
            item["recommended_action_text"], item["avoid_action_text"], item["rationale"], item["inputs_required"],
            item["certainty_type"], item["scope"], item["exceptions"], item["conflict_group"], item["confidence"],
            item["implementation_status"], item["empirically_test"],
        ) for item in DECISION_RULES])
        insert_rows(db, "decision_rule_claims", [
            "decision_rule_id", "claim_id", "relationship",
        ], [(item["id"], claim_id, "derived_from") for item in DECISION_RULES for claim_id in item["claims"]])
        insert_rows(db, "decision_rule_tags", [
            "decision_rule_id", "tag_id",
        ], [(item["id"], tag_id_by_name[tag]) for item in DECISION_RULES for tag in item["tags"]])

        insert_rows(db, "anti_patterns", [
            "id", "name", "condition", "bad_action", "why_bad", "exceptions", "severity", "confidence",
        ], [(
            item["id"], item["name"], item["condition"], item["bad_action"], item["why_bad"], item["exceptions"],
            item["severity"], item["confidence"],
        ) for item in ANTI_PATTERNS])
        insert_rows(db, "anti_pattern_claims", [
            "anti_pattern_id", "claim_id", "relationship",
        ], [(item["id"], claim_id, "derived_from") for item in ANTI_PATTERNS for claim_id in item["claims"]])

        insert_rows(db, "interactions", [
            "id", "entity_a", "entity_b", "interaction_type", "description", "strategic_implication", "conditions", "confidence",
        ], [(
            item["id"], item["entity_a"], item["entity_b"], item["interaction_type"], item["description"],
            item["strategic_implication"], item["conditions"], item["confidence"],
        ) for item in INTERACTIONS])
        insert_rows(db, "interaction_claims", [
            "interaction_id", "claim_id", "relationship",
        ], [(item["id"], claim_id, "derived_from") for item in INTERACTIONS for claim_id in item["claims"]])

        insert_rows(db, "probability_models", [
            "id", "name", "description", "formula", "variables", "assumptions", "example", "competition_use",
        ], [(
            item["id"], item["name"], item["description"], item["formula"], item["variables"], item["assumptions"],
            item["example"], item["competition_use"],
        ) for item in PROBABILITY_MODELS])
        insert_rows(db, "probability_model_claims", [
            "probability_model_id", "claim_id", "relationship",
        ], [(item["id"], claim_id, "derived_from") for item in PROBABILITY_MODELS for claim_id in item["claims"]])

        insert_rows(db, "search_features", [
            "id", "name", "description", "direction", "calculation_hint", "scope", "terminal_override", "confidence",
        ], [(
            item["id"], item["name"], item["description"], item["direction"], item["calculation_hint"], item["scope"],
            item["terminal_override"], item["confidence"],
        ) for item in SEARCH_FEATURES])
        insert_rows(db, "search_feature_claims", [
            "search_feature_id", "claim_id", "relationship",
        ], [(item["id"], claim_id, "derived_from") for item in SEARCH_FEATURES for claim_id in item["claims"]])

        insert_rows(db, "observed_replay_patterns", [
            "id", "team_or_player", "submission_or_deck", "archetype_id", "episode_id", "decision_context",
            "observation", "action", "outcome", "pattern_name", "frequency_count", "inference_strength", "notes",
        ], [(
            item["id"], item["team_or_player"], item["submission_or_deck"], item["archetype_id"], item["episode_id"],
            item["decision_context"], item["observation"], item["action"], item["outcome"], item["pattern_name"],
            item["frequency_count"], item["inference_strength"], item["notes"],
        ) for item in OBSERVED_REPLAYS])

        insert_rows(db, "contradictions", [
            "id", "topic", "claim_a_id", "claim_b_id", "reason_for_difference", "likely_resolution",
            "format_or_matchup_dependency", "unresolved",
        ], [(
            item["id"], item["topic"], item["claim_a_id"], item["claim_b_id"], item["reason_for_difference"],
            item["likely_resolution"], item["format_or_matchup_dependency"], item["unresolved"],
        ) for item in CONTRADICTIONS])

        insert_rows(db, "research_questions", [
            "id", "question", "priority", "why_it_matters", "status", "best_current_answer", "confidence", "next_search_direction",
        ], [(
            item["id"], item["question"], item["priority"], item["why_it_matters"], item["status"],
            item["best_current_answer"], item["confidence"], item["next_search_direction"],
        ) for item in RESEARCH_QUESTIONS])
        insert_rows(db, "research_question_claims", [
            "research_question_id", "claim_id", "relationship",
        ], [(item["id"], claim_id, "informs") for item in RESEARCH_QUESTIONS for claim_id in item["claims"]])

        # Sources are tagged by evidence domain so later agents can filter before reading claims.
        source_tag_rows = []
        for item in SOURCES:
            if item["competition_specific"]:
                source_tag_rows.append((item["id"], tag_id_by_name["competition"]))
            if "strategy" in item["source_type"] or "analysis" in item["source_type"]:
                source_tag_rows.append((item["id"], tag_id_by_name["sequencing"]))
            if "replay" in item["source_type"] or "meta" in item["source_type"]:
                source_tag_rows.append((item["id"], tag_id_by_name["replays"]))
            if "official" in item["source_type"]:
                source_tag_rows.append((item["id"], tag_id_by_name["rules"]))
            if "Standard" in item["format_scope"] or "Pocket" in item["format_scope"]:
                source_tag_rows.append((item["id"], tag_id_by_name["external-standard"]))
        insert_rows(db, "source_tags", ["source_id", "tag_id"], sorted(set(source_tag_rows)))

        fts_rows = []
        fts_rows.extend(("claim", item["id"], " ".join([item["statement"], item["scope"], item["claim_type"], item["format_scope"], item["justification"]])) for item in CLAIMS)
        fts_rows.extend(("strategy", item["id"], " ".join([item["name"], item["description"], item["preconditions"], item["recommended_action"], item["rationale"], item["exceptions"]])) for item in STRATEGIES)
        fts_rows.extend(("decision_rule", item["id"], " ".join([item["name"], item["decision_context"], item["condition_text"], item["recommended_action_text"], item["avoid_action_text"], item["rationale"], item["scope"]])) for item in DECISION_RULES)
        fts_rows.extend(("anti_pattern", item["id"], " ".join([item["name"], item["condition"], item["bad_action"], item["why_bad"], item["exceptions"]])) for item in ANTI_PATTERNS)
        fts_rows.extend(("matchup_plan", item["id"], " ".join([item["phase"], item["condition"], item["action_or_goal"], item["rationale"]])) for item in MATCHUP_PLANS)
        fts_rows.extend(("research_question", item["id"], " ".join([item["question"], item["why_it_matters"], item["best_current_answer"] or "", item["next_search_direction"]])) for item in RESEARCH_QUESTIONS)
        insert_rows(db, "knowledge_fts", ["entity_type", "entity_id", "text"], fts_rows)

        metadata = {
            "schema_version": "1",
            "database_built_at": TODAY,
            "research_as_of": TODAY,
            "database_purpose": "Evidence-first competitive Pokemon TCG decision knowledge for a deterministic/search-based CABT agent.",
            "source_of_truth": "SQLite rows and provenance links; README is operational only.",
            "format_boundary": "CABT-specific facts are separate from tabletop, Standard, Expanded, Pocket, and external meta evidence.",
            "research_status": "substantial_corpus_open_questions_remain",
        }
        insert_rows(db, "metadata", ["key", "value"], list(metadata.items()))
        db.commit()

        table_names = [
            "sources", "people", "claims", "strategies", "archetypes", "cards", "matchups", "matchup_plans",
            "decision_rules", "anti_patterns", "interactions", "probability_models", "search_features",
            "observed_replay_patterns", "contradictions", "research_questions",
        ]
        counts = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in table_names}
        counts["claim_sources"] = db.execute("SELECT COUNT(*) FROM claim_sources").fetchone()[0]
        counts["knowledge_fts"] = db.execute("SELECT COUNT(*) FROM knowledge_fts").fetchone()[0]
        counts["decision_rule_candidates"] = db.execute("SELECT COUNT(*) FROM decision_rules WHERE empirically_test=1").fetchone()[0]
        counts["search_feature_candidates"] = db.execute("SELECT COUNT(*) FROM search_features").fetchone()[0]
        tier_counts = {row["credibility_tier"]: row["n"] for row in db.execute("SELECT credibility_tier, COUNT(*) AS n FROM sources GROUP BY credibility_tier")}
        player_count = db.execute("SELECT COUNT(*) FROM people WHERE role LIKE '%elite Pokemon TCG%' OR role LIKE '%World Champion%'").fetchone()[0]
        competition_archetypes = db.execute("SELECT COUNT(*) FROM archetypes WHERE competition_present=1").fetchone()[0]
        unresolved_contradictions = db.execute("SELECT COUNT(*) FROM contradictions WHERE unresolved=1").fetchone()[0]

        status = {
            "status": "SUBSTANTIAL_EVIDENCE_CORPUS_WITH_OPEN_P0_QUESTIONS",
            "created_at": TODAY,
            "last_updated_at": TODAY,
            "database": "knowledge_base/ptcg_gold.sqlite",
            "coverage": {
                "exact_competition_format": True,
                "official_rules_mechanics": True,
                "current_competition_decks": "partial_exact_anchors_and_public_meta",
                "top_leaderboard_archetypes": "partial_selected_public_snapshots",
                "candidate_deck": True,
                "turn_sequencing": True,
                "prize_mapping": True,
                "resource_management": True,
                "board_development": True,
                "attack_choice": True,
                "retreat_switch_logic": "general_principles; exact card regression pending",
                "bench_management": True,
                "target_selection": True,
                "evolution_timing": True,
                "supporter_timing": True,
                "hidden_information": True,
                "probability_outs": True,
                "playing_ahead": True,
                "playing_behind": True,
                "matchup_plans": "hypotheses_pending_controlled_games",
                "common_expert_mistakes": True,
                "top_player_strategy": True,
                "important_card_interactions": "prioritized_local_ids; transition regressions pending",
                "deterministic_rule_candidates": True,
                "tactical_search_features": True,
                "contradictions": True,
                "unresolved_questions": True,
            },
            "counts": counts,
            "source_tiers": {tier: tier_counts.get(tier, 0) for tier in ["A", "B", "C", "D"]},
            "elite_players_represented": player_count,
            "important_competition_archetypes": competition_archetypes,
            "unresolved_contradictions": unresolved_contradictions,
            "unresolved_high_priority_questions": [
                {"id": item["id"], "question": item["question"], "priority": item["priority"], "status": item["status"]}
                for item in RESEARCH_QUESTIONS
                if item["priority"] in ("P0", "P1") and item["status"] != "SOLVED"
            ],
            "strongest_actionable_findings": [
                "DR-002", "DR-004", "DR-006", "DR-007", "DR-009", "DR-011", "DR-012", "DR-013", "DR-015", "DR-018",
                "DR-019", "DR-020", "DR-022", "DR-023", "DR-024", "DR-025", "DR-029", "DR-030", "DR-031", "DR-032",
            ],
            "recommended_next_research": [
                "Refresh hosted engine/card/version contract before final packaging.",
                "Run controlled Mega Abomasnow versus four native anchors with natural seat deployment.",
                "Build exact local card-transition regression capsules for route-critical cards.",
                "Ablate prize-route, next-attacker, gust, belief, and option-order features separately.",
                "Revisit user-identified Kaggle discussions through an authorized session and ingest full nested replies.",
            ],
        }
        STATUS_PATH.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"counts": counts, "source_tiers": tier_counts, "status": status["status"]}
    finally:
        db.close()


if __name__ == "__main__":
    print(json.dumps(build_database(), indent=2, sort_keys=True))
