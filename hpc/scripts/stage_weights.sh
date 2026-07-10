#!/bin/bash
# ============================================================================
# Pre-stage model weights to Lustre project storage.
# RUN ON THE LANTA TRANSFER NODE: transfer.lanta.nstda.or.th — the ONLY node
# with outbound internet (compute nodes have none). Verified July 2026.
#
# Usage:  ./stage_weights.sh [target_dir]
# Needs:  the `hf` CLI from huggingface_hub in a Mamba env, e.g.:
#           module load Mamba/23.11.0-0 && mamba run -n hf hf download ...
#         (`huggingface-cli` is deprecated; use `hf`)
# ============================================================================
set -euo pipefail

TARGET="${1:-${LANTA_PROJECT_DIR:-/project/tn999991-cstu/chin}/models}"

# Phase 1 (staged, done): chat + OCR. Qwen3-32B AWQ deferred to Phase-2 decision point.
MODELS=(
    "scb10x/typhoon2.5-qwen3-30b-a3b"   # ~62GB BF16 — chat/RAG, needs TP2
    "scb10x/typhoon-ocr1.5-2b"          # ~4GB — Thai OCR (Qwen3-VL; needs vLLM >= 0.11)
    # "Qwen/Qwen3-32B-AWQ"              # ~19GB — add ONLY if Phase-2 quality evals justify it
)

mkdir -p "$TARGET"
for model in "${MODELS[@]}"; do
    echo ">>> staging $model -> $TARGET/$model"
    hf download "$model" \
        --local-dir "$TARGET/$model" \
        --exclude "*.bin" "*.pth" "*.gguf"   # safetensors only
done

echo ">>> staged models:"
du -sh "$TARGET"/*/*  2>/dev/null || du -sh "$TARGET"/*
echo ">>> done. Compute jobs bind-mount $TARGET at /models (HF_HUB_OFFLINE=1)."
