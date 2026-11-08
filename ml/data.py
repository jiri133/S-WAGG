"""Date ML pentru SolarTriage (spec §3.1–3.2).

Descarcă InfraredSolarModules (Raptor Maps) în data/raptor/, verifică SHA-256, extrage,
elimină duplicatele exacte, grupează aproape-duplicatele cu un hash perceptual,
mapează cele 12 clase Raptor pe 8 și scrie ml/splits/{train,val,test}.csv (70/15/15,
stratificat, seed fix). Un grup de aproape-duplicate nu traversează niciodată split-urile.

Rulează din rădăcina repo-ului:  uv run --project ml python ml/data.py
"""

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image
from sklearn.model_selection import train_test_split

from fetch_raptor import DATASET_DIR, N_IMAGES, download, extract

ROOT = Path(__file__).resolve().parent.parent
SPLITS_DIR = ROOT / "ml" / "splits"

SEED = 42

# Spec §3.2. Glare nu e clasă.
CLASS_MAP = {
    "Cell": "hot_cell",
    "Hot-Spot": "hot_cell",
    "Cell-Multi": "multi_hot",
    "Hot-Spot-Multi": "multi_hot",
    "Diode": "diode_substring",
    "Diode-Multi": "diode_substring",
    "Offline-Module": "module_offline",
    "Soiling": "soiling",
    "Shadowing": "shadow_vegetation",
    "Vegetation": "shadow_vegetation",
    "Cracking": "other",
    "No-Anomaly": "ok",
}
CLASSES = [
    "ok", "hot_cell", "multi_hot", "diode_substring",
    "module_offline", "soiling", "shadow_vegetation", "other",
]

# Tichetul 02: perechi byte-identice cu etichete diferite. Se elimină complet.
CONFLICTING_PAIRS = {
    (1124, 7387), (161, 4518), (3915, 7027), (450, 7484), (483, 6888), (543, 5171),
}

# Aproape-duplicate: distanța RMS dintre pixelii crop-urilor (nivele de gri 0–255).
# dHash a fost încercat și respins: pe crop-uri 24×40 aproape uniforme biții lui sunt zgomot
# (perechi reale la 40/128 biți, module fără legătură la 0). Sub 3,0 perechile vin în
# majoritate din același zbor (id-uri vecine) și aproape niciodată nu au etichete diferite.
NEAR_DUP_RMS = 3.0


def load_records() -> list[dict]:
    meta = json.loads((DATASET_DIR / "module_metadata.json").read_text(encoding="utf-8"))
    records = []
    for key, item in meta.items():
        raptor_class = item["anomaly_class"]
        records.append({
            "image_id": int(key),
            "path": f"data/raptor/InfraredSolarModules/{item['image_filepath']}",
            "raptor_class": raptor_class,
            "class": CLASS_MAP[raptor_class],
        })
    records.sort(key=lambda r: r["image_id"])
    assert len(records) == N_IMAGES, len(records)
    return records


def drop_exact_duplicates(records: list[dict]) -> tuple[list[dict], dict]:
    """Elimină copiile byte-identice: o copie dacă eticheta e aceeași, toate dacă diferă."""
    by_digest = defaultdict(list)
    for r in records:
        by_digest[hashlib.sha256((ROOT / r["path"]).read_bytes()).digest()].append(r)
    drop, conflicting, same_label = set(), set(), 0
    for group in by_digest.values():
        if len(group) < 2:
            continue
        ids = sorted(r["image_id"] for r in group)
        if len({r["raptor_class"] for r in group}) > 1:
            conflicting.add(tuple(ids))
            drop.update(ids)
        else:
            same_label += len(ids) - 1
            drop.update(ids[1:])
    if conflicting != CONFLICTING_PAIRS:
        raise SystemExit(f"Perechile conflictuale diferă de tichetul 02: {sorted(conflicting)}")
    kept = [r for r in records if r["image_id"] not in drop]
    return kept, {"same_label": same_label, "conflicting": 2 * len(conflicting)}


