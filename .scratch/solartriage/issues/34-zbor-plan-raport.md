# Zborul legat de analiză, plan și raport (finding-uri reale, factorul k, scenariile demo)

Type: task
Status: resolved
Owner: Tu
Țintă: H19
Blocked by: 10, 17, 18, 20, 21, 33

## Question

Cererea omului: „vreau sa se lege simularea dronei de plan si raport”. Zborul și verificarea cadrelor erau reale, dar analiza misiunii citea `services/mock_data.py`, deci lista, planul și raportul nu reflectau zborul.

1. **Analiza reală:** pe fiecare masă inspectată, crop-urile celor 12 module din cadrele zborului (cu offset-ul GPS din `register.py`) → `infer` + `calibrate` → ΔT aparent față de mediana mesei → `consistency` (anomalie într-o singură trecere = reflexie probabilă) → `Finding`. `ok` fără ΔT ≥ 20 K nu devine finding; mesele `not_inspected` nu primesc finding-uri.
2. **Factorul k:** ales din distribuția crop-urilor de antrenare, ca o parte mică (~10–20%) din hot_cell/multi_hot să treacă de 20 K, iar `ok` să rămână sub ~5 K.
3. **Totul din misiune:** finding-uri, review, crop, Grad-CAM, ordine, plan, alerte și raport citesc finding-urile misiunii, salvate în SQLite după `analyse`. Stratul de decizie (33) rămâne neschimbat.
4. **Scenariile demo:** scenariul 1 are cu seed fix un hot cell critical (ΔT ≥ 20 K + alertă), o diodă, un nesigur și o reflexie într-o singură trecere.
5. `mock_data.py` se șterge dacă nu-l mai folosește nimeni.

**Gata când:** `POST /api/missions/demo/normal` → fly → analyse dă finding-uri din model pe cadrele zborului, iar `/findings`, `/work-orders`, `/plan`, `/alerts` și `/report` arată aceleași finding-uri; review „respins” scoate finding-ul din plan și din raport. Test backend cap-coadă pe scenariul 1, e2e actualizate, pytest + ruff + build + Playwright verzi, screenshot-uri în `reports/`.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Modelul în pipeline: /api/analyse, inferență, incertitudine](10-model-analyse.md)
- [Pipeline: data check, înregistrare GPS, consistency check](17-pipeline-check.md)
- [Starea misiunii: SQLite, SSE, endpoint-urile de misiune](18-stare-sse.md)
- [Alerte, webhook cu receptor mock, jurnalul agentului](20-alerte-webhook.md)
- [React: FindingCard, ReviewQueue, AlertBanner, TicketInbox, AgentTimeline, ReportView, EvalView](21-ui-finding.md)
- [Prioritate și urgență din ML (risc așteptat), ordine de lucru automate](33-prioritate-ml.md)

## Answer

Branch `claude/34-zbor-plan-raport-275c21`: merge cu `origin/docs/design-spec` (tichetul 21; conflictul din `map.md` rezolvat păstrând ambele linii), apoi commit-urile `44e57cb` (backend) și `d2b3897` (e2e + tipuri). Fără push.

**Ce e făcut (doar backend; React neschimbat, tipurile regenerate diferă doar prin docstring-uri):**

