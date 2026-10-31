"""Build the whole pack and answer key from deal.yaml.

    python -m dealkit.build
"""

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np

from dealkit.agreement import build_agreement
from dealkit.calc import borrower_view
from dealkit.config import KEY_DIR, OUTPUT_DIR, PACK_DIR, ROOT, load_deal
from dealkit.key import PACK_FILES, build_key
from dealkit.legal_docs import build_amendment, build_fee_letter
from dealkit.reports import build_financials, build_servicer_report
from dealkit.tape import generate_tape, write_csv
from dealkit.workbooks import build_bbc, build_requirements

MANIFEST = ROOT / "pack.manifest.json"


def digests(*folders: Path) -> dict[str, str]:
    result = {}
    for folder in folders:
        for path in sorted(folder.iterdir()):
            relative = path.relative_to(OUTPUT_DIR).as_posix()
            result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def build_all() -> dict[str, str]:
    deal = load_deal()
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    PACK_DIR.mkdir(parents=True)

    tape = generate_tape(deal)
    pack = {doc: PACK_DIR / name for doc, name in PACK_FILES.items()}
    write_csv(tape, pack["loan_tape"])
    build_agreement(deal, np.random.default_rng(deal["seed"] + 1), pack["credit_agreement"])
    build_amendment(deal, pack["amendment_1"])
    build_fee_letter(deal, pack["fee_letter"])
    build_servicer_report(deal, tape.rows, pack["servicer_report"])
    build_financials(deal, pack["financial_statements"])
    build_bbc(deal, borrower_view(tape.rows, deal), pack["borrowing_base_certificate"])
    build_requirements(deal, pack["lender_requirements"])
    build_key(deal, tape, PACK_DIR, KEY_DIR)
    shutil.rmtree(OUTPUT_DIR / "work", ignore_errors=True)
    return digests(PACK_DIR, KEY_DIR)


def main() -> None:
    manifest = build_all()
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Built {len(manifest)} files in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
