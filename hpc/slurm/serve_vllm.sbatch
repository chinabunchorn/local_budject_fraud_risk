#!/bin/bash
#SBATCH --job-name=m3-vllm-serve
#SBATCH --account=ltXXXXXX            # TODO: LANTA project allocation
#SBATCH --partition=gpu               # TODO: confirm GPU partition name for your tier
#SBATCH --nodes=1
#SBATCH --gpus-per-node=4             # 4x A100 40GB
#SBATCH --cpus-per-task=32
#SBATCH --time=24:00:00               # TODO: confirm walltime limit on your tier
#SBATCH --output=%x-%j.out

# ============================================================================
# Serves the Thai chat model (Typhoon 2.5) via the vLLM OpenAI-compatible API
# on :8000 for the demo window. The app VM reaches it ONLY through the SSH
# tunnel (scripts/tunnel.sh) — this endpoint is ephemeral BY DESIGN and dies
# at walltime; scrontab.txt resubmits it.
# ============================================================================
set -euo pipefail

PROJECT_DIR="${LANTA_PROJECT_DIR:-/project/ltXXXXXX-mission3}"   # TODO
SIF="$PROJECT_DIR/containers/vllm.sif"
WEIGHTS="$PROJECT_DIR/models"          # pre-staged by scripts/stage_weights.sh
RUN_DIR="$PROJECT_DIR/run"
CHAT_MODEL="scb10x/typhoon2.5-qwen3-30b-a3b"

mkdir -p "$RUN_DIR"

# Publish the compute-node hostname so tunnel.sh can find us
hostname > "$RUN_DIR/current_node.txt"
echo "$SLURM_JOB_ID" > "$RUN_DIR/current_job.txt"

# Chat model: BF16, tensor-parallel 2 on GPUs 0-1.
# (GPU 2 reserved for Qwen3-32B AWQ if Phase-2 evals justify it; GPU 3 for
#  Typhoon-OCR — launch as separate processes with CUDA_VISIBLE_DEVICES.)
apptainer exec --nv \
    --bind "$WEIGHTS:/models" \
    --env CUDA_VISIBLE_DEVICES=0,1 \
    "$SIF" \
    python3 -m vllm.entrypoints.openai.api_server \
        --model "/models/$CHAT_MODEL" \
        --served-model-name "$CHAT_MODEL" \
        --tensor-parallel-size 2 \
        --dtype bfloat16 \
        --max-model-len 16384 \
        --guided-decoding-backend xgrammar \
        --host 0.0.0.0 \
        --port 8000
