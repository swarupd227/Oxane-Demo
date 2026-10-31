from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEAL_FILE = ROOT / "deal.yaml"
OUTPUT_DIR = ROOT / "output"
PACK_DIR = OUTPUT_DIR / "pack"
KEY_DIR = OUTPUT_DIR / "answer-key"


def load_deal(path: Path = DEAL_FILE) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))
