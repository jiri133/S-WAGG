# React: ParkMap, DronePlayer, FrameStrip, PhasePanel, useMissionStream

Type: task
Status: resolved
Owner: Tu
Țintă: H8
Blocked by: 05

## Question

Spec: §10. Canvas portat din `draw()` (simulatorul vechi e în PoC-ul `pv-inspection-poc/simulator/index.html`), interpolarea dronei cu `requestAnimationFrame`, banda de cadre, controalele pe faze, store-ul Zustand alimentat doar din `useMissionStream`. Merge întâi pe mock-uri, apoi pe tichetul 18.

**Gata când (H8):** zbor → cadre → data check → hartă colorată, cap-coadă prin FastAPI.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Scheme Pydantic, mock-uri FastAPI și schelet React cu tipuri generate](05-contracte.md)

## Answer

Ce e gata (doar `frontend/`, `backend/` neatins):

- `store/missionStore.ts` extins (nu rescris): `frames`, `findings`, `drone` (ultimul `waypoint`), `irradiance` (din `cloud`), `flightDone`, plus `update(patch)`.
- `hooks/useMissionStream.ts`: singurul loc care scrie store-ul. `EventSource` pe `/api/missions/{id}/stream` cât timp `mission.phase === 'flying'`; aplică `waypoint`, `frame_captured`, `frame_checked`, `cloud`, `flight_done`, `findings_ready`. La `flight_done` și când SSE cade: un singur `resync` (`GET /missions/{id}` + `/frames` + `/findings` după analiză). Tot aici `missionActions` (create, fly, refly, analyse), apelate din `PhasePanel`.
- `components/DronePlayer.ts`: `useDronePlayer(target, speed)`, interpolare cu `requestAnimationFrame` de la punctul de decolare spre ultimul waypoint, fără desen.
- `components/ParkMap.tsx`: `<canvas>` portat din `draw()` al simulatorului vechi. Straturi: status (în așteptare, ok, finding pe urgență critical/high/medium/low, nesigur, reflexie probabilă, neinspectat hașurat), cadre respinse (contur roșu punctat pe masă), adevăr (✕, bifă când `mission.truth` există), dronă + amprenta camerei pe masa curentă. Legenda are numărul de module pe fiecare culoare.
- `components/FrameStrip.tsx`: banda de cadre (thumb-uri din `/frames/{id}/thumb.png`), cele mai noi primele, chenar roșu pe cadrele respinse.
- `components/PhasePanel.tsx`: pașii Setări (seed, defecte, șanse nor/GPS/glare/pierdut, viteză, `inject`) → Zbor → Verificare (cadre primite/respinse cu motiv, module neinspectate, re-zbor) → Analiză (finding-uri, nesigure, critical) → Review (link spre `/plan`).
- `pages/Main.tsx`: grila veche înlocuită de hartă + bandă în stânga, `PhasePanel` în dreapta. Stratul de status apare de la pasul Verificare.
- `e2e/map.spec.ts` (2 teste) și `reports/19-harta-dupa-analiza.png`.

Cum am verificat:

- `cd frontend && npm run build`: verde. `npx oxlint src e2e`: fără avertismente.
- `cd frontend && npx playwright test`: 3 passed (`plan.spec.ts` + cele 2 noi: fluxul cap-coadă pe mock-uri și drona care ajunge la waypoint, cu un stream stubuit, verificată pe pixelul canvas-ului).
- `cd backend && uv run pytest -q`: 140 passed, 1 skipped (inclusiv `test_file_size.py`; cel mai mare fișier nou e `PhasePanel.tsx`, 7,9 KB).
- Manual cu MCP `playwright` pe FastAPI :8019 + Vite :5190: Creează misiunea → Pornește zborul → „Zbor terminat · 78 cadre”, „☁ Nor: iradianță 450 W/m²”, banda plină → Verificare: „78 cadre primite, 0 respinse · 12 module neinspectate”, masa B2-R4-T3 hașurată → Analizează: „5 finding-uri · 1 nesigure · 1 critical”, harta colorată (463 ok, 1 critical, 2 high, 1 low, 1 nesigur, 12 neinspectate). Fără erori în consolă. Drona: cu stream stubuit (waypoint B2-R3-T2) se vede cum zboară de la decolare și se oprește pe masă, cu amprenta camerei.

## Comments

Pentru tichetul 18 (contracte, nu am inventat câmpuri):

- Pe mock-uri, `mission()` întoarce mereu `phase: analysed` cu statusul final, iar `/stream` trimite un singur waypoint și un singur cadru la 0,1 s. De aceea pe mock-uri harta e colorată deja la Verificare, iar drona abia se vede. Cu SSE-ul real (statusuri `pending` → `not_inspected` → final și waypoint-uri pe toată ruta), React nu trebuie schimbat.
- Payload-urile `StreamEvent.data` nu au tipuri generate. Citesc: `waypoint` = `{x_m, y_m, table}` (`Pick<Module, ...>`), `frame_captured` = `FrameMeta`, `frame_checked` = `{frame_id, check_ok, problems}`, `cloud` = `{irradiance_wm2}`. Dacă 18 schimbă forma, se schimbă doar `apply()` din `useMissionStream.ts`.
- Pentru `waypoint`, drona e desenată exact la `(x_m, y_m)`. Mock-ul trimite colțul primului modul; pentru animație e mai frumos centrul mesei.
- „Reflexie probabilă” = finding cu `evidence.seen_in_both_passes === false` (doar afișare, câmpul vine din FastAPI).
- `PhasePanel` repetă valorile implicite din `MissionSettings` (tipurile generate nu au default-uri). Dacă se schimbă în FastAPI, trebuie schimbate și acolo.
- Stratul „outcome” (găsit/ratat/alarmă falsă față de adevăr) din §10 nu e făcut: are nevoie de comparația din `/score` (ecranul de adevăr), nu de logică în React.
- `alert_raised` și `agent_event` sunt ignorate aici; le preiau `AlertBanner` și `AgentTimeline`.
