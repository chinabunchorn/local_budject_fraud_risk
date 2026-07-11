"""OCR-batch staging between the app VM and LANTA — an ATTENDED runbook tool.

LANTA enforces password + Google 2FA on every SSH connection (see
hpc/LANTA_CONFIG_NOTES.md), so none of this runs unattended. SSH connection
multiplexing (ControlMaster) means you authenticate ONCE per session; every
following command reuses the open connection.

Runbook (Phase-1-verified pattern, documents/ in → ocr_results/ out):

    python -m hpc_io.ocr_batch stage    # outbox PDFs → $LANTA_PROJECT_DIR/documents/
    python -m hpc_io.ocr_batch submit   # sbatch the OCR job
    python -m hpc_io.ocr_batch status   # squeue for your jobs
    python -m hpc_io.ocr_batch fetch    # ocr_results/ → local dir
    # then: uv run python -m flows.ingest_documents  (pass 2, with ocr_results_dir)

Configuration via env (.env): LANTA_SSH_HOST, LANTA_SSH_USER,
LANTA_PROJECT_DIR; optional LANTA_OCR_SBATCH (default
$LANTA_PROJECT_DIR/slurm/ocr_batch.sbatch — must match the script actually
staged on LANTA).

Every command is printed before it runs — no hidden side effects.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

_CONTROL_OPTS = [
    "-o", "ControlMaster=auto",
    "-o", "ControlPath=~/.ssh/lanta-%r@%h-%p",
    "-o", "ControlPersist=15m",
]


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value or value == "CHANGE_ME":
        sys.exit(f"error: {name} is not configured (set it in .env)")
    return value


def _target() -> str:
    return f"{_env('LANTA_SSH_USER')}@{_env('LANTA_SSH_HOST', 'lanta.nstda.or.th')}"


def _run(cmd: list[str]) -> int:
    print("+", " ".join(shlex.quote(part) for part in cmd), flush=True)
    return subprocess.call(cmd)


def _ssh(remote_command: str) -> int:
    return _run(["ssh", *_CONTROL_OPTS, _target(), remote_command])


def stage(outbox_dir: str) -> int:
    outbox = Path(outbox_dir)
    pdfs = sorted(outbox.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"error: no PDFs in {outbox} — run the ingestion flow (pass 1) first")
    remote_docs = f"{_env('LANTA_PROJECT_DIR')}/documents"
    if (code := _ssh(f"mkdir -p {shlex.quote(remote_docs)}")) != 0:
        return code
    print(f"staging {len(pdfs)} PDF(s) → {remote_docs}/")
    return _run(
        ["scp", *_CONTROL_OPTS, *[str(p) for p in pdfs], f"{_target()}:{remote_docs}/"]
    )


def submit() -> int:
    project_dir = _env("LANTA_PROJECT_DIR")
    sbatch_path = os.environ.get("LANTA_OCR_SBATCH", f"{project_dir}/slurm/ocr_batch.sbatch")
    return _ssh(f"cd {shlex.quote(project_dir)} && sbatch {shlex.quote(sbatch_path)}")


def status() -> int:
    return _ssh(f"squeue -u {_env('LANTA_SSH_USER')} -o '%.10i %.20j %.8T %.10M %R'")


def fetch(results_dir: str) -> int:
    remote_results = f"{_env('LANTA_PROJECT_DIR')}/ocr_results"
    Path(results_dir).mkdir(parents=True, exist_ok=True)
    print(f"fetching {remote_results}/ → {results_dir}/")
    return _run(
        ["scp", *_CONTROL_OPTS, "-r", f"{_target()}:{remote_results}/.", results_dir]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_stage = sub.add_parser("stage", help="upload OCR-outbox PDFs to LANTA documents/")
    p_stage.add_argument("--outbox", default="../data/ocr_outbox")
    sub.add_parser("submit", help="sbatch the OCR job on LANTA")
    sub.add_parser("status", help="squeue for your LANTA jobs")
    p_fetch = sub.add_parser("fetch", help="download ocr_results/ from LANTA")
    p_fetch.add_argument("--into", default="../data/ocr_results")
    args = parser.parse_args()

    if args.command == "stage":
        sys.exit(stage(args.outbox))
    if args.command == "submit":
        sys.exit(submit())
    if args.command == "status":
        sys.exit(status())
    if args.command == "fetch":
        sys.exit(fetch(args.into))


if __name__ == "__main__":
    main()
