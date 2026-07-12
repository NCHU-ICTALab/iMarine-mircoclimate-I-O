from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from ..config import ROOT, load_config
    from ..predict import TAIPEI
except ImportError:  # pragma: no cover
    from config import ROOT, load_config
    from predict import TAIPEI


def evaluate_wind_speed_gust_source_comparison(
    config_path: str | Path = "config.yaml",
    project_root: str | Path = ROOT,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    project = Path(project_root)
    cfg = load_config(config_path)
    out_dir = Path(output_dir) if output_dir is not None else project / "results" / "model_benchmark_v13" / "wind_speed_gust_source_comparison"
    out_dir.mkdir(parents=True, exist_ok=True)
    khwd_rows = _load_khwd_rows(project)
    available_rows = int(len(khwd_rows))
    min_required_rows = int(cfg.get("wind_speed_gust_source_comparison", {}).get("min_required_khwd_rows", 500))
    report = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "evaluation_mode": "insufficient_khwd_history_for_formal_scale",
        "candidate_source": "nearby_cwa_historical_model",
        "baseline_source": "legacy_lstm",
        "available_khwd_rows": available_rows,
        "min_required_khwd_rows": min_required_rows,
        "formal_comparison_ready": available_rows >= min_required_rows,
        "default_source_decision": cfg.get("wind_speed_gust_prediction_source", "legacy_lstm"),
        "recommended_default_source": "legacy_lstm",
        "decision_reason": (
            "KHWD history is not yet sufficient for a future-aligned MAE/R2 comparison, so the nearby CWA wind/gust model is wired as a candidate but not enabled by default."
        ),
        "metrics": {},
    }
    (out_dir / "comparison_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _load_khwd_rows(project: Path) -> pd.DataFrame:
    root = project / "data" / "raw" / "observed_hourly"
    rows = []
    for path in sorted(root.glob("KHWD*.csv")):
        try:
            frame = pd.read_csv(path)
        except Exception:
            continue
        if not {"obs_time", "wind_speed", "wind_gust"}.issubset(frame.columns):
            continue
        frame = frame[["obs_time", "wind_speed", "wind_gust"]].copy()
        frame["station_id"] = path.stem
        rows.append(frame)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def main() -> None:
    report = evaluate_wind_speed_gust_source_comparison()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
