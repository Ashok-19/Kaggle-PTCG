# Replay Data and Meta Findings

Public episodes are useful for opponent sampling, deck discovery, failure analysis, and optional behavior-cloning experiments. They are not a clean view of the hidden evaluation distribution.

## Official episode access

The official [How to Play](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/how-to-play) and [Kaggle simulation CLI guide](https://github.com/Kaggle/kaggle-cli/blob/main/docs/simulation_competitions.md) describe access to submissions, episodes, replays, logs, and public top-team artifacts. Kaggle also publishes a daily top-episode index:

- [Pokemon TCG AI Battle Episodes Index](https://www.kaggle.com/datasets/kaggle/pokemon-tcg-ai-battle-episodes-index)
- [Daily Top Episodes discussion](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709160)

The daily collection is selected from highly rated participants. It is biased toward the public top of the ladder and does not reveal all hidden opponents, decks, or random situations.

## Episode/action alignment

This is the most important parsing trap.

[Clarification on Episode JSON Action/Observation Alignment](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/716557) asks whether an action belongs to the same row as the observation or to the next environment step. The thread does not provide an official answer. [Replay action alignment correction](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/717279) contains a participant validation across 22 episodes: their parser initially paired the action with the same observation, then corrected it by searching forward to the next active step with a non-empty action. They report 1,277/1,277 corrected matches, with steps 0 and 1 requiring special handling.

Treat this as a parser hypothesis that must be verified against the current JSON schema, not as permission to blindly shift every row. A safe parser should:

1. Preserve the raw step number and raw observation/action fields.
2. Mark whether a step is active, terminal, empty, or a no-op.
3. For a decision observation, search forward only according to the observed engine transition and validate the returned indices against that step's legal option list.
4. Handle the initial deck response separately from game selections.
5. Test single-select and multi-select actions independently.

The original filtering suggestions in [716557](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/716557) include keeping active selections, requiring a positive count, checking that there is more than one option, validating the action range, and excluding non-decision/replay artifacts. Those filters are useful for a first behavior-cloning dataset, but they can throw away strategically important forced or optional one-option decisions. Keep both a raw dataset and a filtered learning view.

## Replay triage workflow

[Replay triage template](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/718783) proposes classifying losses into buckets such as:

- setup or mulligan miss;
- failed tempo or missed early development;
- no backup attacker/bench management;
- missed bench knockout or wrong target;
- poor discard/resource choice;
- bad switch, retreat, or energy attachment;
- deck-out;
- variance or unavoidable matchup loss.

[Replay log curation](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/717832) suggests a notebook workflow for cleaning and labeling public logs. The value is not just a larger dataset: it gives a failure taxonomy for deciding whether an RL change actually fixes an error.

Recommended stored fields per decision:

| Field | Why it matters |
| --- | --- |
| Raw observation and raw selection | Preserve evidence when the parser is corrected. |
| Turn/action/log position | Reconstruct the transition and long-horizon context. |
| Legal option objects | Re-score choices without losing card/target semantics. |
| Selected indices and resolved cards | Distinguish index errors from card-identity errors. |
| Public state delta | Diagnose damage, prizes, energy, bench, hand, and deck changes. |
| Deck fingerprint and opponent fingerprint | Build matchup-stratified splits. |
| Outcome and timeout/error flags | Prevent invalid or incomplete episodes from becoming positive labels. |

## Human and external logs

In [Self-play / human-play logs as external data](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712119), host replies say that self-prepared human or external battle logs may be used when the user has the rights to use them, including games against people outside the team. This does not override the competition rules: external data must be public/equally accessible where required, legally usable, and not an unfairly restricted resource. Keep provenance and permission records for every non-Kaggle source.

If the agent must be strictly pure RL, use these logs for opponent/deck analysis and evaluation rather than action supervision. If hybrid training is later allowed, verify the action alignment before cloning anything.

## Public meta observations

### Meta changes quickly

[Daily public meta notes](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709263) report the visible top-ten archetypes changing over a short period:

| Visible date | Reported top-ten pattern |
| --- | --- |
| 2026-06-17 | All ten were Crustle sustain. |
| 2026-06-18 | Iono, Psychic, Crustle, and other archetypes appeared. |
| 2026-06-19 | Four Lucario, four Psychic, two Iono. |
| 2026-06-20 | Four Lucario, three Psychic, two Hop, one Iono. |
| 2026-06-21 | Five Hop, five Psychic. |
| 2026-06-26 | Grass/fire/spread dominated eight of ten, with two Psychic. |
| 2026-06-28 | Five Starmie, three Archaludon, two Psychic. |

These are visible top-ten snapshots, not the hidden matchmaker distribution.

[Public Top-100 Meta Snapshot](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709554) gives a rough June 19 visible top-100 split of fast Fighting about 43%, Psychic 20%, Lightning 19%, sustain 7%, grass 4%, fire 2%, and other 5%. The same thread notes that rank bands had different distributions. Use multiple strata instead of a top-ten-only sampler.

### Small matchup studies

[Public matchup matrix](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709498) compares 11 public/sample agents over only 550 games, ten per pair. Its numbers are a screening tool, not a stable rating estimate. The useful output is the existence of matchup holes: test policies by opponent archetype, not only by aggregate win rate.

[Analysis of 30,000 top-team games](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/724362) uses action-time patterns to infer that some top agents may combine a model with bounded search. That algorithmic conclusion is explicitly an inference by the participant, not a revealed fact about the top submissions. The analysis also reports model startup times from hundreds of milliseconds to tens of seconds; measure your own startup cost on the submission image.

### Deck and counter-meta sources

- [Japanese City League deck dataset](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712011) links a converted 16-deck top-cut dataset. It can seed deck hypotheses, but card IDs and legality must be validated against the competition data.
- [Archaludon meta counter discoveries](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/716207) reports that Cornerstone Ogerpon can wall an Archaludon ability, but pure Ogerpon had poor Starmie/Lucario matchups. Toolbox variants were proposed to address those holes. Treat this as a deck-design hypothesis, not a universal counter.
- [Live meta dashboard and API](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712481) provides `https://ptcg-ladder-meta.vercel.app`, `/api`, and `/api-docs`. The author says it is built from observed daily top episodes, so it is useful for visible-meta monitoring but not hidden-evaluation truth.

## Suggested data pipeline

1. Download the official episode index and the episodes/replays it references.
2. Parse raw observations/actions without discarding any rows.
3. Validate each selected index against the legal options at the resolved decision step.
4. Create a second, filtered decision table for training or imitation experiments.
5. Infer deck fingerprints from submitted decks and revealed cards; keep uncertainty when a deck is only partially revealed.
6. Split by episode, deck, opponent, and time. Do not put adjacent steps from the same game in train and validation independently.
7. Build opponent samplers from several dates and rating bands. Refresh them as the public meta changes.
8. Label terminal result, timeout, engine error, and parser uncertainty separately.
9. Use replay buckets to choose RL evaluation slices: setup, resource, target, deck-out, and matchup-specific failures.

