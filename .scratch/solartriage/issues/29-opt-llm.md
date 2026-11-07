# Opțional: LLM pentru rezumatul raportului

Type: task
Status: open
Owner: Alina
Țintă: după H20
Blocked by: 24

## Question

Spec: §2 și decizia Q13. Flag `REPORT_LLM=1`, primește doar JSON-ul cu cifrele, fallback pe template. Dacă apare un număr care nu e în JSON, se folosește template-ul.

Doar FastAPI (backend) și React (frontend), conform `AGENTS.md`.

### Depinde de

- [Code freeze H20: verificare cap-coadă](24-code-freeze.md)
