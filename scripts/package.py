"""Bundle the runnable source, trained artifacts and built frontend for local download."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "frontend/dist/AtmoTrust-project.zip"
EXCLUDE_DIRS = {".git", ".venv", ".npm-cache", "node_modules", "__pycache__", ".pytest_cache", "raw"}
INCLUDE_ROOTS = {"backend", "frontend", "data", "artifacts", "benchmarks", "docs", "scripts", "README.md", ".env.example", ".gitignore", ".dockerignore", "Dockerfile", "render.yaml"}


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(OUTPUT, "w", ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            if relative.parts[0] not in INCLUDE_ROOTS:
                continue
            if any(part in EXCLUDE_DIRS for part in relative.parts):
                continue
            if path.name == ".env" or path.suffix in {".pyc", ".log", ".db", ".sqlite3", ".zip"} or "sqlite3-" in path.name or "db-" in path.name:
                continue
            archive.write(path, f"AtmoTrust/{relative.as_posix()}")
    print(f"{OUTPUT} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
