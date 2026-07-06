from __future__ import annotations

import argparse
from pathlib import Path

from src.config import ROOT, load_config
from src.preprocess import load_observations
from src.train import train_model


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", default="data/raw")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--station_column", default="station_id")
    args = parser.parse_args()
    cfg = load_config(args.config)
    data_dir = ROOT / args.data_dir
    files = sorted([*data_dir.glob("*.csv"), *data_dir.glob("*.parquet")])
    if not files:
        raise SystemExit(f"No CSV/Parquet files found in {data_dir}")
    for path in files:
        df = load_observations(path)
        if args.station_column in df.columns:
            station_ids = sorted(df[args.station_column].dropna().astype(str).unique())
        else:
            station_ids = [path.stem]
        for station_id in station_ids:
            for target in cfg["targets"]:
                try:
                    train_model(station_id, target, path, args.config, ROOT)
                except Exception as exc:  # keep batch jobs moving
                    print(f"skip {station_id}/{target}: {exc}")


if __name__ == "__main__":
    main()
