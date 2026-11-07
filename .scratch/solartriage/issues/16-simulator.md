# Simulator în FastAPI: parc, compunere Raptor, 2 treceri, artefacte

Type: task
Status: claimed
Owner: Alina
Țintă: H6
Blocked by: 05

## Question

Spec: §4. `services/sim/park.py` (2×5×4 mese, ID-uri, string-uri, invertoare), `compose.py` (slot 24×40 din crop-uri Raptor din test, conversie în temperatură aparentă), `artefacts.py` (nor, glare pe o trecere, GPS cu sol, cadru pierdut, RGB, fără panouri, iradianță scăzută). Totul determinist din `seed`.

Până e gata tichetul 6: crop-uri sintetice de rezervă, generate ca în PoC.

**Gata când:** același seed dă aceleași cadre, iar toate injectările se pot activa din `MissionSettings`.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Scheme Pydantic, mock-uri FastAPI și schelet React cu tipuri generate](05-contracte.md)
