#!/bin/bash
#SBATCH --job-name=m3-vllm-serve
#SBATCH --account=tn999991            # billing account (sbalance descr: cstu)
#SBATCH --partition=gpu               # 5-day cap. gpu-devel (2h) is for smoke tests ONLY —
                                      # its walltime WILL kill a "persistent" server
#SBATCH --nodes=1
#SBATCH --gpus-per-node=2             # chat model needs tensor-parallel 2 (2x A100 40GB)
#SBATCH --cpus-per-task=16
#SBATCH --time=24:00:00
#SBATCH --output=%x-%j.out

# ============================================================================
# Serves the Thai chat model (Typhoon 2.5) via the vLLM OpenAI-compatible API
# on :8000 for the demo window. The app VM reaches it ONLY through the SSH
# tunnel (scripts/tunnel.sh) — this endpoint is ephemeral BY DESIGN and dies
# at walltime. scrontab is DISABLED on LANTA: resubmission runs from the
# always-on app VM instead (see slurm/scrontab.txt for the cron pattern).
# Verified end-to-end July 2026 — see hpc/LANTA_CONFIG_NOTES.md.
# ============================================================================
set -euo pipefail

module load Apptainer/1.1.6

PROJECT_DIR="${LANTA_PROJECT_DIR:-/project/tn999991-cstu/chin}"
SIF="$PROJECT_DIR/containers/vllm-v0110.sif"   # vLLM v0.11.0 — CUDA <= 12.7 only (driver limit)
WEIGHTS="$PROJECT_DIR/models"                  # pre-staged by scripts/stage_weights.sh
RUN_DIR="$PROJECT_DIR/run"
CHAT_MODEL="scb10x/typhoon2.5-qwen3-30b-a3b"

mkdir -p "$RUN_DIR"

# Publish the compute-node hostname so tunnel.sh can find us
hostname > "$RUN_DIR/current_node.txt"
echo "$SLURM_JOB_ID" > "$RUN_DIR/current_job.txt"

# Chat model: BF16, tensor-parallel 2.
# --cleanenv + PYTHONNOUSERSITE=1 + explicit --bind are all REQUIRED on LANTA
# (host env leakage / ~/.local package shadowing / project storage not auto-bound).
# --max-model-len 8192: the model's 256K default blows the KV-cache budget on
# 2x40GB; 8192 is the verified setting and covers chunked Thai legal documents.
# Guided decoding (guided_choice / guided_json) is available per-request by
# default in v0.11.0 — the enum lock was verified against this exact setup.
apptainer exec --nv \
    --cleanenv \
    --env PYTHONNOUSERSITE=1 \
    --env HF_HUB_OFFLINE=1 \
    --bind /project/tn999991-cstu:/project/tn999991-cstu \
    "$SIF" \
    vllm serve "$WEIGHTS/$CHAT_MODEL" \
        --served-model-name "$CHAT_MODEL" \
        --tensor-parallel-size 2 \
        --dtype bfloat16 \
        --max-model-len 8192 \
        --gpu-memory-utilization 0.90 \
        --host 0.0.0.0 \
        --port 8000
