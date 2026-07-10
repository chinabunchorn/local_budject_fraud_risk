# LANTA HPC Configuration Notes

Working notes from hands-on setup and testing on LANTA, for the Local Budget Fraud Risk & Document Intelligence Assistant project. Compiled to fill in the placeholders flagged in `LANTA_BRIEF.md` and to record what actually worked, so the next session (or a teammate) doesn't have to re-discover it.

Last verified: July 2026.

## Account & Access

- Billing account (`#SBATCH --account=`, `#SCRON -A`): **`tn999991`**
- Descr on `sbalance`: `cstu`
- Login node: `lanta.nstda.or.th` (SSH + Google 2FA required on every connection)
- Transfer node: `transfer.lanta.nstda.or.th` (SSH + Google 2FA; this is the only node with outbound internet — used for all downloads/pulls)
- Both nodes require password + Google Authenticator 2FA. No verified exemption exists yet for automated/unattended connections (see Open Questions).

## Storage Layout

- Project storage root: `/project/tn999991-cstu` — **note the mismatch**: the billing account code (`tn999991`) is not the same string as the storage directory name (`tn999991-cstu`, with the `-cstu` descriptor suffix). Easy to trip on.
- Personal workspace within the shared project (kept separate since this project folder is shared with faculty): `/project/tn999991-cstu/chin/`
  - `models/` — staged model weights
  - `containers/` — Apptainer `.sif` images + `.apptainer_cache/` (redirected here via `APPTAINER_CACHEDIR` to avoid filling the 100GiB `/home` quota)
  - `documents/` — source documents for OCR batch processing (PDFs/images)
  - `ocr_results/` — OCR batch output (one `.md` per page/image)
  - job scripts (`.sbatch`), test scripts (`.py`), logs
- Quotas: `/home` 100GiB, `/project` 5,120GiB (shared across project), `/scratch` 900TiB (shared, purged after 30 days of no access). Check anytime with `myquota`.

## Partitions & Scheduling

| Partition | Walltime cap | Use |
|---|---|---|
| `gpu-devel` | 2h | Quick tests/smoke tests only — NOT for anything meant to stay up |
| `gpu` | 5 days | Real serving sessions, longer jobs |
| `gpu-limited` | 1 day | Free-tier queue; still showing active in `sinfo` as of July 2026 despite docs stating it was only meant to run through Oct 2025 — worth double-checking with ThaiSC support if relying on it |
| `compute-devel` | 2h | Cheap/lightweight CPU tasks (e.g. `scrontab` checker jobs, if ever enabled) |

Each `lanta-g-xxx` GPU node has 4× NVIDIA A100 40GB. Useful commands: `sbalance` (credit), `myqueue` (job status), `sinfo` (cluster status), `myquota` (storage).

**Lesson learned:** `gpu-devel`'s 2-hour cap will silently kill a "persistent" serving job. Use `gpu` partition for anything meant to survive longer than a quick test.

## Environment Setup (Mamba/conda)

- Module: `Mamba/23.11.0-0` (ThaiSC EasyBuild module)
- One-time setup: `mamba init` (modifies `~/.bashrc`; requires a fresh shell — `exec bash` — to take effect)
- Environment name used throughout: `hf`, Python 3.11
- Packages installed into `hf`: `huggingface_hub` (provides the `hf` CLI, `huggingface-cli` is deprecated), `torch` + `torchvision` (both pinned to **cu121** build, see CUDA gotcha below), `transformers`, `accelerate`, `pillow`, `requests`, `pymupdf`

**Gotcha:** `mamba activate <env>` silently fails inside non-interactive Slurm scripts unless `mamba init` has been run for that shell. Inside `.sbatch` scripts, use `mamba run -n <env> python ...` instead — it doesn't depend on shell initialization and is more robust.

## The CUDA/Driver Version Gotcha (recurring theme)

LANTA's GPU driver reports **CUDA 12.7 max supported**. Anything compiled against a newer CUDA toolkit (12.8, 12.9) fails at runtime with `RuntimeError: The NVIDIA driver on your system is too old`.

- Plain pip installs of `torch`/`torchvision`: use `--index-url https://download.pytorch.org/whl/cu121` explicitly — a bare `pip install torch` grabs the newest build (too new).
- vLLM official Docker images: the `latest` tag now ships CUDA 12.9 (incompatible). Verified working, CUDA-12.4-based tags:
  - `vllm/vllm-openai:v0.9.2` — works, but predates Qwen3-VL support (only good for text models)
  - `vllm/vllm-openai:v0.11.0` — works, and is the first version with Qwen3-VL support (needed for the OCR model). **Use this one for both models going forward** to avoid maintaining two container images.

## Containers (Apptainer)

- Module: `Apptainer/1.1.6`
- Pull images directly, no `--fakeroot`/root needed: `apptainer pull <dest>.sif docker://<image>:<tag>`
- Redirect build cache off `/home`: `export APPTAINER_CACHEDIR=/project/tn999991-cstu/chin/containers/.apptainer_cache`
- **Critical flags for every `apptainer exec --nv` call:**
  - `--cleanenv` — without this, host shell environment variables leak into the container
  - `--env PYTHONNOUSERSITE=1` — without this, stray packages in `~/.local/lib/python3.12/site-packages/` (since Apptainer shares `$HOME` by default) collide with the container's own bundled libraries and cause bizarre import errors (e.g. `torchvision::nms does not exist`)
  - `--bind /project/tn999991-cstu:/project/tn999991-cstu` — project storage is not auto-bound by default on this system
