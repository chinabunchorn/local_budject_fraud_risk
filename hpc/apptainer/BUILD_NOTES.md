# Building/obtaining the vLLM image for LANTA

**Verified working path (July 2026):** pull the official image directly on the login
node — no custom build, no root, no `--fakeroot` needed:

```bash
module load Apptainer/1.1.6
export APPTAINER_CACHEDIR=/project/tn999991-cstu/chin/containers/.apptainer_cache  # keep cache off the 100GiB /home
apptainer pull vllm-v0110.sif docker://vllm/vllm-openai:v0.11.0
```

## Image tag rules (learned the hard way)

- **LANTA's GPU driver supports CUDA ≤ 12.7.** vLLM `latest` ships CUDA 12.9 and dies
  at runtime with `RuntimeError: The NVIDIA driver on your system is too old`.
- Verified good: `vllm/vllm-openai:v0.11.0` (CUDA 12.4; first tag with Qwen3-VL
  support, which Typhoon-OCR 1.5 needs). `v0.9.2` also runs but has no Qwen3-VL —
  don't use it; one image serves both models.
- **A100 40GB = Ampere.** BF16 or AWQ/GPTQ-INT4 checkpoints only. Never FP8, never
  GGUF (llama.cpp format; vLLM wants safetensors/AWQ repos).

## Required flags on every `apptainer exec --nv` (verified)

```bash
apptainer exec --nv \
    --cleanenv \                                      # host env leaks in otherwise
    --env PYTHONNOUSERSITE=1 \                        # ~/.local packages shadow container libs otherwise
    --bind /project/tn999991-cstu:/project/tn999991-cstu \   # project storage NOT auto-bound
    vllm-v0110.sif ...
```

Skipping `PYTHONNOUSERSITE=1` causes bizarre import errors (e.g.
`torchvision::nms does not exist`) because Apptainer shares `$HOME` by default.

- **Never build or pull on compute nodes** — they have no internet.
- Smoke-test before scheduling:
  `apptainer exec --nv vllm-v0110.sif python3 -c "import vllm; print(vllm.__version__)"`
- Custom builds from this `.def` (with `%post` steps) are untried on LANTA and may
  need `--fakeroot` — open question with ThaiSC support.
