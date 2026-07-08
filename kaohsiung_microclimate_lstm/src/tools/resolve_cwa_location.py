from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from ..config import load_config
    from ..cwa.location_resolver import resolve_cwa_location
except ImportError:  # pragma: no cover
    from config import load_config
    from cwa.location_resolver import resolve_cwa_location


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="kaohsiung_microclimate_lstm/config_hourly_codis.yaml")
    parser.add_argument("--output", default="kaohsiung_microclimate_lstm/config/resolved_cwa_location.json")
    parser.add_argument("--project_root", default="kaohsiung_microclimate_lstm")
    args = parser.parse_args()
    cfg = load_config(args.config)
    cwa_cfg = cfg.get("rain_postprocess", {}).get("cwa_pop3h", {})
    candidates = [str(item) for item in cwa_cfg.get("location_candidates", [])]
    fallback = str(cwa_cfg.get("fallback_location", candidates[0] if candidates else "前鎮區"))
    result = resolve_cwa_location(candidates, fallback, project_root=args.project_root)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] CWA location resolved: {result['resolved_location_name']}")
    for item in result["tested_locations"]:
        print(f"[INFO] tested {item['location_name']}: {item['record_count']} records")
    print(f"[INFO] saved to {out}")


if __name__ == "__main__":
    main()
