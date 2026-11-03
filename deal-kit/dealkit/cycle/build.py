"""Build the May 2026 monitoring cycle and its answer key from cycle.yaml and deal.yaml.

python -m dealkit.cycle.build
"""

import hashlib
import json
import shutil

from dealkit.config import OUTPUT_DIR, ROOT, load_deal
from dealkit.cycle import bramble, kestrel, northmoor
from dealkit.cycle.common import CYCLE_DIR, CYCLE_KEY_DIR, load_cycle
from dealkit.cycle.key import build_cycle_key
from dealkit.reports import build_financials
from dealkit.tape import generate_tape

MANIFEST = ROOT / "cycle.manifest.json"


def build_cycle() -> dict[str, str]:
    deal, cycle = load_deal(), load_cycle()
    shutil.rmtree(CYCLE_DIR, ignore_errors=True)
    shutil.rmtree(CYCLE_KEY_DIR, ignore_errors=True)
    folders = {name: CYCLE_DIR / name for name in ("bramble", "northmoor", "kestrel")}
    for folder in folders.values():
        folder.mkdir(parents=True)

    # Bramble's April tape is the facility record's last month, rebuilt from the deal file.
    april = generate_tape(deal).rows
    bramble_facts = bramble.build_bramble(deal, cycle, april, folders["bramble"])
    build_financials(deal, folders["bramble"] / "BAF_Financial_Statements_Q1_2026.pdf")
    northmoor_facts = northmoor.build_northmoor(cycle, folders["northmoor"], bramble_facts["rows"])
    kestrel_facts = kestrel.build_kestrel(cycle, folders["kestrel"])

    files = {
        "bramble": {
            **bramble.FILES,
            "financial_statements": "BAF_Financial_Statements_Q1_2026.pdf",
        },
        "northmoor": northmoor.FILES,
        "kestrel": kestrel.FILES,
    }
    build_cycle_key(
        deal, cycle, bramble_facts, northmoor_facts, kestrel_facts, files, CYCLE_KEY_DIR
    )
    return {
        path.relative_to(OUTPUT_DIR).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for folder in (*folders.values(), CYCLE_KEY_DIR)
        for path in sorted(folder.iterdir())
    }


def main() -> None:
    manifest = build_cycle()
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Built {len(manifest)} files in {CYCLE_DIR}")


if __name__ == "__main__":
    main()
