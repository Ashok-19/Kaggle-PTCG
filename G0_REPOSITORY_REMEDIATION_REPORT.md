# G0 Repository Remediation Report

Date: 2026-07-17  
Status: **CONTAINMENT PASSED; INCIDENT CLOSURE BLOCKED ON PACKAGES AUDIT**

## Outcome

The legacy repository was changed from public to private without rewriting,
force-pushing, archiving, or deleting it. A reviewed snapshot was exported into
a separate directory without the legacy `.git` database, checked, initialized as
a new repository with one root commit, pushed to a new private repository, and
cloned into a second fresh directory for verification.

The new repository is now the sanitized source of truth:

- Legacy: <https://github.com/Ashok-19/Kaggle-PTCG> (`PRIVATE`)
- Sanitized: <https://github.com/Ashok-19/Kaggle-PTCG-RL> (`PRIVATE`)
- Sanitized default branch: `main`
- Selected legacy source commit: `e5308b5b410f14ce84adce0ca4fd3582f8118f19`
- New root and remote `main`: `08be5cec0fac9a954a3fe127a3f51122be4736d1`
- Exposing commit: `70b44042b2a5b2e5e361bb897bfb72452c2b2699`

The new root does not descend from the exposing commit. That object is absent
from the new object database.

## Mutations Performed

1. Preserved the pre-existing unstaged `CODEX_MASTER_PROMPT.md` edit as an
   ignored local patch in the legacy worktree.
2. Changed `Ashok-19/Kaggle-PTCG` visibility from `PUBLIC` to `PRIVATE` and
   verified it.
3. Exported an allowlisted tracked-file snapshot from the selected source
   commit into `/tmp/PTCG-RL-sanitized-source-20260717`.
4. Initialized a new Git repository in that snapshot and created one root
   commit.
5. Created `Ashok-19/Kaggle-PTCG-RL` as `PRIVATE`, pushed only the new root
   history, and verified its remote refs.
6. Cloned the private remote into
   `/tmp/PTCG-RL-fresh-clone-20260717` and verified the clone.

No legacy history was rewritten or force-pushed. Neither repository was
archived or deleted. No ignored/untracked private asset, sample-agent archive or
notebook, engine library, card data, credential, replay body, checkpoint, or
submission artifact was copied into the sanitized snapshot.

## Manifest And Snapshot Evidence

- Reviewed files exported before adding the manifest: `78`
- Root commit files (including the generated manifest): `79`
- Reviewed file bytes: `364962`
- Manifest content digest: `20e5635e6ff9bce5852f7b786c516c4549c8ee3f1b32b6f4cca81337b35a7640`
- Manifest file SHA-256: `3a6731ba244a5d2fc4cf7d146416445b62339621ae29faf533d026c750991229`
- Source/clone `ptcg-rl/uv.lock` SHA-256:
  `0097f4b9dc7ebfd5d59e1601868d6775dd489d0eabedd4dce2901438327de1dd`

Pre-initialization checks found zero restricted paths, secret-pattern matches,
symlinks, or files above 5 MiB. `ptcg audit-staged` passed after repository
initialization. The snapshot was created from tracked files only and did not
copy the old `.git` directory.

## Full-History And Remote Verification

- New reachable commit count: `1`
- New root count: `1`
- Remote refs: only `refs/heads/main` at `08be5cec...`
- Tags: none
- LFS objects: none
- Releases: none
- Actions workflows: none
- Actions artifacts: `0`
- Fresh clone worktree: clean and tracking `origin/main`
- Fresh clone commit: `08be5cec...`, matching the source snapshot and remote
- Fresh clone lock and manifest hashes: match the source snapshot

All seven previously reported restricted blob IDs are absent from the fresh
clone object database:

`c229f203630fb520d777b65141cca48a3d9b12f3`,
`59c089f26d733c1bdd3ffc5e42d6ef83b3e97c0f`,
`c459cdb4a97b0f7e7f6064ebad73c62a64e270ca`,
`296b09bbcd48e5ce67a0c5ea88735dda6beaf73e`,
`65e43c8bf3b8ae00663d92ecab3a3662a96254cc`,
`f394b0843d01bacf533f49e5c6a9d428ee36db93`, and
`70c5548e8635678d221d35cddbbdb155bf659c34`.

The seven restricted paths also have no reachable occurrence in the new
history. The exposing commit itself is not a valid object in the new clone.

## Packages Disposition

GitHub Packages remains **UNKNOWN** and is the sole incident-closure blocker.
The authenticated REST query returned HTTP 403 with:
`You need at least read:packages scope to list packages.`

This does not invalidate containment or the new sanitized source of truth. It
does prevent claiming that every historical publishing surface has been fully
audited. Close this gap with a `read:packages` credential or timestamped manual
inspection of the owner Packages page.

## Preserved User Edit

The pre-existing unstaged root `CODEX_MASTER_PROMPT.md` edit remains unchanged
in the legacy worktree. Its patch was preserved at the ignored local path:

`ptcg-rl/private/preserved-user-edits/CODEX_MASTER_PROMPT.pre-sanitize.patch`

Patch SHA-256:
`18fde2231074583a0dabf8f895b70dde3fe1c3705c411f4cd3a877a72ed44e61`.

It was not included in the sanitized root and was not discarded.

## Commands Executed

Commands are listed without credentials; GitHub CLI authentication remained in
the credential store and was never printed.

```text
git diff --binary -- CODEX_MASTER_PROMPT.md
git archive e5308b5 <reviewed allowlist>
ptcg audit-staged
git init -b main
git add .
git commit -m "Create sanitized project root"
gh repo edit Ashok-19/Kaggle-PTCG --visibility private \
  --accept-visibility-change-consequences
gh repo create Ashok-19/Kaggle-PTCG-RL --private
git remote add origin https://github.com/Ashok-19/Kaggle-PTCG-RL.git
git push -u origin main
gh repo view Ashok-19/Kaggle-PTCG --json isPrivate,visibility,url
gh repo view Ashok-19/Kaggle-PTCG-RL --json isPrivate,visibility,url
git ls-remote --heads --tags https://github.com/Ashok-19/Kaggle-PTCG-RL.git
git clone https://github.com/Ashok-19/Kaggle-PTCG-RL.git \
  /tmp/PTCG-RL-fresh-clone-20260717
git rev-list --objects --all
git cat-file -e <restricted-blob-id>^{blob}
git lfs ls-files --all
gh release list --repo Ashok-19/Kaggle-PTCG-RL
gh workflow list --repo Ashok-19/Kaggle-PTCG-RL --all
gh api repos/Ashok-19/Kaggle-PTCG-RL/actions/artifacts
gh api -X GET users/Ashok-19/packages -f package_type=container
sha256sum ptcg-rl/uv.lock SANITIZED_SNAPSHOT_MANIFEST.json
git status --short --branch
```

## Failures And Deviations

- `ptcg audit-staged` was initially invoked from the snapshot root and could not
  resolve the nested `ptcg-rl` project. It was rerun from `ptcg-rl` and passed.
- `git diff --cached --check` returned exit code 2 on the unborn branch without
  diagnostics through the local command wrapper. The created root was checked
  after commit, and the staged repository audit passed.
- The Packages query could not be completed because the current token lacks
  `read:packages`; the gap is explicitly retained above.

## Next Action

Use the sanitized clone for all new work. Complete the G0 result-sentinel
regression and Python 3.11 primary runtime profile, then run the full G0 checks.
The dashboard may proceed through D0-D2 against this sanitized source while the
Packages gap remains visibly blocked; do not begin G1.
