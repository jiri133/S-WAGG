# Macro-F1 mai mare fără reantrenare: TTA cu flip-uri + bias pe clase

Type: task
Status: claimed
Owner: Tu
Țintă: H18
Blocked by: 08, 09, 15

## Question

Creștem macro-F1 al ResNet18 v1 (test 0,657) fără reantrenare pe Kaggle, cu două tehnici puse direct în graful ONNX, ca backend-ul să rămână neschimbat (intrare `crop` `(batch,1,40,24)` = pixel/255 → `logits` pe 8 clase):

1. **TTA cu flip-uri:** media pe 4 variante ale crop-ului (original, flip orizontal, flip vertical, ambele).
2. **Bias pe clase:** un vector de 8 valori adunat la logits, ales prin coordinate ascent pe o grilă ca să maximizeze macro-F1.

**Toate alegerile se fac doar pe val** (TTA da/nu, media pe logits sau pe probabilități, vectorul de bias). Bias-ul se alege înainte de temperatură; apoi `ml/calibrate.py` refit-uiește T și pragurile pe noul `model.onnx`. **Testul se folosește o singură dată, la final**, prin `evaluate.py`. Varianta nouă se păstrează doar dacă bate v1 pe val; altfel artefactele rămân neschimbate. `best.pt` (Grad-CAM) nu se schimbă.

**Gata când:** tabel cu macro-F1 pe val pentru cele 4 variante (v1, doar TTA, doar bias, ambele), cifrele noi pe test (macro-F1, F1 pe clase, ECE, acoperire la precizia țintă) față de cele vechi (0,657, ECE 0,013, 48,8% la 97,1%), comenzile rulate; teste în `ml/tests/`; backend, ruff, frontend și ml trec; `/api/analyse` răspunde valid.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`. Nu se atinge `backend/app/`.

### Depinde de

- [ResNet18 pe Kaggle → model.onnx](08-resnet-onnx.md)
- [Calibrare (temperature scaling) și praguri pe severitate](09-calibrare.md)
- [evaluate.py, reports/eval.json și figuri](15-evaluate.md)

## Answer

