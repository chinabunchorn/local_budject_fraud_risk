#!/bin/bash
# ============================================================================
# Pre-stage model weights to Lustre project storage.
# RUN ON THE LANTA TRANSFER NODE (it has internet; compute nodes do NOT).
#
# Usage:  ./stage_weights.sh [target_dir]
# Needs:  pip install --user huggingface_hub  (on the transfer node)
# ============================================================================
set -euo pipefail

TARGET="${1:-${LANTA_PROJECT_DIR:-/project/ltXXXXXX-mission3}/models}"   # TODO

# Phase 1: chat + OCR. Qwen3-32B AWQ is deferred to the Phase-2 decision point.
MODELS=(
    "scb10x/typhoon2.5-qwen3-30b-a3b"
    "scb10x/typhoon-ocr1.5-2b"
    # "Qwen/Qwen3-32B-AWQ"            # add ONLY if Phase-2 quality evals justify it
)

mkdir -p "$TARGET"
for model in "${MODELS[@]}"; do
    echo ">>> staging $model -> $TARGET/$model"
    huggingface-cli download "$model" \
        --local-dir "$TARGET/$model" \
        --exclude "*.bin" "*.pth" "*.gguf"   # safetensors only
done

echo ">>> staged models:"
du -sh "$TARGET"/*/*  2>/dev/null || du -sh "$TARGET"/*
echo ">>> done. Compute jobs bind-mount $TARGET at /models (HF_HUB_OFFLINE=1)."
