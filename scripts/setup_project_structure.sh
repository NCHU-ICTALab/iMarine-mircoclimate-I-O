#!/usr/bin/env bash
set -euo pipefail

directories=(
  "config"
  "data/raw/cwa"
  "data/raw/codis"
  "data/raw/harbor"
  "data/processed/merged"
  "data/processed/features"
  "data/processed/train_test_split"
  "data/external"
  "notebooks"
  "kaohsiung_microclimate_lstm/src/data"
  "kaohsiung_microclimate_lstm/src/features"
  "kaohsiung_microclimate_lstm/src/models"
  "kaohsiung_microclimate_lstm/src/evaluation"
  "kaohsiung_microclimate_lstm/src/visualization"
  "kaohsiung_microclimate_lstm/src/utils"
  "scripts"
  "tests"
  "kaohsiung_microclimate_lstm/models/rainfall"
  "kaohsiung_microclimate_lstm/models/wind"
  "kaohsiung_microclimate_lstm/models/visibility"
  "kaohsiung_microclimate_lstm/models/tide"
  "kaohsiung_microclimate_lstm/results/metrics"
  "kaohsiung_microclimate_lstm/results/predictions"
  "kaohsiung_microclimate_lstm/results/figures"
  "kaohsiung_microclimate_lstm/results/reports"
  "docs"
  "logs"
)

for directory in "${directories[@]}"; do
  mkdir -p "${directory}"
done

touch kaohsiung_microclimate_lstm/src/__init__.py
touch tests/__init__.py

echo "Project structure is ready."
