# Submission, Evaluation, and Ladder Behavior

The live ladder is a noisy opponent-sampling system, not a deterministic unit test. Use it for external confirmation after local evaluation, not as the only signal for choosing a checkpoint.

## Official submission behavior

The [Evaluation page](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/evaluation) says:

- The metric is a Gaussian skill/rating estimate initialized around mean 600.
- Outcomes are win, draw, or loss; score margin does not directly improve the result.
- Similar-rated agents are matched where possible.
- A new agent is given a larger uncertainty and its rating should converge with games.
- Up to five submissions are allowed per day.
- Only the most recent two eligible submissions remain active.
- Games continue after the final deadline for about two weeks to allow rating convergence.

The [How to Submit page](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/how-to-submit-to-this-competition) and [Simulation competition format reminder](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/714189) are the operational references. The host said that resubmitting an older agent is required to reactivate it and that a final active pair is used; do not assume an old high-rated agent remains active indefinitely.

## Runtime and timeout

Discussion answers in [Inference environment](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/708810), [Game timer](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/713603), and [per-game time limit](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/726708) report 600 seconds cumulative for an entire game, with no per-move time limit. The inference discussion reports CPU-only execution, approximately 1.6 vCPU and 8 GB RAM.

These values come from discussion answers and should be checked against the current server. Design for a much smaller practical budget because process startup, model loading, native calls, serialization, and long games consume the same wall clock.

[Updated simulation environment](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/716045) says the June 30 update:

- updated the sample/cg libraries;
- added macOS and Linux ARM64 native libraries;
- fixed library loading;
- increased the step limit so infinite loops eventually time out instead of becoming draws;
- preserved existing scores;
- targeted about 48 matches per day per submission and included roughly 10% random-opponent games at that time.

Do not write a policy that intentionally loops. A timeout is a loss-risk, not a draw strategy.

## What the rating discussions imply

### Rating noise is real

[Leaderboard Scoring Inconsistency](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712621) reports identical or near-identical submissions differing by roughly 150-400+ points during early evaluation. The thread attributes much of this to opening hands, turn order, matchup mix, and the small number of games.

[Live rating reproducibility](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/715251) asks for fixed seeds and confidence intervals. The practical answer from the discussion is to build a local benchmark and use broad matchups; the host does not promise a deterministic ladder schedule.

[Battle simulation matching](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712657) contains reports of submissions receiving only a few rounds and then stopping, without a definitive explanation. [Episode-rate disparity](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/726690) reports one higher-ranked group receiving roughly 14-24 episodes/hour while two lower-rate submissions received roughly 2.4/hour. These are observations, not an official episode-rate contract.

[Matchmaking question](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/724904) contains a report of about a 10% random-opponent chance. Combine this with the host update rather than treating any one observed rate as permanent.

### Active-submission management

[Keeping an older agent active](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712476) confirms the operational consequence of the two-active-submission rule: resubmit an older build if it must play again. A new submission's rating can differ from its previous rating because uncertainty and matchmaking are recalculated.

Do not spend all five daily submissions on tiny variations. Use them for deliberately distinct hypotheses: a champion, a challenger, a search/no-search ablation, and a runtime-safe fallback.

## Local evaluation protocol

Use a fixed local harness with the same native engine and wrapper as the submission. The engine does not expose a normal seed hook, so if exact deterministic replay is unavailable, report confidence intervals over repeated stochastic games rather than pretending a single seed is authoritative.

For every checkpoint, record:

- win/draw/loss and Wilson or bootstrap intervals;
- result by first/second player;
- result by own deck and opponent archetype;
- timeout, invalid-selection, native exception, and process-restart counts;
- median and tail decision latency;
- turns, selections, and native search calls per game;
- terminal reason, prizes, deck-out, and unresolved/unknown parser flags.

Use at least three opponent sets:

1. Basic sanity opponents: random legal policy and simple public rule agents.
2. A fixed validation league: public agents, frozen checkpoints, and representative deck archetypes.
3. A hard-matchup set: policies trained or selected specifically to exploit the current checkpoint.

Keep episodes grouped by game in train/validation and hold out entire opponents or decks. A checkpoint that wins more against its training mirror but loses to the held-out set is not an improvement.

## Promotion rules

Promote a checkpoint only when:

- it passes a long memory/timeout soak;
- invalid selections and native errors are zero or explained;
- aggregate improvement survives a held-out opponent matrix;
- no major matchup regresses beyond the chosen confidence threshold;
- CPU startup and per-decision latency fit the submission image;
- the packaged `.tar.gz` passes the sample submission's contract.

Keep a second build that is less ambitious but operationally safe. A theoretically stronger checkpoint that crashes, leaks native memory, or times out is not a candidate for the active pair.

## Infinite games and old engine reports

[Possible infinite move](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/714030) reports a historical loop involving Mega Venusaur's Solar Transfer. The host said the updated environment increased the step limit so a looping agent eventually loses by timeout; the old drawn games were not retroactively changed. Test loop detection and ensure every branch either advances the game or yields a legal action that can be resolved.

## Bottom line

The right local question is not "what is my current Kaggle rating?" It is "does this checkpoint beat a held-out, changing population with no runtime failures, and does it improve the weakest important matchup?" Use the ladder for calibration, but use the local cross-play matrix and replay failure buckets for engineering decisions.

