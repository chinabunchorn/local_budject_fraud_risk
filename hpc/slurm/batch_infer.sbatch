#!/bin/bash
#SBATCH --job-name=m3-batch-infer
#SBATCH --account=tn999991            # billing account (sbalance descr: cstu)
#SBATCH --partition=gpu               # gpu-devel (2h cap) is fine for small test batches
#SBATCH --nodes=1
#SBATCH --gpus-per-node=2             # BATCH_MODEL below is the 30B chat model (needs TP2,
                                       # see hpc/LANTA_CONFIG_NOTES.md); drop to 1 GPU only if
                                       # this job is dedicated to the 2B OCR / INT4 batch models
#SBATCH --cpus-per-task=16
#SBATCH --time=12:00:00
#SBATCH --output=%x-%j.out

# ============================================================================
# Pipeline-1 primitive: offline batch inference (B6-B7).
# Reads staged inputs from Lustre, generates schema-locked risk JSON at
# temperature 0 with guided decoding, writes results back for SFTP pull +
# guardrails validation on the app VM.
# The OCR document batch (PDF pages -> markdown via Typhoon-OCR) follows this
# same file-in/file-out shape and was verified on a real 33-page scanned Thai
# financial report — see hpc/LANTA_CONFIG_NOTES.md.
# ============================================================================
set -euo pipefail

module load Apptainer/1.1.6

PROJECT_DIR="${LANTA_PROJECT_DIR:-/project/tn999991-cstu/chin}"
SCRATCH_DIR="${LANTA_SCRATCH_DIR:-$PROJECT_DIR/batches}"   # /scratch is purged after 30 idle days
SIF="$PROJECT_DIR/containers/vllm-v0110.sif"
WEIGHTS="$PROJECT_DIR/models"
BATCH_MODEL="scb10x/typhoon2.5-qwen3-30b-a3b"   # Phase-2 decision point: Qwen3-32B AWQ
# NOTE: BATCH_MODEL and --gpus-per-node above must stay in sync. The 30B chat
# model requires --tensor-parallel-size 2 (2 GPUs); the 2B OCR model and any
# future INT4 batch model fit on 1 GPU. If Phase 2 splits this into separate
# risk-scoring vs. OCR sbatch scripts, right-size --gpus-per-node per script.

IN_DIR="$SCRATCH_DIR/in"
OUT_DIR="$SCRATCH_DIR/out"
mkdir -p "$OUT_DIR"

# TODO(Phase 2): replace with the real batch runner from pipelines/ once the
# risk-scoring prompts exist. The runner must:
#   - load one JSONL of prompts per risk factor from $IN_DIR
#   - call vLLM offline inference with guided_json bound to the
#     schemas.RiskAssessment JSON schema, temperature 0
#   - write raw JSON outputs to $OUT_DIR (guardrails validation happens on
#     the app VM — NEVER write directly to PostgreSQL from here)
apptainer exec --nv \
    --cleanenv \
    --env PYTHONNOUSERSITE=1 \
    --env HF_HUB_OFFLINE=1 \
    --bind "$PROJECT_DIR:$PROJECT_DIR" \
    "$SIF" \
    python3 -c "print('batch runner placeholder — implemented in Phase 2')"