- Recommended image going forward: `vllm-v0110.sif` (from `vllm/vllm-openai:v0.11.0`)

## Models Staged

All downloaded via `hf download <repo>` from the **transfer node** (compute nodes have no internet) to `/project/tn999991-cstu/chin/models/`:

| Model | Size | Notes |
|---|---|---|
| `Qwen/Qwen2.5-0.5B-Instruct` | ~1GB | Small test model only |
| `scb10x/typhoon2.5-qwen3-30b-a3b` | ~62GB (31B, BF16, 3B active MoE) | Chat/RAG model. Requires `--tensor-parallel-size 2` (2×A100 needed) |
| `scb10x/typhoon-ocr1.5-2b` | ~4GB (2B, vision-language, `Qwen3VLForConditionalGeneration`) | OCR model. Task-specific — only works with its documented extraction prompt, not general chat |

All Apache 2.0 / open license, no HF token/gating required.

## Serving Setup (Chat Model)

Persistent `vllm serve` inside Apptainer, `gpu` partition, `--tensor-parallel-size 2`, `--max-model-len 8192` (default 256K context is impractical for KV cache on 2×40GB GPUs), `--gpu-memory-utilization 0.90`. Job writes its assigned node to `current_node.txt` for the tunnel step.

Verified working: `/v1/models`, non-streaming and streaming (`"stream": true`) chat completions, and **guided-JSON enum locking** via `"guided_choice": ["LOW", "MEDIUM", "HIGH", "REQUIRES_INVESTIGATION"]` — confirmed the model's output is structurally constrained to exactly one of the four risk-level strings, which is the actual mechanism behind the project's "flag, never accuse" rule.

## Tunnel Setup

Since compute nodes have no public IP, access from a local machine goes: local machine → login node (SSH) → compute node (port forward). From a fresh local terminal:

```
ssh -L 8000:<compute-node-hostname>:8000 tn991035@lanta.nstda.or.th -N
```

Then `curl http://localhost:8000/v1/models` from the local machine reaches the LANTA-hosted server. Confirmed working end-to-end.

## OCR Batch Pipeline (Document Prep)

**Architecture decision:** OCR runs as a batch job (file(s) in → markdown out), not a persistent server — matches the project's existing "offline batch" workload pattern (same shape as `batch_infer.sbatch`). No GPU sits idle waiting for requests; a job processes whatever's in `documents/` and exits.

- PDFs are not natively readable by the vision-language model — each page must be rendered to an image first. Used `PyMuPDF` (`pip install pymupdf`, `import fitz`) rather than `pdf2image`/`poppler`, since `poppler` needs a system-level binary install that requires root (unavailable on LANTA).
- Pages resized to ~1800px on the long edge before OCR (matches the model's training resolution).
- **Verified on real data:** a real 33-page เทศบาลตำบลท่าช้าง financial report (scanned, zero embedded text layer) processed cleanly in a single job — correctly extracted complex Thai financial tables, exact baht figures, and signature blocks. Full pipeline validated end-to-end on production-representative input, not just synthetic test images.

## Kill-and-Recovery

Tested (accidentally, then deliberately): the `gpu-devel` partition's 2-hour walltime cap killed the persistent chat server mid-session. Confirmed this matches the intended "graceful degradation" behavior — the tunnel simply stops responding, nothing else breaks (the OCR batch job running independently on the same node was unaffected). Recovery is a manual `sbatch` resubmit + re-checking `current_node.txt` + reopening the tunnel if the node changed.

## Automation Status: NOT fully automatic (open item)

`scrontab` is confirmed **disabled** on LANTA (`scrontab: fatal: scrontab is disabled on this cluster`). This resolves the open question from the original checklist, but in the negative — LANTA-native cron-style automation is not available.

Per the project's own architecture (`scrontab (or Prefect from the app VM) resubmits`), the fallback is to run the check-and-resubmit logic from the **always-on app VM** instead of from LANTA, via a normal cron job there that SSHes into the LANTA login node:

```
*/15 * * * * ssh -i <deploy_key> tn991035@lanta.nstda.or.th 'bash /project/tn999991-cstu/chin/check_and_resubmit.sh'
```

The `check_and_resubmit.sh` script (checks `squeue` for the serving job by name; resubmits `serve_typhoon.sbatch` if absent) is written and ready.

**Unresolved blocker:** LANTA requires SSH + Google 2FA on every connection, as tested. It is not confirmed whether a dedicated automation/deploy SSH key is exempted from this requirement. If not, an unattended cron job cannot log in at all, since no one is present to enter the 2FA code. **This needs a direct question to `thaisc-support@nstda.or.th`**: does a registered deploy key bypass 2FA for non-interactive/automated connections, or is there a sanctioned alternative for scheduled unattended access to the login node? Until answered, resubmission after a job death remains a manual step.

## Open Questions Still Outstanding (for ThaiSC support)

1. Whether a dedicated deploy/automation SSH key can bypass the Google 2FA requirement (blocks full automation — see above).
2. Whether the `gpu-limited` partition (shown active in `sinfo`) is still actually valid, given docs stated it was only available through October 2025.
3. Recommended production pattern for building custom Apptainer images from a `.def` file (we only tested `apptainer pull` of pre-built images; building from source with `%post` install steps wasn't tried, and may need `--fakeroot`).
