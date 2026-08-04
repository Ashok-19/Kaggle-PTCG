# DEC-013 — Reopen E01-A Source Provenance

Status: Accepted

Date: 2026-07-24

## Context

The accepted E01-A dry run selected eight named replay candidates while transferring zero replay JSON. It binds `kaggle/pokemon-tcg-ai-battle-episodes-2026-07-23` version 1 to a 378,402-byte daily `manifest.csv` with SHA-256 `e082c3cf80638e4ba5a8915e40eca25683a83c4abb79a4b7f41c02133b01f31a` and the normalized columns required by `ptcg_rl.replay.planner`.

A fresh read-only retrieval of the same owner, slug, version and file name produced a different 378,253-byte object with SHA-256 `136dbdb174e6bbd6057023e0271d1016fe0ff143e5958ddbef38d105cc59d5c2`. Its columns are `id`, `create_time`, `agents`, `score1`, `score2`, `data_size`, `file_name`, rather than the planner contract `episode_id`, `create_time`, `avg_score`, `min_score`, `sum_score`, `agent_count`, `size_bytes`. The eight episode IDs still exist, but their reported timestamps, scores and byte sizes differ from the accepted dry-run records.

The pinned index dataset version 38 remains byte-reproducible and still declares 4,559 episodes and 21,474,555,587 bytes for the July 23 daily dataset. It does not bind the daily manifest object hash or define a lossless mapping between the two daily schemas.

## Decision

Reopen E01-A source provenance and block every replay-body transfer.

Do not prepare an executable provenance probe until the daily manifest used by the accepted dry run is reproduced byte-for-byte or a separately reviewed schema-adapter contract establishes which fields are authoritative, how timestamps and scores map, and how exact replay byte caps are obtained.

The placeholder `configs/e01_provenance_probe_request_v1.json` must remain `request_ready: false`, `authorized: false`, name no episode file, permit zero files and zero bytes, and have no output directory.

## Acceptance Conditions For Reopening The Probe

A later provenance-probe request may become reviewable only after all of the following pass:

1. exact daily source object identity and SHA-256 are reproducible;
2. manifest schema semantics are frozen and independently reviewed;
3. all selected file names and exact byte caps are rederived from that source;
4. deterministic selection is rerun under the frozen planner or an explicitly superseding planner version;
5. the request names exactly one smallest selected file and remains non-authorizing until separate approval.

## Non-Authorization

This decision does **not** authorize any replay body, agent log, action sequence, observation, training label, optimizer step, notebook, accelerator, paid compute, deck freeze or submission. It does not qualify a teacher, deck or policy.

## Revisit Trigger

Revisit when the original daily manifest is recovered or a reviewed source/schema reconciliation artifact passes.
