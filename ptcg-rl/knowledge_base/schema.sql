PRAGMA foreign_keys = ON;

CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE environments (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    format_scope TEXT NOT NULL,
    description TEXT NOT NULL,
    as_of TEXT NOT NULL,
    source_id TEXT REFERENCES sources(id)
);

CREATE TABLE environment_facts (
    environment_id TEXT NOT NULL REFERENCES environments(id) ON DELETE CASCADE,
    fact_key TEXT NOT NULL,
    fact_value TEXT NOT NULL,
    value_type TEXT NOT NULL,
    confidence TEXT NOT NULL CHECK (confidence IN ('VERY_HIGH','HIGH','MEDIUM','LOW','HYPOTHESIS')),
    source_id TEXT NOT NULL REFERENCES sources(id),
    notes TEXT,
    PRIMARY KEY (environment_id, fact_key)
);

CREATE TABLE sources (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    canonical_url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    publisher TEXT,
    author TEXT,
    source_type TEXT NOT NULL,
    credibility_tier TEXT NOT NULL CHECK (credibility_tier IN ('A','B','C','D')),
    published_at TEXT,
    updated_at TEXT,
    retrieved_at TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    format_scope TEXT NOT NULL,
    competition_specific INTEGER NOT NULL DEFAULT 0 CHECK (competition_specific IN (0,1)),
    elite_player_id TEXT,
    notes TEXT,
    content_hash_or_identifier TEXT
);

CREATE TABLE people (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    aliases TEXT,
    country TEXT,
    role TEXT NOT NULL,
    credential_summary TEXT,
    credential_confidence TEXT NOT NULL CHECK (credential_confidence IN ('VERY_HIGH','HIGH','MEDIUM','LOW','HYPOTHESIS')),
    evidence_source_id TEXT REFERENCES sources(id)
);

CREATE TABLE claims (
    id TEXT PRIMARY KEY,
    statement TEXT NOT NULL,
    claim_type TEXT NOT NULL,
    scope TEXT NOT NULL,
    confidence TEXT NOT NULL CHECK (confidence IN ('VERY_HIGH','HIGH','MEDIUM','LOW','HYPOTHESIS')),
    evidence_strength TEXT NOT NULL,
    competition_applicability TEXT NOT NULL,
    format_scope TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    created_at TEXT NOT NULL,
    justification TEXT
);

CREATE TABLE claim_sources (
    claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    support_type TEXT NOT NULL CHECK (support_type IN ('supports','contradicts','qualifies','example','primary_rule_evidence')),
    short_excerpt TEXT,
    source_location TEXT,
    video_timestamp TEXT,
    PRIMARY KEY (claim_id, source_id, support_type)
);

CREATE TABLE strategies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    preconditions TEXT NOT NULL,
    recommended_action TEXT NOT NULL,
    rationale TEXT NOT NULL,
    expected_benefit TEXT,
    failure_modes TEXT,
    exceptions TEXT,
    deterministic_rule_candidate INTEGER NOT NULL DEFAULT 0 CHECK (deterministic_rule_candidate IN (0,1)),
    search_feature_candidate INTEGER NOT NULL DEFAULT 0 CHECK (search_feature_candidate IN (0,1)),
    confidence TEXT NOT NULL CHECK (confidence IN ('VERY_HIGH','HIGH','MEDIUM','LOW','HYPOTHESIS')),
    competition_relevance TEXT NOT NULL
);

CREATE TABLE strategy_evidence (
    strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    PRIMARY KEY (strategy_id, claim_id)
);

CREATE TABLE archetypes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    format_scope TEXT NOT NULL,
    competition_present INTEGER NOT NULL CHECK (competition_present IN (0,1)),
    description TEXT NOT NULL,
    primary_game_plan TEXT NOT NULL,
    source_confidence TEXT NOT NULL CHECK (source_confidence IN ('VERY_HIGH','HIGH','MEDIUM','LOW','HYPOTHESIS'))
);

