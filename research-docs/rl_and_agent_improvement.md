# RL and Agent Improvement Findings

This is the highest-signal collection of discussion evidence for a learned agent. Unless a line says host/organizer, the result is a participant report. The reports are valuable for experiment design, but they are not controlled benchmarks and many were written before the June 30 engine/runtime update.

## Executive takeaways

- Pure RL is viable enough to test seriously. One participant reports a small pure-RL agent reaching silver after fixing training bugs; another reports a public RL/MCTS sample peaking at 74% in a local rerun. Neither result establishes a final-leaderboard ceiling.
- Search, imitation, and heuristics are not interchangeable with win rate. Several participants saw very high action accuracy but poor head-to-head results, or saw a heuristic beat PPO. That means evaluation must be games against a diverse population, not token/action accuracy.
- The environment already supplies legal variable-size options. A policy over the current option list is more natural than a giant fixed action vocabulary.
- A compact semantic state representation is a major bottleneck. Card IDs alone are poor features; card metadata and zone/instance features matter. One participant reported a transformer/card-identity representation breaking a 73-74% feature ceiling.
- Mirror self-play is unsafe as the only opponent. The strongest reports use a population, historical checkpoints, public rule agents, or matchup-focused exploiters.
- One consistent deck per submission is the intended contract. A fixed-deck specialist is a reasonable first pure-RL target.
- The engine's exact search interface can improve analysis, but hidden-state search must use legal, without-replacement hypotheses and fair coin handling.

## Full-thread findings

### 717697 - Pure RL journey and local training

Source: [Sharing my Reinforcement Learning journey (updated)](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/717697)

The author started without knowing the card game, used a compact board representation and policy, and reports that after about four hours of training the agent beat the top public bots and reached roughly the top 30% of their local comparison. After fixing bugs, the author reports a silver result. This is an encouraging existence proof for pure RL, not a reproducible performance guarantee.

The thread's detailed observations:

- A small pool of about six learned agents plus three public rule agents made a more stable local league than a single mirror opponent.
- The author's generalist was trained across a broad card pool rather than hard-coded to one deck. One report says the top 250 unique cards covered about 95% of observed games, but the same discussion also reports that a local plateau appeared below 800 rating and that ladder transfer was weak.
- Deck variety and exploiters became more important after the agent reached about 700 local Elo. A fixed small deck pool was enough to learn a local equilibrium, but not enough to guarantee robustness.
- A participant reports roughly 7,000 environment steps/second and 45 games/second on a CPU/GPU setup with a model under 2M parameters. This is a throughput report, not a target benchmark.
- A strong local round-robin agent still failed to transfer to Kaggle. Replay review exposed obvious errors: over-attaching energy, missing lethal lines, wasting resources, and losing to deck-out.
- A domain expert argues that behavior cloning from strong episodes can supply game/card competence much cheaper than RL, but that advice is hybrid rather than pure RL.
- The discussion recommends fixed validation opponents, multiple deck archetypes, and replay inspection because later checkpoints and local strength did not always correlate with public rating.

Pure-RL interpretation: begin with a fixed deck and a broad, non-mirror opponent pool; log every terminal loss by tactical category; promote checkpoints from held-out games, not training reward.

### 711644 - PPO, MCTS, and imitation reports

Source: [How has your experience been with RL/PPO/MCTS in this competition so far?](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/711644)

The original author describes a behavior-cloning transformer/value setup and a PPO experiment. The reported numbers are historical and pre-source-release:

- A clone of a Lucario heuristic achieved about 66% exact combination accuracy but only about 10% win rate against the teacher.
- PPO used a mixture of self-play and heuristic opponents, with KL regularization toward a frozen behavior-cloning prior. The reported KL values were 0.01-0.09, and the raw policy reached about 25% against the heuristic without search.
- A small PUCT/MCTS layer using roughly ten rollouts per turn and the policy prior was tried; it was not enough to establish a robust result.

Other replies report imitation accuracy around 85% with weak match results, while another participant reports a Crustle imitation model plus PPO gaining roughly 65 Elo over a rule agent. A different participant abandoned RL/PPO and climbed using a heuristic trained from top-game observations. The consistent lesson is that policy accuracy and model sophistication do not predict win rate by themselves.

