# Local Kaggle MCP Contract — To Be Completed on the User’s Machine

Do not guess these fields. The user will provide/confirm them when replay Gate R0 begins.

## Server and authentication

- MCP server name:
- Authentication method:
- Credential location/secret name (never paste token):
- Required competition/dataset consent already accepted: yes/no

## Exact tools

### Dataset metadata/version

- Tool name:
- Input schema:
- Output schema:
- Pagination:

### List or retrieve one named file

- Tool name:
- Input schema:
- Can pin dataset version: yes/no
- Can request exactly `manifest.csv`: yes/no
- Can request exactly `<episode_id>.json`: yes/no
- Output is local path / bytes / resource / URL:
- Destination behavior:
- Size/timeout limits:

### Structured inbox receipt

For every delivered file, the MCP bridge must also produce machine-readable JSON with:

- dataset owner and slug;
- resolved integer version;
- requested filename;
- actual bytes and SHA-256;
- retrieval timestamp;
- provider/tool identity.

The importer must reject a missing receipt, an unpinned/latest-only version, a filename mismatch or a hash/byte mismatch. Record the exact method by which the MCP resolves and proves `currentVersionNumber`:

- Metadata/version tool:
- Receipt generation method:
- Version/hash fields verified by Python:

## Required probes

Record command/tool input and redacted result for:

1. index dataset `manifest.csv` only;
2. one recent daily dataset `manifest.csv` only;
3. generate an immutable one-episode probe plan for a manifest-listed episode under 1 MiB (or the smallest non-error-risk file), review its zero-write dry run, and only then execute that exact approved plan;
4. a deliberately missing filename as a metadata/no-fallback test only (must fail without initiating a dataset download).

## Decision

- Provider accepted for single-file workflow: yes/no
- Reason:
- Fallback provider if rejected: official KaggleHub single-file download
- Verified date/version:

Recommended integration is an inbox bridge: Python exports a hashed plan, local Codex invokes MCP for the exact plan items, and Python independently verifies and promotes files. Ordinary Python training code must not assume an interactive MCP is callable.