CREATE TABLE cards (
    id TEXT PRIMARY KEY,
    canonical_card_id TEXT,
    name TEXT NOT NULL,
    card_type TEXT NOT NULL,
    relevant_archetypes TEXT,
    strategic_role TEXT NOT NULL,
    competition_present INTEGER NOT NULL CHECK (competition_present IN (0,1)),
    notes TEXT
);

CREATE TABLE archetype_cards (
    archetype_id TEXT NOT NULL REFERENCES archetypes(id) ON DELETE CASCADE,
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    PRIMARY KEY (archetype_id, card_id, relationship)
);

CREATE TABLE matchups (
    id TEXT PRIMARY KEY,
    our_archetype_id TEXT NOT NULL REFERENCES archetypes(id),
    opponent_archetype_id TEXT NOT NULL REFERENCES archetypes(id),
    seat_or_turn_context TEXT NOT NULL,
    summary TEXT NOT NULL,
    confidence TEXT NOT NULL CHECK (confidence IN ('VERY_HIGH','HIGH','MEDIUM','LOW','HYPOTHESIS'))
);

CREATE TABLE matchup_plans (
    id TEXT PRIMARY KEY,
    matchup_id TEXT NOT NULL REFERENCES matchups(id) ON DELETE CASCADE,
    phase TEXT NOT NULL,
    priority INTEGER NOT NULL,
    condition TEXT NOT NULL,
    action_or_goal TEXT NOT NULL,
    rationale TEXT NOT NULL,
    evidence_strength TEXT NOT NULL,
    deterministic_rule_candidate INTEGER NOT NULL CHECK (deterministic_rule_candidate IN (0,1))
);

CREATE TABLE matchup_plan_claims (
    matchup_plan_id TEXT NOT NULL REFERENCES matchup_plans(id) ON DELETE CASCADE,
    claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    PRIMARY KEY (matchup_plan_id, claim_id)
);

CREATE TABLE decision_rules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    decision_context TEXT NOT NULL,
    priority INTEGER NOT NULL,
    condition_text TEXT NOT NULL,
    recommended_action_text TEXT NOT NULL,
    avoid_action_text TEXT,
    rationale TEXT NOT NULL,
    inputs_required TEXT NOT NULL,
    certainty_type TEXT NOT NULL CHECK (certainty_type IN ('forced','deterministic','probabilistic','heuristic','matchup_specific')),
    scope TEXT NOT NULL,
    exceptions TEXT,
    conflict_group TEXT,
    confidence TEXT NOT NULL CHECK (confidence IN ('VERY_HIGH','HIGH','MEDIUM','LOW','HYPOTHESIS')),
    implementation_status TEXT NOT NULL DEFAULT 'research_only',
    empirically_test INTEGER NOT NULL DEFAULT 1 CHECK (empirically_test IN (0,1))
);

CREATE TABLE decision_rule_claims (
    decision_rule_id TEXT NOT NULL REFERENCES decision_rules(id) ON DELETE CASCADE,
    claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    PRIMARY KEY (decision_rule_id, claim_id)
);

CREATE TABLE anti_patterns (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    condition TEXT NOT NULL,
    bad_action TEXT NOT NULL,
    why_bad TEXT NOT NULL,
    exceptions TEXT,
    severity TEXT NOT NULL CHECK (severity IN ('critical','high','medium','low')),
    confidence TEXT NOT NULL CHECK (confidence IN ('VERY_HIGH','HIGH','MEDIUM','LOW','HYPOTHESIS'))
);

CREATE TABLE anti_pattern_claims (
    anti_pattern_id TEXT NOT NULL REFERENCES anti_patterns(id) ON DELETE CASCADE,
    claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    PRIMARY KEY (anti_pattern_id, claim_id)
);

CREATE TABLE interactions (
    id TEXT PRIMARY KEY,
    entity_a TEXT NOT NULL,
    entity_b TEXT NOT NULL,
    interaction_type TEXT NOT NULL,
    description TEXT NOT NULL,
    strategic_implication TEXT NOT NULL,
    conditions TEXT NOT NULL,
    confidence TEXT NOT NULL CHECK (confidence IN ('VERY_HIGH','HIGH','MEDIUM','LOW','HYPOTHESIS'))
);

