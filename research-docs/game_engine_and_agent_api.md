# Game Engine and Agent API

The competition data includes both a native CABT engine and a sample Python agent. The engine source is the best local specification for legal options and card effects; the Python wrapper is the best specification for the submission-facing call pattern.

## Downloaded data tree

The data listing contained 60 files. The useful groups are:

```text
Card_ID List_EN.pdf
Card_ID List_JP.pdf
EN_Card_Data.csv
JP_Card_Data.csv
ptcg_engine/ptcgProgram 22/
  Export.cpp
  All.h
  Api.h
  BattleData.h
  ... other C++ headers, Visual Studio files, README.md
  LICENSES/LicenseRef-PTCG-ABC-Competition-Use-Only.txt
sample_submission/sample_submission/
  main.py
  deck.csv
  cg/api.py
  cg/game.py
  cg/sim.py
  cg/utils.py
  cg.dll
  libcg.so
  libcg-arm64.so
  libcg.dylib
```

The source README describes a C++20, header-oriented engine with `Export.cpp`/`All.h` entry points and no third-party dependencies. The native libraries cover the supported submission platforms. Do not publish any of these files; the competition-use-only license applies.

## Submission call pattern

The sample `main.py` does three things:

1. Load a 60-card deck from `deck.csv`.
2. When no selection is requested, return the deck as the agent's initial deck response.
3. Otherwise, inspect `obs.select` and return a legal list of option indices. The sample chooses randomly.

The native contract rejects an invalid selection, duplicate index, out-of-range index, or a response whose count is outside the requested minimum/maximum. A policy should therefore score the options supplied in the current observation rather than create a global action vocabulary and hope that a mask is correct.

