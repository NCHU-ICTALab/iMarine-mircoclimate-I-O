from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import ROOT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="高雄港微氣候預測系統")
    parser.add_argument("--project-root", default=str(ROOT))
    subparsers = parser.add_subparsers(dest="command", required=True)

    download = subparsers.add_parser("download", help="Load locally available source data into a tabular output")
    download.add_argument("--source", required=True, choices=["cwa", "codis", "harbor", "twport", "observed_hourly", "all"])
    download.add_argument("--start-date", required=True)
    download.add_argument("--end-date", required=True)
    download.add_argument("--stations", nargs="*")
    download.add_argument("--output", required=True)

    preprocess = subparsers.add_parser("preprocess", help="Preprocess a CSV or Parquet file")
    preprocess.add_argument("--input", required=True)
    preprocess.add_argument("--output", required=True)
    preprocess.add_argument("--config", default=None)

    features = subparsers.add_parser("features", help="Create feature table")
    features.add_argument("--input", required=True)
    features.add_argument("--output", required=True)
    features.add_argument("--variable", required=True)
    features.add_argument("--config", default=None)

    train = subparsers.add_parser("train", help="Train a station target model")
    train.add_argument("--station-id", required=True)
    train.add_argument("--target", required=True)
    train.add_argument("--data-path", required=True)
    train.add_argument("--config", default="config.yaml")

    evaluate = subparsers.add_parser("evaluate", help="Evaluate a trained model")
    evaluate.add_argument("--station-id", required=True)
    evaluate.add_argument("--target", required=True)
    evaluate.add_argument("--config", default="config.yaml")

    predict = subparsers.add_parser("predict", help="Run anchor prediction for recent observations")
    predict.add_argument("--station-id", required=True)
    predict.add_argument("--target", required=True)
    predict.add_argument("--data-path", required=True)
    predict.add_argument("--config", default="config.yaml")
    predict.add_argument("--uncertainty", action="store_true")

    dispatch = subparsers.add_parser("dispatch-risk", help="Run dispatch risk prediction")
    dispatch.add_argument("--target-area", default="KHH")
    dispatch.add_argument("--fallback-station-id", default="467441")
    dispatch.add_argument("--config", default="config.yaml")
    dispatch.add_argument("--no-realtime-khwd-mode", action="store_true")

    audit = subparsers.add_parser("system-audit", help="Build v3.5 system audit")
    audit.add_argument("--target-area", default="KHH")
    audit.add_argument("--config", default="config.yaml")
    audit.add_argument("--report-dir", default=None)

    run_all = subparsers.add_parser("run-all", help="Run a lightweight v2.0 data -> features manifest flow")
    run_all.add_argument("--start-date", required=True)
    run_all.add_argument("--end-date", required=True)
    run_all.add_argument("--config", default=None)
    run_all.add_argument("--output", default="results/run_all_manifest.json")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    project_root = Path(args.project_root)

    if args.command == "download":
        from .data.api import DataAPI

        frame = DataAPI.collect_data(args.source, args.start_date, args.end_date, args.stations, project_root / "data" / "raw")
        _write_frame(frame, Path(args.output))
        print(json.dumps({"rows": int(len(frame)), "output": args.output}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "preprocess":
        from .data.api import DataAPI

        frame = _read_frame(Path(args.input))
        processed = DataAPI.preprocess_data(frame, {})
        _write_frame(processed, Path(args.output))
        print(json.dumps({"rows": int(len(processed)), "output": args.output}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "features":
        from .features.api import FeatureAPI

        frame = _read_frame(Path(args.input))
        features = FeatureAPI.create_features(frame, args.variable, {"variables": [args.variable]})
        _write_frame(features.reset_index(), Path(args.output))
        print(json.dumps({"rows": int(len(features)), "columns": int(len(features.columns)), "output": args.output}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "train":
        from .train import train_model

        path = train_model(args.station_id, args.target, args.data_path, args.config, project_root)
        print(json.dumps({"checkpoint": str(path)}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "evaluate":
        from .evaluate import evaluate_model

        report = evaluate_model(args.station_id, args.target, args.config, project_root)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "predict":
        from .predict import predict
        from .preprocess import load_observations

        observations = load_observations(args.data_path)
        result = predict(args.station_id, args.target, observations, args.config, args.uncertainty, project_root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "dispatch-risk":
        from .predict import predict_dispatch_risk_current
        from .preprocess import load_observations

        data_path = project_root / "data" / "raw" / "observed_hourly" / f"{args.fallback_station_id}.csv"
        observations = load_observations(data_path)
        result = predict_dispatch_risk_current(
            fallback_observations=observations,
            config_path=args.config,
            project_root=project_root,
            target_area=args.target_area,
            no_realtime_khwd_mode=args.no_realtime_khwd_mode,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "system-audit":
        from .system_audit import build_v35_system_audit

        report_dir = Path(args.report_dir) if args.report_dir else project_root / "results" / "dispatch_risk_v35"
        result = build_v35_system_audit(args.config, args.target_area, report_dir, project_root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "run-all":
        manifest = {
            "start_date": args.start_date,
            "end_date": args.end_date,
            "project_root": str(project_root),
            "steps": ["download", "preprocess", "features", "train", "evaluate", "predict"],
            "note": "run-all is a lightweight manifest command; source-specific network collection and long training are executed by dedicated commands/tools.",
        }
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"manifest": str(out)}, ensure_ascii=False, indent=2))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


def _read_frame(path: Path):
    import pandas as pd

    return pd.read_parquet(path) if path.suffix.lower() in {".parquet", ".pq"} else pd.read_csv(path)


def _write_frame(frame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in {".parquet", ".pq"}:
        frame.to_parquet(path, index=False)
    else:
        frame.to_csv(path, index=False)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
