# Game Rules and Simulator Quirks

This file separates ordinary Pokemon TCG rules from behavior that is specific to the CABT competition simulator. The simulator behavior is what the agent must satisfy.

## Deck legality

The engine source validates the following at battle start:

- Exactly 60 cards.
- Every card ID must be valid.
- At least one Basic Pokemon.
- At most one ACE SPEC card.
- No more than the engine's same-named-card limit for a card, except Basic Energy.

The engine checks card names, not just numeric IDs, for the duplicate-card rule. Validate decks locally before training so invalid deck samples do not consume rollouts.

The intended competition contract is one consistent deck per submitted agent. In [One agent with multiple decks](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/711741), the host said that selecting a different deck per game is technically possible but not intended; the documentation was updated to make the expected behavior clear. Treat `deck.csv` as fixed for a submission.

## Turn and selection model

The agent does not emit arbitrary Pokemon TCG actions. The engine advances until a decision is needed, then supplies a `SelectData` object:

- `type` and `context` describe the selection being requested.
- `minCount` and `maxCount` define how many option indices must be returned.
- `option` is the legal option list.
- `deck` is populated for searches where the agent may choose from a deck.
- `contextCard`, `effect`, and remaining damage/energy fields provide additional context for some effects.

The response is a list of integer indices into the supplied options, not card IDs. It must:

- Have a length between `minCount` and `maxCount`.
- Contain no duplicate indices.
- Contain only indices in the current option list.
- Respect the order/semantics of the current selection context.

For an optional selection with `minCount == 0`, returning `[]` is the normal way to decline it; there is not a general `END` response needed for this case. This behavior was clarified in [Official rules vs simulator behavior](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/708586).

The observation includes public logs and state. A player's visible state can include active and bench Pokemon, damage, attached energy/tools, discard, prize count, deck count, stadium, status conditions, and hand count. Hidden cards are not available to the actor unless a game effect has revealed them.

## Simulator behavior that differs from tabletop expectations

The host's detailed clarification is [Differences Between Official Rules and Simulator Behavior](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/708586). The important differences are:

1. Some attacks that a tabletop player may be allowed to declare are absent from the legal options when their effect cannot resolve in the simulator. Examples include a Basic-Pokemon search with no bench space, a draw effect with an empty deck, or a hand-targeting effect when the target hand is empty.
2. Mega Zygarde ex's `Nullifying Zero` resolves coin-dependent damage in the simulator's automatic left-to-right order, rather than allowing the player to choose the order.
3. Simultaneous knockouts are resolved sequentially. The next player takes their prizes and then the other player resolves theirs. If both players take all prizes, the simulator reports a draw.
4. An Ability is an explicit selectable action when the engine exposes it. A passive/continuous Skill is not necessarily an action. Some effects, such as Clefairy's effect mentioned in the thread, are automatic.
5. Deck-search decisions expose the actual candidate cards in `select.deck`. The options point into that list; the agent is not expected to infer the search result from a hidden deck. See [Deck Search "blind"](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/714920).

These are not edge details to patch after training. They change the transition and action distributions, so the local environment used for training must be the same engine build as the submission environment.

## Resolved reports that are useful as tests

The following threads contain reports that were explained or corrected. They are good regression-test candidates, not exploits:

- [Rare Candy engine bug](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/716241): an apparent failure to evolve was explained by Evolution Jammer preventing the normal evolution while the Rare Candy option remained exposed.
- [Mirage Barrage discard bug](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712226): the reporter later said their adjustment resolved the observation; no reproducible engine bug was established.
- [First player turn-one attack](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/709895): the apparent violation came from reading a replay incorrectly; the player was actually second.
- [Zero-damage attack](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/726485): Rock Fighting Energy prevented all attack effects, including Alakazam's damage-counter effect; this was card behavior, not an engine error.
- [Unfair Stamp behavior](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/712811): a report that opponent hands were not returned had no confirmed resolution in the thread, so add a targeted replay test before relying on this effect.

## Search and hidden information

The engine search API is not a free-information oracle. The caller must provide an observation-consistent hypothesis for hidden zones, including exact hidden lengths. A hidden-card particle should be a legal world: cards must be allocated without replacement, and already revealed cards must be removed from the remaining deck.

Use `manual_coin=False` for fair competition search. `manual_coin=True` lets the search caller select coin outcomes and must not be used to give the agent favorable randomness.

The search API can still be valuable for checking the immediate consequences of a legal option, but it should not be used to smuggle hidden state into the actor. See [game_engine_and_agent_api.md](game_engine_and_agent_api.md) for the exact wrapper contract.

## Randomness and reproducibility

The native engine initializes randomness internally. The source configuration uses a random device and the Python wrapper does not expose a normal seed-setting call. Do not assume that setting a Python, NumPy, or PyTorch seed makes a battle reproducible. Build stochastic regression tests around distributions and invariants unless you have verified a supported engine-level seed path.

## Rulebook and engine authority

Start with the [official How to Play page](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/how-to-play), the [CABT API documentation](https://matsuoinstitute.github.io/cabt/api.html), and the downloaded engine source. When a tabletop rule and the simulator differ, follow the simulator and the host clarification for this competition.

