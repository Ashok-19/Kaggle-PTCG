#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: $0 CONTAINER IMAGE ptcg-arguments..." >&2
  exit 2
fi

container=$1
image=$2
shift 2
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

docker image inspect "$image" >/dev/null
docker run --detach --pull never --name "$container" --network none \
  --user "$(id -u):$(id -g)" --env HOME=/tmp --env PYTHONPATH=/workspace/src \
  --volume "$repo:/workspace" --workdir /workspace "$image" \
  python -m ptcg_rl.cli "$@"
docker inspect --format '{{.Id}} {{.State.Running}} {{.State.Pid}}' "$container"
