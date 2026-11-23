"""Zip each test deal's documents for download from the hosted app.

    python -m dealkit.newdeals.samples /samples

Writes <deal>-onboarding.zip and <deal>-monthly.zip. The answer keys (key.json) are left out:
they belong to the tests, not to someone trying the app.
"""

import sys
import zipfile
from pathlib import Path

from dealkit.newdeals.build import NEWDEALS_DIR


def write_samples(out: Path) -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for deal in sorted(p for p in NEWDEALS_DIR.iterdir() if p.is_dir()):
        for stage in ("onboarding", "monthly"):
            folder = deal / stage
            if not folder.is_dir():
                continue
            target = out / f"{deal.name}-{stage}.zip"
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
                for file in sorted(folder.iterdir()):
                    archive.write(file, file.name)
            written.append(target.name)
    return written


if __name__ == "__main__":
    print(write_samples(Path(sys.argv[1] if len(sys.argv) > 1 else "samples")))