The official wrapper files are `sample_submission/sample_submission/cg/api.py`, `cg/game.py`, and `cg/sim.py` in the competition download. The public API reference is [CABT API](https://matsuoinstitute.github.io/cabt/api.html).

## Important API types

### Areas and cards

`AreaType` identifies `DECK`, `HAND`, `DISCARD`, `ACTIVE`, `BENCH`, `PRIZE`, `STADIUM`, `ENERGY`, `TOOL`, `PRE_EVOLUTION`, `PLAYER`, and `LOOKING`.

`CardType` includes `POKEMON`, `ITEM`, `TOOL`, `SUPPORTER`, `STADIUM`, `BASIC_ENERGY`, and `SPECIAL_ENERGY`.

`EnergyType` includes Colorless, Grass, Fire, Water, Lightning, Psychic, Fighting, Darkness, Metal, Dragon, Rainbow, and Team Rocket energy types.

`SpecialConditionType` covers poison, burn, sleep, paralysis, and confusion.

### Selection and options

`SelectType` distinguishes main decisions, card selection, attached-card selection, card-or-attached-card selection, energy selection, skill, attack, evolution, count, yes/no, and special-condition decisions.

`OptionType` includes number, yes/no, card, tool card, energy card, energy, play, attach, evolve, ability, discard, retreat, attack, end, skill, and special-condition options.

An `Option` can contain an area, index, player index, tool/energy index, count, in-play area/index, attack ID, card ID, serial, and special-condition type. Encode the option fields semantically. The numeric option index is only a pointer into the current legal option array.

`SelectContext` covers setup active/bench selection, switch and movement, damage/effects, attachment, look/search, skill ordering, attack, draw count, first-player choice, mulligan, activation, coin result, and special conditions. Context is often as important as the card identity.

### State and logs

The public `State` includes turn, action count, player index, first-player flag, supporter/stadium/energy/retreat flags, result, stadium, looking/search data, and player states. A `PlayerState` includes active, bench, discard, prize, deck count, hand count, visible hand where allowed, damage/statuses, and bench capacity. A `Pokemon` includes HP, damage-relevant state, attached energies/tools, evolution information, and whether it appeared this turn.

`LogType` includes shuffle, turn start/end, draw, card movement, switch, play, attach, evolve/devolve, attack, HP change, statuses, coin, and result events. Logs are useful for a recurrent memory, replay parser, and debugging, but are not a substitute for the current legal option list.

The API also exposes `CardData` and `Attack` metadata through `all_card_data()` and `all_attack()`. [Attack damage lookup](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/715572) specifically confirms that these functions are the intended way to obtain attack IDs and damage data for a value network or evaluator.

## Battle wrapper

The sample `cg.game` wrapper exposes the important calls:

- `battle_start(deck0, deck1)`: starts a battle; both decks must contain exactly 60 cards and satisfy engine validation.
- `battle_select(...)`: submits a selection and advances the engine.
- `battle_finish(...)`: closes the battle and returns the final result/data.
- `visualize_data(...)`: renders battle data for inspection.

The lower-level `cg.sim` wrapper loads a platform library and exposes native calls corresponding to `GameInitialize`, `BattleStart`, `BattleFinish`, `GetBattleData`, `Select`, `VisualizeData`, `SearchBegin`, `SearchStep`, `SearchEnd`, `SearchRelease`, `AllCard`, and `AllAttack`.

## Search API

The wrapper types are `SearchState`, `SearchBegin`, `SearchStep`, `SearchEnd`, and `SearchRelease`. The practical flow is:

```text
search_begin(agent_observation, own_deck, own_prize,
             opponent_deck, opponent_prize, opponent_hand,
             opponent_active, manual_coin=False)
search_step(search_id, selection)
search_end(search_id)
search_release(search_id)
```

`search_begin` requires a coherent observation and predictions for hidden zones. Hidden lists must have the correct lengths; a face-down opponent active Pokemon must be supplied when required. It is not legal to give the search an omniscient hidden state while the actor sees only public information.

`search_step` validates the search ID and the selection against the current search state. The thread [search_step error](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/715644) is a warning to log the exact `SelectData` and option list at every search node, especially around Team Rocket's Bother-Bot and visible opponent prizes.

For fair play, keep `manual_coin=False`. A search implementation that samples hidden cards must allocate them without replacement from a legal deck hypothesis. See [game_rules_and_simulator_quirks.md](game_rules_and_simulator_quirks.md).

## Engine source release and scope

In [Game engine source code](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/717141), the host announced the engine source download on the Data page and said it is intended for local testing, verification, and training. The host later clarified that derived, adapted, or compiled engine code may be used in a submission, subject to the rules and competition-only scope. The source may differ from the official tabletop game and may change during the competition.

[Engine source/reverse engineering ruling](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/711737) is the earlier thread; its final state is superseded by the source release. Do not exploit or depend on reported engine bugs. Report them to the host and test the current build.

## Runtime facts and engineering consequences

Host/community answers in [Inference environment](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/708810), [Game timer](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/713603), and [per-game time limit](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/726708) report:

- 600 seconds cumulative per game, with no separate per-move limit.
- CPU execution, reported as about 1.6 vCPU and 8 GB RAM in the inference-environment discussion.
- A timeout is preferable to an infinite game; the June 30 update increased the step limit so loopers eventually time out rather than creating a draw.

These are discussion answers and can change. Measure local throughput and leave a large wall-clock reserve for model startup, native calls, serialization, and cleanup.

The thread [Environment speed](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/717698) reports that neural inference, rather than the engine, is often the bottleneck and that GPU acceleration of the compositional engine is non-trivial. [CPU vs GPU runtime](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709704) says submitted games run on CPU, so a GPU-only training design still needs a CPU-compatible inference path.

## Native-library hazards reported by participants

[libcg.so memory leak](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709152) reports a historical leak during long Stable-Baselines3 training runs. The suggested workaround was process isolation/checkpoint restart, and the participant suspected repeated `VisualizeData`/ctypes pointer handling. This was not an official root-cause fix. For training infrastructure:

- Never call visualization in the rollout hot path.
- Run a long memory soak before spending compute.
- Check native allocations and release search handles.
- Make checkpoint/restart cheap.

