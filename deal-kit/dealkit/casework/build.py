"""Build the casework files and their key. Called by dealkit.build, after the pack."""

import json
from pathlib import Path
from typing import Any

from dealkit.casework.backbook import build_backbook
from dealkit.casework.client_model import build_client_model
from dealkit.casework.common import CASEWORK_DIR, CASEWORK_KEY_DIR, load_casework
from dealkit.casework.key import client_model_key, definitions_key
from dealkit.casework.pipeline import build_pipeline
from dealkit.casework.qc import build_qc
from dealkit.casework.variants import impacts
from dealkit.tape import Tape

FOLDERS = ("client", "qc", "backbook", "pipeline")


def build_casework(deal: dict[str, Any], tape: Tape, pack_dir: Path,
                   pack_files: dict[str, str]) -> list[Path]:
    casework = load_casework()
    folders = {name: CASEWORK_DIR / name for name in FOLDERS}
    for folder in folders.values():
        folder.mkdir(parents=True, exist_ok=True)
    CASEWORK_KEY_DIR.mkdir(parents=True, exist_ok=True)

    cells = build_client_model(deal, casework,
                               folders["client"] / casework["client_model"]["file"])
    effects = impacts(tape.rows, deal)
    qc = build_qc(tape.rows, effects["agreed"], deal, casework,
                  folders["qc"] / casework["qc"]["file"])
    backbook = build_backbook(casework, deal["tape"]["cutoff_date"], folders["backbook"])
    # The team's other cases, with their own seed, so the files above are unchanged.
    build_pipeline(casework, folders["pipeline"])
    key = {
        "definitions": definitions_key(pack_dir, pack_files),
        "client_model": client_model_key(cells, effects),
        "qc": qc,
        "backbook": backbook,
    }
    (CASEWORK_KEY_DIR / "key.json").write_text(
        json.dumps(key, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return [*folders.values(), CASEWORK_KEY_DIR]