- `services/pipeline/analyse.py` (nou): pe fiecare masă și trecere validă, `register.slots` (cu `gps_offset_detected`) → `compose.to_gray` → `infer.probs` + `calibrate.predictions` → `consistency.merge`. **ΔT aparent** = vârful modulului față de mediana modulelor mesei în acea trecere. Dintre treceri se păstrează **minimul**, ca o reflexie dintr-o singură trecere să nu declanșeze regula de siguranță. `ok` cu ΔT < 20 K nu devine finding. Reflexia probabilă primește urgența `low` din `consistency`, cu excepția celor critice. `baseline_cls` vine din `rules_classifier`, iar `pattern` din trăsăturile baseline-ului. Un modul `pending` fără imagine în nicio trecere validă devine `not_inspected`.
- `models/finding.py` + `services/findings.py` (noi): finding-urile misiunii stau în SQLite (`finding`: `mission_id`, `id`, `data` JSON, `crop` PNG 24×40, `created_at`), la fel ca alertele. Review-ul le actualizează. Ordinele și planul se reconstruiesc la citire cu `services/decision/` (33), neschimbat. Planul începe pe 2026-11-08, ziua de după zbor.
- `services/missions.py`: `analyse` rulează pipeline-ul într-un thread (`asyncio.to_thread`), ca stream-urile SSE să nu stea. `flown_frames` dă cadrele din memorie sau, după restart, regenerate din seed (folosit și de `/frames`).
- Rutele `findings.py`, `actions.py`, `missions.py` (`/score` compară acum cu adevărul plantat) și `services/report/` citesc misiunea. Raportul lasă afară finding-urile respinse.
- Grad-CAM: cheia din cache e hash(crop + clasă), pentru că id-urile `F-NNN` se repetă între misiuni. Review/crop/Grad-CAM pe un id merg la **cea mai recentă analiză** care îl are, pentru că rutele §9 nu primesc misiunea.
- **Șterse:** `services/mock_data.py` și `artifacts/sample_crops/`. Testele unitare ale stratului de decizie folosesc `tests/fakes.py`, iar fallback-ul mock din `/alerts/{id}/ack` a dispărut (404).
- **Atinse minim la Alina:** `sim/compose.py` (doar `K_PER_LEVEL`). Pipeline-ul (17) și alertele (20) au rămas neatinse; testul helper `_table_predictions` din `test_pipeline.py` apelează acum `analyse.table_looks`.

**Factorul k = 0,20 K/nivel** (era 0,15). L-am măsurat pe crop-urile din **train**: fiecare crop e pus într-o masă cu 11 crop-uri `ok` aleatoare, iar ΔT = vârful lui − mediana mesei, în niveluri de gri.

| k | hot_cell+multi_hot ≥ 20 K | hot_cell | multi_hot | ok ≥ 20 K | ok p50 / p90 |
|---|---|---|---|---|---|
| 0,15 | 0,0% | 0,0% | 0,1% | 0,0% | 3,8 / 9,5 K |
| 0,18 | 3,2% | 2,7% | 3,8% | 0,1% | 4,5 / 11,3 K |
| **0,20** | **10,1%** | 8,4% | 12,5% | 0,4% | **5,0** / 12,6 K |
| 0,22 | 19,9% | 14,7% | 27,1% | 1,0% | 5,5 / 13,9 K |
| 0,25 | 34,4% | 26,4% | 45,6% | 2,9% | 6,2 / 15,8 K |

Am ales 0,20 pentru că e cea mai mică valoare la care ~10% din clasele de risc trec de 20 K, cu `ok` la 5 K mediana. La 0,22 dublăm alertele false pe `ok` (1%). Cu un vârf de un singur pixel, coada `ok` e mare: Raptor are luminozități foarte diferite între crop-uri (tichetul 16). Pe crop-urile de test asta înseamnă ~1–3 alerte pe module `ok` per misiune (plasa de siguranță din ADR 0001 le prinde pe orice clasă). Glare-ul (7–11 K) rămâne vizibil modelului (`test_robustness` trece).

**Scenariile demo:** scenariul 1 (`normal`) are acum **seed 22** (era 7, unde niciun hot cell nu trecea de 20 K; am scanat seed-urile 1–40). Seed-ul 22 dă un hot cell prezis și plantat pe B1-R5-T1-M11 cu ΔT 22,4 K → critical + AL-022, ca în §12 („ΔT 22 K”). Mai are 2 diode sigure (F-033 pe B2-R2-T3-M08), 40 de nesigure și 2 reflexii într-o singură trecere (F-019, F-040). `explain` (seed 23) are o diodă sigură și nesigure; `bad_day` e neschimbat.

**Lista de priorități reală (scenariul 1, `GET /missions/demo-normal/findings`, primele 4):**

- F-027 · B1-R5-T4-M10 · other p = 0,61 · **critical** (ΔT 21,0 K) · scor 0,145 · nesigur, „verifică și repară”
- F-001 · B1-R1-T1-M04 · soiling p = 0,73 · **critical** (ΔT 24,0 K) · scor 0,102 · nesigur
- F-022 · B1-R5-T1-M11 · hot_cell p = 1,00 · **critical** (ΔT 22,4 K) · scor 0,070 · nesigur (hot_cell merge mereu la inginer)
- F-021 · B1-R5-T1-M01 · module_offline p = 0,94 · high · scor 5,516 · trece automat

