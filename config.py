# config.py
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

M4_TARBALL_URL = (
    "https://github.com/carlanetto/M4comp2018/releases/download/0.2.0/"
    "M4comp2018_0.2.0.tar.gz"
)

M4_TARBALL_PATH = DATA_DIR / "M4comp2018_0.2.0.tar.gz"
RDA_PATH = DATA_DIR / "M4.rda"  # we’ll copy/rename here
