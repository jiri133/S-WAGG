# React: ParkMap, DronePlayer, FrameStrip, PhasePanel, useMissionStream

Type: task
Status: claimed
Owner: Tu
Țintă: H8
Blocked by: 05

## Question

Spec: §10. Canvas portat din `draw()` (simulatorul vechi e în PoC-ul `pv-inspection-poc/simulator/index.html`), interpolarea dronei cu `requestAnimationFrame`, banda de cadre, controalele pe faze, store-ul Zustand alimentat doar din `useMissionStream`. Merge întâi pe mock-uri, apoi pe tichetul 18.

**Gata când (H8):** zbor → cadre → data check → hartă colorată, cap-coadă prin FastAPI.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Scheme Pydantic, mock-uri FastAPI și schelet React cu tipuri generate](05-contracte.md)
