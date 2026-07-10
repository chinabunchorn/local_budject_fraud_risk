#!/bin/bash
#SBATCH --job-name=m3-batch-infer
#SBATCH --account=ltXXXXXX            # TODO: LANTA project allocation
#SBATCH --partition=gpu               # TODO: confirm GPU partition name
#SBATCH --nodes=1
#SBATCH --gpus-per-node=4
#SBATCH --cpus-per-task=32
#SBATCH --time=12:00:00
#SBATCH --output=%x-%j.out

# ============================================================================
# Pipeline-1 primitive: offline batch inference (B6-B7).
# Reads staged prompt batches (JSONL) from Lustre scratch, generates
# schema-locked risk JSON at temperature 0 with XGrammar guided decoding,
# writes results back to scratch for SFTP pull + guardrails validation.
# Prefect stages inputs to $SCRATCH_DIR/batches/in/ and pulls from .../out/.
# ============================================================================
set -euo pipefail

PROJECT_DIR="${LANTA_PROJECT_DIR:-/project/ltXXXXXX-mission3}"   # TODO
SCRATCH_DIR="${LANTA_SCRATCH_DIR:-/scratch/ltXXXXXX-mission3}"   # TODO
SIF="$PROJECT_DIR/containers/vllm.sif"
WEIGHTS="$PROJECT_DIR/models"
BATCH_MODEL="scb10x/typhoon2.5-qwen3-30b-a3b"   # Phase-2 decision point: Qwen3-32B AWQ

IN_DIR="$SCRATCH_DIR/batches/in"
OUT_DIR="$SCRATCH_DIR/batches/out"
mkdir -p "$OUT_DIR"

# TODO(Phase 2): replace with the real batch runner from pipelines/ once the
# risk-scoring prompts exist. The runner must:
#   - load one JSONL of prompts per risk factor from $IN_DIR
#   - call vLLM offline inference with guided_json bound to the
#     schemas.RiskAssessment JSON schema, temperature 0
#   - write raw JSON outputs to $OUT_DIR (guardrails validation happens on
#     the app VM — NEVER write directly to PostgreSQL from here)
apptainer exec --nv \
    --bind "$WEIGHTS:/models" \
    --bind "$SCRATCH_DIR:/scratch" \
    "$SIF" \
    python3 -c "print('batch runner placeholder — implemented in Phase 2')"
