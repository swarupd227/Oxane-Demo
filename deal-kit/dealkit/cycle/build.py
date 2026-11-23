"""Build the May 2026 monitoring cycle and its answer key from cycle.yaml and deal.yaml.

python -m dealkit.cycle.build
"""

import hashlib
import json
import shutil

from dealkit.config import OUTPUT_DIR, ROOT, load_deal
from dealkit.cycle import (
    book,
    bramble,
    daily,
    kestrel,
    larkspur,
    northmoor,
    qc,
    ravenglass,
    statements,
    wharfedale,
)
from dealkit.cycle.common import CYCLE_DIR, CYCLE_KEY_DIR, load_cycle
from dealkit.cycle.key import add_review_scenarios, build_cycle_key
from dealkit.reports import build_financials
from dealkit.tape import generate_tape

MANIFEST = ROOT / "cycle.manifest.json"


def build_cycle() -> dict[str, str]:
    deal, cycle = load_deal(), load_cycle()
    shutil.rmtree(CYCLE_DIR, ignore_errors=True)
    shutil.rmtree(CYCLE_KEY_DIR, ignore_errors=True)
    folders = {
        name: CYCLE_DIR / name
        for name in (
            "bramble", "northmoor", "kestrel", "larkspur", "qc", "book", "ravenglass",
            "wharfedale", daily.FOLDER,
        )
    }
    for folder in folders.values():
        folder.mkdir(parents=True)

    # Bramble's April tape is the facility record's last month, rebuilt from the deal file.
    april = generate_tape(deal).rows
    bramble_facts = bramble.build_bramble(deal, cycle, april, folders["bramble"])
    build_financials(deal, folders["bramble"] / "BAF_Financial_Statements_Q1_2026.pdf")
    northmoor_facts = northmoor.build_northmoor(cycle, folders["northmoor"], bramble_facts["rows"])
    kestrel_facts = kestrel.build_kestrel(cycle, folders["kestrel"])
    larkspur_facts = larkspur.build_larkspur(cycle, folders["larkspur"])
    # The rest of the book: nothing planted, nothing in the key.
    book.build_book(cycle, folders["book"])
    # The RFP review's scenarios: middle-market, a subscription line and the CLO daily feeds.
    ravenglass_facts = ravenglass.build_ravenglass(cycle, folders["ravenglass"])
    wharfedale_facts = wharfedale.build_wharfedale(cycle, folders["wharfedale"])
    daily_facts = daily.build_daily(cycle, folders["larkspur"], folders[daily.FOLDER])
    statements.build_statements(folders["bramble"], folders["northmoor"])

    files = {
        "bramble": {
            **bramble.FILES,
            "financial_statements": "BAF_Financial_Statements_Q1_2026.pdf",
        },
        "northmoor": northmoor.FILES,
        "kestrel": kestrel.FILES,
        "larkspur": larkspur.FILES,
    }
    key = build_cycle_key(
        deal,
        cycle,
        bramble_facts,
        northmoor_facts,
        kestrel_facts,
        files,
        CYCLE_KEY_DIR,
        larkspur_facts,
    )
    add_review_scenarios(key, cycle, ravenglass_facts, wharfedale_facts, daily_facts)
    key["checks"]["qc"] = qc.build_qc(key, folders["qc"])
    (CYCLE_KEY_DIR / "key.json").write_text(
        json.dumps(key, indent=2, default=str) + "\n", encoding="utf-8"
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
