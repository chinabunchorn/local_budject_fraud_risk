#!/bin/bash
#SBATCH --partition=gpu-devel
#SBATCH --nodes=1
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --time=00:30:00
#SBATCH -J chin_ocr_batch
#SBATCH -A tn999991

module purge
module load Mamba/23.11.0-0

srun mamba run -n hf python /project/tn999991-cstu/chin/batch_ocr.py