The thread also raises implementation questions about dynamic action masking and autoregressive multi-select actions. These are still relevant: each selection must be masked to the current engine options, and a model should not confuse a sequence of options with one flat action.

### 713608 - Large empirical ceiling study

Source: [What We Tried, What Ceilinged, and Two Questions We Can't Answer Alone](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/713608)

This is a participant's long experiment report, not an official benchmark. The most useful findings are:

- The interface returns indices into pre-generated legal options. The author found that returning option 0 was a surprisingly strong baseline in some engine orderings, around 88-90% against random, but reordering options changed performance. Do not hard-code this: use it as evidence that option order carries engine heuristic information and must be measured.
- The author tried 1-ply/2-ply search, ISMCTS, MLP, FSP, demonstration RL, static action reorder, and multiple decks. Many approaches plateaued around the same feature ceiling.
- A card-identity embedding plus a small transformer reportedly broke that ceiling, reaching about 73-74% in the author's evaluation. This does not mean 74% generalizes to the ladder.
- Beam search with width 3 and depth 4 helped a weak Alakazam policy by about 11.3 percentage points but hurt a strong Starmie policy by about 15.4 points. The leaf evaluator and policy quality matter more than adding search blindly.
- Behavior cloning/DAgger reached about 99% action accuracy in one setup while head-to-head performance collapsed to roughly 28-41% of games. Teacher replay coverage and state distribution mismatch are severe.
- A privileged critic performed poorly compared with a public-state critic in one AUC comparison. Hidden information can make value labels noisy when the actor cannot reproduce the critic's state.
- A forensic/LLM guard reduced pooled performance because it was selected on survivorship-biased losses. Every proposed rule or guard needs fresh A/B evaluation.
- The author reports a small root-search gain for some matchups and a large loss for others, reinforcing the need for opponent- and matchup-conditioned search.

Pure-RL interpretation: learn to score the legal options with a semantic state encoder, and treat search as an ablation or fallback. Never conclude that a representation or search change works from action accuracy or one deck matchup.

### 709304 - Public RL/MCTS sample rerun

Source: [Kiyota RL/MCTS sample rerun](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709304)

The participant reran the public Kiyota sample with a small policy/value network and self-play/search. Across five iterations, the reported win rate rose from about 18% to a peak near 74%, then fell near 60%. Checkpoints were saved as model0 through model4. The author explicitly notes that the notebook did not create a complete `main.py`/`deck.csv` submission and that the starter submission itself floated around 250-320 rating.

Use this as a smoke-test curriculum and checkpoint-selection warning:

- early improvement can be real without being robust;
- later training can regress;
- a notebook that beats a local random baseline is not a competition agent;
- every checkpoint needs a fixed, held-out cross-play matrix.

### 712654 and 715572 - Representation and card metadata

Sources: [card2vec](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712654), [attack damage lookup](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/715572)

The card2vec proposal uses an autoencoder over card attributes, compressing roughly 148 attributes to a smaller embedding. The motivation is sound: raw IDs do not provide semantic similarity, while HP, type, stage, costs, effects, and evolution relationships do.

The API answer confirms that attack metadata can be extracted from `all_card_data()` and `all_attack()`. Build the representation from stable semantic fields and a card-ID embedding, then add dynamic instance features:

- zone and owner;
- active/bench position;
- current damage and HP;
- attached energy and tools;
- appeared-this-turn/evolution state;
- visible/revealed/hidden status;
- turn, prizes, deck/hand counts, and once-per-turn flags.

Do not assume an unsupervised card embedding improves win rate. Compare ID-only, metadata-only, and combined encoders under the same opponent matrix.

### 721338 - High-leverage tactical decisions

Source: [How do you teach an agent when to use Boss's Orders and what to discard for Ultra Ball?](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/721338)

Participants describe useful priors, not rules:

- Boss's Orders is usually valuable for a knockout, a stalled high-retreat target, a pre-evolution threat, or an energized target.
- Ultra Ball discards should account for dead, redundant, currently uncastable, or surplus cards, as well as future hand value.
- A useful search policy is to expose only the best one or two discard candidates to deeper evaluation, but let the resulting state value choose among them. Hard-coding one target is brittle.

For pure RL, expose these as state features and let the terminal objective learn the preference. For a hybrid ablation, use them as a bounded candidate generator and measure whether the policy improves against fresh games.

### 711280 - Universal versus deck-specific policy

Source: [Strategy scoring and universal vs deck-specific design](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/711280)

The thread asks whether a universal policy or a deck-specialist policy is more appropriate and does not resolve the question. The related host clarification in [One agent with multiple decks](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/711741) makes a fixed deck per submission the intended format. For a first pure-RL run, specialize the policy and state encoder to one legal deck; only add a deck-conditioning input after a specialist has a stable held-out result.

### 709490, 724637, 709414, and 726696 - Lower-signal strategy threads

- [Previous card-game AI competitions](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709490) points toward rule agents plus search, move ordering, pruning, and lethal detection. It mentions PPO as a plausible learned method but gives no Pokemon-specific benchmark.
- [Mathematical theories](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/724637) asks whether RL/MCTS can discover theories; the thread does not produce an actionable method or result.
- [Rule-based, RL, or agentic RLed?](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709414) is an unanswered question about pure RL and LLM fine-tuning.
- [Heuristic vs RL performance](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/726696) is also an unanswered comparison request.

These threads are included for completeness, but they should not be used as evidence for an algorithm choice.

### 715117 and 709974 - Non-RL reports

Sources: [Japanese no-RL progress](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/715117), [Japanese AI progress](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709974)

One participant reports briefly reaching rank 60 with log analysis and hand-built strategic decisions, including a Crustle/Cornerstone Ogerpon counter and an energyless loss-of-opportunity line. Another reports using an automated PDCA loop and learning a particular attack pattern, reaching a low-hundreds rank. These reports matter because they show how much domain knowledge can lift a simple policy, but they are not evidence against pure RL; they are useful opponents and diagnostic baselines.

## Pure-RL-compatible design implications

If the training objective must remain pure RL, the following keeps the useful lessons without importing labeled actions:

1. Start with one fixed, legal deck and a small number of verified opponents. Add public rule agents, historical checkpoints, and matchup exploiters as the policy improves.
2. Use terminal win/draw/loss as the principal reward. Track prizes, damage, deck count, and resource changes as diagnostics or auxiliary prediction targets; do not let shaped proxy rewards replace the competition objective.
3. Use a masked policy over the current engine options. Encode option semantics, context, target, card metadata, and count rather than learning only an option index.
4. Give the policy recurrent memory over public logs and prior decisions. Hidden information requires belief-like memory even if the actor does not receive privileged state.
5. Compare a simple MLP, a metadata encoder, and a small transformer before increasing network size. The reported feature ceiling makes representation a higher-priority experiment than an elaborate search algorithm.
6. Train against a population rather than a single self-play clone. Track a cross-play matrix and promote checkpoints using held-out games.
7. Add selective engine search only after the policy is competent. Search forced actions and one-option selections zero times; spend budget on attacks, gust/target choices, discard choices, evolution, retreat, and prize-race decisions.
8. Treat action ordering as an input statistic, not a hidden promise. Measure whether option 0 is strong for a given engine version, but never assume that it remains strong after an update.
9. Run memory and timeout soak tests before long rollouts. Keep visualization out of the training loop and make process restart/checkpoint recovery cheap.

## Recommended experiment order

| Stage | Experiment | Keep only if |
| --- | --- | --- |
| 0 | Random legal-option policy and one-option policy | The wrapper passes validation and never emits an invalid selection. |
| 1 | Pure PPO/self-play on one deck | It beats random and weak rule agents on held-out seeds/episodes. |
| 2 | Add a diverse opponent pool | It retains performance against the original opponents and improves cross-play. |
| 3 | Add recurrent public-history memory | It improves hidden-information and long-horizon matchups, not only training reward. |
| 4 | Compare ID-only vs semantic card encoder | The improvement survives deck/opponent holdouts. |
| 5 | Add selective search or action candidate pruning | It improves the weakest matchups within the CPU/time budget. |
| 6 | Package the strongest checkpoint and run a local submission harness | Startup, memory, engine cleanup, and timeout behavior remain stable. |

The most important negative result from the discussions is simple: a higher action-match percentage, a larger model, more MCTS rollouts, or more self-play steps is not itself evidence of a stronger agent.
