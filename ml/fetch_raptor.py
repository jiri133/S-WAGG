"""Download and extract the Raptor InfraredSolarModules crops (SolarTriage §3.1).

Stdlib only. CI runs this before the backend tests, which exercise scenarios that need
the real crops; the full preparation (dedup, near-duplicate groups, splits) stays in
``ml/data.py``. The zip is pinned by SHA-256, so a changed upstream file fails loudly.
"""

from __future__ import annotations

import hashlib
import re
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "raptor"
ZIP_PATH = DATA_DIR / "2020-02-14_InfraredSolarModules.zip"
DATASET_DIR = DATA_DIR / "InfraredSolarModules"
N_IMAGES = 20_000

ZIP_URL = (
    "https://raw.githubusercontent.com/RaptorMaps/InfraredSolarModules/master/"
    "2020-02-14_InfraredSolarModules.zip"
)
ZIP_SHA256 = "b82c706bc719b045ac4f8930570d81767a8a170d0998ca3e09283b585db05b5e"
ALLOWED_MEMBER = re.compile(r"^InfraredSolarModules/(module_metadata\.json|images/\d+\.jpg)$")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download() -> None:
    if ZIP_PATH.exists() and sha256(ZIP_PATH) == ZIP_SHA256:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Descarc {ZIP_URL}")
    tmp = ZIP_PATH.with_suffix(".part")
    urllib.request.urlretrieve(ZIP_URL, tmp)
    digest = sha256(tmp)
    if digest != ZIP_SHA256:
        tmp.unlink()
        raise SystemExit(f"SHA-256 greșit: {digest}, așteptat {ZIP_SHA256}")
    tmp.replace(ZIP_PATH)


def extract() -> None:
    meta = DATASET_DIR / "module_metadata.json"
    if meta.exists() and len(list((DATASET_DIR / "images").glob("*.jpg"))) == N_IMAGES:
        return
    with zipfile.ZipFile(ZIP_PATH) as zf:
        # Doar metadatele și imaginile; fără __MACOSX/, .DS_Store sau căi neașteptate.
        members = [n for n in zf.namelist() if ALLOWED_MEMBER.match(n)]
        zf.extractall(DATA_DIR, members)


def main() -> None:
    download()
    extract()
    print(f"Crops gata în {DATASET_DIR}")


if __name__ == "__main__":
    main()
