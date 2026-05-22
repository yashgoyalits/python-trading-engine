# src/config.py
from pathlib import Path
import yaml

_CONFIG_PATH = Path(__file__).parent / "config.yml"


def load() -> dict:
    with open(_CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)