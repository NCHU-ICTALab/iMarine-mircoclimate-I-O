from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from ..config import load_config
    from ..cwa.cwa_open_data_client import load_cwa_api_key
    from ..cwa.location_resolver import resolve_cwa_forecast_source
except ImportError:  # pragma: no cover
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from config import load_config
    from cwa.cwa_open_data_client import load_cwa_api_key
    from cwa.location_resolver import resolve_cwa_forecast_source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="kaohsiung_microclimate_lstm/config.yaml")
    parser.add_argument("--output", default="kaohsiung_microclimate_lstm/config/resolved_cwa_forecast_source.json")
    parser.add_argument("--project-root", default="kaohsiung_microclimate_lstm")
    args = parser.parse_args()

    cfg = load_config(args.config)
    cwa_cfg = cfg.get("cwa_open_data", {})
    result = resolve_cwa_forecast_source(
        cwa_cfg.get("pop_datasets", {}).get("candidates", []),
        [str(item) for item in cwa_cfg.get("location_candidates", [])],
        cwa_cfg.get("element_name_candidates", {}),
        load_cwa_api_key(str(cwa_cfg.get("api_key_env", "CWA_API_KEY")), args.project_root),
        cfg,
        args.project_root,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    printable = {k: v for k, v in result.items() if k != "valid_times"}
    print(json.dumps(printable, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
