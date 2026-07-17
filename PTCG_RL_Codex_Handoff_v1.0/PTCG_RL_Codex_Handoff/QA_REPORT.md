# Handoff Bundle QA Report

Prepared: 2026-07-17  
Bundle version: 1.0

## Validation completed

- All YAML configuration files parse successfully with `yaml.safe_load`.
- The run-manifest JSON Schema parses successfully as JSON.
- Every Markdown file has balanced fenced-code blocks.
- Every relative Markdown link resolves to an existing bundle file.
- Replay sampling fractions sum to 1.0 in every supplied profile.
- Kaggle GPU-hour allocations sum to the reported 45-hour envelope.
- Each Modal account envelope sums to its conservative $28 cap.
- The mature league mixture sums to 1.0, with declared empty-pool behavior.
- Stale/ambiguous replay quality classes, quantile populations and stability-split settings were removed.
- Recurrent PPO contracts were cross-checked for compound actions, forced-action classification, truncation bootstrap, policy-version boundaries, value clipping and idempotent inference sequencing.
- Repository/private-asset rules ignore the complete submission staging tree and private asset root.

## Intentional unresolved fields

These are blocking preflight inputs, not omissions to guess:

- exact local paths and SHA-256 values for the official package, research ZIP and sample agents;
- the exact official competition close instant, runtime limits and current package rules;
- the user’s real local Kaggle MCP tool names, version-resolution method and receipt format;
- current Modal pricing/terms and resource-second caps at G4;
- the main exact deck, selected only at D1;
- the final catastrophic-matchup floor and minimum meaningful evaluation effect, frozen before seeing finalist results.

Every executable command must reject unresolved configuration values beginning with `REQUIRED`.

## Scope statement

This is an implementation and experiment-control specification, not proof that a top-20 result is guaranteed. It is designed to maximize that goal while preventing invalid-action, data-leakage, replay-download, evaluation and cloud-cost failures from consuming the one-month schedule.
