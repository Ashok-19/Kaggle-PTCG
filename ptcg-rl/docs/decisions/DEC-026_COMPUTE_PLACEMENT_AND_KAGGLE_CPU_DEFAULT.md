# DEC-026: Default Heavy Work to Private Kaggle CPU and Approval-Gate All Training

Date: 2026-08-04
Status: Accepted and implemented
User decision: proceed with light local work only; use private Kaggle notebooks for heavier work, default to CPU, and require separate approval before every training run or accelerator use

## Decision

Local execution is restricted to source edits, metadata inspection, deterministic planning, unit and contract tests, packaging, and very light bounded smokes. No heavy experiment may run locally.

When work is too large for the light-local boundary, prepare a reproducible private Kaggle input dataset and notebook. Reuse a stable dataset slug and increment its version instead of creating noisy duplicate datasets or models. Relevant notebooks must attach the exact competition data source or an independently verified versioned substitute, remain private, and record source, configuration, input versions, machine type, wall-time cap, stop conditions, outputs, byte counts, and SHA-256 hashes.

Private Kaggle CPU is the default remote runtime. GPU and TPU remain off unless the user separately approves their exact use. GPU is reserved for an approved training run that materially benefits from it; quota availability is not authorization.

Every optimizer-backed or otherwise meaningful training run requires separate explicit approval before launch, including CPU training, the existing 64-step BC engineering canary, PPO, self-play, fine-tuning, or any later continuation. Approval must bind the exact request/configuration and does not authorize production continuation, promotion, submission, or a second run.

This decision authorizes only bounded non-training infrastructure work needed to prepare or verify private Kaggle CPU execution. It does not authorize replay-body or agent-log transfer, optimizer construction or steps, model mutation, production training, GPU/TPU use, external paid compute, model or dataset proliferation, deck freeze, submission, active-submission changes, Git commit, or Git push.

## Kaggle CPU attachment qualification

A private CPU-only notebook exists at `ashok205/kptcg-e01-cpu-infra-v1` (kernel ID `129685552`). Versions 1 and 2 failed closed before input access because the competition source was not mounted. Those failures remain retained as negative evidence.

The user corrected the notebook attachment and input root, then ran saved version 4 / scriptVersionId `340139179`. Kaggle metadata explicitly records `pokemon-tcg-ai-battle` as the competition data source. The run completed as `PASS` with decision `PRIVATE_KAGGLE_CPU_COMPETITION_ATTACHMENT_QUALIFIED`.

The verified mount root is `/kaggle/input/competitions`, with the competition available at `/kaggle/input/competitions/pokemon-tcg-ai-battle`. The notebook enumerated 67 metadata entries comprising 60 files and 7 directories, but read no file bodies or replay bodies.

Observed runtime was four CPU cores, Python `3.12.13`, PyTorch `2.10.0+cpu`, zero CUDA devices, and no TPU environment. Internet, GPU, and TPU were off. No optimizer was created, optimizer steps remained zero, no model parameter changed, no training ran, and no submission was created.

The saved output contained exactly two files. The 8,918-byte qualification receipt has SHA-256 `1111472bd2e6782c684228214b524446c220958b86dab361c12c1716389e2454`. The 296-byte output manifest has SHA-256 `9931a23da9049959ea4ad3557485c4289fce38feb5d911b3a0dfddfd54538efc` and binds the receipt byte count and hash exactly. Independent review is recorded at `reports/artifacts/e01-kaggle-cpu-infra-qualification-review-v1.json`.

## Operational consequence

Private Kaggle CPU with the competition attachment is now qualified for future bounded workflows. This qualification establishes only attachment and runtime availability. It does not authorize replay reads, parsing at scale, optimizer steps, training, GPU/TPU use, model promotion, or submission.

Future notebooks must derive or verify the mounted path from notebook metadata and the actual `/kaggle/input` tree. Do not assume the generic dataset root or silently reuse a path from a different Kaggle source type.

## Revisit triggers

Revisit this decision if the user changes compute placement, approves an exact training or accelerator run, the competition attachment or mounted path changes, a stable versioned input dataset is published, or a proposed workflow exceeds the light-local or bounded private-CPU limits.
