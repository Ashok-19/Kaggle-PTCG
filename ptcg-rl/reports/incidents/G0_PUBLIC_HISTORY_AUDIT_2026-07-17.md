# G0 Public-History Exposure Audit

Audit time: 2026-07-17 UTC  
Mode: read-only remote/history/LFS/release/artifact inspection  
Status: BLOCKED pending approved remediation

## Outcome

The configured GitHub repository `Ashok-19/Kaggle-PTCG` is public. Its only remote branch, `origin/main`, points to the initial commit that introduced one sample-agent ZIP and six sample-agent notebooks. The later local removal commit does not make those blobs unreachable from local history, and it has not been pushed.

No restricted file contents were printed or copied during this audit.

## Repository And Refs

| Item | Result |
|---|---|
| Remote | `https://github.com/Ashok-19/Kaggle-PTCG.git` |
| GitHub visibility | `PUBLIC` |
| Default branch | `main` |
| Local `main` | `e5308b5b410f14ce84adce0ca4fd3582f8118f19` |
| Remote `origin/main` | `70b44042b2a5b2e5e361bb897bfb72452c2b2699` |
| Remote branches | one: `main` |
| Local/remote tags | none |
| Git LFS objects | none reported by `git lfs ls-files --all` |

Both `refs/heads/main` and `refs/remotes/origin/main` contain the exposing initial commit.

## Restricted Reachable Blobs

Exposing commit: `70b44042b2a5b2e5e361bb897bfb72452c2b2699` (`Initial commit`)  
Local removal commit: `04fc9038001f33be1bec5d427384c28d2fd9a4e6`

| Blob ID | Bytes | Path |
|---|---:|---|
| `c229f203630fb520d777b65141cca48a3d9b12f3` | 210491 | `sample-agents.zip` |
| `59c089f26d733c1bdd3ffc5e42d6ef83b3e97c0f` | 46133 | `sample-agents/a-sample-rule-based-agent-dragapult-ex-deck.ipynb` |
| `c459cdb4a97b0f7e7f6064ebad73c62a64e270ca` | 25397 | `sample-agents/a-sample-rule-based-agent-iono-s-deck.ipynb` |
| `296b09bbcd48e5ce67a0c5ea88735dda6beaf73e` | 18455 | `sample-agents/a-sample-rule-based-agent-mega-abomasnow-ex-deck.ipynb` |
| `65e43c8bf3b8ae00663d92ecab3a3662a96254cc` | 29392 | `sample-agents/a-sample-rule-based-agent-mega-lucario-ex-deck.ipynb` |
| `f394b0843d01bacf533f49e5c6a9d428ee36db93` | 258696 | `sample-agents/how-to-output-local-battle-as-json-and-view.ipynb` |
| `70c5548e8635678d221d35cddbbdb155bf659c34` | 37888 | `sample-agents/reinforcement-learning-and-mcts-sample-code.ipynb` |

The full reachable-path scan found no tracked engine libraries, card CSV/PDF data, `.env`, Kaggle credential files, checkpoints, model weights, raw replay roots or submission staging paths.

## GitHub Surfaces

| Surface | Result |
|---|---|
| Releases/assets | none |
| Actions workflows | none |
| Actions artifacts | none |
| GitHub secret-scanning alerts | none returned; this is not proof that no secret ever existed |
| Packages | UNKNOWN: the active GitHub token lacks `read:packages` scope |
| Forks, caches, mirrors, prior clones | UNKNOWN and not retractable by history cleanup |

No credential path or secret-scanning alert was found. If independent evidence later identifies a credential, rotate it; repository cleanup is not credential rotation.

## Required Containment And Remediation

Pushes remain frozen. The reviewed preferred remediation is:

1. make the affected GitHub repository private immediately;
2. create a new private GitHub repository from a sanitized current-tree snapshot without importing existing history;
3. keep only reviewed source, config, tests and documentation;
4. attach the current working root to the new private remote;
5. clone it into a genuinely new directory and rerun G0 under Python 3.11;
6. verify every reachable ref in the new remote has zero restricted blobs;
7. retain this incident record and decide separately whether to archive, rewrite or delete the old repository.

Changing visibility, creating/replacing a remote, pushing a sanitized snapshot, rewriting history or deleting the old remote requires explicit user approval. No such mutation was performed by this audit.

