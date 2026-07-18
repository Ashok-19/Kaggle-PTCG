#!/bin/sh
set -eu

: "${PTCG_ENGINE_ROOT:?set PTCG_ENGINE_ROOT to the private sample_submission directory}"
: "${PTCG_CARD_DATA:?set PTCG_CARD_DATA to the private English card CSV}"
: "${PTCG_DECK_PATH:?set PTCG_DECK_PATH to a private 60-card deck.csv}"

G1_GAMES="${G1_GAMES:-50}"
G1_REQUEST_CAP="${G1_REQUEST_CAP:-20000}"
G1_WALL_SECONDS="${G1_WALL_SECONDS:-1800}"

uv sync --frozen --group dev --group dashboard
uv run --no-sync ptcg g1 cloud-validate \
  --contract-only \
  --engine-root "$PTCG_ENGINE_ROOT" \
  --card-data "$PTCG_CARD_DATA" \
  --deck "$PTCG_DECK_PATH" \
  --games "$G1_GAMES" \
  --request-cap "$G1_REQUEST_CAP" \
  --wall-seconds "$G1_WALL_SECONDS"
