# Building `vllm.sif` for LANTA

- **Pin the base image.** `vllm/vllm-openai:v0.9.1` is a placeholder pin — verify the
  current stable tag before building, then keep it fixed for reproducibility.
- **A100 40GB = Ampere.** No FP8 tensor cores: use BF16 or AWQ/GPTQ-INT4 checkpoints.
  Never FP8, never GGUF (GGUF is a llama.cpp format; vLLM wants safetensors/AWQ repos).
- **Where to build.** Either on the LANTA login node (`apptainer build vllm.sif vllm.def`)
  or locally on any Linux box with Apptainer, then SFTP the `.sif` to
  `$LANTA_PROJECT_DIR/containers/`.
- **Never rebuild on compute nodes** — they have no internet access.
- Smoke-test the image before scheduling:
  `apptainer exec --nv vllm.sif python3 -c "import vllm; print(vllm.__version__)"`
