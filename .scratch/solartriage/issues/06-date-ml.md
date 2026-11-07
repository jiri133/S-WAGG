# Date ML: descărcare Raptor, dedup, split, mapare 12→8

Type: task
Status: resolved
Owner: Tu
Țintă: H5
Blocked by: 01, 02

## Question

**Din tichetul 02:** URL-ul, SHA-256-ul, structura arhivei și cele 6 perechi de duplicate cu etichete conflictuale (de eliminat) sunt în răspunsul tichetului 02. Distribuția pe clase se ia din arhivă, nu din paper. `soiling` are doar 204 imagini, deci class weights sunt obligatorii.

Spec: §3.1–3.2. `ml/data.py`: descarcă în `data/raptor/` (în `.gitignore`), deduplicare cu hash perceptual, split stratificat 70/15/15 cu seed fix, mapare 12→8. Scrie `ml/splits/{train,val,test}.csv`, care intră în repo.

**Gata când:** cele 3 CSV-uri există, distribuția pe clase e afișată, iar simulatorul (tichetul 16) poate citi crop-urile din test.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Python 3.15 merge cu PyTorch, ONNX Runtime și numpy?](01-python-compat.md)
- [Formatul exact al dataset-ului InfraredSolarModules](02-raptor-format.md)

## Answer

**Comanda:** `uv run --project ml python ml/data.py`, din rădăcina repo-ului. Proiectul `ml/` e separat (Python 3.14, numpy, pillow, scikit-learn). Prima rulare descarcă zip-ul (15,5 MB), verifică SHA-256-ul și extrage doar `module_metadata.json` și `images/*.jpg` în `data/raptor/InfraredSolarModules/`. Rulările următoare durează ~17 s. Seed 42, iar ieșirea e identică byte cu byte la fiecare rulare.

**Deduplicare (20.000 → 19.944):**
- Duplicate exacte (SHA-256 pe fișier): 16 copii cu aceeași etichetă eliminate. Cele 12 imagini din cele 6 perechi conflictuale din tichetul 02 sunt eliminate complet. Scriptul verifică faptul că perechile găsite sunt exact cele 6.
- Aproape-duplicate: **dHash a fost încercat și respins.** Pe crop-uri 24×40 aproape uniforme, biții lui sunt zgomot: 10.786 de perechi la distanța 0 (din 128 de biți), dintre care 41 % cu etichete diferite, iar perechile reale ajung până la 40 de biți distanță. Am folosit în schimb **distanța RMS dintre pixeli ≤ 3,0 nivele de gri**. Sub acest prag, 50–75 % din perechi vin din același zbor (id-uri la cel mult 20 distanță) și aproape niciuna nu are etichete diferite. Peste 3, ambele semnale se degradează brusc. Rezultatul: 504 perechi, 174 de grupuri cu 522 de imagini (cel mai mare are 22 de crop-uri `ok` uniforme). Un grup stă mereu într-un singur split (coloana `group`).
- 6 grupuri de aproape-duplicate cu clase diferite (din cele 8) au fost eliminate complet, 28 de imagini, după aceeași regulă ca la tichetul 02. Cel mai mare e un lanț de 16 imagini, 8 `shadow_vegetation` și 8 `ok`. Celelalte sunt perechi `ok` vs. defect, de exemplu 13046/1594, practic aceeași imagine.
- **Abatere de la spec §3.1** („hash perceptual”): intenția, adică aproape-duplicatele să nu ajungă în train și în test deodată, e respectată, dar cu distanța dintre pixeli. De confirmat de om.

**Distribuția pe clase (split stratificat pe grupuri, 70/15/15):**

| clasa | train | val | test | total |
|---|---:|---:|---:|---:|
| ok | 7001 | 1502 | 1483 | 9986 |
| hot_cell | 1486 | 318 | 319 | 2123 |
| multi_hot | 1072 | 230 | 229 | 1531 |
| diode_substring | 1169 | 250 | 250 | 1669 |
| module_offline | 575 | 123 | 123 | 821 |
| soiling | 143 | 31 | 30 | 204 |
| shadow_vegetation | 1870 | 401 | 402 | 2673 |
| other | 656 | 140 | 141 | 937 |
| **total** | **13972** | **2995** | **2977** | **19944** |

`soiling` are doar 143 imagini în train, deci class weights + oversampling (§3.3) rămân obligatorii.

**CSV-uri** (`ml/splits/{train,val,test}.csv`, în repo, exceptate de la regula de 30 KB conform §11). Coloanele sunt `image_id,path,raptor_class,class,group`. `path` e relativ la rădăcina repo-ului, de exemplu `data/raptor/InfraredSolarModules/images/2.jpg`. `class` e una din cele 8 clase SolarTriage.

**Pentru simulator (tichetul 16):** citește `ml/splits/test.csv` și alege crop-urile după coloana `class` (`ok` pentru modulele sănătoase). Imaginea e la `<rădăcina repo>/<path>`, un JPEG gri pe 8 biți de 24×40 (`PIL.Image.open(...).convert("L")`). Crop-urile trebuie să existe local, deci rulează o dată `uv run --project ml python ml/data.py`. Din backend, rădăcina e `Path(__file__).parents[...]` până la repo; nu copia imaginile în `backend/`.
