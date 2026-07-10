from __future__ import annotations

from pathlib import Path

from setuptools import find_packages, setup


ROOT = Path(__file__).parent


def read_requirements(path: str) -> list[str]:
    requirements = []
    for line in (ROOT / path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            requirements.append(line)
    return requirements


setup(
    name="khh-microclimate-forecast",
    version="2.0.0",
    description="Kaohsiung Port microclimate prediction and dispatch-risk system",
    long_description=(ROOT / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    packages=find_packages(include=["app", "app.*", "kaohsiung_microclimate_lstm", "kaohsiung_microclimate_lstm.*"]),
    python_requires=">=3.9",
    install_requires=read_requirements("requirements.txt"),
    entry_points={
        "console_scripts": [
            "khh-microclimate=kaohsiung_microclimate_lstm.src.cli:main",
        ],
    },
)