**Cum am verificat:**

- `cd backend && uv run pytest -q` → **203 passed** (inclusiv `test_file_size.py` și noul `tests/test_scenario1.py`: demo/normal → fly → analyse; probabilități reale, nu 0,55/0,93; F-022 critical + AL-022; diodă, nesigur, reflexie `low`; findings = ordine = plan = raport; respins F-033 → iese din plan și raport). `uv run ruff check .` → All checks passed.
- `cd frontend && npm run build` → ok. `npx playwright test` → **4 passed** (2,9 min). `finding.spec`/`plan.spec` creează scenariul 1 prin `e2e/demo.ts` (rutează „Creează misiunea” spre `/missions/demo/normal`): card F-022 cu 22.4 K, crop + Grad-CAM, ack AL-022, WO-022 în plan și inbox, raportul `demo-normal`; respins F-022 → `task-WO-022` dispare.
- Server pornit (`fastapi run` pe :8134, Vite pe :5134): `POST /missions/demo/normal` → fly → `analyse` 200 în **17,8 s** → 46 de finding-uri, 3 alerte (AL-001, AL-022, AL-027), plan pe 5 zile cu 38 de sarcini și 8 neplanificate, prima sarcină WO-027 „alertă critică de siguranță”. `/score`: 13 TP, 33 FP, 1 ratat, 0 neinspectate. Review „rejected” pe F-033 → WO-033 dispare din `/plan`, F-033 din `/report`; „confirmed” îl readuce.
- Screenshot-uri cu Playwright MCP pe scenariul 1: `reports/34-harta-dupa-analiza.png` (harta după analiză, 46 finding-uri · 40 nesigure · 3 critical) și `reports/34-raport.png` (raportul). `reports/19-harta-dupa-analiza.png` e regenerat de `map.spec` pe analiza reală.

**Ce rămâne deschis (nu blochează tichetul):**

- **Multe fals pozitive:** 33 din 46 de finding-uri sunt pe module `ok`, aproape toate nesigure. E rata reală a modelului v1.1 pe crop-urile `ok` din test (~7% din ~466), adică ~33 de ordine „verifică și repară” per misiune. Spec-ul §12 spunea „14 finding-uri”. N-am ascuns nimic: e o decizie de produs (de ex. un prag de încredere pentru ordinele automate ale nesigurelor).
- **Analiza durează ~18 s:** ~4 s modelul (TTA, 80 de cadre), restul ~49 de livrări webhook secvențiale (tichetul 20). Se poate grăbi cu livrări paralele.
- Datele Raptor lipseau din worktree; am pus un junction `data/` → `S-WAGG/data` (ignorat de git).

### Corecție ΔT (după review cu omul)

Alertele critice false nu veneau dintr-un vârf de un pixel: o medie pe cei mai calzi 4/16 pixeli le păstra (un modul `ok` la 21 K, o umbră la 24 K pe scenariul 1) și pierdea hot cell-ul. Veneau din moduli calzi peste tot față de masă (crop-uri Raptor mai luminoase). Acum ΔT = vârful modulului − mediana **aceluiași modul** (`analyse.delta_t`, GLOSSARY actualizat).

- Pe 20 de seed-uri (`MissionSettings(seed=1..20)`, pipeline complet): alerte pe defecte reale 13 → 8, alerte pe ok/soiling/umbră **57 → 11**. Se pierd alertele pe multi_hot (rămân finding-uri cu urgența din model).
- Scenariul 1: alerte doar pe hot cell-ul plantat (F-022, ΔT 31,0 K) și pe un `other` plantat (22,4 K); cele două false au dispărut.
- Teste: `test_delta_t_counts_a_hot_spot_not_a_module_warm_all_over`; testele de alertă din `test_missions.py` rulează pe seed 22 (seed 5 avea doar alerte false). `uv run pytest -q` → verde, Playwright 7/7.
