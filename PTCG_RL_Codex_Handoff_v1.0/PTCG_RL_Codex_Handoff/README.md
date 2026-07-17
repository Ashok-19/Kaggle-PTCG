# Pokémon TCG AI Battle — RL Gold Project Handoff

Version: 1.0  
Prepared: 2026-07-17  
Target: top 20 / gold medal by the competition close on 2026-08-16 (confirm the exact closing hour and timezone on Kaggle before scheduling final jobs).

This bundle is the execution contract for a local Codex agent. It turns the approved strategy into a gated implementation program. It does **not** contain or redistribute the competition engine, card data, sample agents, credentials, replays, or model checkpoints.

## Start here

1. Read `CODEX_MASTER_PROMPT.md` and paste it into the local Codex session.
2. Give Codex the local paths to:
   - `PTCG.zip` (research notes);
   - `sample-agents.zip`;
   - the current official competition archive/package;
   - any already-downloaded replay data;
   - the new private Git repository or empty project directory.
3. Give Codex the exact local Kaggle MCP tool names and usage when it reaches replay Gate R0. The implementation must keep those details behind a provider interface.
4. Execute one gate at a time. After every gate, fill `templates/PROGRESS_REPORT.md`, attach the raw command output and relevant artifacts, and return them for review.
5. Do not launch the main Modal run until the exact deck and the training system pass the selection and scale-readiness gates.

## Approved strategy in one paragraph

Build one exact-deck recurrent RL specialist. Use a small semantic Entity-Transformer-GRU policy (target roughly 0.8–1.2M parameters; hard ceiling 2M) and a custom synchronous recurrent PPO learner. Score the complete legal option set, handle ordered multi-select decisions autoregressively, and train first against rule agents, then current/frozen self-play with PFSP, then exploiters. Use public replays for meta/deck discovery, debugging, coverage analysis and evaluation design—not as policy action labels. Select the main deck through replay-based discovery, simulator screening and an equal-compute RL bakeoff. Optimize meta-weighted expected match score, defined as `(wins + 0.5 × draws) / games`, subject to hard reliability and catastrophic-matchup constraints; do not invent a blended score.

## Bundle map

| File | Purpose |
|---|---|
| `docs/00_DECISION_RECORD.md` | Fixed decisions, provisional decisions and explicit non-goals |
| `docs/01_MASTER_PLAN.md` | End-to-end phases, gates, calendar and ownership |
| `docs/02_REPOSITORY_ENVIRONMENT.md` | Target repository tree, dependencies, asset bootstrap and reproducibility |
| `docs/03_ENGINE_CONTRACT_TESTS.md` | Engine invariants, action semantics and test gates |
| `docs/04_REPLAY_META_PIPELINE.md` | Incremental, filtered replay extraction and meta analysis |
| `docs/05_DECK_DISCOVERY.md` | Candidate generation, search, RL bakeoff and selection rule |
| `docs/06_MODEL_ACTION_SCHEMA.md` | Observation, recurrence, legal-action decoder and network specification |
| `docs/07_PPO_LEAGUE.md` | Rollouts, recurrent PPO, league/PFSP, exploiters and fallback gates |
| `docs/08_COMPUTE_RUNBOOKS.md` | Local, Colab, Kaggle and Modal roles and commands |
| `docs/09_EVALUATION_SUBMISSION.md` | Match matrices, statistics, checkpoint promotion and ladder policy |
| `docs/10_SCHEDULE_GATES.md` | Calendar through August 16 and review checkpoints |
| `docs/11_RISK_REGISTER.md` | Failure modes, triggers, mitigations and owners |
| `docs/12_FIRST_WEEK_EXECUTION.md` | Exact Day 1–7 implementation queue and acceptance checks |
| `docs/LOCAL_KAGGLE_MCP_NOTES.md` | User/local-Codex worksheet for the real MCP contract |
| `CODEX_MASTER_PROMPT.md` | Copy-paste operating prompt for local Codex |
| `QA_REPORT.md` | Bundle validation results and intentional preflight blockers |
| `configs/*.yaml` | Starting configurations; every real run must snapshot its resolved config |
| `templates/AGENTS.md` | Repository-level instructions for Codex |
| `templates/PROJECT_STATUS.md` | Durable project state/decision log |
| `templates/PROGRESS_REPORT.md` | Required report after every gate/run |
| `templates/.env.example` | Paths and secret names; never put credentials in Git |
| `templates/.gitignore` / `private_file_denylist.txt` | Private/restricted asset safeguards |
| `schemas/run_manifest.schema.json` | Minimum provenance record for every experiment |

## Gate rule

“Implemented” means code plus tests plus evidence. A phase is not complete merely because a command ran. A gate passes only when its acceptance criteria are recorded in `PROJECT_STATUS.md` and its report is returned for review. If evidence contradicts this plan, preserve the raw evidence and change the smallest justified decision—do not conceal the result or silently expand scope.

## Official references

- [Official daily episode index](https://www.kaggle.com/datasets/kaggle/pokemon-tcg-ai-battle-episodes-index)
- [Official KaggleHub client](https://github.com/Kaggle/kagglehub)
- [Competition submission instructions](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/how-to-submit-to-this-competition)
