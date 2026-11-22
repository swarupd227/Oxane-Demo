from pathlib import Path
from typing import Any

import yaml

from dealkit.config import OUTPUT_DIR, ROOT

CASEWORK_FILE = ROOT / "casework.yaml"
CASEWORK_DIR = OUTPUT_DIR / "casework"
CASEWORK_KEY_DIR = OUTPUT_DIR / "casework-key"


def load_casework(path: Path = CASEWORK_FILE) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))