def near_duplicate_groups(records: list[dict]) -> tuple[list[int], int]:
    """Union-find peste perechile cu RMS <= NEAR_DUP_RMS. Întoarce grupul fiecărui crop."""
    x = np.stack([
        np.asarray(Image.open(ROOT / r["path"]).convert("L"), dtype=np.float64).ravel()
        for r in records
    ])
    sq = (x * x).sum(axis=1)
    limit = NEAR_DUP_RMS**2 * x.shape[1]
    n = len(records)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    pairs = 0
    for start in range(0, n, 1000):
        d2 = sq[start:start + 1000, None] + sq[None, :] - 2 * x[start:start + 1000] @ x.T
        for a, b in zip(*np.nonzero(d2 <= limit), strict=True):
            i, j = start + int(a), int(b)
            if i < j:
                pairs += 1
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)
    # Rădăcina e indexul minim, deci id-ul grupului e image_id-ul celui mai mic membru.
    return [records[find(i)]["image_id"] for i in range(n)], pairs


def drop_conflicting_groups(records: list[dict], groups: list[int]) -> tuple[list, list, int]:
    """Elimină grupurile de aproape-duplicate ai căror membri au clase (din 8) diferite."""
    classes = defaultdict(set)
    for r, g in zip(records, groups, strict=True):
        classes[g].add(r["class"])
    bad = {g for g, c in classes.items() if len(c) > 1}
    keep = [i for i, g in enumerate(groups) if g not in bad]
    return [records[i] for i in keep], [groups[i] for i in keep], len(records) - len(keep)


def split(records: list[dict], groups: list[int]) -> dict[str, list[dict]]:
    """Split stratificat 70/15/15 pe grupuri (toți membrii unui grup au aceeași clasă)."""
    members = defaultdict(list)
    for r, g in zip(records, groups, strict=True):
        members[g].append(r)
    gids = sorted(members)
    labels = [members[g][0]["class"] for g in gids]
    train, rest, _, rest_labels = train_test_split(
        gids, labels, test_size=0.30, stratify=labels, random_state=SEED
    )
    val, test = train_test_split(rest, test_size=0.50, stratify=rest_labels, random_state=SEED)
    out = {}
    for name, part in (("train", train), ("val", val), ("test", test)):
        rows = [dict(r, group=g) for g in part for r in members[g]]
        out[name] = sorted(rows, key=lambda r: r["image_id"])
    return out


def write_splits(splits: dict[str, list[dict]]) -> None:
    SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    fields = ["image_id", "path", "raptor_class", "class", "group"]
    for name, rows in splits.items():
        with (SPLITS_DIR / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)


def print_table(splits: dict[str, list[dict]]) -> None:
    counts = {name: Counter(r["class"] for r in rows) for name, rows in splits.items()}
    print(f"{'clasa':<18}{'train':>7}{'val':>7}{'test':>7}{'total':>7}")
    for c in [*CLASSES, None]:
        vals = [sum(counts[s].values()) if c is None else counts[s][c] for s in splits]
        print(f"{c or 'total':<18}" + "".join(f"{v:>7}" for v in [*vals, sum(vals)]))


def main() -> None:
    download()
    extract()
    records, dup = drop_exact_duplicates(load_records())
    groups, pairs = near_duplicate_groups(records)
    sizes = Counter(groups)
    multi = [g for g, k in sizes.items() if k > 1]
    records, groups, conflicting = drop_conflicting_groups(records, groups)
    print(f"Duplicate exacte: {dup['same_label']} copii eliminate (aceeași etichetă), "
          f"{dup['conflicting']} imagini eliminate (etichete conflictuale)")
    print(f"Aproape-duplicate (RMS pixeli <= {NEAR_DUP_RMS}): {pairs} perechi, {len(multi)} grupuri "
          f"cu {sum(sizes[g] for g in multi)} imagini (cel mai mare: {max(sizes.values())}); "
          f"{conflicting} imagini eliminate din grupuri cu clase diferite")
    splits = split(records, groups)
    write_splits(splits)
    print_table(splits)


if __name__ == "__main__":
    main()
