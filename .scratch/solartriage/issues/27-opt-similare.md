# Opțional: 3 cazuri similare în FindingCard

Type: task
Status: resolved
Owner: Tu
Țintă: după H20
Blocked by: 24

## Question

Spec: §3.5 punctul 3. `ml/build_index.py` → `embeddings.npy`, `services/explain/similar.py`, câmpul `Evidence.similar`.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Code freeze H20: verificare cap-coadă](24-code-freeze.md)

## Answer

**Ce s-a construit**

- `ml/build_index.py`: încarcă `backend/artifacts/best.pt` (`Net` din `train.py`, cu `fc` → `Identity`) și calculează embedding-ul 512-d din avgpool pentru toate cele 13.972 de crop-uri din `ml/splits/train.csv`. Intrarea e `(N,1,40,24)` = pixel/255, iar preprocesarea e în model. Embedding-ul e L2-normalizat. Scrie `backend/artifacts/embeddings.npy` (float16, **14,3 MB**) și `embeddings.csv` (`image_id, cls, path`, 0,9 MB). Rularea durează ~80 s pe CPU.
- **Artefactele sunt în git** (14 MB, ca `model.onnx`), ca juriul să vadă cazurile similare dintr-o clonă curată. Imaginile lor vin din `data/`, pe care `evaluate.py` îl descarcă. Se pot regenera cu `uv run --project ml python ml/build_index.py`. Fără index, finding-urile au `similar = []` și backend-ul scrie un warning.
- `backend/app/services/explain/similar.py`: `embed()` folosește aceeași rețea ca Grad-CAM (`gradcam.load_model()`, hook pe `avgpool`). `cases()` face cosine top-3 cu numpy contra indexului, cu `distance = 1 − cosine`. `crop_url` e un `data:image/png;base64,...` al crop-ului 24×40 din train, citit din `data/`. Așa contractul §9 rămâne neschimbat și nu e nevoie de endpoint nou. Fără index sau fără imaginile din `data/`, rezultatul e `[]`.
- `pipeline/analyse.py`: `with_similar()` completează `Evidence.similar` pentru toate finding-urile, cu un singur forward pass pe lot.
- `FindingCard.tsx`: afișează cele 3 crop-uri similare (h-20 × w-12, pixelated), cu clasa și distanța. Schema nu s-a schimbat, deci `types.gen.ts` nu s-a regenerat.

**Cum am verificat**

- `cd backend && uv run pytest -q` → 218 passed. `uv run ruff check .` → All checks passed.
- `tests/test_similar.py` are 6 teste:
  - embedding-ul are 512 dimensiuni și normă 1;
  - pe un index din cele 8 crop-uri fixture, cel mai apropiat caz e chiar crop-ul (distanța ≈ 0, iar PNG-ul din data URL are aceiași pixeli);
  - fără index, rezultatul e `[]`;
  - `with_similar` pune 3 cazuri;
  - pe indexul real, 8 crop-uri din train se găsesc pe ele însele, deci `ml/` și backend-ul calculează embedding-ul la fel;
  - misiunea M-0001 are 3 cazuri la fiecare finding.
- `cd ml && uv run pytest -q tests/test_build_index.py` → 1 passed. Testul rulează `build(limit=16)` și verifică (16, 512) float16, cu rânduri de normă 1.
- `cd frontend && npm run build` → ok. În `e2e/finding.spec.ts`, cardul F-022 are 0 sau 3 cazuri similare, iar fiecare imagine se încarcă cu 24 px lățime. `npx playwright test` → 7 passed (5,8 min). Am rulat cu indexul construit, deci s-a verificat ramura cu 3 cazuri, pe porturile 8101/5180→5181 dintr-o copie temporară a config-ului, pentru că 8100/5180 erau ocupate de un alt run.
- Rulare reală: TestClient, setările demo `explain`, misiuni noi zburate și apoi analizate.
  - Fără index: 7,85 s.
  - Cu index: 7,54 s la rece și 8,18 s la cald.
  - 47 din 47 de finding-uri au 3 cazuri.
  - `similar.cases`, măsurat separat pe 47 de crop-uri: 0,34 s la rece (încărcarea modelului și a indexului), 0,14 s la cald. Diferența dintre rulările analizei e zgomot.
- Observație: pe scenariul explain, cel mai apropiat caz are clasa prezisă la 22 din 47 de finding-uri. Crop-urile din zbor sunt re-randate din temperaturi, deci nu sunt identice cu cele Raptor. Multe finding-uri sunt FP pe ok, iar vecinii lor sunt adesea ok.
