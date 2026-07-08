from __future__ import annotations

import argparse
import csv
from pathlib import Path


def plot_loss(csv_path: str | Path, output_path: str | Path | None = None) -> Path:
    csv_path = Path(csv_path)
    if output_path is None:
        output_path = csv_path.parents[1] / "results" / "plots" / f"{csv_path.stem}.png"
    output_path = Path(output_path)
    rows = []
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError(f"No rows found in {csv_path}")

    epochs = [int(row["epoch"]) for row in rows]
    train_loss = [float(row["train_loss"]) for row in rows]
    val_loss = [float(row["val_loss"]) for row in rows]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.figure(figsize=(8, 4.5))
    plt.plot(epochs, train_loss, label="train_loss")
    plt.plot(epochs, val_loss, label="val_loss")
    plt.xlabel("epoch")
    plt.ylabel("loss")
    plt.title(csv_path.stem)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=140)
    plt.close()
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--output")
    args = parser.parse_args()
    print(plot_loss(args.csv_path, args.output))


if __name__ == "__main__":
    main()
