from __future__ import annotations

try:
    import torch
    from torch import nn
except ImportError as exc:  # pragma: no cover - runtime dependency
    raise RuntimeError("torch is required for LSTM models. Install kaohsiung_microclimate_lstm/requirements.txt") from exc


class LSTMEncoder(nn.Module):
    def __init__(self, n_features: int, hidden_size_1: int = 128, hidden_size_2: int = 64, dropout: float = 0.2) -> None:
        super().__init__()
        self.lstm1 = nn.LSTM(n_features, hidden_size_1, batch_first=True)
        self.dropout1 = nn.Dropout(dropout)
        self.lstm2 = nn.LSTM(hidden_size_1, hidden_size_2, batch_first=True)
        self.norm = nn.LayerNorm(hidden_size_2)
        self.dropout2 = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x, _ = self.lstm1(x)
        x = self.dropout1(x)
        _, (h, _) = self.lstm2(x)
        encoded = h[-1]
        return self.dropout2(self.norm(encoded))


class BaselineLSTM(nn.Module):
    def __init__(self, n_features: int, output_steps: int = 4, **kwargs) -> None:
        super().__init__()
        hidden = int(kwargs.get("hidden_size_2", 64))
        self.encoder = LSTMEncoder(n_features, **kwargs)
        self.head = nn.Linear(hidden, output_steps)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.encoder(x))


class MultiTaskWindLSTM(nn.Module):
    def __init__(self, n_features: int, output_steps: int = 4, **kwargs) -> None:
        super().__init__()
        hidden = int(kwargs.get("hidden_size_2", 64))
        self.encoder = LSTMEncoder(n_features, **kwargs)
        self.wind_speed = nn.Linear(hidden, output_steps)
        self.wind_gust = nn.Linear(hidden, output_steps)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = self.encoder(x)
        return torch.stack([self.wind_speed(z), self.wind_gust(z)], dim=-1)


class TwoStageRainLSTM(nn.Module):
    def __init__(self, n_features: int, output_steps: int = 4, **kwargs) -> None:
        super().__init__()
        hidden = int(kwargs.get("hidden_size_2", 64))
        self.encoder = LSTMEncoder(n_features, **kwargs)
        self.rain_logits = nn.Linear(hidden, output_steps)
        self.amount = nn.Linear(hidden, output_steps)
        self.relu = nn.ReLU()

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        z = self.encoder(x)
        amount = self.relu(self.amount(z))
        logits = self.rain_logits(z)
        return {"logits": logits, "probability": torch.sigmoid(logits), "amount": amount}

    def predict_amount(self, x: torch.Tensor, threshold: float = 0.5) -> torch.Tensor:
        out = self.forward(x)
        return torch.where(out["probability"] > threshold, out["amount"], torch.zeros_like(out["amount"]))


def build_model(model_type: str, n_features: int, model_cfg: dict, output_steps: int = 4) -> nn.Module:
    kwargs = {
        "hidden_size_1": int(model_cfg.get("hidden_size_1", 128)),
        "hidden_size_2": int(model_cfg.get("hidden_size_2", 64)),
        "dropout": float(model_cfg.get("dropout", 0.2)),
    }
    if model_type == "lstm":
        return BaselineLSTM(n_features, output_steps, **kwargs)
    if model_type == "multitask_lstm":
        return MultiTaskWindLSTM(n_features, output_steps, **kwargs)
    if model_type == "twostage_lstm":
        return TwoStageRainLSTM(n_features, output_steps, **kwargs)
    raise ValueError(f"Unsupported model_type: {model_type}")


def prediction_tensor(model: nn.Module, x: torch.Tensor, model_type: str) -> torch.Tensor:
    if model_type == "twostage_lstm":
        return model.predict_amount(x)  # type: ignore[attr-defined]
    return model(x)
