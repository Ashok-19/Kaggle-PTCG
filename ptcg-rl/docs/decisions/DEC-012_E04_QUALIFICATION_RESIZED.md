# DEC-012: Resize E04 Qualification from 100 to 180 Games

Date: 2026-07-24  
Status: Accepted

## Decision

Supersede only the E04 confirmation-stage sizing in DEC-011. Replace the
internally unsupported combination of exactly 100 games and at least 10,000
meaningful decisions with exactly 180 games and the unchanged minimum of 10,000
meaningful decisions.

The active E04 sequence is now:

```text
1-game single-process trace
→ 10-game smoke
→ 180-game zero-update qualification with at least 10,000 meaningful decisions
```

Every other DEC-011 strategy, safety, evidence and authorization boundary
remains unchanged.

## Evidence

The independently reviewed ten-game smoke is
`reports/evaluations/e04-ten-game-smoke-v1.json`, SHA-256
`66d00da9e0b99783fd3f7ec441a89fa298597acbc1818220014a97481ba68236`.
It completed ten terminal games with:

- 711 engine decisions;
- 648 meaningful decisions;
- 63 forced decisions;
- zero optimizer steps;
- zero reliability events;
- both-player terminal boundaries in all ten games;
- maximum compound log-probability replay error
  `1.9428366693219346e-07`.

Per-game meaningful decisions were:

```text
58, 70, 57, 70, 56, 70, 70, 66, 63, 68
```

The observed mean was `64.8`, sample standard deviation was
`5.846176338238334`, minimum was `56`, and maximum was `70`.

## Why 100 games is rejected

The audit correctly required a substantial zero-update reliability exposure,
but it combined two confirmation requirements without a measured decision-rate
basis:

- 100 complete games;
- at least 10,000 meaningful decisions.

At the accepted smoke mean, 100 games project only `6,480` meaningful decisions.
Even if every future game matched the observed maximum of `70`, 100 games would
produce only `7,000`. The old exact combination therefore cannot satisfy its
own decision floor under the observed range.

## Why 180 games is selected

The decision floor remains 10,000 because it measures compound-action,
recurrent and lifecycle exposure rather than policy strength. The game count is
resized using the accepted smoke evidence:

- `ceil(10,000 / 56) = 179` games at the observed minimum rate;
- round upward to the next ten-game boundary: `180` games;
- projection at the observed minimum: `10,080` decisions;
- projection at the observed mean: `11,664` decisions;
- a one-sided 99% Student-t lower bound on the mean is
  `59.583942015953184`, projecting `10,725.109562871574` decisions at
  180 games.

These projections do not guarantee passage. The stage still fails closed if
180 games produce fewer than 10,000 meaningful decisions or any zero-tolerance
condition is nonzero.

## Runtime and evidence policy

The accepted smoke used `13.843765318000806` seconds for ten games, or
`1.3843765318000805` seconds per game. A linear 180-game projection is
`249.1877757240145` seconds. This is planning evidence only, not an execution
guarantee.

The qualification runner must retain:

- an atomic game ledger after every completed game;
- an atomic full bridge checkpoint every ten games and after the final game;
- exact authorization, asset, checkpoint, deck and source hashes;
- zero optimizer steps and no training loop;
- both-player terminal or classified truncation boundaries;
- exact compound-action replay within `1e-5`;
- zero invalid, fallback, stale, duplicate, out-of-order, policy-lag,
  recurrent-ownership, nonfinite, replay, terminal, worker-death and optimizer
  attempt counters.

## Scope of supersession

This decision supersedes only the phrase “100 games with at least 10,000
meaningful decisions” in DEC-011 and its machine-readable E04 work order. It
does not alter:

- the accepted one-game or ten-game evidence;
- the historical audit files or historical G3b plan;
- the 970,022-parameter architecture;
- any E01, E08, BC, PPO, external-compute, deck-freeze or submission boundary;
- the zero-tolerance reliability requirements;
- the 10,000-meaningful-decision floor.

## Authorization boundary

This decision authorizes repository implementation, deterministic review, unit
tests and preparation of one exact non-authorizing qualification request. It
does **not** authorize:

- the 180-game qualification execution;
- an overwrite or rerun;
- any optimizer step or training loop;
- replay-body transfer;
- Kaggle, TPU, Modal, paid compute or other external execution;
- deck freeze, submission, staging, commit or push.

The exact qualification request must remain `authorized: false` until a
separate smallest-possible user approval names the file, game count, decision
floor, compute location and output directory.
