# Grad-CAM pe crop

Type: task
Status: resolved
Owner: Tu
Țintă: H16
Blocked by: 08, 10

## Question

Spec: §3.5. `services/explain/gradcam.py` (PyTorch pe CPU, ultimul bloc conv), `GET /api/findings/{id}/gradcam.png` cu cache pe disc.

**Gata când:** heatmap-ul pentru un finding de diodă cade pe banda de 1/3.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [ResNet18 pe Kaggle → model.onnx](08-resnet-onnx.md)
- [Modelul în pipeline: /api/analyse, inferență, incertitudine](10-model-analyse.md)

## Answer

**Ce s-a făcut**
- `torch` 2.15.0+cpu și `torchvision` 0.29.2+cpu în `backend/pyproject.toml`, din indexul PyTorch CPU (`[[tool.uv.index]] pytorch-cpu`, `explicit = true`, deci doar ele vin de acolo); `uv.lock` actualizat. `AGENTS.md › Biblioteci permise › Backend` le permite doar pentru Grad-CAM (decizia omului: „torch CPU în backend”).
- `backend/artifacts/best.pt` (45 MB, `state_dict` v1, epoca 19), copiat din `ml/runs/v1/best.pt` (branch-ul 08). Intră în git, ca `model.onnx`.
- `backend/app/services/explain/gradcam.py`: `Net` (copie minimă a `ml/train.py:Net`, fără import din `ml/`), `load_model()` leneș (`lru_cache`, la primul apel, nu în `lifespan`), `heatmap(model, crop, cls)` → hartă (40, 24) în [0, 1], `overlay_png(crop, cam)` (gri + jet, numpy + pillow), `gradcam_png(id, crop, cls)` cu cache în `backend/cache/gradcam/<id>.png`.
- `GET /api/findings/{id}/gradcam.png` e real: Grad-CAM pe clasa prezisă a finding-ului. Finding-urile sunt încă mock, deci fiecare primește un crop Raptor real al clasei lui din `backend/artifacts/sample_crops/<cls>.jpg` (copii ale fixture-urilor). `crop.png` servește același crop, ca overlay-ul să se potrivească cu crop-ul afișat. Când vine simulatorul (16/17), `mock_data.crop(finding)` se înlocuiește cu crop-ul real al finding-ului.

**Abatere: layer3, nu layer4.** La intrarea 64×96, layer4 e o grilă 2×3, deci are doar 2 coloane pentru 24 px. Nu poate arăta o bandă de 8 px. Am măsurat pe toate cele 250 de crop-uri `diode_substring` din val ce fracție din căldura hărții cade pe cea mai caldă treime de coloane (uniform = 0,33):

| strat, ponderare | fracție medie pe bandă | vârful în bandă |
|---|---|---|
| layer4, Grad-CAM | 0,33 | 1% |
| layer3, Grad-CAM | 0,46 | 60% |
| layer3, grad × act (HiResCAM) | **0,48** | 56% |
| layer2, Grad-CAM | 0,45 | 53% |

Am ales layer3 cu ponderare gradient × activare pe celulă (forma HiResCAM a Grad-CAM, fără medierea gradienților): cea mai mare fracție pe bandă și, pe crop-ul fixture, vârful e în bandă (la Grad-CAM clasic pe layer3 vârful cade pe coloana 9, lângă bandă). Pe crop-ul de demo vârful cade în bandă, dar harta e o pată în banda caldă, nu o bandă întreagă pe toată înălțimea. Modelul se uită în zona corectă, dar nu „desenează” treimea.

**Cum am verificat**
- Logits torch vs ONNX pe cele 8 crop-uri din `tests/fixtures/crops/`: diferență maximă 7,6e-6, aceeași clasă pe toate 8 (test: `test_torch_weights_match_onnx`).
- `cd backend && uv run pytest -q` → `102 passed`. Noi, în `tests/test_gradcam.py`: potrivirea cu ONNX; `test_diode_heat_falls_on_its_third` (pe `diode_substring_829.jpg` banda caldă e la coloanele 12–19, vârful hărții e în ea și fracția pe bandă e > 0,4); overlay-ul e PNG RGB 24×40; endpoint-ul răspunde cu PNG, scrie cache-ul, a doua cerere vine din cache (fișier suprascris → se întoarce conținutul lui), 404 pe id necunoscut.
- `uv run ruff check .` → `All checks passed!`. `cd frontend && npm run build` → verde.
- Server real (`fastapi dev`, prin `.claude/launch.json`, port 8001): `curl http://127.0.0.1:8001/api/findings/F-002/gradcam.png` (F-002 = diode_substring) → `200 image/png 1753 B` în 0,154 s la primul apel (cu încărcarea modelului), 0,005 s la al doilea (din cache); `backend/cache/gradcam/F-002.png` creat. PNG-ul deschis mărit ×8: crop-ul are banda caldă în dreapta-mijloc, iar vârful roșu al hărții e în ea.
- Pornirea rămâne rapidă: torch se importă la import-ul rutei, dar greutățile se încarcă abia la prima cerere de Grad-CAM.

**De știut**
- Cache-ul nu se invalidează: după un model nou, șterge `backend/cache/gradcam/`.
- `ruff format --check` reclamă `services/baseline/rules_classifier.py` (din 07, neatins aici).
