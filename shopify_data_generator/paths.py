from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
DATA_DIR = REPO_ROOT / "data"
RUNTIME_DIR = REPO_ROOT / "runtime"
SCRIPTS_DIR = REPO_ROOT / "scripts"
ENV_FILE = REPO_ROOT / ".env"


def data_path(filename: str) -> Path:
    """Return a data file path, with root-level fallback for older worktrees."""
    path = DATA_DIR / filename
    if path.exists():
        return path
    legacy_path = REPO_ROOT / filename
    if legacy_path.exists():
        return legacy_path
    return path


def runtime_path(filename: str) -> Path:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    return RUNTIME_DIR / filename
