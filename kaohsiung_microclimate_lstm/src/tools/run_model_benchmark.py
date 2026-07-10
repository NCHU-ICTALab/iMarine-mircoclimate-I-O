from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from ..model_wrappers import benchmark_regressors


ROOT = Path(__file__).resolve().parents[2]


def run_model_benchmark(
    dataset_path: str | Path,
    target_column: str,
    output_dir: str | Path = ROOT / "results" / "model_benchmark_v13",
    config_path: str | Path | None = ROOT / "config.yaml",
    algorithms: list[str] | None = None,
    test_fraction: float = 0.2,
) -> dict[str, Any]:
    frame = _read_dataset(Path(dataset_path))
    if target_column not in frame.columns:
        raise ValueError(f"target column is missing: {target_column}")
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must be between 0 and 1")

    feature_frame = frame.drop(columns=[target_column])
    numeric_features = feature_frame.select_dtypes(include=["number"]).columns.tolist()
    if not numeric_features:
        raise ValueError("benchmark dataset must contain at least one numeric feature column")

    prepared = pd.concat([feature_frame[numeric_features], frame[[target_column]]], axis=1).dropna()
    if len(prepared) < 5:
        raise ValueError("benchmark dataset needs at least 5 complete rows")

    split_index = max(1, min(len(prepared) - 1, int(len(prepared) * (1 - test_fraction))))
    train = prepared.iloc[:split_index]
    test = prepared.iloc[split_index:]
    config = _load_benchmark_config(config_path)
    selected_algorithms = algorithms or config.get("algorithms") or ["random_forest", "lightgbm", "xgboost"]

    results = benchmark_regressors(
        train[numeric_features],
        train[target_column],
        test[numeric_features],
        test[target_column],
        config=config,
        algorithms=selected_algorithms,
    )
    report = {
        "dataset_path": str(dataset_path),
        "target_column": target_column,
        "feature_columns": numeric_features,
        "rows_total": int(len(prepared)),
        "rows_train": int(len(train)),
        "rows_test": int(len(test)),
        "requested_algorithms": selected_algorithms,
        "results": results,
    }

    output_path = Path(output_dir) / "benchmark_report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(output_path)
    return report


def _read_dataset(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def _load_benchmark_config(config_path: str | Path | None) -> dict[str, Any]:
    if not config_path:
        return {}
    path = Path(config_path)
    if not path.exists():
        return {}
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return config.get("model_benchmark", {})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output-dir", default=str(ROOT / "results" / "model_benchmark_v13"))
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--algorithms", default=None)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    args = parser.parse_args()

    algorithms = [item.strip() for item in args.algorithms.split(",") if item.strip()] if args.algorithms else None
    report = run_model_benchmark(
        dataset_path=args.dataset,
        target_column=args.target,
        output_dir=args.output_dir,
        config_path=args.config,
        algorithms=algorithms,
        test_fraction=args.test_fraction,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
