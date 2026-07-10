from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from ..model_wrappers import GustModel, RainfallCascadeModel, RainfallModel, VisibilityModel, WindModel


class ModelAPI:
    """Internal model API for tabular v2.0 model wrappers."""

    @staticmethod
    def train_model(model_type: str, X: pd.DataFrame, y: Any, config: dict[str, Any] | None = None) -> Any:
        model = _build_model(model_type, config or {})
        model.train(X, y)
        return model

    @staticmethod
    def load_model(model_path: str | Path) -> Any:
        payload = joblib.load(model_path)
        class_name = payload.get("class")
        reverse = {
            "RainfallModel": "rainfall",
            "RainfallCascadeModel": "rainfall_cascade",
            "WindModel": "wind",
            "GustModel": "gust",
            "VisibilityModel": "visibility",
        }
        model = _build_model(reverse.get(class_name, "rainfall"), payload.get("config", {}))
        return model.load(model_path)

    @staticmethod
    def predict(model: Any, X: pd.DataFrame) -> Any:
        return model.predict(X)


def _build_model(model_type: str, config: dict[str, Any]) -> Any:
    model_type = model_type.lower()
    if model_type in {"rainfall", "precipitation"}:
        return RainfallModel(config)
    if model_type in {"rainfall_cascade", "precipitation_cascade"}:
        return RainfallCascadeModel(config)
    if model_type in {"wind", "wind_speed"}:
        return WindModel(config)
    if model_type in {"gust", "wind_gust"}:
        return GustModel(config)
    if model_type == "visibility":
        return VisibilityModel(config)
    raise ValueError(f"Unsupported model_type: {model_type}")
