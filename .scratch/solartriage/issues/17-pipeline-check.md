# Pipeline: data check, înregistrare GPS, consistency check

Type: task
Status: open
Owner: Alina
Țintă: H8
Blocked by: 16

## Question

Spec: §5 pașii 1, 2 și 4. `services/pipeline/check.py`, `register.py`, `consistency.py`. Până la tichetul 10, clasificarea folosește baseline-ul.

**Gata când:** mesele cu probleme devin `not_inspected` cu motiv, decalajul GPS e corectat, iar glare-ul dintr-o singură trecere ajunge în coadă.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Simulator în FastAPI: parc, compunere Raptor, 2 treceri, artefacte](16-simulator.md)