CREATE TABLE interaction_claims (
    interaction_id TEXT NOT NULL REFERENCES interactions(id) ON DELETE CASCADE,
    claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    PRIMARY KEY (interaction_id, claim_id)
);

CREATE TABLE probability_models (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    formula TEXT NOT NULL,
    variables TEXT NOT NULL,
    assumptions TEXT NOT NULL,
    example TEXT,
    competition_use TEXT NOT NULL
);

CREATE TABLE probability_model_claims (
    probability_model_id TEXT NOT NULL REFERENCES probability_models(id) ON DELETE CASCADE,
    claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    PRIMARY KEY (probability_model_id, claim_id)
);

CREATE TABLE search_features (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('maximize','minimize','contextual')),
    calculation_hint TEXT NOT NULL,
    scope TEXT NOT NULL,
    terminal_override INTEGER NOT NULL DEFAULT 0 CHECK (terminal_override IN (0,1)),
    confidence TEXT NOT NULL CHECK (confidence IN ('VERY_HIGH','HIGH','MEDIUM','LOW','HYPOTHESIS'))
);

CREATE TABLE search_feature_claims (
    search_feature_id TEXT NOT NULL REFERENCES search_features(id) ON DELETE CASCADE,
    claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    PRIMARY KEY (search_feature_id, claim_id)
);

CREATE TABLE observed_replay_patterns (
    id TEXT PRIMARY KEY,
    team_or_player TEXT NOT NULL,
    submission_or_deck TEXT,
    archetype_id TEXT REFERENCES archetypes(id),
    episode_id TEXT,
    decision_context TEXT NOT NULL,
    observation TEXT NOT NULL,
    action TEXT,
    outcome TEXT,
    pattern_name TEXT NOT NULL,
    frequency_count INTEGER,
    inference_strength TEXT NOT NULL CHECK (inference_strength IN ('observed_behavior','metadata_only','inferred_algorithm','hypothesis')),
    notes TEXT
);

CREATE TABLE contradictions (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    claim_a_id TEXT NOT NULL REFERENCES claims(id),
    claim_b_id TEXT NOT NULL REFERENCES claims(id),
    reason_for_difference TEXT NOT NULL,
    likely_resolution TEXT NOT NULL,
    format_or_matchup_dependency TEXT NOT NULL,
    unresolved INTEGER NOT NULL CHECK (unresolved IN (0,1))
);

CREATE TABLE research_questions (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('P0','P1','P2','P3')),
    why_it_matters TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('OPEN','IN_REVIEW','SOLVED','BLOCKED')),
    best_current_answer TEXT,
    confidence TEXT NOT NULL CHECK (confidence IN ('VERY_HIGH','HIGH','MEDIUM','LOW','HYPOTHESIS')),
    next_search_direction TEXT NOT NULL
);

CREATE TABLE research_question_claims (
    research_question_id TEXT NOT NULL REFERENCES research_questions(id) ON DELETE CASCADE,
    claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    PRIMARY KEY (research_question_id, claim_id)
);

CREATE TABLE tags (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE source_tags (
    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    tag_id TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (source_id, tag_id)
);

CREATE TABLE claim_tags (
    claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    tag_id TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (claim_id, tag_id)
);

CREATE TABLE strategy_tags (
    strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    tag_id TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (strategy_id, tag_id)
);

CREATE TABLE archetype_tags (
    archetype_id TEXT NOT NULL REFERENCES archetypes(id) ON DELETE CASCADE,
    tag_id TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (archetype_id, tag_id)
);

CREATE TABLE matchup_tags (
    matchup_id TEXT NOT NULL REFERENCES matchups(id) ON DELETE CASCADE,
    tag_id TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (matchup_id, tag_id)
);

CREATE TABLE decision_rule_tags (
    decision_rule_id TEXT NOT NULL REFERENCES decision_rules(id) ON DELETE CASCADE,
    tag_id TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (decision_rule_id, tag_id)
);

CREATE VIRTUAL TABLE knowledge_fts USING fts5(
    entity_type UNINDEXED,
    entity_id UNINDEXED,
    text,
    tokenize = 'unicode61'
);
