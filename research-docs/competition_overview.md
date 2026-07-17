# Competition Overview

Snapshot collected 2026-07-16 for `pokemon-tcg-ai-battle`.

## Objective

This is a Kaggle Simulation competition for an agent that plays the Pokemon Trading Card Game through the CABT simulator. The game contains hidden opponent information, random draws and coin outcomes, and a large number of interacting card effects. The official description explicitly warns that a purely fixed rule-based policy is unlikely to reach the top by itself; adaptation and forward planning matter.

Primary pages:

- [Competition home](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle)
- [Description](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/description)
- [How to Play](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/how-to-play)
- [Data Description](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/data-description)
- [Evaluation](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/evaluation)
- [How to Submit](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/how-to-submit-to-this-competition)
- [Rules](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/rules)
- [Timeline](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/timeline)

## Dates and limits

The competition metadata returned by Kaggle at collection time:

| Item | Value |
| --- | --- |
| Competition start | 2026-06-16 11:00 UTC |
| Final deadline | 2026-08-16 23:59 UTC |
| Team/merger/new-entrant deadline | 2026-08-09 23:59 UTC |
| Maximum daily submissions | 5 |
| Maximum team size | 5 |
| Final active submissions | 2 |
| Evaluation metric | `cabt` |

The public timeline page was returned with unresolved template placeholders in one API response, so the dates above come from Kaggle competition metadata rather than that rendered page. Recheck the live page before packaging a final submission.

## Evaluation

The simulation track uses a Gaussian rating, described as `N(mu, sigma^2)`, rather than a score based on prize margin. The initial rating mean is 600. Agents are matched against similarly rated agents, and a win, draw, or loss changes the rating; the size of a win does not.

Only the most recent two eligible submissions are active. The best active result is displayed. The host said that games continue for roughly two weeks after the deadline so ratings can converge, and that a favorable or unfavorable early schedule is not intended to determine the final result.

The competition overview is authoritative for scoring. Community reports about episode rate and rating variance are collected in [submission_evaluation_and_ladder.md](submission_evaluation_and_ladder.md).

## Submission contract

Submit a `.tar.gz` archive with these files at its top level:

- `main.py`
- `deck.csv`

The official packaging example is:

```bash
tar -czvf submission.tar.gz *
```

The server performs self-validation. The sample agent reads the deck from the submission directory or `/kaggle_simulations/agent/`, returns the 60-card deck on the initial request, and returns indices into the legal options supplied by the environment on later requests. The exact archive structure and current validation behavior should be tested with the current sample submission before submitting.

See [How to Submit](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/how-to-submit-to-this-competition) and Kaggle's [simulation competition CLI guide](https://github.com/Kaggle/kaggle-cli/blob/main/docs/simulation_competitions.md).

## Card data

The competition data page lists:

- `Card_ID List_EN.pdf`
- `Card_ID List_JP.pdf`
- `EN_Card_Data.csv`
- `JP_Card_Data.csv`

The CSV columns include Card ID, card name, expansion, collection number, stage/type, rule, category, previous stage, HP, type, weakness, resistance, retreat cost, move name, cost, damage, and effect explanation. The PDFs map card IDs to English and Japanese card names.

The data download also contains the CABT C++ engine source and a `sample_submission` directory with Python wrappers and platform libraries. See [game_engine_and_agent_api.md](game_engine_and_agent_api.md).

## Game and simulator

The agent receives an observation containing logs, a public state, and a structured selection request. It must select from legal options by returning option indices. The official API documentation is [CABT API](https://matsuoinstitute.github.io/cabt/api.html).

The important implications for an RL design are:

- The action space is variable and already legality-filtered.
- The opponent's hidden hand, deck order, and prizes must be treated as uncertain, not read from the actor observation.
- The engine has a native search API, but search requires a coherent prediction of hidden zones.
- Randomness is internal to the engine; the Python wrapper does not expose a normal competition seed hook.
- The environment's exact behavior, not a paper rulebook, defines what is selectable in the competition.

Runtime values in older research notes should not be treated as the current contract. In particular, `Initial-research.md` records an older `runTimeout=2000`/`remainingOverageTime=600` configuration, while the later host/runtime discussions report 600 seconds cumulative for the whole game and no per-move limit. Use the current sample/server behavior and the linked runtime discussions when packaging.

The official [How to Play](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/how-to-play) page links the rulebook, card data, and simulator documentation.

## Official rules and licensing

The competition rules state that the supplied competition data, including Pokemon card assets and source code, is for competition/forum use and must be deleted after the competition. Winning submissions have additional licensing obligations. External data must be public and equally accessible, with rights to use it and no more than a reasonable/minimal cost under the rules.

Do not publish the downloaded card PDFs, card assets, native libraries, or engine source in a repository. Use the competition's download only within the allowed scope. The engine package includes an explicit competition-use-only license file; read it together with the Kaggle [Rules](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/rules).

The host clarified in [Game engine source code](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/717141) that derived, adapted, or compiled engine code may be used in a submission subject to the competition rules and scope. That clarification is not permission to redistribute the engine or its card content.

## Official CLI and episode access

Kaggle's simulation workflow supports downloading data, listing submissions, inspecting episodes, downloading replays, reading agent logs, and inspecting public top-team submissions where available. The relevant guide is the [Kaggle simulation competitions CLI documentation](https://github.com/Kaggle/kaggle-cli/blob/main/docs/simulation_competitions.md).

The competition also publishes daily top-episode datasets. Their limitations and practical replay-mining workflow are in [replay_data_and_meta.md](replay_data_and_meta.md).
