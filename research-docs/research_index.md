# Pokemon TCG AI Battle Research Index

Research snapshot: 2026-07-16 (Asia/Kolkata)

This folder records the competition information needed before implementing an RL agent. Discussion findings are paraphrased, not quoted. Each linked discussion was fetched through the Kaggle MCP `list_topic_messages` endpoint with old-first ordering and the nested replies recursively read. Organizer/host replies are labeled; everything else is a participant report or an unanswered question.

## Source hierarchy

1. Competition overview pages and competition data are the primary sources for rules, packaging, evaluation, and the engine interface.
2. Kaggle host/organizer replies are the primary source for clarifications that are not in the overview.
3. Participant experiments are useful evidence, but are not guaranteed to reproduce after engine, meta, or runtime changes.

The NVIDIA Kaggle discussion ingest fetched 152 discussion records and 471 comments into its local SQLite cache. The Kaggle MCP topic listing exposed 146 current topics at collection time. The cache and this folder are research artifacts; the competition's card and engine data remain subject to the competition-use-only license.

## Files

| File | Coverage |
| --- | --- |
| [competition_overview.md](competition_overview.md) | Official objective, dates, submission format, scoring, data, and licensing. |
| [game_rules_and_simulator_quirks.md](game_rules_and_simulator_quirks.md) | Game flow, deck legality, observation semantics, and simulator-vs-official-rule differences. |
| [game_engine_and_agent_api.md](game_engine_and_agent_api.md) | Engine source tree, Python wrapper, legal-option contract, search API, runtime, and engine hazards. |
| [rl_and_agent_improvement.md](rl_and_agent_improvement.md) | Full-thread findings about pure RL, PPO, MCTS, imitation, representations, and tactical improvement. |
| [replay_data_and_meta.md](replay_data_and_meta.md) | Public episodes, behavioral-cloning alignment, replay triage, deck/meta observations, and external-data constraints. |
| [submission_evaluation_and_ladder.md](submission_evaluation_and_ladder.md) | Rating noise, active submissions, game rates, timeout behavior, and a practical evaluation protocol. |

## Full-read topic coverage

### RL and agent improvement

- [717697 - Sharing my Reinforcement Learning journey](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/717697)
- [711644 - RL/PPO/MCTS experience](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/711644)
- [713608 - What We Tried, What Ceilinged](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/713608)
- [709414 - Rule-based, RL, or agentic RLed?](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709414)
- [709304 - Kiyota RL/MCTS sample rerun](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709304)
- [726696 - Heuristic vs RL performance](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/726696)
- [712654 - Card2vec embeddings for RL](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712654)
- [715572 - Attack damage lookup](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/715572)
- [721338 - Boss's Orders and Ultra Ball decisions](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/721338)
- [711280 - Universal vs deck-specific agent design](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/711280)
- [709490 - Lessons from previous card-game AI competitions](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709490)
- [724637 - RL/MCTS and mathematical theories](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/724637)
- [715117 - Japanese no-RL progress report](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/715117)
- [709974 - Japanese AI progress](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709974)

### Replay, supervision, and meta

- [712119 - Self-play/human-play logs as external data](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712119)
- [716557 - Episode JSON action/observation alignment](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/716557)
- [717279 - Replay action alignment correction](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/717279)
- [718783 - Replay triage template](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/718783)
- [717832 - Replay log curation](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/717832)
- [709160 - Daily Top Episodes datasets](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709160)
- [724362 - Analysis of 30,000 top-team games](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/724362)
- [709263 - Daily public meta notes](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709263)
- [709554 - Public Top-100 meta snapshot](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709554)
- [709498 - Public matchup matrix](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709498)
- [712011 - Japanese City League deck dataset](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712011)
- [716207 - Archaludon meta counter discoveries](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/716207)
- [712481 - Live meta dashboard and API](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712481)
- [710545 - Replay interpretation question](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/710545)

### Engine, rules, and runtime

- [717141 - Game engine source code](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/717141)
- [711737 - Engine source/reverse-engineering ruling](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/711737)
- [708586 - Official rules vs simulator behavior](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/708586)
- [716045 - Updated simulation environment](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/716045)
- [708810 - Inference environment](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/708810)
- [726708 - Per-game time limit](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/726708)
- [713603 - Game timer](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/713603)
- [709704 - CPU vs GPU runtime](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709704)
- [717698 - Environment speed](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/717698)
- [709152 - libcg.so memory leak](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709152)
- [715644 - search_step error](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/715644)
- [714920 - Deck search observation](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/714920)
- [716241 - Rare Candy engine report](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/716241)
- [712226 - Mirage Barrage report](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712226)
- [709895 - First-player turn-one attack report](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709895)
- [712811 - Unfair Stamp behavior](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712811)
- [726485 - Zero-damage attack report](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/726485)
- [709390 - Revenge KOs](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709390)
- [711741 - One agent with multiple decks](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/711741)

### Submission and evaluation behavior

- [714189 - Simulation competition format reminder](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/714189)
- [712621 - Leaderboard scoring inconsistency](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712621)
- [715251 - Reproducible evaluation loop](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/715251)
- [712657 - Battle simulation matching](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712657)
- [726690 - Episode-rate disparity](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/726690)
- [724904 - Matchmaking question](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/724904)
- [714030 - Infinite move report](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/714030)
- [712893 - Temporary game-rate decrease](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712893)
- [712476 - Keeping an older agent active](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712476)

## Reading caveats

- A strong participant result is evidence to reproduce, not a leaderboard guarantee.
- Several runtime and engine details changed during the competition. The current official overview and engine files take precedence over old comments.
- Public episodes reveal visible play and selection logs; they do not expose the hidden evaluation distribution.
- Do not copy card assets or engine source outside the competition's allowed scope. See [competition_overview.md](competition_overview.md).
