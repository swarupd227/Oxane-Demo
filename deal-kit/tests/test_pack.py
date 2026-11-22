import ast
from pathlib import Path

from dealkit.build import build_all, digests
from dealkit.casework.build import FOLDERS
from dealkit.casework.common import CASEWORK_DIR, CASEWORK_KEY_DIR
from dealkit.config import KEY_DIR, PACK_DIR
from dealkit.verify import main as verify


def test_pack_rebuilds_byte_for_byte():
    assert build_all() == build_all()


def test_independent_checks_pass():
    build_all()
    assert verify() == 0


def test_digests_cover_all_eight_documents_and_the_key():
    build_all()
    names = list(digests(PACK_DIR, KEY_DIR))
    assert sum(name.startswith("pack/") for name in names) == 8
    assert sum(name.startswith("answer-key/") for name in names) == 6


def test_manifest_covers_the_casework_files_and_their_key():
    names = list(build_all())
    casework = list(digests(*(CASEWORK_DIR / name for name in FOLDERS), CASEWORK_KEY_DIR))
    assert set(casework) <= set(names)
    assert sum(name.startswith("casework/backbook/") for name in names) == 4
    assert "casework-key/key.json" in names


def test_verifier_imports_nothing_from_the_generators():
    source = (Path(__file__).parent.parent / "dealkit" / "verify.py").read_text(encoding="utf-8")
    imported = [
        node.module for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module
    ]
    assert not any(module.startswith("dealkit") for module in imported)
