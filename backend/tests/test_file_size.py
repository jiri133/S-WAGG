"""AGENTS.md: no hand-written source file over 30 KB (generated files are exempt)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIMIT = 30 * 1024
DIRS = ["backend/app", "backend/tests", "backend/config", "ml", "frontend/src", "frontend/e2e"]
EXTS = {".py", ".ts", ".tsx", ".css", ".yaml", ".json", ".ps1"}
SKIP_DIRS = {".venv", "node_modules", "__pycache__", "splits", "fixtures"}
GENERATED = {"types.gen.ts"}


def too_big(root: Path = ROOT) -> list[str]:
    out = []
    for d in DIRS:
        for f in (root / d).rglob("*"):
            if f.suffix not in EXTS or f.name in GENERATED or SKIP_DIRS & set(f.parts):
                continue
            if f.stat().st_size > LIMIT:
                out.append(f"{f.relative_to(root)} ({f.stat().st_size // 1024} KB)")
    return out


def test_no_source_file_over_30kb():
    assert too_big() == [], "Sparge fișierele pe responsabilități (AGENTS.md)"


def test_catches_a_big_file(tmp_path):
    (tmp_path / "ml").mkdir()
    (tmp_path / "ml" / "big.py").write_text("x" * (LIMIT + 1))
    (tmp_path / "ml" / "small.py").write_text("x = 1")
    assert too_big(tmp_path) == [str(Path("ml/big.py")) + " (30 KB)"]
